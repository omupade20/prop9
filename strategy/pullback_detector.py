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
    max_proximity: float = 0.018,
    min_bars: int = 35
) -> Optional[Dict]:

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

    level = nearest["level"]

    # --------------------------------------------------
    # 2) LIQUIDITY SWEEP + RECLAIM (NEW LOGIC)
    # --------------------------------------------------

    sweep_detected = False

    if trade_direction == "LONG":

        if lows[-1] < level and closes[-1] > level:
            sweep_detected = True

    if trade_direction == "SHORT":

        if highs[-1] > level and closes[-1] < level:
            sweep_detected = True

    if not sweep_detected:
        return None

    # --------------------------------------------------
    # 3) EXTENSION FILTER
    # --------------------------------------------------

    atr = compute_atr(highs, lows, closes)

    recent_move = abs(closes[-1] - closes[-6])

    if atr and recent_move > atr * 1.6:
        return None

    # --------------------------------------------------
    # 4) VOLATILITY QUALITY
    # --------------------------------------------------

    volat_ctx = analyze_volatility(
        current_move=closes[-1] - closes[-2],
        atr_value=atr
    )

    if volat_ctx.state in ["CONTRACTING", "EXHAUSTION"]:
        return None

    # --------------------------------------------------
    # 5) STOP-HUNT CANDLE FILTER
    # --------------------------------------------------

    candle_range = highs[-1] - lows[-1]

    if atr and candle_range > atr * 1.8:
        return None

    # --------------------------------------------------
    # 6) PRICE ACTION CONFIRMATION
    # --------------------------------------------------

    last_bar_rejection = rejection_info(
        closes[-2],
        highs[-1],
        lows[-1],
        closes[-1]
    )

    price_reaction = False

    if trade_direction == "LONG" and last_bar_rejection["rejection_type"] == "BULLISH":
        price_reaction = True

    if trade_direction == "SHORT" and last_bar_rejection["rejection_type"] == "BEARISH":
        price_reaction = True

    if trade_direction == "LONG" and closes[-1] > closes[-3]:
        price_reaction = True

    if trade_direction == "SHORT" and closes[-1] < closes[-3]:
        price_reaction = True

    # --------------------------------------------------
    # 7) VOLUME CONFIRMATION
    # --------------------------------------------------

    vol_ctx = analyze_volume(volumes, close_prices=closes)

    volume_ok = vol_ctx.score >= 0.6

    # --------------------------------------------------
    # 8) MOMENTUM FILTER
    # --------------------------------------------------

    short_term_trend = closes[-1] - closes[-5]

    momentum_ok = False

    if trade_direction == "LONG" and short_term_trend > 0:
        momentum_ok = True

    if trade_direction == "SHORT" and short_term_trend < 0:
        momentum_ok = True

    # --------------------------------------------------
    # 9) CONFIDENCE SCORING
    # --------------------------------------------------

    components = {
        "location": 0.0,
        "price_action": 0.0,
        "volume": 0.0,
        "volatility": 0.0,
        "momentum": 0.0,
        "liquidity_sweep": 0.0
    }

    # SR proximity
    proximity_score = max(0, (max_proximity - nearest["dist_pct"]) * 60)
    components["location"] = min(proximity_score, 2.0)

    if sweep_detected:
        components["liquidity_sweep"] = 1.5

    if price_reaction:
        components["price_action"] = 2.0

    if volume_ok:
        components["volume"] = 1.5

    if volat_ctx.state == "EXPANDING":
        components["volatility"] = 1.2

    if momentum_ok:
        components["momentum"] = 1.3

    total_score = sum(components.values())

    # --------------------------------------------------
    # 10) CLASSIFICATION
    # --------------------------------------------------

    if total_score >= 5.5:
        signal = "CONFIRMED"

    elif total_score >= 3.5:
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
            "rejection": last_bar_rejection["rejection_type"],
            "liquidity_sweep": sweep_detected
        },
        "reason": f"{signal}_{trade_direction}"
    }
