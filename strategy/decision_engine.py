# strategy/decision_engine.py

from dataclasses import dataclass
from typing import Optional, Dict

from strategy.volume_context import analyze_volume
from strategy.volatility_context import analyze_volatility, compute_atr
from strategy.liquidity_context import analyze_liquidity
from strategy.price_action import price_action_context
from strategy.sr_levels import sr_location_score
from strategy.vwap_filter import VWAPContext


# =========================================================
# Output Structure
# =========================================================

@dataclass
class DecisionResult:

    state: str
    score: float
    direction: Optional[str]
    components: Dict[str, float]
    reason: str


# =========================================================
# Final Decision Engine
# =========================================================

def final_trade_decision(

    inst_key: str,
    prices: list[float],
    highs: list[float],
    lows: list[float],
    closes: list[float],
    volumes: list[float],
    market_regime: str,
    htf_bias_direction: str,
    vwap_ctx: VWAPContext,
    pullback_signal: Optional[Dict]

) -> DecisionResult:

    components: Dict[str, float] = {}
    score = 0.0

    # =====================================================
    # 1️⃣ STRUCTURE (pullback signal)
    # =====================================================

    if not pullback_signal:

        return DecisionResult(
            state="IGNORE",
            score=0.0,
            direction=None,
            components={},
            reason="no pullback setup"
        )

    direction = pullback_signal["direction"]
    signal_type = pullback_signal["signal"]

    if signal_type == "POTENTIAL":

        components["structure"] = 1.5

        return DecisionResult(
            state=f"PREPARE_{direction}",
            score=1.5,
            direction=direction,
            components=components,
            reason="potential pullback"
        )

    components["structure"] = 3.0
    score += 3.0

    # =====================================================
    # 2️⃣ HTF TREND ALIGNMENT
    # =====================================================

    if direction == "LONG" and htf_bias_direction != "BULLISH":
        return DecisionResult("IGNORE", 0.0, None, {}, "HTF conflict")

    if direction == "SHORT" and htf_bias_direction != "BEARISH":
        return DecisionResult("IGNORE", 0.0, None, {}, "HTF conflict")

    components["htf"] = 1.2
    score += 1.2

    # =====================================================
    # 3️⃣ MARKET REGIME
    # =====================================================

    if market_regime == "WEAK":

        components["regime"] = -0.5
        score -= 0.5

    elif market_regime == "COMPRESSION":

        components["regime"] = 0.3
        score += 0.3

    elif market_regime == "EARLY_TREND":

        components["regime"] = 1.0
        score += 1.0

    elif market_regime == "TRENDING":

        components["regime"] = 1.4
        score += 1.4

    # =====================================================
    # 4️⃣ VWAP CONTEXT
    # =====================================================

    components["vwap"] = vwap_ctx.score
    score += vwap_ctx.score

    # =====================================================
    # 5️⃣ VOLUME
    # =====================================================

    vol_ctx = analyze_volume(volumes, close_prices=closes)

    components["volume"] = vol_ctx.score
    score += vol_ctx.score

    # =====================================================
    # 6️⃣ VOLATILITY
    # =====================================================

    atr = compute_atr(highs, lows, closes)

    move = closes[-1] - closes[-2] if len(closes) > 1 else 0.0

    volat_ctx = analyze_volatility(move, atr)

    components["volatility"] = volat_ctx.score
    score += volat_ctx.score

    # =====================================================
    # 7️⃣ LIQUIDITY
    # =====================================================

    liq_ctx = analyze_liquidity(volumes)

    components["liquidity"] = liq_ctx.score
    score += liq_ctx.score

    # =====================================================
    # 8️⃣ PRICE ACTION
    # =====================================================

    pa_ctx = price_action_context(

        prices=closes,
        highs=highs,
        lows=lows,
        opens=closes,
        closes=closes

    )

    components["price_action"] = pa_ctx["score"]
    score += pa_ctx["score"]

    # =====================================================
    # 9️⃣ SR LOCATION
    # =====================================================

    nearest = pullback_signal.get("nearest_level")

    sr_score = sr_location_score(closes[-1], nearest, direction)

    components["sr"] = sr_score

    score += sr_score * 1.2

    # =====================================================
    # 🔟 FINAL DECISION
    # =====================================================

    score = round(max(min(score, 10.0), 0.0), 2)

    if score >= 8.2:

        state = f"EXECUTE_{direction}"
        reason = "high quality setup"

    elif score >= 6.5:

        state = f"PREPARE_{direction}"
        reason = "developing setup"

    else:

        state = "IGNORE"
        reason = "edge insufficient"

    return DecisionResult(

        state=state,
        score=score,
        direction=direction if state != "IGNORE" else None,
        components=components,
        reason=reason

    )
