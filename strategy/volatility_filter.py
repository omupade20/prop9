# strategy/volatility_context.py

"""
Volatility Context Analyzer

Purpose
-------
Evaluate whether price movement is:

• CONTRACTING  → avoid trades
• BUILDING     → potential setup
• EXPANDING    → good continuation
• EXHAUSTION   → avoid chasing

This module operates on **1-minute data**.
"""

from dataclasses import dataclass
from typing import List, Optional


# =========================================================
# True Range
# =========================================================

def compute_true_range(
    highs: List[float],
    lows: List[float],
    closes: List[float]
) -> List[float]:

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


# =========================================================
# ATR
# =========================================================

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


# =========================================================
# Volatility Context Output
# =========================================================

@dataclass
class VolatilityContext:

    state: str
    score: float
    atr: float
    move_pct_atr: float
    comment: str


# =========================================================
# Volatility Analysis
# =========================================================

def analyze_volatility(
    current_move: float,
    atr_value: Optional[float],
    atr_history: Optional[List[float]] = None
) -> VolatilityContext:

    """
    Evaluate volatility quality relative to ATR.
    """

    if atr_value is None or atr_value <= 0:

        return VolatilityContext(
            state="UNKNOWN",
            score=0.0,
            atr=0.0,
            move_pct_atr=0.0,
            comment="ATR unavailable"
        )

    move_pct_atr = abs(current_move) / atr_value

    # ----------------------------------------------------
    # CONTRACTING (noise)
    # ----------------------------------------------------

    if move_pct_atr < 0.6:

        return VolatilityContext(
            state="CONTRACTING",
            score=-0.6,
            atr=round(atr_value, 6),
            move_pct_atr=round(move_pct_atr, 2),
            comment="low volatility"
        )

    # ----------------------------------------------------
    # BUILDING (potential setup)
    # ----------------------------------------------------

    if move_pct_atr < 1.2:

        return VolatilityContext(
            state="BUILDING",
            score=0.3,
            atr=round(atr_value, 6),
            move_pct_atr=round(move_pct_atr, 2),
            comment="volatility building"
        )

    # ----------------------------------------------------
    # EXPANDING (ideal continuation)
    # ----------------------------------------------------

    if move_pct_atr < 1.8:

        score = 1.1
        comment = "healthy expansion"

        if atr_history and len(atr_history) >= 5:

            if atr_history[-1] > atr_history[-3]:
                score += 0.2
                comment += " + ATR rising"

        return VolatilityContext(
            state="EXPANDING",
            score=min(score, 1.5),
            atr=round(atr_value, 6),
            move_pct_atr=round(move_pct_atr, 2),
            comment=comment
        )

    # ----------------------------------------------------
    # EXHAUSTION (avoid chasing)
    # ----------------------------------------------------

    return VolatilityContext(
        state="EXHAUSTION",
        score=-1.0,
        atr=round(atr_value, 6),
        move_pct_atr=round(move_pct_atr, 2),
        comment="volatility spike"
    )


# =========================================================
# Legacy breakout confirmation
# =========================================================

def volatility_breakout_confirmed(
    current_move: float,
    atr_value: Optional[float],
    atr_multiplier: float = 1.1
) -> bool:

    if atr_value is None:
        return False

    return abs(current_move) >= atr_value * atr_multiplier
