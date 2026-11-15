"""Country point-in-polygon lookup for events and map clicks."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from django.conf import settings


def _point_in_ring(lon: float, lat: float, ring: list) -> bool:
    inside = False
    if not ring:
        return False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def _point_in_polygon(lon: float, lat: float, coords: list) -> bool:
    if not coords:
        return False
    # Polygon: [outer_ring, hole, hole...]
    if isinstance(coords[0][0], (int, float)):
        return _point_in_ring(lon, lat, coords)
    if _point_in_ring(lon, lat, coords[0]):
        for hole in coords[1:]:
            if _point_in_ring(lon, lat, hole):
                return False
        return True
    return False


@lru_cache(maxsize=1)
def _features():
    path = Path(settings.WORLD_GEOJSON)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        feature
        for feature in data.get("features", [])
        if feature.get("properties", {}).get("kind") == "polygon"
    ]


def country_for_point(lat: float, lon: float) -> str | None:
    for feature in _features():
        geometry = feature.get("geometry") or {}
        kind = geometry.get("type")
        coords = geometry.get("coordinates") or []
        if kind == "Polygon" and _point_in_polygon(lon, lat, coords):
            return feature["properties"]["iso2"]
        if kind == "MultiPolygon":
            for polygon in coords:
                if _point_in_polygon(lon, lat, polygon):
                    return feature["properties"]["iso2"]
    return None
