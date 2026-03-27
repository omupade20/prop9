from strategy.market_regime import detect_market_regime
from strategy.pullback_detector import detect_pullback_signal
from strategy.decision_engine import final_trade_decision

from strategy.vwap_filter import VWAPCalculator
from strategy.mtf_builder import MTFBuilder
from strategy.mtf_context import analyze_mtf


class StrategyEngine:
    """
    CLEAN PULLBACK-BASED STRATEGY ENGINE

    Hierarchy:

    MTF (15m) → Regime (5m) → VWAP → Pullback → Decision Engine
    """

    def __init__(self, scanner, vwap_calculators):
        self.scanner = scanner
        self.vwap_calculators = vwap_calculators
        self.mtf_builder = MTFBuilder()

        # 🔥 FIX: prevent duplicate 1m → MTF updates
        self.last_bar_time = {}

    def evaluate(self, inst_key: str, ltp: float):

        # ==================================================
        # 1️⃣ DATA SUFFICIENCY
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
        # 2️⃣ MULTI TIMEFRAME CONTEXT (15m direction)
        # ==================================================

        last_bar = self.scanner.get_last_n_bars(inst_key, 1)
        if not last_bar:
            return None

        bar = last_bar[0]
        bar_time = bar["time"]

        # 🔥 FIX: avoid duplicate MTF updates
        if self.last_bar_time.get(inst_key) != bar_time:
            self.last_bar_time[inst_key] = bar_time

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
        hist_5m_small = self.mtf_builder.get_tf_history(inst_key, minutes=5, lookback=3)

        candle_15m = self.mtf_builder.get_latest_15m(inst_key)
        hist_15m = self.mtf_builder.get_tf_history(inst_key, minutes=15, lookback=3)

        mtf_ctx = analyze_mtf(
            candle_5m,
            candle_15m,
            history_5m=hist_5m_small,
            history_15m=hist_15m
        )

        if mtf_ctx.direction == "NEUTRAL":
            return None

        # 🔥 FIX: allow strong trends even if slight conflict
        if mtf_ctx.conflict and mtf_ctx.strength < 1.2:
            return None

        # ==================================================
        # 3️⃣ MARKET REGIME (5m)
        # ==================================================

        hist_5m = self.mtf_builder.get_tf_history(inst_key, minutes=5, lookback=120)

        if not hist_5m or len(hist_5m) < 30:
            return None

        highs_5m = [c["high"] for c in hist_5m]
        lows_5m = [c["low"] for c in hist_5m]
        closes_5m = [c["close"] for c in hist_5m]

        regime = detect_market_regime(
            highs=highs_5m,
            lows=lows_5m,
            closes=closes_5m
        )

        # 🔥 FIX: allow EARLY_TREND
        if regime.state == "WEAK":
            return None

        # ==================================================
        # 4️⃣ VWAP CONTEXT
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
        # 5️⃣ PULLBACK DETECTION
        # ==================================================

        pullback = detect_pullback_signal(
            prices=prices,
            highs=highs_5m,
            lows=lows_5m,
            closes=closes,
            volumes=volumes,
            htf_direction=mtf_ctx.direction
        )

        if not pullback:
            return None

        # ==================================================
        # 6️⃣ FINAL DECISION ENGINE
        # ==================================================

        decision = final_trade_decision(
            inst_key=inst_key,
            prices=prices,
            highs=highs,
            lows=lows,
            closes=closes,
            volumes=volumes,
            market_regime=regime.state,
            htf_bias_direction=mtf_ctx.direction,
            vwap_ctx=vwap_ctx,
            pullback_signal=pullback
        )

        # Debug info
        decision.components["mtf_direction"] = mtf_ctx.direction
        decision.components["mtf_strength"] = mtf_ctx.strength
        decision.components["regime"] = regime.state

        return decision
