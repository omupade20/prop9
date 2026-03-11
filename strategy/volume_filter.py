# strategy/volume_context.py

"""
Volume Context Analyzer

Purpose
-------
Evaluate whether current volume supports price movement.

Used for:
• Confirming breakouts
• Detecting absorption
• Filtering weak moves

This module operates on **1-minute volume data**.
"""

from dataclasses import dataclass
from typing import List, Optional


# =========================================================
# Output Structure
# =========================================================

@dataclass
class VolumeContext:

    score: float          # -2 .. +2
    strength: str         # STRONG | MODERATE | WEAK | NONE
    trend: str            # RISING | FALLING | FLAT
    comment: str


# =========================================================
# Volume Analysis
# =========================================================

def analyze_volume(
    volume_history: List[float],
    close_prices: Optional[List[float]] = None,
    lookback: int = 20,
    rising_bars: int = 4
) -> VolumeContext:

    if not volume_history or len(volume_history) < lookback + rising_bars:

        return VolumeContext(
            score=0.0,
            strength="NONE",
            trend="FLAT",
            comment="insufficient volume data"
        )

    recent = volume_history[-lookback:]
    avg_volume = sum(recent) / lookback
    current_volume = volume_history[-1]

    # =====================================================
    # 1️⃣ Volume strength relative to average
    # =====================================================

    rel = current_volume / avg_volume if avg_volume > 0 else 1.0

    if rel >= 1.8:
        strength = "STRONG"
        score = 2.0

    elif rel >= 1.4:
        strength = "MODERATE"
        score = 1.2

    elif rel >= 1.0:
        strength = "WEAK"
        score = 0.4

    else:
        strength = "NONE"
        score = -0.4

    # =====================================================
    # 2️⃣ Volume trend
    # =====================================================

    last_n = volume_history[-rising_bars:]

    rising = all(last_n[i] > last_n[i - 1] for i in range(1, len(last_n)))
    falling = all(last_n[i] < last_n[i - 1] for i in range(1, len(last_n)))

    if rising:

        trend = "RISING"
        score += 0.4

    elif falling:

        trend = "FALLING"
        score -= 0.4

    else:

        trend = "FLAT"

    # =====================================================
    # 3️⃣ Price / volume relationship
    # =====================================================

    comment = "volume only"

    if close_prices and len(close_prices) >= rising_bars:

        price_move = close_prices[-1] - close_prices[-rising_bars]

        price_threshold = 0.002 * close_prices[-1]

        if abs(price_move) < price_threshold:

            if strength in ("STRONG", "MODERATE"):

                score -= 0.7
                comment = "absorption suspected"

            else:

                comment = "volume but no price move"

        else:

            comment = "volume supports move"

    # =====================================================
    # Clamp score
    # =====================================================

    score = max(min(score, 2.0), -2.0)

    return VolumeContext(
        score=round(score, 2),
        strength=strength,
        trend=trend,
        comment=comment
    )


# =========================================================
# Legacy Boolean Helper
# =========================================================

def volume_spike_confirmed(
    volume_history: List[float],
    threshold_multiplier: float = 1.25,
    lookback: int = 20
) -> bool:

    if not volume_history or len(volume_history) < lookback:
        return False

    recent = volume_history[-lookback:]
    avg_volume = sum(recent) / lookback

    return volume_history[-1] > avg_volume * threshold_multiplier
