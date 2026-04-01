# strategy/decision_engine.py

from dataclasses import dataclass
from typing import Optional, Dict

from strategy.volume_filter import analyze_volume
from strategy.volatility_filter import analyze_volatility, compute_atr
from strategy.price_action import price_action_context
from strategy.sr_levels import sr_location_score
from strategy.vwap_filter import VWAPContext


# =========================
# Output Structure
# =========================

@dataclass
class DecisionResult:
    state: str                 # IGNORE | PREPARE_LONG | PREPARE_SHORT | EXECUTE_LONG | EXECUTE_SHORT
    score: float               # 0 – 10
    direction: Optional[str]
    components: Dict[str, float]
    reason: str


# =========================
# CLEAN DECISION ENGINE
# =========================

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

    # ==================================================
    # 1️⃣ SETUP CHECK (MANDATORY)
    # ==================================================

    if not pullback_signal:
        return DecisionResult("IGNORE", 0.0, None, {}, "no setup")

    direction = pullback_signal["direction"]
    components["structure"] = 3.0
    score += 3.0

    # ==================================================
    # 2️⃣ HTF AUTHORITY
    # ==================================================

    if direction == "LONG" and htf_bias_direction != "BULLISH":
        return DecisionResult("IGNORE", 0.0, None, {}, "htf mismatch")

    if direction == "SHORT" and htf_bias_direction != "BEARISH":
        return DecisionResult("IGNORE", 0.0, None, {}, "htf mismatch")

    components["htf"] = 2.0
    score += 2.0

    # ==================================================
    # 3️⃣ MARKET REGIME (SOFT FILTER)
    # ==================================================

    if market_regime in ("WEAK", "COMPRESSION"):
        return DecisionResult("IGNORE", 0.0, None, {}, "bad regime")

    if market_regime == "TRENDING":
        components["regime"] = 1.2
        score += 1.2
    else:
        components["regime"] = 0.8
        score += 0.8

    # ==================================================
    # 4️⃣ VWAP FILTER (LOCATION ONLY)
    # ==================================================

    if direction == "LONG" and vwap_ctx.acceptance == "BELOW":
        return DecisionResult("IGNORE", 0.0, None, {}, "below vwap")

    if direction == "SHORT" and vwap_ctx.acceptance == "ABOVE":
        return DecisionResult("IGNORE", 0.0, None, {}, "above vwap")

    components["vwap"] = vwap_ctx.score
    score += vwap_ctx.score

    # ==================================================
    # 5️⃣ VOLUME (SOFT CONFIRMATION)
    # ==================================================

    vol_ctx = analyze_volume(volumes, close_prices=closes)
    components["volume"] = vol_ctx.score
    score += vol_ctx.score

    # ==================================================
    # 6️⃣ VOLATILITY (SOFT CONFIRMATION)
    # ==================================================

    atr = compute_atr(highs, lows, closes)
    move = closes[-1] - closes[-2] if len(closes) > 1 else 0.0

    volat_ctx = analyze_volatility(move, atr)
    components["volatility"] = volat_ctx.score
    score += volat_ctx.score

    # ==================================================
    # 7️⃣ PRICE ACTION
    # ==================================================

    pa_ctx = price_action_context(
        prices=closes,
        highs=highs,
        lows=lows,
        opens=closes,
        closes=closes
    )

    components["price_action"] = pa_ctx["score"]
    score += max(0, pa_ctx["score"])  # only positive impact

    # ==================================================
    # 8️⃣ SR LOCATION
    # ==================================================

    nearest = pullback_signal.get("nearest_level")
    sr_score = sr_location_score(closes[-1], nearest, direction)

    components["sr"] = sr_score
    score += sr_score

    # ==================================================
    # 9️⃣ BREAKOUT TRIGGER (KEY FIX)
    # ==================================================

    recent_high = max(closes[-3:-1])
    recent_low = min(closes[-3:-1])

    trigger_ok = False

    if direction == "LONG" and closes[-1] > recent_high:
        trigger_ok = True

    if direction == "SHORT" and closes[-1] < recent_low:
        trigger_ok = True

    # ==================================================
    # 🔟 FINAL DECISION
    # ==================================================

    score = round(max(min(score, 10.0), 0.0), 2)

    if score >= 6.5:
        if trigger_ok:
            return DecisionResult(
                state=f"EXECUTE_{direction}",
                score=score,
                direction=direction,
                components=components,
                reason="breakout confirmed"
            )
        else:
            return DecisionResult(
                state=f"PREPARE_{direction}",
                score=score,
                direction=direction,
                components=components,
                reason="waiting breakout"
            )

    elif score >= 5.0:
        return DecisionResult(
            state=f"PREPARE_{direction}",
            score=score,
            direction=direction,
            components=components,
            reason="setup forming"
        )

    return DecisionResult("IGNORE", score, None, components, "low quality")
