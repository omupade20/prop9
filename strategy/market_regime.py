# strategy/market_regime.py

"""
Market Regime Detector

Purpose
-------
Detect whether the market is:
• TRENDING
• EARLY_TREND
• COMPRESSION
• WEAK

IMPORTANT
---------
This module must use **5-minute candles** from MTFBuilder.
"""

from typing import List, Optional
from dataclasses import dataclass


# ==========================================================
# True Range
# ==========================================================

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


# ==========================================================
# ATR
# ==========================================================

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


# ==========================================================
# ADX (simplified directional strength)
# ==========================================================

def compute_adx(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    period: int = 14
) -> Optional[float]:

    if len(highs) < period + 1:
        return None

    plus_dm = []
    minus_dm = []

    for i in range(1, len(highs)):

        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]

        plus_dm.append(up if up > down and up > 0 else 0)
        minus_dm.append(down if down > up and down > 0 else 0)

    atr = compute_atr(highs, lows, closes, period)

    if atr is None or atr == 0:
        return None

    plus_di = (sum(plus_dm[-period:]) / atr) * 100
    minus_di = (sum(minus_dm[-period:]) / atr) * 100

    if plus_di + minus_di == 0:
        return 0.0

    dx = abs(plus_di - minus_di) / (plus_di + minus_di) * 100

    return dx


# ==========================================================
# Output structure
# ==========================================================

@dataclass
class MarketRegime:

    state: str
    mode: str
    strength: float
    volatility: float
    comment: str


# ==========================================================
# Market Regime Detection (5-minute candles)
# ==========================================================

def detect_market_regime(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    min_bars: int = 30
) -> MarketRegime:

    """
    Detect structural market regime using 5-minute candles.
    """

    # ------------------------------------------------------
    # Safety
    # ------------------------------------------------------

    if len(highs) < min_bars:

        return MarketRegime(
            state="WEAK",
            mode="RANGE_DAY",
            strength=0.5,
            volatility=0.0,
            comment="Insufficient 5m data"
        )

    # ------------------------------------------------------
    # Indicators
    # ------------------------------------------------------

    adx = compute_adx(highs, lows, closes)
    atr = compute_atr(highs, lows, closes)

    if adx is None or atr is None:

        return MarketRegime(
            state="WEAK",
            mode="RANGE_DAY",
            strength=0.5,
            volatility=0.0,
            comment="Indicators unavailable"
        )

    # ------------------------------------------------------
    # Volatility normalization
    # ------------------------------------------------------

    avg_price = sum(closes[-10:]) / 10
    volatility = atr / avg_price if avg_price > 0 else 0

    # ------------------------------------------------------
    # Range expansion
    # ------------------------------------------------------

    recent_range = max(highs[-10:]) - min(lows[-10:])

    prev_range = max(highs[-20:-10]) - min(lows[-20:-10])

    if prev_range <= 0:
        prev_range = recent_range

    # ------------------------------------------------------
    # Regime Logic
    # ------------------------------------------------------

    # EARLY TREND

    if adx >= 18 and recent_range > prev_range * 1.25:

        strength = min(4 + (adx - 18) * 0.25, 7)

        return MarketRegime(
            state="EARLY_TREND",
            mode="TREND_DAY",
            strength=round(strength, 2),
            volatility=round(volatility, 6),
            comment="Fresh expansion"
        )

    # TRENDING

    if adx >= 28:

        strength = min(6 + (adx - 28) * 0.2, 10)

        return MarketRegime(
            state="TRENDING",
            mode="TREND_DAY",
            strength=round(strength, 2),
            volatility=round(volatility, 6),
            comment="Strong trend"
        )

    # COMPRESSION

    if recent_range < prev_range * 0.75:

        return MarketRegime(
            state="COMPRESSION",
            mode="RANGE_DAY",
            strength=2.5,
            volatility=round(volatility, 6),
            comment="Range contraction"
        )

    # DEFAULT WEAK

    strength = min(1.5 + adx / 30, 4)

    return MarketRegime(
        state="WEAK",
        mode="RANGE_DAY",
        strength=round(strength, 2),
        volatility=round(volatility, 6),
        comment="Low momentum"
    )
