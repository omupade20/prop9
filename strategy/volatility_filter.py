# strategy/volatility_context.py

from dataclasses import dataclass
from typing import List, Optional


# =========================
# ATR CALCULATIONS
# =========================

def compute_true_range(highs: List[float], lows: List[float], closes: List[float]) -> List[float]:
    if len(highs) < 2:
        return []
    tr = []
    for i in range(1, len(highs)):
        tr.append(
            max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1])
            )
        )
    return tr


def compute_atr(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    period: int = 14
) -> Optional[float]:
    tr = compute_true_range(highs, lows, closes)
    if len(tr) < period:
        return None
    return sum(tr[-period:]) / period


# =========================
# OUTPUT
# =========================

@dataclass
class VolatilityContext:
    state: str          # LOW | NORMAL | EXPANDING | HIGH
    score: float        # -1 to +1
    atr: float
    move_pct_atr: float
    comment: str


# =========================
# SIMPLIFIED VOLATILITY LOGIC
# =========================

def analyze_volatility(
    current_move: float,
    atr_value: Optional[float],
) -> VolatilityContext:
    """
    SIMPLIFIED VOLATILITY CONTEXT

    Purpose:
    - confirm movement quality
    - avoid over-blocking trades
    """

    if atr_value is None or atr_value <= 0:
        return VolatilityContext("UNKNOWN", 0.0, 0.0, 0.0, "no_atr")

    move_pct_atr = abs(current_move) / atr_value

    # ----------------------
    # LOW VOLATILITY
    # ----------------------
    if move_pct_atr < 0.5:
        return VolatilityContext(
            state="LOW",
            score=-0.3,   # very small penalty only
            atr=round(atr_value, 6),
            move_pct_atr=round(move_pct_atr, 2),
            comment="low_volatility"
        )

    # ----------------------
    # NORMAL (ACCEPTABLE)
    # ----------------------
    if move_pct_atr < 1.2:
        return VolatilityContext(
            state="NORMAL",
            score=0.3,
            atr=round(atr_value, 6),
            move_pct_atr=round(move_pct_atr, 2),
            comment="normal_volatility"
        )

    # ----------------------
    # EXPANSION (BEST ZONE)
    # ----------------------
    if move_pct_atr < 1.8:
        return VolatilityContext(
            state="EXPANDING",
            score=0.8,
            atr=round(atr_value, 6),
            move_pct_atr=round(move_pct_atr, 2),
            comment="expansion"
        )

    # ----------------------
    # HIGH / SPIKE
    # ----------------------
    return VolatilityContext(
        state="HIGH",
        score=-0.2,   # small caution only (not blocking)
        atr=round(atr_value, 6),
        move_pct_atr=round(move_pct_atr, 2),
        comment="high_volatility"
    )


# =========================
# LEGACY SUPPORT
# =========================

def volatility_breakout_confirmed(
    current_move: float,
    atr_value: Optional[float],
    atr_multiplier: float = 1.1
) -> bool:
    if atr_value is None:
        return False
    return abs(current_move) >= atr_value * atr_multiplier
