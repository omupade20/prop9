from strategy.market_regime import detect_market_regime
from strategy.htf_bias import get_htf_bias
from strategy.pullback_detector import detect_pullback_signal
from strategy.decision_engine import final_trade_decision

from strategy.mtf_builder import MTFBuilder


class StrategyEngine:
    """
    CLEAN PULLBACK STRATEGY ENGINE

    Architecture:

    1m data → Scanner
           ↓
    5m candles → MTFBuilder
           ↓
    HTF Bias (5m trend)
           ↓
    Market Regime
           ↓
    Pullback Detection
           ↓
    Decision Engine
    """

    def __init__(self, scanner):

        self.scanner = scanner
        self.mtf_builder = MTFBuilder()

    def evaluate(self, inst_key: str, ltp: float):

        # ==================================================
        # 1️⃣ DATA SUFFICIENCY
        # ==================================================

        if not self.scanner.has_enough_data(inst_key, min_bars=30):
            return None

        prices = self.scanner.get_prices(inst_key)
        highs = self.scanner.get_highs(inst_key)
        lows = self.scanner.get_lows(inst_key)
        closes = self.scanner.get_closes(inst_key)
        volumes = self.scanner.get_volumes(inst_key)

        if not (prices and highs and lows and closes and volumes):
            return None

        # ==================================================
        # 2️⃣ UPDATE MTF BUILDER
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

        # ==================================================
        # 3️⃣ GET 5m HISTORY
        # ==================================================

        hist_5m = self.mtf_builder.get_tf_history(
            inst_key,
            minutes=5,
            lookback=120
        )

        if not hist_5m or len(hist_5m) < 60:
            return None

        # ==================================================
        # 4️⃣ HTF BIAS (5m trend)
        # ==================================================

        htf_bias = get_htf_bias(
            candles_5m=hist_5m
        )

        if htf_bias.direction == "NEUTRAL":
            return None

        # ==================================================
        # 5️⃣ MARKET REGIME
        # ==================================================

        regime = detect_market_regime(
            highs=highs,
            lows=lows,
            closes=closes
        )

        if regime.state == "WEAK":
            return None

        # ==================================================
        # 6️⃣ PULLBACK DETECTION
        # ==================================================

        pullback = detect_pullback_signal(
            prices=prices,
            highs=highs,
            lows=lows,
            closes=closes,
            volumes=volumes,
            candles_5m=hist_5m,
            htf_direction=htf_bias.direction
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
            htf_bias_direction=htf_bias.direction,
            vwap_ctx=None,
            pullback_signal=pullback
        )

        # Debug info
        decision.components["regime"] = regime.state
        decision.components["htf_bias"] = htf_bias.label

        return decision
        
