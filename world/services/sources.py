"""Keyless source adapters for the world layer.

Every fetch returns plain Python data and records failures rather than raising
into a request. Raw responses are cached on disk so a restart does not re-hit
the public APIs.
"""
from __future__ import annotations

import calendar
import json
import logging
import math
import time
from datetime import date, datetime, timedelta, timezone as dt_timezone
from pathlib import Path
from typing import Any, Iterable

import requests

from django.conf import settings

logger = logging.getLogger("world.sources")

CACHE_DIR = Path(settings.BASE_DIR) / "world" / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": "AquaStateWorld/2.0 (NASA Space Apps challenge; local demo)",
        "Accept": "application/json",
    }
)

NASA_URL = "https://power.larc.nasa.gov/api/temporal/monthly/point"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
FLOOD_URL = "https://flood-api.open-meteo.com/v1/flood"
EONET_URL = "https://eonet.gsfc.nasa.gov/api/v3/events"
WORLD_BANK_URL = "https://api.worldbank.org/v2/country/all/indicator/{code}"


def _cache_path(key: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in key)
    return CACHE_DIR / f"{safe}.json"


def load_cache(key: str, max_age_seconds: int | None = None) -> Any | None:
    path = _cache_path(key)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if max_age_seconds is not None:
        fetched = payload.get("_fetched_at")
        if not fetched:
            return None
        age = (datetime.now(dt_timezone.utc) - datetime.fromisoformat(fetched)).total_seconds()
        if age > max_age_seconds:
            return None
    return payload.get("data")


def _json_default(value: Any):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"not JSON serializable: {type(value)!r}")


def save_cache(key: str, data: Any) -> None:
    path = _cache_path(key)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(
            {"_fetched_at": datetime.now(dt_timezone.utc).isoformat(), "data": data},
            ensure_ascii=False,
            default=_json_default,
        ),
        encoding="utf-8",
    )
    tmp.replace(path)


def _restore_dates(value: Any, fields: tuple[str, ...] = ("date", "month")) -> Any:
    """Turn ISO date strings back into date objects after a cache read."""
    if isinstance(value, list):
        return [_restore_dates(item, fields) for item in value]
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if key in fields and isinstance(item, str):
                try:
                    out[key] = date.fromisoformat(item[:10])
                    continue
                except ValueError:
                    pass
            out[key] = _restore_dates(item, fields)
        return out
    return value


_LAST_OPEN_METEO = 0.0


def _polite_wait(seconds: float = 1.5) -> None:
    """Space out keyless public API calls so a 250-country pass stays polite."""
    global _LAST_OPEN_METEO
    elapsed = time.time() - _LAST_OPEN_METEO
    if elapsed < seconds:
        time.sleep(seconds - elapsed)
    _LAST_OPEN_METEO = time.time()


def _get_json(
    url: str,
    *,
    params: dict | None = None,
    timeout: int = 30,
    retries: int = 3,
) -> Any:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = SESSION.get(url, params=params, timeout=timeout)
            if response.status_code == 429:
                wait = 20.0 * (attempt + 1)
                logger.warning("Rate limited by %s; sleeping %.0fs", url.split("?")[0], wait)
                time.sleep(wait)
                last_error = RuntimeError("429 Too Many Requests")
                continue
            response.raise_for_status()
            # Some public endpoints emit lowercase nan/inf, which is not valid
            # JSON. Normalise those tokens before parsing.
            text = (
                response.text.replace(":nan", ":null")
                .replace(":NaN", ":null")
                .replace(":inf", ":null")
                .replace(":-inf", ":null")
                .replace(",nan", ",null")
                .replace(",NaN", ",null")
                .replace("[nan", "[null")
            )
            return json.loads(text)
        except Exception as exc:  # network dependent
            last_error = exc
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"{url}: {last_error}")


def _num(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number <= -900:
        return None
    return number


# ---------------------------------------------------------------------------
# NASA POWER monthly climatology
# ---------------------------------------------------------------------------
def fetch_nasa_monthly(
    lat: float,
    lon: float,
    *,
    start_year: int = 2016,
    end_year: int | None = None,
    force: bool = False,
) -> list[dict]:
    end_year = end_year or date.today().year
    # v2: PRECTOTCORR monthly is a daily mean (mm/day); convert to a monthly
    # total so annual sums and SPI windows are in millimetres.
    key = f"nasa_monthly_v2_{lat:.3f}_{lon:.3f}_{start_year}_{end_year}"
    cached = None if force else load_cache(key, max_age_seconds=settings.WCRI_CLIMATE_TTL_HOURS * 3600)
    if cached is not None:
        return _restore_dates(cached, ("month",))
    params = {
        "parameters": "PRECTOTCORR,T2M,T2M_MAX,T2M_MIN,GWETROOT,GWETTOP",
        "community": "AG",
        "longitude": f"{lon:.4f}",
        "latitude": f"{lat:.4f}",
        "start": str(start_year),
        "end": str(end_year),
        "format": "JSON",
    }
    payload = _get_json(NASA_URL, params=params, timeout=settings.NASA_POWER_TIMEOUT, retries=2)
    params_payload = payload.get("properties", {}).get("parameter", {})
    precip = params_payload.get("PRECTOTCORR", {})
    t2m = params_payload.get("T2M", {})
    tmax = params_payload.get("T2M_MAX", {})
    tmin = params_payload.get("T2M_MIN", {})
    soil_root = params_payload.get("GWETROOT", {})
    soil_top = params_payload.get("GWETTOP", {})
    rows: list[dict] = []
    for stamp in sorted(precip.keys()):
        if len(stamp) != 6:
            continue
        month = int(stamp[4:6])
        if month < 1 or month > 12:
            continue
        year = int(stamp[:4])
        if year < start_year or year > end_year:
            continue
        days = calendar.monthrange(year, month)[1]
        daily_rain = _num(precip.get(stamp))
        rows.append(
            {
                "month": date(year, month, 1),
                "precip_mm": round(daily_rain * days, 2) if daily_rain is not None else None,
                "precip_daily_mm": daily_rain,
                "tmean": _num(t2m.get(stamp)),
                "tmax": _num(tmax.get(stamp)),
                "tmin": _num(tmin.get(stamp)),
                "soil_root": _num(soil_root.get(stamp)),
                "soil_top": _num(soil_top.get(stamp)),
                "source": "NASA POWER / MERRA-2",
            }
        )
    rows = [row for row in rows if row["precip_mm"] is not None]
    save_cache(key, rows)
    return rows


# ---------------------------------------------------------------------------
# Open-Meteo forecast, 100 locations per request
# ---------------------------------------------------------------------------
FORECAST_VARIABLES = (
    "precipitation_sum,et0_fao_evapotranspiration,temperature_2m_max,"
    "temperature_2m_min,relative_humidity_2m_min,wind_speed_10m_max"
)


def fetch_forecast(
    points: list[dict],
    *,
    batch_size: int = 50,
    force: bool = False,
) -> dict[str, list[dict]]:
    """Return {iso2: [daily rows]} for up to 250 country points."""
    result: dict[str, list[dict]] = {}
    for start in range(0, len(points), batch_size):
        chunk = points[start : start + batch_size]
        key = "forecast_" + "_".join(p["iso2"] for p in chunk)
        cached = None if force else load_cache(key, max_age_seconds=settings.WCRI_FORECAST_TTL_MINUTES * 60)
        if cached is not None:
            result.update(_restore_dates(cached, ("date",)))
            continue
        _polite_wait(10.0)
        params = {
            "latitude": ",".join(f"{p['lat']:.3f}" for p in chunk),
            "longitude": ",".join(f"{p['lon']:.3f}" for p in chunk),
            "daily": FORECAST_VARIABLES,
            "forecast_days": "16",
            "past_days": "92",
            "timezone": "auto",
        }
        payload = _get_json(FORECAST_URL, params=params, timeout=settings.OPEN_METEO_TIMEOUT)
        items = payload if isinstance(payload, list) else [payload]
        chunk_result: dict[str, list[dict]] = {}
        for point, item in zip(chunk, items):
            daily = item.get("daily") or {}
            dates = daily.get("time") or []
            rows = []
            for index, stamp in enumerate(dates):
                def value(name: str):
                    values = daily.get(name) or []
                    return _num(values[index]) if index < len(values) else None

                rows.append(
                    {
                        "date": date.fromisoformat(stamp),
                        "precip_mm": value("precipitation_sum") or 0.0,
                        "et0_mm": value("et0_fao_evapotranspiration"),
                        "tmax": value("temperature_2m_max"),
                        "tmin": value("temperature_2m_min"),
                        "rh_min": value("relative_humidity_2m_min"),
                        "wind_max": value("wind_speed_10m_max"),
                        "soil_surface": value("soil_moisture_0_to_7cm"),
                        "soil_root": value("soil_moisture_7_to_28cm"),
                        "source": "Open-Meteo",
                    }
                )
            chunk_result[point["iso2"]] = rows
        save_cache(key, chunk_result)
        result.update(chunk_result)
    return result


# ---------------------------------------------------------------------------
# Open-Meteo GloFAS flood discharge
# ---------------------------------------------------------------------------
def fetch_flood(
    points: list[dict],
    *,
    batch_size: int = 50,
    force: bool = False,
) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    for start in range(0, len(points), batch_size):
        chunk = points[start : start + batch_size]
        key = "flood_" + "_".join(p["iso2"] for p in chunk)
        cached = None if force else load_cache(key, max_age_seconds=settings.WCRI_FLOOD_TTL_MINUTES * 60)
        if cached is not None:
            result.update(_restore_dates(cached, ("date",)))
            continue
        _polite_wait(10.0)
        params = {
            "latitude": ",".join(f"{p['lat']:.3f}" for p in chunk),
            "longitude": ",".join(f"{p['lon']:.3f}" for p in chunk),
            "daily": "river_discharge",
            "past_days": "60",
            "forecast_days": "16",
        }
        payload = _get_json(FLOOD_URL, params=params, timeout=settings.OPEN_METEO_TIMEOUT)
        items = payload if isinstance(payload, list) else [payload]
        chunk_result: dict[str, list[dict]] = {}
        for point, item in zip(chunk, items):
            daily = item.get("daily") or {}
            dates = daily.get("time") or []
            discharge = daily.get("river_discharge") or []
            rows = []
            for index, stamp in enumerate(dates):
                rows.append(
                    {
                        "date": date.fromisoformat(stamp),
                        "discharge": _num(discharge[index]) if index < len(discharge) else None,
                        "source": "Open-Meteo GloFAS",
                    }
                )
            chunk_result[point["iso2"]] = rows
        save_cache(key, chunk_result)
        result.update(chunk_result)
    return result


# ---------------------------------------------------------------------------
# NASA EONET active natural events
# ---------------------------------------------------------------------------
EONET_CATEGORIES = ("drought", "floods", "wildfires", "dustHaze", "tempExtremes")


def fetch_eonet(*, force: bool = False) -> list[dict]:
    key = "eonet_events"
    cached = None if force else load_cache(key, max_age_seconds=1800)
    if cached is not None:
        return cached
    events: list[dict] = []
    for category in EONET_CATEGORIES:
        payload = _get_json(
            EONET_URL,
            params={"category": category, "status": "open", "limit": "200"},
            timeout=settings.OPEN_METEO_TIMEOUT,
        )
        for event in payload.get("events", []):
            geometry = event.get("geometry") or []
            if not geometry:
                continue
            latest = geometry[-1]
            coords = latest.get("coordinates") or []
            if len(coords) < 2:
                continue
            events.append(
                {
                    "eonet_id": event.get("id"),
                    "title": event.get("title") or "Untitled event",
                    "category": category,
                    "lat": float(coords[1]),
                    "lon": float(coords[0]),
                    "event_date": latest.get("date"),
                    "source": "NASA EONET",
                    "source_url": (event.get("sources") or [{}])[0].get("url", ""),
                    "magnitude": (latest.get("magnitudeValue") if isinstance(latest, dict) else None),
                    "metadata": {
                        "description": event.get("description"),
                        "closed": event.get("closed"),
                        "sources": event.get("sources", []),
                    },
                }
            )
    # Deduplicate by EONET id.
    unique = {event["eonet_id"]: event for event in events if event.get("eonet_id")}
    rows = list(unique.values())
    save_cache(key, rows)
    return rows


# ---------------------------------------------------------------------------
# World Bank annual indicators
# ---------------------------------------------------------------------------
WORLD_BANK_INDICATORS = {
    "population": "SP.POP.TOTL",
    "freshwater_per_capita": "ER.H2O.INTR.PC",
    "freshwater_withdrawal_pct": "ER.H2O.FWTL.ZS",
    "forest_area_pct": "AG.LND.FRST.ZS",
    "arable_land_pct": "AG.LND.ARBL.ZS",
}


def fetch_world_bank(*, force: bool = False) -> dict[str, dict]:
    key = "world_bank_indicators"
    cached = None if force else load_cache(key, max_age_seconds=settings.WCRI_BANK_TTL_HOURS * 3600)
    if cached is not None:
        return cached
    result: dict[str, dict] = {}
    for name, code in WORLD_BANK_INDICATORS.items():
        payload = _get_json(
            WORLD_BANK_URL.format(code=code),
            params={"format": "json", "per_page": "5000", "date": "2010:2025"},
            timeout=settings.WORLD_BANK_TIMEOUT,
            retries=1,
        )
        if not isinstance(payload, list) or len(payload) < 2 or not payload[1]:
            continue
        grouped: dict[str, list[tuple[int, float]]] = {}
        for row in payload[1]:
            if row.get("value") is None:
                continue
            iso3 = (row.get("countryiso3code") or "").upper()
            year = int(row.get("date") or 0)
            if not iso3 or not year:
                continue
            grouped.setdefault(iso3, []).append((year, float(row["value"])))
        result[name] = {}
        for iso3, values in grouped.items():
            values.sort()
            latest_year, latest = values[-1]
            first_year, first = values[0]
            result[name][iso3] = {
                "latest": latest,
                "year": latest_year,
                "first": first,
                "first_year": first_year,
                "change": latest - first,
                "change_pct": ((latest - first) / abs(first) * 100.0) if first else 0.0,
            }
    save_cache(key, result)
    return result


# ---------------------------------------------------------------------------
# Country point helpers
# ---------------------------------------------------------------------------
def country_points() -> list[dict]:
    from hydro.services.gazetteer import all_countries

    return [
        {
            "iso2": row["iso2"],
            "iso3": row.get("iso3", ""),
            "name": row["name"],
            "lat": float(row.get("lat") or 0.0),
            "lon": float(row.get("lon") or 0.0),
            "bbox": row.get("bbox") or [],
        }
        for row in all_countries()
        if row.get("lat") is not None
        and row.get("lon") is not None
        and abs(float(row["lat"])) < 85.0
        and not (float(row["lat"]) == 0.0 and float(row["lon"]) == 0.0)
    ]
