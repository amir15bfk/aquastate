"""First-level administrative regions (ADM1) for any country, with live environmental layers.

Generalises the Algeria wilaya pipeline to the whole world. Nothing is drawn or invented:

* Boundaries: geoBoundaries ADM1 (gbOpen, falling back to gbHumanitarian), downloaded on demand
  per country and cached in world/data/geo_admin1/<ISO3>.geojson. Source, licence and year are kept
  per country and shown as attribution.
* Layers: every region is evaluated with the same deterministic WCRI-2.0 mathematics as the country
  index (``compute_country``), fed by the same live keyless sources sampled at an interior point:
  NASA POWER / MERRA-2 monthly, Open-Meteo 92+16-day window, Open-Meteo GloFAS discharge, NASA EONET.

Layers (0-100): water_stress, drought, flood, fire (pressures) and vegetation (soil-moisture PROXY).
"""
from __future__ import annotations

import json
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from functools import lru_cache
from pathlib import Path

import requests
from django.conf import settings

from hydro.services.statistics import clamp
from world.services import sources
from world.services.country_index import compute_country
from world.services.statistics import mid_rank_percentile, rolling_sums, same_month_history

GEO_DIR = Path(settings.BASE_DIR) / "world" / "data" / "geo_admin1"
GEO_DIR.mkdir(parents=True, exist_ok=True)
GEO_VERSION = 2  # bump to rebuild cached country files after a processing change
UA = {"User-Agent": "AquaStateWorld/2.0 (NASA Space Apps challenge; local demo)"}

LAYERS = {
    "water_stress": {
        "label": "Water stress", "direction": "pressure", "short": "Rain vs evaporative demand", "history": False,
        "detail": "Climatic water stress: 100 − aridity score, where aridity = annual rain ÷ potential evapotranspiration (NASA POWER, Hargreaves). High means the climate demands far more water than it supplies.",
        "source": "NASA POWER / MERRA-2 monthly",
    },
    "drought": {
        "label": "Drought", "direction": "pressure", "short": "Rain and soil deficit vs normal", "history": True,
        "detail": "Drought pressure: 100 − (0.40·SPI-3 + 0.25·SPI-12 + 0.20·soil-moisture percentile + 0.15·dry-spell score). Past months omit the dry-spell term, which needs daily data.",
        "source": "NASA POWER monthly + Open-Meteo 92-day window",
    },
    "flood": {
        "label": "Flood risk", "direction": "pressure", "short": "Forecast river discharge vs baseline", "history": False,
        "detail": "Flood pressure: 0.75 × GloFAS forecast-discharge pressure + 0.25 × active EONET flood events in the region. Arid regions often have no modelled river at the sample point.",
        "source": "Open-Meteo GloFAS + NASA EONET",
    },
    "fire": {
        "label": "Forest fire risk", "direction": "pressure", "short": "Fire weather coupled to drought", "history": False,
        "detail": "Wildfire pressure: 0.65 × fire-weather pressure (VPD, wind, dry spell, heat) + 0.20 × drought coupling + 0.15 × active EONET wildfires. It is fire weather, not an ignition forecast.",
        "source": "Open-Meteo fire weather + NASA EONET",
    },
    "vegetation": {
        "label": "Vegetation moisture", "direction": "health", "short": "Proxy · root-zone soil wetness", "history": True,
        "detail": "Proxy for vegetation health: percentile of root-zone soil wetness (NASA POWER GWETROOT) against the same month of previous years. 100 = wettest on record for the month. Not a satellite greenness (NDVI) measurement.",
        "source": "NASA POWER / MERRA-2 monthly (GWETROOT)",
    },
}
HISTORY_MONTHS = 12

# What a first-level region is called, where the common English term is well established.
TERMS = {
    "DZ": ("wilaya", "wilayas"), "MR": ("wilaya", "wilayas"), "US": ("state", "states"), "IN": ("state", "states"),
    "BR": ("state", "states"), "MX": ("state", "states"), "AU": ("state or territory", "states and territories"),
    "DE": ("state", "states"), "NG": ("state", "states"), "MY": ("state", "states"), "SD": ("state", "states"),
    "CA": ("province or territory", "provinces and territories"), "CN": ("province", "provinces"), "ZA": ("province", "provinces"),
    "AR": ("province", "provinces"), "TR": ("province", "provinces"), "IR": ("province", "provinces"), "PK": ("province", "provinces"),
    "TH": ("province", "provinces"), "VN": ("province", "provinces"), "ES": ("autonomous community", "autonomous communities"),
    "FR": ("region", "regions"), "IT": ("region", "regions"), "MA": ("region", "regions"), "TN": ("governorate", "governorates"),
    "EG": ("governorate", "governorates"), "JO": ("governorate", "governorates"), "IQ": ("governorate", "governorates"),
    "SY": ("governorate", "governorates"), "YE": ("governorate", "governorates"), "LB": ("governorate", "governorates"),
    "OM": ("governorate", "governorates"), "KW": ("governorate", "governorates"), "BH": ("governorate", "governorates"),
    "SA": ("province", "provinces"), "LY": ("district", "districts"), "RU": ("federal subject", "federal subjects"),
    "JP": ("prefecture", "prefectures"), "KE": ("county", "counties"), "GB": ("country", "countries"),
}


class NoBoundaries(Exception):
    """geoBoundaries publishes no ADM1 layer for this country."""


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _iso_maps() -> tuple[dict, dict]:
    from hydro.services.gazetteer import all_countries

    rows = all_countries()
    to3 = {r["iso2"].upper(): (r.get("iso3") or "").upper() for r in rows}
    to2 = {v: k for k, v in to3.items() if v}
    return to3, to2


def iso3_for(iso2: str) -> str:
    return _iso_maps()[0].get((iso2 or "").upper(), "")


@lru_cache(maxsize=1)
def catalog() -> dict[str, dict]:
    """{ISO2: meta} for every country with an ADM1 release (gbOpen preferred, gbHumanitarian fallback)."""
    to2 = _iso_maps()[1]
    out: dict[str, dict] = {}
    for release in ("gbHumanitarian", "gbOpen"):  # gbOpen last so it wins
        path = GEO_DIR / f"catalog_{release}.json"
        if not path.exists():
            continue
        for row in json.loads(path.read_text(encoding="utf-8")):
            iso2 = to2.get(row.get("boundaryISO", "").upper())
            if not iso2 or not row.get("simplifiedGeometryGeoJSON"):
                continue
            out[iso2] = {
                "iso2": iso2,
                "iso3": row["boundaryISO"].upper(),
                "release": release,
                "units": int(row.get("admUnitCount") or 0),
                "source": row.get("boundarySource") or "",
                "license": row.get("boundaryLicense") or "",
                "year": row.get("boundaryYearRepresented") or "",
                "url": row["simplifiedGeometryGeoJSON"],
            }
    return out


def term(iso2: str) -> tuple[str, str]:
    return TERMS.get((iso2 or "").upper(), ("region", "regions"))


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------
def _rdp(points, eps):
    if len(points) < 4:
        return points
    (x1, y1), (x2, y2) = points[0], points[-1]
    dx, dy = x2 - x1, y2 - y1
    norm = math.hypot(dx, dy) or 1e-12
    dmax, idx = 0.0, 0
    for i in range(1, len(points) - 1):
        x0, y0 = points[i]
        d = abs(dy * x0 - dx * y0 + x2 * y1 - y2 * x1) / norm
        if d > dmax:
            dmax, idx = d, i
    if dmax > eps:
        return _rdp(points[: idx + 1], eps)[:-1] + _rdp(points[idx:], eps)
    return [points[0], points[-1]]


def _rdp_ring(ring, eps):
    """Douglas-Peucker for a closed ring (split at the farthest vertex first so it cannot collapse)."""
    if len(ring) < 8:
        return ring
    x0, y0 = ring[0]
    k = max(range(len(ring)), key=lambda i: (ring[i][0] - x0) ** 2 + (ring[i][1] - y0) ** 2)
    out = _rdp(ring[: k + 1], eps)[:-1] + _rdp(ring[k:], eps)
    return out if len(out) >= 4 else ring


def _polygons(geom: dict) -> list[list]:
    if geom["type"] == "Polygon":
        return [geom["coordinates"]]
    if geom["type"] == "MultiPolygon":
        return list(geom["coordinates"])
    return []


def _in_ring(x: float, y: float, ring: list) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi + 1e-15) + xi:
            inside = not inside
        j = i
    return inside


def _in_polygon(x, y, poly) -> bool:
    return _in_ring(x, y, poly[0]) and not any(_in_ring(x, y, hole) for hole in poly[1:])


def _ring_area_km2(ring) -> float:
    lat0 = sum(p[1] for p in ring) / len(ring)
    kx, ky = 111.32 * math.cos(math.radians(lat0)), 110.57
    s = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        s += (x1 * kx) * (y2 * ky) - (x2 * kx) * (y1 * ky)
    return abs(s) / 2


def _label_point(poly) -> list[float]:
    ring = poly[0]
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    sample = ring[:: max(1, len(ring) // 300)]
    best, best_d = None, -1.0
    steps = 24
    for i in range(1, steps):
        for j in range(1, steps):
            x = min(xs) + (max(xs) - min(xs)) * i / steps
            y = min(ys) + (max(ys) - min(ys)) * j / steps
            if not _in_polygon(x, y, poly):
                continue
            d = min((x - px) ** 2 + (y - py) ** 2 for px, py in sample)
            if d > best_d:
                best, best_d = (x, y), d
    if best is None:
        best = (sum(xs) / len(xs), sum(ys) / len(ys))
    return [round(best[0], 4), round(best[1], 4)]


# ---------------------------------------------------------------------------
# Boundaries (download + process + cache)
# ---------------------------------------------------------------------------
def boundaries(iso2: str, *, force: bool = False) -> dict:
    iso2 = (iso2 or "").upper()
    meta = catalog().get(iso2)
    if not meta:
        raise NoBoundaries(iso2)
    path = GEO_DIR / f"{meta['iso3']}.geojson"
    if path.exists() and not force:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("metadata", {}).get("version") == GEO_VERSION:
            return data
    raw = requests.get(meta["url"], headers=UA, timeout=180)
    raw.raise_for_status()
    src = raw.json()

    feats = [f for f in src.get("features", []) if f.get("geometry") and _polygons(f["geometry"])]
    # Countries straddling the antimeridian (Russia, Fiji, Kiribati, ...): shift west longitudes by 360°
    # so Leaflet draws one continuous shape instead of two halves at opposite ends of the map.
    lons = [p[0] for f in feats for poly in _polygons(f["geometry"]) for p in poly[0]]
    shift = bool(lons) and (max(lons) - min(lons) > 300)
    vertices = sum(len(r) for f in feats for poly in _polygons(f["geometry"]) for r in poly)
    lats = [p[1] for f in feats for poly in _polygons(f["geometry"]) for p in poly[0]]
    extent = max(1e-6, max(lons) - min(lons) if not shift else 360 - (max(lons) - min(lons)), max(lats) - min(lats)) if lons else 1
    # Keep published geometry as-is unless the file is very heavy for a browser; then generalise
    # lightly in proportion to the country's size (borders move by well under a screen pixel).
    eps = extent * 0.0006 if vertices > 60000 else 0.0

    codes = [((f.get("properties") or {}).get("shapeISO") or "").strip() for f in feats]
    use_iso = all(codes) and len(set(codes)) == len(codes)
    out_feats = []
    for i, f in enumerate(feats):
        props = f.get("properties") or {}
        polys = []
        for poly in _polygons(f["geometry"]):
            rings = []
            for ring in poly:
                pts = [[x + 360 if shift and x < 0 else x, y] for x, y in ring]
                if eps:
                    pts = _rdp_ring(pts, eps)
                pts = [[round(x, 4), round(y, 4)] for x, y in pts]
                if pts[0] != pts[-1]:
                    pts.append(pts[0])
                if len(pts) >= 4:
                    rings.append(pts)
            if rings:
                polys.append(rings)
        if not polys:
            continue
        largest = max(polys, key=lambda p: _ring_area_km2(p[0]))
        lx, ly = _label_point(largest)
        name = (props.get("shapeName") or f"Region {i + 1}").replace("‎", "").replace("‏", "").strip()
        code = codes[i] if use_iso else f"{iso2}-{i + 1:02d}"
        all_x = [pt[0] for pp in polys for pt in pp[0]]
        all_y = [pt[1] for pp in polys for pt in pp[0]]
        out_feats.append({
            "type": "Feature",
            "properties": {
                "code": code, "name": name, "label_lon": lx, "label_lat": ly,
                "area_km2": round(sum(_ring_area_km2(p[0]) for p in polys)),
                "bbox": [round(min(all_x), 4), round(min(all_y), 4), round(max(all_x), 4), round(max(all_y), 4)],
            },
            "geometry": {"type": "MultiPolygon", "coordinates": polys} if len(polys) > 1 else {"type": "Polygon", "coordinates": polys[0]},
        })
    out_feats.sort(key=lambda f: f["properties"]["name"])
    data = {
        "type": "FeatureCollection",
        "metadata": {
            "version": GEO_VERSION, "iso2": iso2, "iso3": meta["iso3"], "release": meta["release"],
            "source": f"geoBoundaries {meta['release']} {meta['iso3']} ADM1 ({meta['source']})",
            "license": meta["license"], "boundary_year": meta["year"], "units": len(out_feats),
            "generalised": bool(eps), "antimeridian_shift": shift, "url": "https://www.geoboundaries.org/",
        },
        "features": out_feats,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return data


def region_for_point(features: list[dict], lat: float, lon: float) -> str | None:
    if lat is None or lon is None:
        return None
    for f in features:
        b = f["properties"]["bbox"]
        for x in (lon, lon + 360):
            if b[0] <= x <= b[2] and b[1] <= lat <= b[3]:
                if any(_in_polygon(x, lat, poly) for poly in _polygons(f["geometry"])):
                    return f["properties"]["code"]
    return None


# ---------------------------------------------------------------------------
# Layers
# ---------------------------------------------------------------------------
def _history(monthly: list[dict]) -> list[dict]:
    if not monthly:
        return []
    precip = [row.get("precip_mm") for row in monthly]
    r3, r12 = rolling_sums(precip, 3), rolling_sums(precip, 12)
    out = []
    for i in range(max(0, len(monthly) - HISTORY_MONTHS), len(monthly)):
        month = monthly[i]["month"]
        same = lambda series: [v for k, v in enumerate(series) if v is not None and monthly[k]["month"].month == month.month and monthly[k]["month"].year < month.year]
        spi3 = mid_rank_percentile(same(r3), r3[i])
        spi12 = mid_rank_percentile(same(r12), r12[i])
        soil = mid_rank_percentile(same_month_history(monthly, month.month, "soil_root", before_year=month.year), monthly[i].get("soil_root"))
        avail = [(w, s["score"]) for w, s in ((0.40, spi3), (0.25, spi12), (0.20, soil)) if s["available"]]
        drought = round(100.0 - sum(w * v for w, v in avail) / sum(w for w, _ in avail), 1) if avail else None
        out.append({"month": month.isoformat()[:7], "drought": drought,
                    "vegetation": round(soil["score"], 1) if soil["available"] else None,
                    "precip_mm": monthly[i].get("precip_mm")})
    return out


def compute_region(point: dict, iso2: str, iso3: str, monthly, forecast_rows, flood_rows, bank, event_counts) -> dict:
    result = compute_country(iso2=point["code"], iso3=iso3, country_name=point["name"], lat=point["lat"],
                             monthly=monthly, forecast_rows=forecast_rows, flood_rows=flood_rows,
                             bank=bank, event_counts=event_counts)
    hazards = result["hazards"]
    climate = result["climate"]
    aridity = climate.get("aridity_index")
    water_stress = round(100.0 - clamp(aridity / 0.65 * 100.0, 0.0, 100.0), 1) if aridity is not None else None
    soil_pct = hazards["drought"]["inputs"].get("soil_percentile")
    has_soil = bool(monthly) and soil_pct is not None
    return {
        "code": point["code"], "name": point["name"], "lat": point["lat"], "lon": point["lon"], "area_km2": point["area_km2"],
        "layers": {
            "water_stress": water_stress,
            "drought": hazards["drought"]["pressure"],
            "flood": hazards["flood"]["pressure"],
            "fire": hazards["fire"]["pressure"],
            "vegetation": round(soil_pct, 1) if has_soil else None,
        },
        "confidence": {
            "water_stress": 0.75 if water_stress is not None else 0.0,
            "drought": hazards["drought"]["confidence"], "flood": hazards["flood"]["confidence"],
            "fire": hazards["fire"]["confidence"], "vegetation": 0.5 if has_soil else 0.0,
        },
        "inputs": {
            "aridity_index": aridity, "annual_precip_mm": climate.get("annual_precip_mm"),
            "annual_pet_mm": climate.get("annual_pet_mm"), "precip_trend_pct_per_year": climate.get("precip_trend_pct_per_year"),
            "spi3_percentile": hazards["drought"]["inputs"].get("spi3_percentile"),
            "spi12_percentile": hazards["drought"]["inputs"].get("spi12_percentile"),
            "soil_percentile": soil_pct, "dry_days": hazards["drought"]["inputs"].get("dry_days"),
            "flood": hazards["flood"]["inputs"], "fire": hazards["fire"]["inputs"],
            "latest_month": climate.get("latest_month"),
        },
        "history": _history(monthly),
    }


def build_payload(iso2: str, *, force: bool = False, workers: int = 4, progress=None) -> dict:
    """Fetch (or read cached) sources at every region of ``iso2`` and compute every layer."""
    iso2 = iso2.upper()
    report = progress or (lambda stage, done=0, total=0: None)
    report("boundaries", 0, 1)
    geo = boundaries(iso2)
    feats = geo["features"]
    iso3 = geo["metadata"]["iso3"]
    points = [{
        "iso2": f["properties"]["code"],  # sources key their caches by "iso2"
        "code": f["properties"]["code"], "name": f["properties"]["name"],
        "lat": f["properties"]["label_lat"],
        "lon": f["properties"]["label_lon"] - 360 if f["properties"]["label_lon"] > 180 else f["properties"]["label_lon"],
        "area_km2": f["properties"]["area_km2"],
    } for f in feats]
    errors: list[str] = []

    report("forecast", 0, len(points))
    try:
        bank = sources.fetch_world_bank(force=False)
    except Exception as exc:
        bank = {}
        errors.append(f"World Bank: {exc}")
    try:
        forecast = sources.fetch_forecast(points, force=force)
    except Exception as exc:
        forecast = {}
        errors.append(f"Open-Meteo forecast: {exc}")
    report("flood", 0, len(points))
    try:
        flood = sources.fetch_flood(points, force=force)
    except Exception as exc:
        flood = {}
        errors.append(f"Open-Meteo flood: {exc}")

    monthly: dict[str, list[dict]] = {}

    def one(point):
        try:
            return point["code"], sources.fetch_nasa_monthly(point["lat"], point["lon"], force=force), None
        except Exception as exc:
            return point["code"], [], str(exc)

    report("climate", 0, len(points))
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(one, p) for p in points]
        for n, fut in enumerate(as_completed(futures), start=1):
            code, rows, err = fut.result()
            if rows:
                monthly[code] = rows
            elif err:
                errors.append(f"NASA POWER {code}: {err}")
            report("climate", n, len(points))

    report("events", 0, 1)
    from world.models import DamAtlas, HazardEvent

    event_counts: dict[str, int] = {}
    events = []
    for ev in HazardEvent.objects.exclude(lat=None).exclude(lon=None).filter(country_iso2=iso2):
        code = region_for_point(feats, ev.lat, ev.lon)
        if code:
            event_counts[f"{code}:{ev.category}"] = event_counts.get(f"{code}:{ev.category}", 0) + 1
            events.append({"code": code, "category": ev.category, "title": ev.title,
                           "date": ev.event_date.isoformat() if ev.event_date else None, "url": ev.source_url})

    # The largest catalogued dams (monitored first, then by capacity), assigned by point-in-polygon.
    report("dams", 0, 1)
    dam_rows = list(DamAtlas.objects.filter(country_iso2=iso2).order_by("-is_monitored", "-capacity_m3", "name")
                    .values("name", "lat", "lon", "capacity_m3", "is_monitored", "pilot_slug", "wikidata_id")[:1500])
    dam_total = DamAtlas.objects.filter(country_iso2=iso2).count()
    dams: dict[str, list[dict]] = {}
    for row in dam_rows:
        code = region_for_point(feats, row["lat"], row["lon"])
        if code:
            dams.setdefault(code, []).append({
                "name": row["name"], "lat": round(row["lat"], 4), "lon": round(row["lon"], 4),
                "capacity_mm3": round(row["capacity_m3"] / 1e6, 1) if row["capacity_m3"] else None,
                "monitored": row["is_monitored"], "url": f"/dam/{row['pilot_slug'] or row['wikidata_id']}/",
            })

    report("compute", 0, len(points))
    rows = []
    for point in points:
        r = compute_region(point, iso2, iso3, monthly.get(point["code"], []), forecast.get(point["code"], []),
                           flood.get(point["code"], []), bank, event_counts)
        r["lon"] = point["lon"]
        ds = dams.get(point["code"], [])
        r["dams"] = ds[:8]
        r["dam_count"] = len(ds)
        rows.append(r)

    months = sorted({h["month"] for r in rows for h in r["history"]})
    singular, plural = term(iso2)
    return {
        "region": iso2, "iso3": iso3,
        "country_name": _country_name(iso2),
        "term": singular, "term_plural": plural,
        "generated_at": date.today().isoformat(),
        "latest_month": months[-1] if months else None,
        "months": months[-HISTORY_MONTHS:],
        "layers": LAYERS,
        "regions": rows,
        "events": events,
        "errors": errors,
        "coverage": {
            "regions": len(rows),
            "with_climate": sum(1 for r in rows if r["layers"]["water_stress"] is not None),
            "with_flood_signal": sum(1 for r in rows if r["layers"]["flood"] is not None),
            "dams_considered": len(dam_rows), "dams_total": dam_total,
        },
        "geometry": {k: geo["metadata"][k] for k in ("source", "license", "boundary_year", "units", "generalised", "release")},
    }


def _country_name(iso2: str) -> str:
    from hydro.services.gazetteer import country_row

    row = country_row(iso2) or {}
    return row.get("name") or iso2
