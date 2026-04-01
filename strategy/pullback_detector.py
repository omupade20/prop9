# strategy/pullback_detector.py

from typing import Optional, Dict, List
from strategy.sr_levels import compute_sr_levels, get_nearest_sr
from strategy.price_action import rejection_info


def detect_pullback_signal(
    prices: List[float],
    highs: List[float],
    lows: List[float],
    closes: List[float],
    htf_direction: str,
    max_proximity: float = 0.02,
    min_bars: int = 30
) -> Optional[Dict]:
    """
    CLEAN PULLBACK SETUP DETECTOR

    Purpose:
    - Identify pullback at key level
    - NO scoring, NO filtering
    - Only structure detection

    Output:
    {
        "direction": "LONG" / "SHORT",
        "type": "SETUP",
        "nearest_level": {...}
    }
    """

    if len(prices) < min_bars:
        return None

    last_price = closes[-1]

    # ----------------------
    # 1️⃣ STRUCTURE (SR LEVEL)
    # ----------------------

    sr = compute_sr_levels(highs, lows)
    nearest = get_nearest_sr(last_price, sr, max_search_pct=max_proximity)

    if not nearest:
        return None

    # ----------------------
    # 2️⃣ DIRECTION ALIGNMENT
    # ----------------------

    direction = None

    if nearest["type"] == "support" and htf_direction == "BULLISH":
        direction = "LONG"

    elif nearest["type"] == "resistance" and htf_direction == "BEARISH":
        direction = "SHORT"

    else:
        return None

    # ----------------------
    # 3️⃣ SIMPLE PRICE REACTION (OPTIONAL)
    # ----------------------

    last_rejection = rejection_info(
        closes[-2],
        highs[-1],
        lows[-1],
        closes[-1]
    )

    # Optional light filter (not strict)
    if direction == "LONG" and last_rejection["rejection_type"] == "BEARISH":
        return None

    if direction == "SHORT" and last_rejection["rejection_type"] == "BULLISH":
        return None

    # ----------------------
    # FINAL OUTPUT (SETUP ONLY)
    # ----------------------

    return {
        "type": "SETUP",
        "direction": direction,
        "nearest_level": nearest
    }
