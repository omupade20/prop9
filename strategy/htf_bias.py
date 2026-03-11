# strategy/htf_bias.py

"""
HTF Bias Detector

Purpose
-------
Determine higher timeframe directional bias using 5-minute candles.

This module should ONLY receive candles from MTFBuilder.
"""

from dataclasses import dataclass
from typing import Optional, List, Dict
from strategy.indicators import exponential_moving_average


# ---------------------------------------------------
# Output structure
# ---------------------------------------------------

@dataclass
class HTFBias:
    direction: str       # BULLISH | BEARISH | NEUTRAL
    strength: float      # 0.5 → 10
    label: str           # BULLISH_STRONG | BULLISH_WEAK | BEARISH_STRONG | BEARISH_WEAK
    comment: str


# ---------------------------------------------------
# Main HTF Bias Logic (5-minute candles)
# ---------------------------------------------------

def get_htf_bias(
    candles_5m: List[Dict],
    vwap_value: Optional[float] = None,
    short_period: int = 21,
    long_period: int = 55,
    vwap_tolerance: float = 0.006
) -> HTFBias:

    """
    Determine higher timeframe trend bias.

    candles_5m example element:

    {
        "time_start": "...",
        "open": ...,
        "high": ...,
        "low": ...,
        "close": ...
    }
    """

    # ---------------------------------------------------
    # Safety checks
    # ---------------------------------------------------

    if not candles_5m or len(candles_5m) < long_period + 5:
        return HTFBias(
            direction="NEUTRAL",
            strength=0.5,
            label="NEUTRAL",
            comment="Insufficient 5m data"
        )

    prices = [c["close"] for c in candles_5m]

    ema_short = exponential_moving_average(prices, short_period)
    ema_long = exponential_moving_average(prices, long_period)

    if ema_short is None or ema_long is None:
        return HTFBias(
            direction="NEUTRAL",
            strength=0.5,
            label="NEUTRAL",
            comment="EMA calculation failed"
        )

    last_price = prices[-1]

    # ---------------------------------------------------
    # Direction detection
    # ---------------------------------------------------

    if ema_short > ema_long:
        direction = "BULLISH"
    elif ema_short < ema_long:
        direction = "BEARISH"
    else:
        return HTFBias(
            direction="NEUTRAL",
            strength=1.0,
            label="NEUTRAL",
            comment="EMA crossover flat"
        )

    # ---------------------------------------------------
    # Strength calculation
    # ---------------------------------------------------

    ema_diff = abs(ema_short - ema_long)

    lookback = min(20, len(prices))
    recent = prices[-lookback:]

    price_range = max(recent) - min(recent)

    if price_range <= 0:
        strength = 2.0
    else:
        strength = min((ema_diff / price_range) * 10, 6.0)

    comments = ["EMA alignment"]

    # ---------------------------------------------------
    # Trend persistence bonus
    # ---------------------------------------------------

    if len(prices) > long_period + 10:

        past_prices = prices[:-5]

        past_short = exponential_moving_average(past_prices, short_period)
        past_long = exponential_moving_average(past_prices, long_period)

        if past_short and past_long:

            if direction == "BULLISH" and past_short > past_long:
                strength += 1.0
                comments.append("trend persistence")

            if direction == "BEARISH" and past_short < past_long:
                strength += 1.0
                comments.append("trend persistence")

    # ---------------------------------------------------
    # VWAP influence
    # ---------------------------------------------------

    if vwap_value:

        distance = (last_price - vwap_value) / vwap_value

        if direction == "BULLISH":

            if distance > vwap_tolerance:
                strength += 1.0
                comments.append("above VWAP")

            elif distance < -vwap_tolerance:
                strength -= 1.0
                comments.append("below VWAP pressure")

        else:

            if distance < -vwap_tolerance:
                strength += 1.0
                comments.append("below VWAP")

            elif distance > vwap_tolerance:
                strength -= 1.0
                comments.append("above VWAP pressure")

    # ---------------------------------------------------
    # Clamp strength
    # ---------------------------------------------------

    strength = max(0.5, min(round(strength, 2), 10.0))

    # ---------------------------------------------------
    # Label classification
    # ---------------------------------------------------

    if direction == "BULLISH":
        label = "BULLISH_STRONG" if strength >= 7 else "BULLISH_WEAK"
    else:
        label = "BEARISH_STRONG" if strength >= 7 else "BEARISH_WEAK"

    return HTFBias(
        direction=direction,
        strength=strength,
        label=label,
        comment=" | ".join(comments)
    )
