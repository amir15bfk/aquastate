"""Small, dependency-free statistics used by the index.

No SciPy: the methods are short enough to audit and test directly.
"""
from __future__ import annotations

import math
from statistics import median


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    if value is None or math.isnan(value) or math.isinf(value):
        return low
    return max(low, min(high, value))


def percentile_rank(history: list[float], value: float | None) -> float | None:
    """Percent of historical values at or below ``value`` (0-100)."""
    clean = [float(x) for x in history if x is not None and not math.isnan(float(x))]
    if not clean or value is None:
        return None
    at_or_below = sum(1 for x in clean if x <= value)
    return 100.0 * at_or_below / len(clean)


def sen_slope(points: list[tuple[float, float]]) -> float | None:
    """Theil–Sen slope, y units per x unit."""
    clean = [(float(x), float(y)) for x, y in points if x is not None and y is not None]
    if len(clean) < 3:
        return None
    slopes = []
    for i in range(len(clean)):
        for j in range(i + 1, len(clean)):
            dx = clean[j][0] - clean[i][0]
            if dx:
                slopes.append((clean[j][1] - clean[i][1]) / dx)
    if not slopes:
        return None
    return median(slopes)


def mann_kendall(points: list[tuple[float, float]]) -> dict:
    """Two-sided Mann–Kendall trend test for serially ordered annual values.

    Returns a neutral, low-confidence result for fewer than 8 observations,
    which is the normal-approximation guard used by the index.
    """
    values = [float(y) for _, y in sorted(points, key=lambda pair: pair[0]) if y is not None]
    n = len(values)
    if n < 8:
        return {
            "n": n,
            "s": None,
            "variance": None,
            "z": None,
            "p": None,
            "significant": False,
            "note": "fewer than 8 annual values",
        }
    s = 0
    for i in range(n - 1):
        for j in range(i + 1, n):
            s += (values[j] > values[i]) - (values[j] < values[i])
    # Tie correction.
    counts: dict[float, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    tie_term = sum(t * (t - 1) * (2 * t + 5) for t in counts.values() if t > 1)
    variance = (n * (n - 1) * (2 * n + 5) - tie_term) / 18.0
    if variance <= 0:
        z = 0.0
        p = 1.0
    else:
        if s > 0:
            z = (s - 1) / math.sqrt(variance)
        elif s < 0:
            z = (s + 1) / math.sqrt(variance)
        else:
            z = 0.0
        p = 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(z) / math.sqrt(2.0))))
        p = max(0.0, min(1.0, p))
    return {
        "n": n,
        "s": s,
        "variance": round(variance, 3),
        "z": round(z, 4),
        "p": round(p, 6),
        "significant": p < 0.05,
        "note": "",
    }


def trend_summary(points: list[tuple[float, float]], divisor: float = 1.0) -> dict:
    """Combine Sen slope and MK significance for the trend sub-index."""
    slope = sen_slope(points)
    mk = mann_kendall(points)
    if slope is None:
        return {
            "slope_per_year": None,
            "slope_pct_per_year": None,
            "p": None,
            "significant": False,
            "score": 50.0,
            "confidence": 0.2,
            "n": len(points),
        }
    slope_pct = slope / divisor * 100.0 if divisor else slope
    raw = clamp(0.5 + slope_pct / 4.0, 0.0, 1.0) * 100.0
    p = mk["p"] if mk["p"] is not None else 0.5
    score = 50.0 + (raw - 50.0) * (1.0 - p)
    return {
        "slope_per_year": round(slope, 4),
        "slope_pct_per_year": round(slope_pct, 4),
        "p": mk["p"],
        "significant": mk["significant"],
        "score": round(clamp(score), 2),
        "confidence": 0.8 if mk["p"] is not None else 0.35,
        "n": mk["n"],
        "mk": mk,
    }


def normalise_weights(raw: dict[str, float]) -> dict[str, float]:
    total = sum(max(0.0, value) for value in raw.values())
    if total <= 0:
        return {key: 0.0 for key in raw}
    return {key: max(0.0, value) / total for key, value in raw.items()}
