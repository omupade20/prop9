# strategy/sr_levels.py

"""
Support / Resistance detection using 5-minute candles.

IMPORTANT
---------
This module MUST receive candles from MTFBuilder.
Never use raw 1-minute highs/lows for SR detection.
"""

from typing import List, Dict, Optional, Tuple
from statistics import mean


# =========================================================
# Local extrema detection
# =========================================================

def _find_local_extrema(
    values: List[float],
    window: int = 5
) -> Tuple[List[Tuple[int, float]], List[Tuple[int, float]]]:

    n = len(values)

    maxima = []
    minima = []

    if n < window * 2 + 1:
        return maxima, minima

    half = window // 2

    for i in range(half, n - half):

        center = values[i]

        left = values[i - half:i]
        right = values[i + 1:i + 1 + half]

        if all(center > x for x in left + right):
            maxima.append((i, center))

        if all(center < x for x in left + right):
            minima.append((i, center))

    return maxima, minima


# =========================================================
# Cluster nearby levels
# =========================================================

def _cluster_levels(
    peaks: List[float],
    tol_pct: float = 0.004
) -> List[Dict]:

    if not peaks:
        return []

    peaks = sorted(peaks)

    clusters = []
    current_cluster = [peaks[0]]

    for price in peaks[1:]:

        avg = mean(current_cluster)
        tolerance = avg * tol_pct

        if abs(price - avg) <= tolerance:
            current_cluster.append(price)
        else:
            clusters.append(current_cluster)
            current_cluster = [price]

    clusters.append(current_cluster)

    levels = []

    for cluster in clusters:

        level = mean(cluster)

        levels.append({
            "level": round(level, 6),
            "count": len(cluster),
            "strength": min(len(cluster), 4)
        })

    return levels


# =========================================================
# Main SR calculation (5m candles only)
# =========================================================

def compute_sr_levels(
    candles_5m: List[Dict],
    lookback: int = 120,
    extrema_window: int = 5,
    cluster_tol_pct: float = 0.004,
    max_levels: int = 3
) -> Dict[str, List[Dict]]:

    """
    Compute support and resistance using 5-minute candles.
    """

    if not candles_5m:
        return {"supports": [], "resistances": []}

    candles = candles_5m[-lookback:]

    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]

    max_extrema, _ = _find_local_extrema(highs, window=extrema_window)
    _, min_extrema = _find_local_extrema(lows, window=extrema_window)

    resistance_prices = [price for _, price in max_extrema]
    support_prices = [price for _, price in min_extrema]

    resist_clusters = _cluster_levels(resistance_prices, tol_pct=cluster_tol_pct)
    support_clusters = _cluster_levels(support_prices, tol_pct=cluster_tol_pct)

    # sort by strength and proximity
    resist_sorted = sorted(
        resist_clusters,
        key=lambda x: (-x["strength"], -x["level"])
    )[:max_levels]

    support_sorted = sorted(
        support_clusters,
        key=lambda x: (-x["strength"], x["level"])
    )[:max_levels]

    return {
        "supports": support_sorted,
        "resistances": resist_sorted
    }


# =========================================================
# Nearest SR to price
# =========================================================

def get_nearest_sr(
    price: float,
    sr_levels: Dict[str, List[Dict]],
    max_search_pct: float = 0.03
) -> Optional[Dict]:

    supports = sr_levels.get("supports", [])
    resistances = sr_levels.get("resistances", [])

    best = None
    best_dist = float("inf")

    # check supports
    for s in supports:

        level = s["level"]
        dist = abs(price - level) / max(level, 1e-9)

        if dist < best_dist:
            best_dist = dist
            best = {
                "type": "support",
                "level": level,
                "dist_pct": dist,
                "strength": s.get("strength", 1)
            }

    # check resistances
    for r in resistances:

        level = r["level"]
        dist = abs(level - price) / max(price, 1e-9)

        if dist < best_dist:
            best_dist = dist
            best = {
                "type": "resistance",
                "level": level,
                "dist_pct": dist,
                "strength": r.get("strength", 1)
            }

    if best and best["dist_pct"] <= max_search_pct:
        return best

    return None


# =========================================================
# SR location score
# =========================================================

def sr_location_score(
    price: float,
    nearest_sr: Optional[Dict],
    direction: str,
    proximity_threshold: float = 0.02
) -> float:

    if nearest_sr is None:
        return 0.0

    dist = nearest_sr.get("dist_pct")

    if dist is None or dist > proximity_threshold:
        return 0.0

    closeness = (proximity_threshold - dist) / proximity_threshold

    strength = nearest_sr.get("strength", 1)
    strength_factor = min(1.5, 0.6 + 0.2 * strength)

    sr_type = nearest_sr["type"]

    if direction == "LONG":
        sign = 1 if sr_type == "support" else -1
    elif direction == "SHORT":
        sign = 1 if sr_type == "resistance" else -1
    else:
        sign = 0

    score = sign * closeness * strength_factor

    return round(max(min(score, 1.0), -1.0), 3)
    
