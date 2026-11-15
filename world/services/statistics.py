"""World-layer statistics: mid-rank percentiles, SPI helpers, PET, trends."""
from __future__ import annotations

import math
from statistics import median
from typing import Iterable, Sequence

from hydro.services.statistics import clamp, mann_kendall, sen_slope, trend_summary


def clean(values: Iterable[float | None]) -> list[float]:
    out: list[float] = []
    for value in values:
        if value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            out.append(number)
    return out


def mid_rank_percentile(
    history: Sequence[float | None], value: float | None, *, higher_is_better: bool = True
) -> dict:
    """Mid-rank Weibull plotting position, P = 100·(b + t/2 + 1)/(N + 2).

    Unlike a simple "at or below" count, the mid-rank convention gives an
    unbiased 50 for a symmetric sample and treats ties explicitly.
    """
    values = clean(history)
    if value is None or not values:
        return {
            "score": 50.0,
            "percentile": 50.0,
            "n": len(values),
            "confidence": 0.0,
            "available": False,
        }
    current = float(value)
    if all(v == values[0] for v in values):
        base = 3.571 if current < values[0] else (50.0 if current == values[0] else 96.429)
        score = base if higher_is_better else 100.0 - base
        return {
            "score": round(score, 2),
            "percentile": round(base, 2),
            "n": len(values),
            "confidence": 0.5,
            "available": True,
        }
    below = sum(1 for v in values if v < current)
    ties = sum(1 for v in values if v == current)
    p = 100.0 * (below + ties / 2.0 + 1.0) / (len(values) + 2.0)
    score = p if higher_is_better else 100.0 - p
    return {
        "score": round(score, 2),
        "percentile": round(p, 2),
        "n": len(values),
        "confidence": min(1.0, len(values) / 12.0),
        "available": True,
    }


def rolling_sums(values: Sequence[float | None], window: int) -> list[float | None]:
    """Cumulative window sums on an ordered monthly series."""
    out: list[float | None] = []
    for index in range(len(values)):
        if index + 1 < window:
            out.append(None)
            continue
        chunk = clean(values[index + 1 - window : index + 1])
        if len(chunk) != window:
            out.append(None)
        else:
            out.append(sum(chunk))
    return out


def same_month_history(
    monthly: Sequence[dict],
    month_index: int,
    field: str,
    years: int = 10,
    before_year: int | None = None,
) -> list[float]:
    """Values for the same calendar month over the prior baseline years."""
    rows = [
        row
        for row in monthly
        if row["month"].month == month_index
        and (before_year is None or row["month"].year < before_year)
    ]
    values = clean(row.get(field) for row in rows)
    return values[-years:]


def annual_sums(monthly: Sequence[dict], field: str) -> list[tuple[int, float]]:
    buckets: dict[int, list[float]] = {}
    for row in monthly:
        value = row.get(field)
        if value is None:
            continue
        buckets.setdefault(row["month"].year, []).append(float(value))
    return [(year, sum(values)) for year, values in sorted(buckets.items()) if len(values) >= 10]


def annual_means(monthly: Sequence[dict], field: str) -> list[tuple[int, float]]:
    buckets: dict[int, list[float]] = {}
    for row in monthly:
        value = row.get(field)
        if value is None:
            continue
        buckets.setdefault(row["month"].year, []).append(float(value))
    return [(year, sum(values) / len(values)) for year, values in sorted(buckets.items()) if values]


def _extraterrestrial_radiation(lat_deg: float, day_of_year: int) -> float:
    """FAO-56 Ra in MJ m-2 day-1."""
    phi = math.radians(max(-66.0, min(66.0, lat_deg)))
    dr = 1.0 + 0.033 * math.cos(2.0 * math.pi * day_of_year / 365.0)
    decl = 0.409 * math.sin(2.0 * math.pi * day_of_year / 365.0 - 1.39)
    arg = max(-1.0, min(1.0, -math.tan(phi) * math.tan(decl)))
    omega = math.acos(arg)
    return (
        (24.0 * 60.0 / math.pi)
        * 0.0820
        * dr
        * (omega * math.sin(phi) * math.sin(decl) + math.cos(phi) * math.cos(decl) * math.sin(omega))
    )


def hargreaves_pet_mm_day(
    lat: float, day_of_year: int, tmax: float | None, tmin: float | None, tmean: float | None
) -> float | None:
    if tmax is None or tmin is None:
        return None
    mean = tmean if tmean is not None else (tmax + tmin) / 2.0
    ra = _extraterrestrial_radiation(lat, day_of_year)
    # 0.408 converts MJ m-2 day-1 to mm day-1.
    pet = 0.0023 * 0.408 * ra * (mean + 17.8) * math.sqrt(max(0.0, tmax - tmin))
    return max(0.0, round(pet, 3))


def annual_pet(monthly: Sequence[dict], lat: float) -> list[tuple[int, float]]:
    buckets: dict[int, list[float]] = {}
    for row in monthly:
        month = row["month"]
        day = month.replace(day=15)
        pet = hargreaves_pet_mm_day(
            lat, day.timetuple().tm_yday, row.get("tmax"), row.get("tmin"), row.get("tmean")
        )
        if pet is None:
            continue
        days = 30 if month.month in (4, 6, 9, 11) else (28 if month.month == 2 else 31)
        buckets.setdefault(month.year, []).append(pet * days)
    return [(year, sum(values)) for year, values in sorted(buckets.items()) if len(values) >= 10]


def trend_score(points: Sequence[tuple[int, float]], *, divisor: float = 1.0) -> dict:
    return trend_summary([(float(x), float(y)) for x, y in points], divisor=divisor)


def median_or(values: Sequence[float], default: float) -> float:
    values = clean(values)
    return float(median(values)) if values else default
