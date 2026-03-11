# strategy/mtf_builder.py

"""
MTFBuilder — builds higher timeframe candles from 1-minute bars.

System architecture rule:
1m data  → scanner
5m data  → MTFBuilder

This module is the SINGLE source of 5-minute candles for the system.

Design goals
------------
• deterministic aggregation
• no duplicate minute bars
• fast deque storage
• minimal memory usage
"""

from collections import defaultdict, deque
from datetime import datetime
from typing import Deque, Dict, List, Optional, Union


ISOFMT = "%Y-%m-%dT%H:%M:%S"


def _normalize_minute(ts: Union[str, datetime]) -> str:
    """
    Normalize timestamps to minute boundary.
    """
    if isinstance(ts, str):
        try:
            dt = datetime.strptime(ts, ISOFMT)
        except Exception:
            dt = datetime.fromisoformat(ts)
    else:
        dt = ts

    dt = dt.replace(second=0, microsecond=0)
    return dt.strftime(ISOFMT)


class MTFBuilder:
    """
    Builds 5-minute candles from 1-minute bars.

    Only responsibility:
    -------------------
    Maintain rolling 1m bars and aggregate them into 5m candles.

    Other modules MUST fetch 5m candles from here.
    """

    def __init__(self, max_1m_bars: int = 2000):
        self.max_1m_bars = max_1m_bars

        # instrument → deque of 1m bars
        self.buffers: Dict[str, Deque[dict]] = defaultdict(
            lambda: deque(maxlen=self.max_1m_bars)
        )

    # ---------------------------------------------------
    # 1️⃣ Update with 1-minute bar
    # ---------------------------------------------------

    def update(
        self,
        inst_key: str,
        timestamp: Union[str, datetime],
        o: float,
        h: float,
        l: float,
        c: float,
        v: float
    ):
        """
        Add a 1-minute bar.

        Prevents duplicate bars if websocket sends repeated updates.
        """

        t_iso = _normalize_minute(timestamp)

        bars = self.buffers[inst_key]

        # prevent duplicate minute insert
        if bars and bars[-1]["time"] == t_iso:
            return

        bars.append({
            "time": t_iso,
            "open": o,
            "high": h,
            "low": l,
            "close": c,
            "volume": v
        })

    # ---------------------------------------------------
    # 2️⃣ Aggregation helper
    # ---------------------------------------------------

    def _aggregate_5m(self, bars: List[dict]) -> dict:
        """
        Aggregate 5 × 1m bars into a 5m candle.
        """

        return {
            "time_start": bars[0]["time"],
            "time_end": bars[-1]["time"],
            "open": bars[0]["open"],
            "high": max(b["high"] for b in bars),
            "low": min(b["low"] for b in bars),
            "close": bars[-1]["close"],
            "volume": sum(b["volume"] for b in bars),
        }

    # ---------------------------------------------------
    # 3️⃣ Latest 5m candle
    # ---------------------------------------------------

    def get_latest_5m(self, inst_key: str) -> Optional[dict]:

        bars = self.buffers.get(inst_key)

        if not bars or len(bars) < 5:
            return None

        last_five = list(bars)[-5:]

        return self._aggregate_5m(last_five)

    # ---------------------------------------------------
    # 4️⃣ 5m candle history
    # ---------------------------------------------------

    def get_5m_history(self, inst_key: str, lookback: int = 100) -> List[dict]:
        """
        Return last N 5-minute candles.
        """

        bars = self.buffers.get(inst_key)

        if not bars or len(bars) < 5:
            return []

        bar_list = list(bars)

        out: List[dict] = []

        total = len(bar_list)

        # number of possible 5m candles
        possible = total // 5

        candles_to_build = min(possible, lookback)

        for i in range(candles_to_build):

            end = total - (i * 5)
            start = end - 5

            if start < 0:
                break

            chunk = bar_list[start:end]

            out.append(self._aggregate_5m(chunk))

        return list(reversed(out))
