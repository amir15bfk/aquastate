"""SI unit helpers. Every exporter talks SI; display conversion is separate."""
from __future__ import annotations

import math
from typing import Sequence


def km2_to_m2(area_km2: float) -> float:
    return float(area_km2) * 1_000_000.0


def mm_over_km2_to_m3(precip_mm: float, area_km2: float) -> float:
    """1 mm of rain over 1 km² is 1,000 m³."""
    return float(precip_mm) * float(area_km2) * 1_000.0


def m3_to_mm_over_km2(volume_m3: float, area_km2: float) -> float:
    area = float(area_km2)
    if area <= 0:
        return 0.0
    return float(volume_m3) / (area * 1_000.0)


def frustum_delta_volume_m3(
    h1_m: float, h2_m: float, a1_m2: float, a2_m2: float
) -> float:
    """Prismoidal volume between two stage levels; requires dV >= 0."""
    h1, h2 = float(h1_m), float(h2_m)
    a1, a2 = max(0.0, float(a1_m2)), max(0.0, float(a2_m2))
    if h2 < h1:
        raise ValueError("h2 must be greater than or equal to h1")
    return (h2 - h1) / 3.0 * (a1 + a2 + math.sqrt(a1 * a2))


def _attr(point, name: str) -> float:
    if isinstance(point, dict):
        return float(point[name])
    return float(getattr(point, name))


def _normalized(points: Sequence) -> list[tuple[float, float, float]]:
    """Return (elevation, area_m2, volume_m3) sorted and deduped by level."""
    rows: list[tuple[float, float, float]] = []
    for point in sorted(points, key=lambda p: _attr(p, "elevation_m")):
        elevation = _attr(point, "elevation_m")
        area_m2 = km2_to_m2(_attr(point, "area_km2"))
        volume_m3 = _attr(point, "volume_m3")
        if rows and abs(elevation - rows[-1][0]) < 1e-12:
            # Collapse duplicate levels, retaining the larger volume so the
            # monotone table stays physically sensible.
            if volume_m3 >= rows[-1][2]:
                rows[-1] = (elevation, area_m2, volume_m3)
            continue
        rows.append((elevation, area_m2, volume_m3))
    return rows


def level_to_volume_m3(level_m: float, points: Sequence) -> float:
    rows = _normalized(points)
    if not rows:
        return 0.0
    level = float(level_m)
    if level <= rows[0][0]:
        return rows[0][2]
    if level >= rows[-1][0]:
        return rows[-1][2]
    for (h1, _a1, v1), (h2, _a2, v2) in zip(rows, rows[1:]):
        if h1 <= level <= h2:
            if h2 == h1:
                return v2
            fraction = (level - h1) / (h2 - h1)
            return v1 + fraction * (v2 - v1)
    return rows[-1][2]


def volume_to_level_m(volume_m3: float, points: Sequence) -> float:
    rows = _normalized(points)
    if not rows:
        return 0.0
    volume = float(volume_m3)
    if volume <= rows[0][2]:
        return rows[0][0]
    if volume >= rows[-1][2]:
        return rows[-1][0]
    for (h1, _a1, v1), (h2, _a2, v2) in zip(rows, rows[1:]):
        if v1 <= volume <= v2:
            if v2 == v1:
                return h2
            fraction = (volume - v1) / (v2 - v1)
            return h1 + fraction * (h2 - h1)
    return rows[-1][0]


def surface_area_at_volume_m2(volume_m3: float, points: Sequence) -> float:
    rows = _normalized(points)
    if not rows:
        return 0.0
    volume = float(volume_m3)
    if volume <= rows[0][2]:
        return rows[0][1]
    if volume >= rows[-1][2]:
        return rows[-1][1]
    for (_h1, a1, v1), (_h2, a2, v2) in zip(rows, rows[1:]):
        if v1 <= volume <= v2:
            if v2 == v1:
                return a2
            fraction = (volume - v1) / (v2 - v1)
            return a1 + fraction * (a2 - a1)
    return rows[-1][1]
