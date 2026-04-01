# strategy/volume_context.py

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class VolumeContext:
    score: float          # -1 to +1 (controlled impact)
    strength: str         # HIGH | NORMAL | LOW
    trend: str            # RISING | FALLING | FLAT
    comment: str


def analyze_volume(
    volume_history: List[float],
    close_prices: Optional[List[float]] = None,
    lookback: int = 20,
    rising_bars: int = 3
) -> VolumeContext:
    """
    SIMPLIFIED VOLUME LOGIC

    Purpose:
    - Confirm participation
    - Avoid over-penalizing trades
    """

    if not volume_history or len(volume_history) < lookback:
        return VolumeContext(0.0, "LOW", "FLAT", "insufficient_data")

    recent = volume_history[-lookback:]
    avg_volume = sum(recent) / lookback
    current_volume = volume_history[-1]

    # ----------------------
    # 1️⃣ Relative Volume
    # ----------------------
    rel = current_volume / avg_volume if avg_volume > 0 else 1.0

    if rel >= 1.5:
        strength = "HIGH"
        score = 1.0
    elif rel >= 1.0:
        strength = "NORMAL"
        score = 0.5
    else:
        strength = "LOW"
        score = -0.2   # very small penalty only

    # ----------------------
    # 2️⃣ Volume Trend
    # ----------------------
    trend = "FLAT"

    if len(volume_history) >= rising_bars:
        last_n = volume_history[-rising_bars:]

        if all(last_n[i] > last_n[i - 1] for i in range(1, len(last_n))):
            trend = "RISING"
            score += 0.2
        elif all(last_n[i] < last_n[i - 1] for i in range(1, len(last_n))):
            trend = "FALLING"
            score -= 0.2

    # ----------------------
    # 3️⃣ Price Confirmation (LIGHT)
    # ----------------------
    comment = "volume_only"

    if close_prices and len(close_prices) >= 3:
        move = close_prices[-1] - close_prices[-3]

        if abs(move) > 0.002 * close_prices[-1]:
            comment = "volume_supports_move"
        else:
            comment = "low_price_response"

    # ----------------------
    # Clamp score
    # ----------------------
    score = max(min(score, 1.0), -1.0)

    return VolumeContext(
        score=round(score, 2),
        strength=strength,
        trend=trend,
        comment=comment
    )


# ----------------------
# Legacy compatibility
# ----------------------
def volume_spike_confirmed(
    volume_history,
    threshold_multiplier: float = 1.25,
    lookback: int = 20,
    rising_bars: int = 3
) -> bool:
    ctx = analyze_volume(volume_history, lookback=lookback, rising_bars=rising_bars)
    return ctx.score > 0.4
