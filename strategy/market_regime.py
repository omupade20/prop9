from typing import List, Optional
from dataclasses import dataclass


# =========================
# Core Calculations
# =========================

def compute_true_range(highs: List[float], lows: List[float], closes: List[float]) -> List[float]:
    if len(highs) < 2:
        return []
    tr = []
    for i in range(1, len(highs)):
        tr.append(
            max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1])
            )
        )
    return tr


def compute_atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> Optional[float]:
    tr = compute_true_range(highs, lows, closes)
    if len(tr) < period:
        return None
    return sum(tr[-period:]) / period


def compute_adx(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> Optional[float]:
    if len(highs) < period + 1:
        return None

    plus_dm, minus_dm = [], []

    for i in range(1, len(highs)):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]

        plus_dm.append(up if up > down and up > 0 else 0)
        minus_dm.append(down if down > up and down > 0 else 0)

    atr = compute_atr(highs, lows, closes, period)
    if atr is None or atr == 0:
        return None

    plus_di = (sum(plus_dm[-period:]) / atr) * 100
    minus_di = (sum(minus_dm[-period:]) / atr) * 100

    if plus_di + minus_di == 0:
        return 0.0

    dx = abs(plus_di - minus_di) / (plus_di + minus_di) * 100
    return dx


# =========================
# Regime Output
# =========================

@dataclass
class MarketRegime:
    state: str
    mode: str
    strength: float
    volatility: float
    comment: str


# =========================
# Regime Detection (IMPROVED)
# =========================

def detect_market_regime(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    index_regime: Optional["MarketRegime"] = None,
    min_bars: int = 30
) -> MarketRegime:

    if len(highs) < min_bars:
        return MarketRegime("WEAK", "RANGE_DAY", 0.5, 0.0, "Insufficient data")

    atr = compute_atr(highs, lows, closes)
    adx = compute_adx(highs, lows, closes)

    if atr is None:
        return MarketRegime("WEAK", "RANGE_DAY", 0.5, 0.0, "ATR unavailable")

    # ---------------------
    # Volatility Normalization
    # ---------------------

    avg_price = sum(closes[-10:]) / 10
    vol_norm = atr / avg_price if avg_price > 0 else 0.0

    # ---------------------
    # Range Expansion Logic (PRIMARY SIGNAL)
    # ---------------------

    recent_range = max(highs[-10:]) - min(lows[-10:])
    prev_range = max(highs[-20:-10]) - min(lows[-20:-10]) if len(highs) >= 20 else recent_range

    def cap(x):
        return max(0.0, min(10.0, x))

    # =====================
    # CORE LOGIC (FIXED)
    # =====================

    # 🚀 EARLY TREND (EXPANSION BASED)
    if recent_range > prev_range * 1.3:
        strength = cap(4.5 + (recent_range / (prev_range + 1e-9)))
        return MarketRegime(
            state="EARLY_TREND",
            mode="TREND_DAY",
            strength=strength,
            volatility=vol_norm,
            comment="Range expansion detected"
        )

    # 🔥 STRONG TREND
    if recent_range > prev_range * 1.6:
        strength = cap(6.5 + (recent_range / (prev_range + 1e-9)))
        return MarketRegime(
            state="TRENDING",
            mode="TREND_DAY",
            strength=strength,
            volatility=vol_norm,
            comment="Strong expansion trend"
        )

    # 🧊 COMPRESSION
    if recent_range < prev_range * 0.7:
        strength = cap(2.5 + (prev_range - recent_range))
        return MarketRegime(
            state="COMPRESSION",
            mode="RANGE_DAY",
            strength=strength,
            volatility=vol_norm,
            comment="Low volatility compression"
        )

    # ⚠️ EXHAUSTION
    if recent_range < prev_range * 0.85 and vol_norm < 0.008:
        return MarketRegime(
            state="EXHAUSTION",
            mode="RANGE_DAY",
            strength=3.5,
            volatility=vol_norm,
            comment="Weak follow-through"
        )

    # DEFAULT
    return MarketRegime(
        state="WEAK",
        mode="RANGE_DAY",
        strength=2.0,
        volatility=vol_norm,
        comment="Choppy structure"
    )
