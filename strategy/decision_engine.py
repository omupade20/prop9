# strategy/decision_engine.py

from dataclasses import dataclass
from typing import Optional, Dict

from strategy.volume_filter import analyze_volume
from strategy.volatility_filter import analyze_volatility, compute_atr
from strategy.liquidity_filter import analyze_liquidity
from strategy.price_action import price_action_context
from strategy.sr_levels import sr_location_score
from strategy.vwap_filter import VWAPContext


# =========================
# Output Structure
# =========================

@dataclass
class DecisionResult:
    state: str
    score: float
    direction: Optional[str]
    components: Dict[str, float]
    reason: str


# =========================================================
# PRACTICAL PULLBACK DECISION ENGINE (RESTRUCTURED)
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
    pullback_signal: Optional[Dict],
) -> DecisionResult:

    components: Dict[str, float] = {}
    score = 0.0

    # --------------------------------------------------
    # 1) Base Structure – must have pullback signal
    # --------------------------------------------------

    if not pullback_signal:
        return DecisionResult("IGNORE", 0.0, None, {}, "no pullback setup")

    direction = pullback_signal["direction"]
    signal_type = pullback_signal["signal"]

    # CONFIRMED pullbacks get base priority
    if signal_type == "CONFIRMED":
        components["structure"] = 3.0
        score += 3.0
    else:
        components["structure"] = 1.8
        score += 1.8

    # --------------------------------------------------
    # 2) Higher Timeframe Alignment (SOFTENED)
    # --------------------------------------------------

    if direction == "LONG":
        htf_score = 1.5 if htf_bias_direction == "BULLISH" else -1.0
    else:
        htf_score = 1.5 if htf_bias_direction == "BEARISH" else -1.0

    components["htf"] = htf_score
    score += htf_score

    # --------------------------------------------------
    # 3) Market Regime (CONVERTED TO SCORING)
    # --------------------------------------------------

    regime_score = 0.0

    if market_regime == "TRENDING":
        regime_score = 1.4
    elif market_regime == "EARLY_TREND":
        regime_score = 1.0
    elif market_regime == "COMPRESSION":
        regime_score = -0.8
    elif market_regime == "WEAK":
        regime_score = -1.2

    components["regime"] = regime_score
    score += regime_score

    # --------------------------------------------------
    # 4) VWAP CONTEXT (SOFT FILTER)
    # --------------------------------------------------

    vwap_score = vwap_ctx.score

    # small directional adjustment
    if direction == "LONG" and vwap_ctx.acceptance == "BELOW":
        vwap_score -= 0.8
    if direction == "SHORT" and vwap_ctx.acceptance == "ABOVE":
        vwap_score -= 0.8

    components["vwap"] = vwap_score
    score += vwap_score

    # --------------------------------------------------
    # 5) Volume Quality (SOFTENED)
    # --------------------------------------------------

    vol_ctx = analyze_volume(volumes, close_prices=closes)

    volume_score = 0.0

    if vol_ctx.score >= 1.0:
        volume_score = 1.2
    elif vol_ctx.score >= 0.2:
        volume_score = 0.6
    elif vol_ctx.score < 0:
        volume_score = -1.0

    components["volume"] = volume_score
    score += volume_score

    # --------------------------------------------------
    # 6) Volatility Context (SOFT)
    # --------------------------------------------------

    atr = compute_atr(highs, lows, closes)
    move = closes[-1] - closes[-2] if len(closes) > 1 else 0.0

    volat_ctx = analyze_volatility(move, atr)

    volatility_score = 0.0

    if volat_ctx.state == "EXPANDING":
        volatility_score = 1.2
    elif volat_ctx.state == "BUILDING":
        volatility_score = 0.7
    elif volat_ctx.state == "CONTRACTING":
        volatility_score = -0.6
    elif volat_ctx.state == "EXHAUSTION":
        volatility_score = -1.0

    components["volatility"] = volatility_score
    score += volatility_score

    # --------------------------------------------------
    # 7) Liquidity Safety (SOFTENED)
    # --------------------------------------------------

    liq_ctx = analyze_liquidity(volumes)

    liquidity_score = 0.0

    if liq_ctx.score >= 1.0:
        liquidity_score = 1.0
    elif liq_ctx.score >= 0:
        liquidity_score = 0.5
    else:
        liquidity_score = -1.2

    components["liquidity"] = liquidity_score
    score += liquidity_score

    # --------------------------------------------------
    # 8) Price Action Timing
    # --------------------------------------------------

    pa_ctx = price_action_context(
        prices=closes,
        highs=highs,
        lows=lows,
        opens=closes,
        closes=closes
    )

    pa_score = pa_ctx["score"] * 1.3

    components["price_action"] = round(pa_score, 2)
    score += pa_score

    # --------------------------------------------------
    # 9) SR Location Bonus
    # --------------------------------------------------

    nearest = pullback_signal.get("nearest_level")

    sr_score = sr_location_score(closes[-1], nearest, direction)

    components["sr"] = sr_score
    score += sr_score * 1.1

    # --------------------------------------------------
    # 10) FINAL DECISION (TUNED THRESHOLDS)
    # --------------------------------------------------

    score = round(max(min(score, 10.0), 0.0), 2)

    if score >= 5.5:
        state = f"EXECUTE_{direction}"
        reason = "high quality pullback trade"

    elif score >= 3.5:
        state = f"PREPARE_{direction}"
        reason = "developing pullback setup"

    else:
        state = "IGNORE"
        reason = "insufficient edge"

    return DecisionResult(
        state=state,
        score=score,
        direction=direction if state != "IGNORE" else None,
        components=components,
        reason=reason
    )
