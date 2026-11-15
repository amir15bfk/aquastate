"""Keyless open-data adapters.

Every adapter returns plain Python structures and never raises into a request:
the caller gets ``(payload, error)`` and can label the resulting data honestly.
"""
from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone as dt_timezone
from typing import Any

from django.conf import settings

logger = logging.getLogger("hydro.open_data")

USER_AGENT = "AquaStateMVP/1.0 (NASA Space Apps challenge demo; contact: local)"


def _get_json(url: str, timeout: int) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_json(url: str, body: str, timeout: int) -> Any:
    request = urllib.request.Request(
        url,
        data=body.encode("utf-8"),
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Content-Type": "text/plain",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _clean(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number <= -900:
        return None
    return number


def fetch_nasa_climate(lat: float, lon: float) -> tuple[list[dict], str | None]:
    """10 years of daily precipitation and MERRA-2 soil wetness at a point."""
    if not settings.LIVE_DATA_ENABLED:
        return [], "live data disabled"
    end = date.today() - timedelta(days=2)
    start = end - timedelta(days=365 * 10 - 1)
    params = {
        "parameters": "PRECTOTCORR,GWETTOP,GWETROOT",
        "community": "AG",
        "longitude": f"{lon:.4f}",
        "latitude": f"{lat:.4f}",
        "start": start.strftime("%Y%m%d"),
        "end": end.strftime("%Y%m%d"),
        "format": "JSON",
    }
    url = "https://power.larc.nasa.gov/api/temporal/daily/point?" + urllib.parse.urlencode(params)
    try:
        payload = _get_json(url, settings.NASA_POWER_TIMEOUT)
        parameters = payload["properties"]["parameter"]
        precip = parameters.get("PRECTOTCORR", {})
        surface = parameters.get("GWETTOP", {})
        root = parameters.get("GWETROOT", {})
        dates = sorted(precip.keys())
        fetched_at = datetime.now(dt_timezone.utc)
        records = []
        for stamp in dates:
            day = datetime.strptime(stamp, "%Y%m%d").date()
            records.append(
                {
                    "date": day,
                    "precip_mm": _clean(precip.get(stamp)) or 0.0,
                    "soil_surface": _clean(surface.get(stamp)),
                    "soil_root": _clean(root.get(stamp)),
                    "et0_mm": None,
                    "source": "NASA POWER / MERRA-2",
                    "fetched_at": fetched_at,
                }
            )
        return records, None
    except Exception as exc:  # pragma: no cover - network dependent
        logger.warning("NASA POWER failed: %s", exc)
        return [], str(exc)


def fetch_forecast(locations: list[tuple[str, float, float]]) -> tuple[dict[str, list[dict]], str | None]:
    """16-day daily forecast for one or more coordinates.

    ``locations`` is [(key, lat, lon)]. Open-Meteo accepts comma-separated
    coordinates and returns one object per location in the same order.
    """
    if not settings.LIVE_DATA_ENABLED or not locations:
        return {}, "live data disabled"
    lats = ",".join(f"{lat:.4f}" for _, lat, _ in locations)
    lons = ",".join(f"{lon:.4f}" for _, _, lon in locations)
    params = {
        "latitude": lats,
        "longitude": lons,
        "daily": "precipitation_sum,et0_fao_evapotranspiration,temperature_2m_max",
        "forecast_days": "16",
        "timezone": "auto",
    }
    url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(params)
    try:
        payload = _get_json(url, settings.OPEN_METEO_TIMEOUT)
        items = payload if isinstance(payload, list) else [payload]
        fetched_at = datetime.now(dt_timezone.utc)
        result: dict[str, list[dict]] = {}
        for (key, _, _), item in zip(locations, items):
            daily = item.get("daily") or {}
            dates = daily.get("time") or []
            rain = daily.get("precipitation_sum") or []
            et0 = daily.get("et0_fao_evapotranspiration") or []
            temp = daily.get("temperature_2m_max") or []
            records = []
            for index, stamp in enumerate(dates):
                records.append(
                    {
                        "date": datetime.strptime(stamp, "%Y-%m-%d").date(),
                        "precip_mm": float(rain[index] or 0) if index < len(rain) else 0.0,
                        "et0_mm": float(et0[index]) if index < len(et0) and et0[index] is not None else None,
                        "temp_max_c": float(temp[index]) if index < len(temp) and temp[index] is not None else None,
                        "source": "Open-Meteo",
                        "fetched_at": fetched_at,
                    }
                )
            result[key] = records
        return result, None
    except Exception as exc:  # pragma: no cover - network dependent
        logger.warning("Open-Meteo forecast failed: %s", exc)
        return {}, str(exc)


def fetch_osm_reservoirs(bbox: list[float], limit: int = 30) -> tuple[list[dict], str | None]:
    """Optional community reservoir inventory. Overpass is best-effort only."""
    if not bbox or len(bbox) != 4:
        return [], "country bbox missing"
    south, west, north, east = bbox
    query = f"""
[out:json][timeout:12];
(
  way["water"="reservoir"]["name"]({south},{west},{north},{east});
  way["landuse"="reservoir"]["name"]({south},{west},{north},{east});
);
out center {limit};
""".strip()
    endpoints = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
    ]
    last_error = "unknown"
    for endpoint in endpoints:
        try:
            payload = _post_json(endpoint, query, settings.OVERPASS_TIMEOUT)
            rows = []
            for element in payload.get("elements", []):
                tags = element.get("tags") or {}
                name = (tags.get("name") or "").strip()
                center = element.get("center") or {}
                lat = center.get("lat") or element.get("lat")
                lon = center.get("lon") or element.get("lon")
                if not name or lat is None or lon is None:
                    continue
                rows.append(
                    {
                        "name": name,
                        "lat": float(lat),
                        "lon": float(lon),
                        "osm_id": element.get("id"),
                        "tags": tags,
                    }
                )
            return rows, None
        except Exception as exc:  # pragma: no cover - network dependent
            last_error = str(exc)
            logger.info("Overpass endpoint %s failed: %s", endpoint, exc)
    return [], last_error
