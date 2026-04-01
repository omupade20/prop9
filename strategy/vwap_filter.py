# strategy/vwap_filter.py

from collections import deque
from dataclasses import dataclass
from typing import Optional


# =========================
# VWAP Context Output
# =========================

@dataclass
class VWAPContext:
    vwap: Optional[float]
    distance_pct: float        # price minus VWAP (%)
    acceptance: str            # ABOVE | BELOW | NEAR
    score: float               # -1 to +1
    comment: str


# =========================
# VWAP Calculator
# =========================

class VWAPCalculator:
    """
    Simplified VWAP (LOCATION-BASED)

    Purpose:
    - Identify market bias (above/below VWAP)
    - Avoid overfitting (no slope, no noise)
    """

    def __init__(self, window: Optional[int] = None):
        self.window = window

        self.price_volume_sum = 0.0
        self.volume_sum = 0.0

        if window:
            self.price_volume_deque = deque(maxlen=window)
            self.volume_deque = deque(maxlen=window)

        self.reset()

    def reset(self):
        self.price_volume_sum = 0.0
        self.volume_sum = 0.0

        if hasattr(self, "price_volume_deque"):
            self.price_volume_deque.clear()
            self.volume_deque.clear()

    def update(self, price: float, volume: float) -> Optional[float]:
        if price is None or volume is None or volume <= 0:
            return None

        if self.window:
            self.price_volume_deque.append(price * volume)
            self.volume_deque.append(volume)
            self.price_volume_sum = sum(self.price_volume_deque)
            self.volume_sum = sum(self.volume_deque)
        else:
            self.price_volume_sum += price * volume
            self.volume_sum += volume

        if self.volume_sum <= 0:
            return None

        return self.price_volume_sum / self.volume_sum

    def get_vwap(self) -> Optional[float]:
        if self.volume_sum <= 0:
            return None
        return self.price_volume_sum / self.volume_sum

    # =========================
    # VWAP CONTEXT (SIMPLIFIED)
    # =========================

    def get_context(self, price: float) -> VWAPContext:
        vwap = self.get_vwap()

        if vwap is None or price is None:
            return VWAPContext(
                vwap=None,
                distance_pct=0.0,
                acceptance="NEAR",
                score=0.0,
                comment="VWAP unavailable"
            )

        distance_pct = (price - vwap) / vwap * 100.0

        # ----------------------
        # Acceptance Zones
        # ----------------------
        if distance_pct > 0.2:
            acceptance = "ABOVE"
            score = 1.0
            comment = "above_vwap"
        elif distance_pct < -0.2:
            acceptance = "BELOW"
            score = -1.0
            comment = "below_vwap"
        else:
            acceptance = "NEAR"
            score = 0.0
            comment = "near_vwap"

        return VWAPContext(
            vwap=round(vwap, 6),
            distance_pct=round(distance_pct, 3),
            acceptance=acceptance,
            score=score,
            comment=comment
        )
