# strategy/pullback_detector.py

from typing import Optional, Dict, List
from strategy.sr_levels import compute_sr_levels, get_nearest_sr
from strategy.volume_filter import analyze_volume
from strategy.volatility_filter import compute_atr, analyze_volatility
from strategy.price_action import rejection_info


def detect_pullback_signal(
    prices: List[float],
    highs: List[float],
    lows: List[float],
    closes: List[float],
    volumes: List[float],
    htf_direction: str,
    max_proximity: float = 0.03,      # RELAXED: 1.8% → 3%
    min_bars: int = 30               # Slightly relaxed
) -> Optional[Dict]:
    """
    PRACTICAL PULLBACK DETECTOR (TUNED FOR REAL MARKETS)

    - Score based model instead of hard filters
    - Accepts multiple forms of pullbacks
    - Designed to generate DAILY signals, not perfection
    """

    if len(prices) < min_bars:
        return None

    last_price = closes[-1]

    # --------------------------------------------------
    # 1) STRUCTURAL LOCATION
    # --------------------------------------------------

    sr = compute_sr_levels(highs, lows)
    nearest = get_nearest_sr(last_price, sr, max_search_pct=max_proximity)

    if not nearest:
        return None

    trade_direction = None

    if nearest["type"] == "support" and htf_direction == "BULLISH":
        trade_direction = "LONG"

    elif nearest["type"] == "resistance" and htf_direction == "BEARISH":
        trade_direction = "SHORT"

    else:
        return None

    # --------------------------------------------------
    # 2) EXTENSION FILTER (SOFTENED)
    # --------------------------------------------------

    recent_move = abs(closes[-1] - closes[-6])
    atr = compute_atr(highs, lows, closes)

    extended = False

    if atr and recent_move > atr * 2.0:   # Relaxed from 1.6 → 2.0
        extended = True

    # --------------------------------------------------
    # 3) VOLATILITY QUALITY
    # --------------------------------------------------

    volat_ctx = analyze_volatility(
        current_move=closes[-1] - closes[-2],
        atr_value=atr
    )

    volatility_score = 0.0

    if volat_ctx.state == "EXPANDING":
        volatility_score = 1.5
    elif volat_ctx.state == "BUILDING":
        volatility_score = 0.8
    elif volat_ctx.state == "CONTRACTING":
        volatility_score = 0.2
    else:
        volatility_score = 0.0

    # --------------------------------------------------
    # 4) PRICE ACTION CONFIRMATION (NOW SOFT)
    # --------------------------------------------------

    last_bar_rejection = rejection_info(
        closes[-2], highs[-1], lows[-1], closes[-1]
    )

    price_action_score = 0.0

    # Strong rejection
    if trade_direction == "LONG" and last_bar_rejection["rejection_type"] == "BULLISH":
        price_action_score += 1.8

    if trade_direction == "SHORT" and last_bar_rejection["rejection_type"] == "BEARISH":
        price_action_score += 1.8

    # Directional confirmation
    if trade_direction == "LONG" and closes[-1] > closes[-3]:
        price_action_score += 1.0

    if trade_direction == "SHORT" and closes[-1] < closes[-3]:
        price_action_score += 1.0

    # Consolidation style pullback
    recent_range = max(highs[-5:]) - min(lows[-5:])
    if atr and recent_range < atr * 0.7:
        price_action_score += 0.8

    # --------------------------------------------------
    # 5) VOLUME CONFIRMATION (SOFTENED)
    # --------------------------------------------------

    vol_ctx = analyze_volume(volumes, close_prices=closes)

    volume_score = 0.0

    if vol_ctx.score >= 1.0:
        volume_score = 1.5
    elif vol_ctx.score >= 0.2:        # RELAXED: 0.6 → 0.2
        volume_score = 0.8
    elif vol_ctx.score >= 0:
        volume_score = 0.3

    # --------------------------------------------------
    # 6) MOMENTUM FILTER (SOFT)
    # --------------------------------------------------

    short_term_trend = closes[-1] - closes[-5]
    momentum_score = 0.0

    if trade_direction == "LONG" and short_term_trend > 0:
        momentum_score = 1.0

    if trade_direction == "SHORT" and short_term_trend < 0:
        momentum_score = 1.0

    # --------------------------------------------------
    # 7) LOCATION QUALITY
    # --------------------------------------------------

    proximity_score = max(0, (max_proximity - nearest["dist_pct"]) * 40)
    proximity_score = min(proximity_score, 2.0)

    # --------------------------------------------------
    # 8) FINAL SCORING (ADDITIVE MODEL)
    # --------------------------------------------------

    components = {
        "location": round(proximity_score, 2),
        "price_action": round(price_action_score, 2),
        "volume": round(volume_score, 2),
        "volatility": round(volatility_score, 2),
        "momentum": round(momentum_score, 2)
    }

    total_score = sum(components.values())

    # Small penalty if very extended
    if extended:
        total_score -= 1.0

    # --------------------------------------------------
    # 9) CLASSIFICATION (TUNED)
    # --------------------------------------------------

    if total_score >= 4.2:         # Lowered from 5.0
        signal = "CONFIRMED"
    elif total_score >= 2.8:       # Lowered from 3.0
        signal = "POTENTIAL"
    else:
        return None

    return {
        "signal": signal,
        "direction": trade_direction,
        "score": round(total_score, 2),
        "nearest_level": nearest,
        "components": components,
        "context": {
            "volatility": volat_ctx.state,
            "volume": vol_ctx.strength,
            "rejection": last_bar_rejection["rejection_type"]
        },
        "reason": f"{signal}_{trade_direction}"
    }
