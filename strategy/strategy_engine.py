from strategy.market_regime import detect_market_regime
from strategy.htf_bias import get_htf_bias
from strategy.pullback_detector import detect_pullback_signal
from strategy.decision_engine import final_trade_decision

from strategy.vwap_filter import VWAPCalculator
from strategy.mtf_builder import MTFBuilder
from strategy.mtf_context import analyze_mtf


class StrategyEngine:
    """
    CLEAN PULLBACK STRATEGY ENGINE

    Flow:
    MTF → HTF → VWAP → Pullback → Decision
    """

    def __init__(self, scanner, vwap_calculators):
        self.scanner = scanner
        self.vwap_calculators = vwap_calculators
        self.mtf_builder = MTFBuilder()

    def evaluate(self, inst_key: str, ltp: float):

        # ==================================================
        # 1️⃣ DATA CHECK
        # ==================================================

        if not self.scanner.has_enough_data(inst_key, min_bars=25):
            return None

        prices = self.scanner.get_prices(inst_key)
        highs = self.scanner.get_highs(inst_key)
        lows = self.scanner.get_lows(inst_key)
        closes = self.scanner.get_closes(inst_key)
        volumes = self.scanner.get_volumes(inst_key)

        if not (prices and highs and lows and closes and volumes):
            return None

        # ==================================================
        # 2️⃣ MTF CONTEXT
        # ==================================================

        last_bar = self.scanner.get_last_n_bars(inst_key, 1)
        if not last_bar:
            return None

        bar = last_bar[0]

        self.mtf_builder.update(
            inst_key,
            bar["time"],
            bar["open"],
            bar["high"],
            bar["low"],
            bar["close"],
            bar["volume"]
        )

        candle_5m = self.mtf_builder.get_latest_5m(inst_key)
        candle_15m = self.mtf_builder.get_latest_15m(inst_key)

        hist_5m_small = self.mtf_builder.get_tf_history(inst_key, 5, 3)
        hist_15m = self.mtf_builder.get_tf_history(inst_key, 15, 3)

        mtf_ctx = analyze_mtf(
            candle_5m,
            candle_15m,
            history_5m=hist_5m_small,
            history_15m=hist_15m
        )

        if mtf_ctx.direction == "NEUTRAL" or mtf_ctx.conflict:
            return None

        # ==================================================
        # 3️⃣ VWAP CONTEXT
        # ==================================================

        if inst_key not in self.vwap_calculators:
            self.vwap_calculators[inst_key] = VWAPCalculator()

        vwap_calc = self.vwap_calculators[inst_key]

        vwap_calc.update(
            ltp,
            volumes[-1] if volumes else 0
        )

        vwap_ctx = vwap_calc.get_context(ltp)

        # ==================================================
        # 4️⃣ HTF BIAS (FINAL DIRECTION AUTHORITY)
        # ==================================================

        hist_5m = self.mtf_builder.get_tf_history(inst_key, minutes=5, lookback=120)

        if not hist_5m or len(hist_5m) < 60:
            return None

        htf_bias = get_htf_bias(
            candles_5m=hist_5m,
            vwap_value=vwap_ctx.vwap
        )

        # 🔥 FINAL DIRECTION CHECK (STRICT)
        if mtf_ctx.direction != htf_bias.direction:
            return None

        direction = htf_bias.direction

        # ==================================================
        # 5️⃣ MARKET REGIME (SOFT FILTER)
        # ==================================================

        regime = detect_market_regime(
            highs=highs,
            lows=lows,
            closes=closes
        )

        if regime.state in ("WEAK", "COMPRESSION"):
            return None

        # ==================================================
        # 6️⃣ PULLBACK SETUP
        # ==================================================

        highs_5m = [c["high"] for c in hist_5m]
        lows_5m = [c["low"] for c in hist_5m]

        pullback = detect_pullback_signal(
            prices=prices,
            highs=highs_5m,
            lows=lows_5m,
            closes=closes,
            htf_direction=direction
        )

        if not pullback:
            return None

        # ==================================================
        # 7️⃣ FINAL DECISION
        # ==================================================

        decision = final_trade_decision(
            inst_key=inst_key,
            prices=prices,
            highs=highs,
            lows=lows,
            closes=closes,
            volumes=volumes,
            market_regime=regime.state,
            htf_bias_direction=direction,
            vwap_ctx=vwap_ctx,
            pullback_signal=pullback
        )

        # Debug info (optional)
        decision.components["mtf"] = mtf_ctx.direction
        decision.components["htf"] = htf_bias.label
        decision.components["regime"] = regime.state

        return decision
