"""Deterministic statistics: mid-rank Weibull percentiles, SPI, OLS."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class PercentileResult:
    score: float
    rank: float
    n: int
    confidence: float
    data_status: str
    available: bool = True


def _finite(values: Sequence[float]) -> list[float]:
    out: list[float] = []
    for value in values:
        if value is None:
            continue
        as_float = float(value)
        if math.isfinite(as_float):
            out.append(as_float)
    return out


def percentile_score(
    values: Sequence[float],
    current: float,
    *,
    higher_is_better: bool = True,
) -> PercentileResult:
    """Mid-rank Weibull plotting position, P = 100·(b + t/2 + 1)/(N + 2)."""
    clean = _finite(values)
    n = len(clean)
    if n == 0 or current is None or not math.isfinite(float(current)):
        return PercentileResult(
            score=50.0, rank=0.5, n=0, confidence=0.0, data_status="NO_DATA",
            available=False,
        )

    current = float(current)
    if all(value == clean[0] for value in clean):
        base = 3.571 if current < clean[0] else (50.0 if current == clean[0] else 96.429)
        rank = base / 100.0
        score = base if higher_is_better else 100.0 - base
        return PercentileResult(
            score=score, rank=rank, n=n, confidence=0.5, data_status="OK"
        )

    below = sum(1 for value in clean if value < current)
    ties = sum(1 for value in clean if value == current)
    rank_pct = 100.0 * (below + ties / 2.0 + 1.0) / (n + 2.0)
    score = rank_pct if higher_is_better else 100.0 - rank_pct
    return PercentileResult(
        score=score,
        rank=rank_pct / 100.0,
        n=n,
        confidence=min(1.0, n / 26.0),
        data_status="OK",
    )


def week_bin(day_of_year: int) -> int:
    """Fixed 52-bin calendar from 1 January; bin 52 absorbs days 358–366."""
    doy = max(1, min(366, int(day_of_year)))
    return min(52, (doy - 1) // 7 + 1)


def empirical_spi(values: Sequence[float], current: float) -> PercentileResult:
    """Empirical SPI percentile of the raw accumulation; apply it once."""
    return percentile_score(values, current, higher_is_better=True)


def ols_slope(x: Sequence[float], y: Sequence[float]) -> tuple[float, float, float]:
    """Ordinary least squares returning (slope, intercept, r²)."""
    pairs = [
        (float(xi), float(yi))
        for xi, yi in zip(x, y)
        if xi is not None
        and yi is not None
        and math.isfinite(float(xi))
        and math.isfinite(float(yi))
    ]
    n = len(pairs)
    if n < 2:
        return 0.0, 0.0, 0.0
    mean_x = sum(p[0] for p in pairs) / n
    mean_y = sum(p[1] for p in pairs) / n
    sxx = sum((p[0] - mean_x) ** 2 for p in pairs)
    sxy = sum((p[0] - mean_x) * (p[1] - mean_y) for p in pairs)
    if sxx == 0:
        return 0.0, mean_y, 0.0
    slope = sxy / sxx
    intercept = mean_y - slope * mean_x
    ss_tot = sum((p[1] - mean_y) ** 2 for p in pairs)
    ss_res = sum((p[1] - (intercept + slope * p[0])) ** 2 for p in pairs)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return slope, intercept, r2
