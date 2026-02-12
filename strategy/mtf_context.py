# strategy/mtf_context.py

from dataclasses import dataclass
from typing import List, Optional


# =========================
# MTF Context Output
# =========================

@dataclass
class MTFContext:
    direction: str        # BULLISH / BEARISH / NEUTRAL
    strength: float       # 0 – 2 (raw strength)
    confidence: str       # HIGH / MEDIUM / LOW
    conflict: bool        # True if 15m & 30m disagree
    comment: str


# =========================
# Candle Helpers
# =========================

def _is_bullish(candle: dict) -> bool:
    return candle and candle.get("close", 0) > candle.get("open", 0)


def _is_bearish(candle: dict) -> bool:
    return candle and candle.get("close", 0) < candle.get("open", 0)


# =========================
# Persistence Logic
# =========================

def _persistence_score(history: List[dict]) -> float:
    """
    Persistence bonus based on last 3 candles.
    Returns 0.0 / 0.2 / 0.4
    """
    if not history or len(history) < 2:
        return 0.0

    last = history[-3:]
    bull = sum(1 for c in last if _is_bullish(c))
    bear = sum(1 for c in last if _is_bearish(c))

    if bull == 3 or bear == 3:
        return 0.6
    if bull >= 2 or bear >= 2:
        return 0.3
    return 0.0


# =========================
# Main Analyzer (NEW TF LOGIC)
# =========================

def analyze_mtf(
    candle_15m: Optional[dict],
    candle_30m: Optional[dict],
    history_15m: Optional[List[dict]] = None,
    history_30m: Optional[List[dict]] = None
) -> MTFContext:
    """
    Multi-Timeframe Context Analyzer (UPDATED FOR 15m + 30m SYSTEM).

    Purpose:
    - Decide higher-timeframe DIRECTION
    - Measure CONFIDENCE
    - Detect CONFLICT explicitly

    This output IS MEANT to be used as a DIRECTIONAL GATE upstream.
    """

    score = 0.0
    comments = []
    conflict = False

    # ---------------------
    # Base Direction Votes
    # ---------------------

    if candle_15m:
        if _is_bullish(candle_15m):
            score += 0.8
            comments.append("15m bullish")
        elif _is_bearish(candle_15m):
            score -= 0.8
            comments.append("15m bearish")

    if candle_30m:
        if _is_bullish(candle_30m):
            score += 1.4   # 30m has highest authority
            comments.append("30m bullish")
        elif _is_bearish(candle_30m):
            score -= 1.4
            comments.append("30m bearish")

    # ---------------------
    # Conflict Detection
    # ---------------------

    if candle_15m and candle_30m:
        if (_is_bullish(candle_15m) and _is_bearish(candle_30m)) or \
           (_is_bearish(candle_15m) and _is_bullish(candle_30m)):
            conflict = True
            score *= 0.7
            comments.append("15m/30m conflict")

    # ---------------------
    # Persistence Bonus
    # ---------------------

    if history_15m:
        p15 = _persistence_score(history_15m)
        if p15:
            score += p15
            comments.append(f"15m persistence +{p15}")

    if history_30m:
        p30 = _persistence_score(history_30m)
        if p30:
            score += p30
            comments.append(f"30m persistence +{p30}")

    # ---------------------
    # Final Direction
    # ---------------------

    if abs(score) < 0.4:
        direction = "NEUTRAL"
    elif score > 0:
        direction = "BULLISH"
    else:
        direction = "BEARISH"

    strength = round(min(abs(score), 2.0), 2)

    # ---------------------
    # Confidence Buckets
    # ---------------------

    if strength >= 1.1 and not conflict:
        confidence = "HIGH"
    elif strength >= 0.6:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    comment = " | ".join(comments) if comments else "No HTF structure"

    return MTFContext(
        direction=direction,
        strength=strength,
        confidence=confidence,
        conflict=conflict,
        comment=comment
    )
