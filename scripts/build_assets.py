"""Build offline assets: country gazetteer, country outlines, fonts, Leaflet.

Run once from the project root:
    python scripts/build_assets.py

The app itself never needs this script at runtime; it keeps the MVP usable
offline after a first network-enabled setup.
"""
from __future__ import annotations

import json
import math
import pathlib
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "hydro" / "data"
GEO = ROOT / "hydro" / "static" / "hydro" / "geo"
FONTS = ROOT / "hydro" / "static" / "hydro" / "fonts"
VENDOR = ROOT / "hydro" / "static" / "hydro" / "vendor"

UA = {"User-Agent": "AquaStateMVP/1.0 (NASA Space Apps challenge demo)"}
NE_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/"
    "geojson/ne_110m_admin_0_countries.geojson"
)
ISO_URL = "https://raw.githubusercontent.com/mledoze/countries/master/countries.json"
POP_URL = (
    "https://api.worldbank.org/v2/country/all/indicator/SP.POP.TOTL"
    "?format=json&per_page=400&date=2024"
)

FONT_FILES = {
    "ibm-plex-sans-400.woff2": "https://cdn.jsdelivr.net/npm/@fontsource/ibm-plex-sans/files/ibm-plex-sans-latin-400-normal.woff2",
    "ibm-plex-sans-500.woff2": "https://cdn.jsdelivr.net/npm/@fontsource/ibm-plex-sans/files/ibm-plex-sans-latin-500-normal.woff2",
    "ibm-plex-sans-600.woff2": "https://cdn.jsdelivr.net/npm/@fontsource/ibm-plex-sans/files/ibm-plex-sans-latin-600-normal.woff2",
    "ibm-plex-mono-400.woff2": "https://cdn.jsdelivr.net/npm/@fontsource/ibm-plex-mono/files/ibm-plex-mono-latin-400-normal.woff2",
    "ibm-plex-mono-500.woff2": "https://cdn.jsdelivr.net/npm/@fontsource/ibm-plex-mono/files/ibm-plex-mono-latin-500-normal.woff2",
}

VENDOR_FILES = {
    "leaflet.css": "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css",
    "leaflet.js": "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js",
}


def fetch(url: str, timeout: int = 90) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def rings(geometry: dict):
    if geometry["type"] == "Polygon":
        yield from geometry["coordinates"]
    elif geometry["type"] == "MultiPolygon":
        for polygon in geometry["coordinates"]:
            yield from polygon


def _ring_area(ring) -> float:
    area = 0.0
    for index in range(len(ring) - 1):
        x1, y1 = ring[index][:2]
        x2, y2 = ring[index + 1][:2]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0


def bbox(geometry: dict) -> list[float]:
    """Bounding box of the main landmass.

    For a MultiPolygon, use the largest polygon when it dominates the total
    area (France, USA), otherwise include all parts (Indonesia, NZ).
    """
    if geometry["type"] == "Polygon":
        polygons = [geometry["coordinates"]]
    else:
        polygons = geometry["coordinates"]
    areas = [_ring_area(polygon[0]) for polygon in polygons if polygon and polygon[0]]
    if not areas:
        return [0, 0, 0, 0]
    largest = max(areas)
    total = sum(areas)
    selected = (
        [polygons[areas.index(largest)]]
        if total > 0 and largest / total >= 0.65
        else polygons
    )
    xs, ys = [], []
    for polygon in selected:
        for ring in polygon:
            for lon, lat in ring:
                xs.append(lon)
                ys.append(lat)
    return [round(min(xs), 4), round(min(ys), 4), round(max(xs), 4), round(max(ys), 4)]


def approx_bbox(lat: float, lon: float, area_km2: float) -> list[float]:
    """A rough box used only when Natural Earth has no outline (small islands)."""
    side = max(0.12, math.sqrt(max(area_km2, 1.0)) / 111.0 / 2.0)
    return [round(lon - side, 4), round(lat - side, 4), round(lon + side, 4), round(lat + side, 4)]


def key(value: str) -> str:
    return (value or "").strip().lower()


def main() -> None:
    for directory in (DATA, GEO, FONTS, VENDOR):
        directory.mkdir(parents=True, exist_ok=True)

    iso = json.loads(fetch(ISO_URL))
    ne = json.loads(fetch(NE_URL))

    # World Bank population (latest, 2024). Fall back to Natural Earth POP_EST.
    population_by_iso3: dict[str, int] = {}
    try:
        wb = json.loads(fetch(POP_URL))
        for row in wb[1]:
            value = row.get("value")
            code = (row.get("countryiso3code") or "").upper()
            if value and code:
                population_by_iso3[code] = int(value)
        print(f"population: {len(population_by_iso3)} World Bank entries")
    except Exception as exc:  # pragma: no cover - network dependent asset step
        print(f"WARN population fetch failed, using Natural Earth POP_EST: {exc}")

    ne_by_iso = {}
    ne_by_name = {}
    for feature in ne["features"]:
        props = feature["properties"]
        iso2 = (props.get("ISO_A2") or "").strip()
        if iso2 and iso2 not in {"-99", "AQ"}:
            ne_by_iso[iso2] = feature
        for label in (props.get("NAME"), props.get("ADMIN"), props.get("NAME_LONG")):
            if label:
                ne_by_name[key(label)] = feature

    outlines = {"type": "FeatureCollection", "features": []}
    countries = []
    used_outline_isos: set[str] = set()
    for item in iso:
        iso2 = (item.get("cca2") or "").strip()
        iso3 = (item.get("cca3") or "").strip()
        if not iso2:
            continue
        name = item["name"]["common"]
        official = item["name"].get("official") or name
        lat, lon = (item.get("latlng") or [0, 0])[:2]
        area = float(item.get("area") or 0)
        feature = (
            ne_by_iso.get(iso2)
            or ne_by_name.get(key(name))
            or ne_by_name.get(key(official))
        )
        geometry = feature["geometry"] if feature else None
        box = bbox(geometry) if geometry else approx_bbox(lat, lon, area)
        ne_props = feature["properties"] if feature else {}
        population = (
            population_by_iso3.get(iso3)
            or int(ne_props.get("POP_EST") or 0)
            or 0
        )
        countries.append(
            {
                "iso2": iso2,
                "iso3": iso3,
                "name": name,
                "official": official,
                "continent": ne_props.get("CONTINENT") or item.get("region") or "—",
                "region": ne_props.get("REGION_UN") or item.get("region") or "—",
                "subregion": ne_props.get("SUBREGION") or item.get("subregion") or "—",
                "population": int(population),
                "area_km2": round(area, 1),
                "lat": round(float(lat), 4),
                "lon": round(float(lon), 4),
                "bbox": box,
                "has_outline": geometry is not None,
            }
        )
        if geometry is not None and iso2 not in used_outline_isos:
            used_outline_isos.add(iso2)
            outlines["features"].append(
                {
                    "type": "Feature",
                    "properties": {"iso2": iso2, "name": name},
                    "geometry": geometry,
                }
            )

    countries.sort(key=lambda c: c["name"])
    (DATA / "countries.json").write_text(
        json.dumps(countries, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    (GEO / "countries-110m.geojson").write_text(
        json.dumps(outlines, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    print(f"countries: {len(countries)} -> world gazetteer")
    print(f"outlines: {len(outlines['features'])} -> static geojson")
    print(f"with population: {sum(1 for c in countries if c['population'] > 0)}")

    for name, url in {**FONT_FILES, **VENDOR_FILES}.items():
        target = (FONTS if name.endswith(".woff2") else VENDOR) / name
        if target.exists() and target.stat().st_size > 1000:
            print(f"keep {name} ({target.stat().st_size} bytes)")
            continue
        try:
            payload = fetch(url, timeout=45)
            target.write_bytes(payload)
            print(f"fetched {name} ({len(payload)} bytes)")
        except Exception as exc:  # pragma: no cover - network dependent asset step
            print(f"WARN could not fetch {name}: {exc}")


if __name__ == "__main__":
    main()
