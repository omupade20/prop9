# strategy/pullback_detector.py

"""
Pullback Signal Detector

Purpose
-------
Detect high-quality pullback entries aligned with higher timeframe trend.

Structure:
5m candles → support/resistance
1m candles → entry confirmation
"""

from typing import Optional, Dict, List

from strategy.sr_levels import compute_sr_levels_from_5m, get_nearest_sr
from strategy.volume_context import analyze_volume
from strategy.volatility_context import compute_atr, analyze_volatility
from strategy.price_action import rejection_info


def detect_pullback_signal(
    prices: List[float],
    highs: List[float],
    lows: List[float],
    closes: List[float],
    volumes: List[float],
    candles_5m: List[Dict],
    htf_direction: str,
    max_proximity: float = 0.018,
    min_bars: int = 35
) -> Optional[Dict]:

    if len(closes) < min_bars or not candles_5m:
        return None

    last_price = closes[-1]

    # =====================================================
    # 1️⃣ STRUCTURAL LOCATION (5m SR)
    # =====================================================

    sr = compute_sr_levels_from_5m(candles_5m)

    nearest = get_nearest_sr(last_price, sr, max_search_pct=max_proximity)

    if not nearest:
        return None

    # Determine trade direction
    if nearest["type"] == "support" and htf_direction == "BULLISH":
        trade_direction = "LONG"

    elif nearest["type"] == "resistance" and htf_direction == "BEARISH":
        trade_direction = "SHORT"

    else:
        return None

    # =====================================================
    # 2️⃣ EXTENSION FILTER (avoid chasing)
    # =====================================================

    atr = compute_atr(highs, lows, closes)

    if atr:

        recent_move = abs(closes[-1] - closes[-6])

        if recent_move > atr * 1.6:
            return None

    # =====================================================
    # 3️⃣ VOLATILITY QUALITY
    # =====================================================

    volat_ctx = analyze_volatility(
        current_move=closes[-1] - closes[-2],
        atr_value=atr
    )

    if volat_ctx.state in ("CONTRACTING", "EXHAUSTION"):
        return None

    # =====================================================
    # 4️⃣ PRICE ACTION CONFIRMATION
    # =====================================================

    rejection = rejection_info(
        closes[-2],
        highs[-1],
        lows[-1],
        closes[-1]
    )

    price_reaction = False

    if trade_direction == "LONG" and rejection["rejection_type"] == "BULLISH":
        price_reaction = True

    if trade_direction == "SHORT" and rejection["rejection_type"] == "BEARISH":
        price_reaction = True

    # fallback directional movement
    if trade_direction == "LONG" and closes[-1] > closes[-3]:
        price_reaction = True

    if trade_direction == "SHORT" and closes[-1] < closes[-3]:
        price_reaction = True

    # =====================================================
    # 5️⃣ VOLUME CONFIRMATION
    # =====================================================

    vol_ctx = analyze_volume(volumes, close_prices=closes)

    volume_ok = vol_ctx.score >= 0.5

    # =====================================================
    # 6️⃣ MOMENTUM CHECK
    # =====================================================

    momentum = closes[-1] - closes[-5]

    momentum_ok = False

    if trade_direction == "LONG" and momentum > 0:
        momentum_ok = True

    if trade_direction == "SHORT" and momentum < 0:
        momentum_ok = True

    # =====================================================
    # 7️⃣ SIGNAL SCORING
    # =====================================================

    components = {
        "location": 0.0,
        "price_action": 0.0,
        "volume": 0.0,
        "volatility": 0.0,
        "momentum": 0.0
    }

    # Location quality
    proximity_score = max(0, (max_proximity - nearest["dist_pct"]) * 60)
    components["location"] = min(proximity_score, 2.0)

    if price_reaction:
        components["price_action"] = 1.8

    if volume_ok:
        components["volume"] = 1.2

    if volat_ctx.state == "EXPANDING":
        components["volatility"] = 1.2

    if momentum_ok:
        components["momentum"] = 1.0

    total_score = sum(components.values())

    # =====================================================
    # 8️⃣ CLASSIFICATION
    # =====================================================

    if total_score >= 5:
        signal = "CONFIRMED"

    elif total_score >= 3:
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
            "rejection": rejection["rejection_type"]
        },
        "reason": f"{signal}_{trade_direction}"
    }
