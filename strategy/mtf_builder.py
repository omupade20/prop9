# strategy/mtf_builder.py
"""
MTFBuilder — build higher-timeframe candles from 5-minute bars.

Design goals:
- No extra API calls (aggregate 5m bars you already have).
- Low latency: aggregates the last N 5-minute bars immediately.
- Memory-safe: uses deque with configurable maxlen.
- Simple, deterministic API: update(...) + get_latest_tf(...) / get_tf_history(...).

NEW STRUCTURE:
- Base bars = 5-minute
- Builds:
    - 15m (3 x 5m)
    - 30m (6 x 5m)
"""

from collections import defaultdict, deque
from datetime import datetime
from typing import Deque, Dict, List, Optional, Union

ISOFMT = "%Y-%m-%dT%H:%M:%S"


def _to_5min_iso(ts: Union[str, datetime]) -> str:
    """
    Normalize timestamp to 5-minute boundary.
    """
    if isinstance(ts, str):
        try:
            dt = datetime.strptime(ts, ISOFMT)
        except Exception:
            dt = datetime.fromisoformat(ts)
    else:
        dt = ts

    # Round DOWN to nearest 5 minutes
    minute = (dt.minute // 5) * 5
    dt = dt.replace(minute=minute, second=0, microsecond=0)

    return dt.strftime(ISOFMT)


class MTFBuilder:
    """
    Builds higher timeframe candles (N-minute) from 5-minute bars.

    Usage:
      - Call update(inst_key, timestamp, o,h,l,c,v) for each 5-minute bar
      - Use get_latest_tf(inst_key, minutes=15) to get aggregated 15m candle
      - Use get_tf_history(inst_key, minutes=15, lookback=3) to get last 3 aggregated 15m candles
    """

    def __init__(self, max_5m_bars: int = 1200):
        # store recent 5-minute bars per instrument
        self.max_5m_bars = max_5m_bars
        self.buffers: Dict[str, Deque[dict]] = defaultdict(
            lambda: deque(maxlen=self.max_5m_bars)
        )

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
        Add a 5-minute bar. timestamp may be ISO string or datetime.
        """
        t_iso = _to_5min_iso(timestamp)

        bar = {
            "time": t_iso,
            "open": o,
            "high": h,
            "low": l,
            "close": c,
            "volume": v
        }

        self.buffers[inst_key].append(bar)

    def _aggregate(self, bars: List[dict]) -> dict:
        """
        Aggregate a list of 5-minute bar dicts (oldest->newest) into one higher TF candle.
        """
        return {
            "time_start": bars[0]["time"],
            "time_end": bars[-1]["time"],
            "open": bars[0]["open"],
            "high": max(b["high"] for b in bars),
            "low": min(b["low"] for b in bars),
            "close": bars[-1]["close"],
            "volume": sum(b.get("volume", 0) for b in bars)
        }

    def get_latest_tf(self, inst_key: str, minutes: int = 15) -> Optional[dict]:
        """
        Return aggregated candle of the last N 5-minute bars.

        Example:
        - minutes=15  -> needs 3 bars (3 * 5m)
        - minutes=30  -> needs 6 bars (6 * 5m)
        """

        bars = self.buffers.get(inst_key)

        if not bars:
            return None

        # Convert minutes to required 5m bar count
        required_bars = minutes // 5

        if len(bars) < required_bars:
            return None

        chunk = list(bars)[-required_bars:]
        return self._aggregate(chunk)

    def get_tf_history(
        self,
        inst_key: str,
        minutes: int = 15,
        lookback: int = 3
    ) -> List[dict]:
        """
        Return list of aggregated candles for given TF.

        Each aggregated candle uses contiguous blocks of required 5m bars.
        """

        out: List[dict] = []

        bars = self.buffers.get(inst_key)
        if not bars:
            return out

        bar_list = list(bars)
        total = len(bar_list)

        required_bars = minutes // 5

        for i in range(lookback, 0, -1):
            end = total - (i - 1) * required_bars
            start = end - required_bars

            if start < 0:
                continue

            chunk = bar_list[start:end]
            out.append(self._aggregate(chunk))

        return out

    # --------------------------------------------------
    # Convenience helpers for NEW system
    # --------------------------------------------------

    def get_latest_15m(self, inst_key: str) -> Optional[dict]:
        return self.get_latest_tf(inst_key, minutes=15)

    def get_latest_30m(self, inst_key: str) -> Optional[dict]:
        return self.get_latest_tf(inst_key, minutes=30)
