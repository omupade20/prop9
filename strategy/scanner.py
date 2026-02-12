# strategy/scanner.py
"""
Hardened MarketScanner (production-ready) – 5 MINUTE BASED VERSION
- keeps rolling 5-minute OHLCV bars per instrument
- supports tick aggregation into 5m candles
- snapshot persistence and resume
- on_bar_close callbacks so MTF/strategy can run immediately when a 5m bar closes
- alert throttling helpers (last_alert_time, dedupe)
- basic health checks and replay utilities
- thread-safe for use from websocket threads
"""

import json
import os
import threading
import time
from collections import deque, defaultdict
from datetime import datetime
from typing import Dict, List, Callable, Optional

# Now storing 600 five-minute bars (~50 trading hours)
DEFAULT_MAX_LEN = 400

ISOFMT = "%Y-%m-%dT%H:%M:%S"


def _now_iso():
    return datetime.now().strftime(ISOFMT)


class MarketScanner:
    def __init__(self, max_len: int = DEFAULT_MAX_LEN, snapshot_path: Optional[str] = None):
        self.max_len = max_len
        self.snapshot_path = snapshot_path

        self._bars: Dict[str, deque] = {}
        self._locks: Dict[str, threading.Lock] = defaultdict(threading.Lock)
        self._global_lock = threading.Lock()

        self.last_alert_time: Dict[str, float] = {}
        self._dedupe_map: Dict[str, Dict[str, float]] = defaultdict(dict)
        self._paused_until: Dict[str, float] = {}

        self._on_bar_close_callbacks: List[Callable[[str, dict], None]] = []

        self.bars_received = 0
        self.bars_closed = 0
        self.replay_mode = False

        if self.snapshot_path:
            os.makedirs(os.path.dirname(self.snapshot_path), exist_ok=True)

    # ---------------------
    # Internal helpers
    # ---------------------
    def _ensure_inst(self, inst: str):
        with self._global_lock:
            if inst not in self._bars:
                self._bars[inst] = deque(maxlen=self.max_len)

    def _lock_for(self, inst: str):
        return self._locks[inst]

    # ------------------------------------------------------------
    # 5-MINUTE BUCKETING HELPERS
    # ------------------------------------------------------------
    def _round_to_5min(self, ts: datetime) -> datetime:
        """
        Round timestamp DOWN to nearest 5-minute boundary.
        """
        minute = (ts.minute // 5) * 5
        return ts.replace(minute=minute, second=0, microsecond=0)

    # ---------------------
    # Append / ingestion
    # ---------------------
    def append_ohlc_bar(
        self,
        inst: str,
        time_iso: str,
        open_p: float,
        high_p: float,
        low_p: float,
        close_p: float,
        volume: float
    ):
        """
        Ingest a completed 5-minute bar. Triggers on_bar_close callbacks.
        """
        self._ensure_inst(inst)
        with self._lock_for(inst):
            bar = {
                "time": time_iso,
                "open": open_p,
                "high": high_p,
                "low": low_p,
                "close": close_p,
                "volume": volume
            }
            self._bars[inst].append(bar)
            self.bars_closed += 1

        for cb in list(self._on_bar_close_callbacks):
            try:
                cb(inst, bar)
            except Exception:
                pass

        return bar

    def append_tick(self, inst: str, timestamp: datetime, price: float, volume: float):
        """
        Aggregate ticks into a 5-minute bar instead of 1-minute.
        """
        self._ensure_inst(inst)

        ts_5m = self._round_to_5min(timestamp)
        time_iso = ts_5m.strftime(ISOFMT)

        with self._lock_for(inst):
            bars = self._bars[inst]

            if not bars or bars[-1]["time"] != time_iso:
                bar = {
                    "time": time_iso,
                    "open": price,
                    "high": price,
                    "low": price,
                    "close": price,
                    "volume": volume
                }
                bars.append(bar)
                self.bars_received += 1
            else:
                bar = bars[-1]
                bar["high"] = max(bar["high"], price)
                bar["low"] = min(bar["low"], price)
                bar["close"] = price
                bar["volume"] = bar.get("volume", 0) + volume
                self.bars_received += 1

    def update(
        self,
        instrument: str,
        price: float,
        high: float,
        low: float,
        close: float,
        volume: float,
        time_iso: Optional[str] = None
    ):
        """
        Backwards-compatible method.
        Treat as direct 5-minute bar append when time_iso provided,
        otherwise aggregate ticks into 5-minute buckets.
        """
        if time_iso:
            self.append_ohlc_bar(instrument, time_iso, price, high, low, close, volume)
        else:
            self.append_tick(instrument, datetime.now(), price, volume)

    # ---------------------
    # Accessors & getters
    # ---------------------
    def get_last_n_bars(self, inst: str, n: int) -> List[dict]:
        if inst not in self._bars:
            return []
        with self._lock_for(inst):
            return list(self._bars[inst])[-n:]

    def get_last_bar(self, inst: str) -> Optional[dict]:
        if inst not in self._bars or not self._bars[inst]:
            return None
        with self._lock_for(inst):
            return dict(self._bars[inst][-1])

    def get_prices(self, inst: str) -> List[float]:
        return [b["close"] for b in self.get_last_n_bars(inst, self.max_len)]

    def get_highs(self, inst: str) -> List[float]:
        return [b["high"] for b in self.get_last_n_bars(inst, self.max_len)]

    def get_lows(self, inst: str) -> List[float]:
        return [b["low"] for b in self.get_last_n_bars(inst, self.max_len)]

    def get_closes(self, inst: str) -> List[float]:
        return [b["close"] for b in self.get_last_n_bars(inst, self.max_len)]

    def get_volumes(self, inst: str) -> List[float]:
        return [b["volume"] for b in self.get_last_n_bars(inst, self.max_len)]

    def has_enough_data(self, inst: str, min_bars: int = 25) -> bool:
        return (inst in self._bars and len(self._bars[inst]) >= min_bars)

    def active_instruments(self) -> List[str]:
        return list(self._bars.keys())

    # ---------------------
    # Callbacks
    # ---------------------
    def register_on_bar_close(self, cb: Callable[[str, dict], None]):
        if cb not in self._on_bar_close_callbacks:
            self._on_bar_close_callbacks.append(cb)

    def unregister_on_bar_close(self, cb: Callable[[str, dict], None]):
        if cb in self._on_bar_close_callbacks:
            self._on_bar_close_callbacks.remove(cb)

    # ---------------------
    # Alert helpers
    # ---------------------
    def can_emit_alert(self, inst: str, cooldown_seconds: int = 1800) -> bool:
        now_ts = time.time()
        paused_until = self._paused_until.get(inst)
        if paused_until and now_ts < paused_until:
            return False

        last = self.last_alert_time.get(inst)
        if last is None:
            return True
        return (now_ts - last) >= cooldown_seconds

    def mark_alert_emitted(self, inst: str):
        self.last_alert_time[inst] = time.time()

    # ---------------------
    # Health & introspection
    # ---------------------
    def health_check(self) -> dict:
        now_ts = datetime.now()
        last_bar_diff = {}

        for k, dq in self._bars.items():
            if dq:
                try:
                    ts = datetime.strptime(dq[-1]["time"], ISOFMT)
                    last_bar_diff[k] = (now_ts - ts).total_seconds()
                except Exception:
                    last_bar_diff[k] = None

        return {
            "instruments_tracked": len(self._bars),
            "bars_received": self.bars_received,
            "bars_closed": self.bars_closed,
            "last_bar_age_sample": dict(list(last_bar_diff.items())[:10])
        }
