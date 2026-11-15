"""Country profile lifecycle: inventory, climate, forecast, freshness."""
from __future__ import annotations

import logging
import math
import random
from datetime import date, datetime, timedelta, timezone as dt_timezone

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from hydro.models import ClimateDay, Country, ForecastDay, Reservoir
from hydro.services import open_data, storage
from hydro.services.statistics import clamp

logger = logging.getLogger("hydro.data")


def _seasonal_rain_probability(day: date, lat: float) -> float:
    """Crude climate envelope used only for the labelled synthetic fallback."""
    month = day.month
    if abs(lat) < 12:
        wet = 0.55 + 0.18 * math.cos(2 * math.pi * (month - 8) / 12)
        return clamp(wet, 0.25, 0.75) / 100.0 * 18
    if 12 <= abs(lat) < 28:
        wet = 0.10 + 0.08 * math.cos(2 * math.pi * (month - 7) / 12)
        return clamp(wet, 0.02, 0.20) / 100.0 * 15
    # Mediterranean / temperate: wet winters, dry summers.
    winter = 0.5 + 0.5 * math.cos(2 * math.pi * (month - 1) / 12)
    return 0.03 + 0.13 * winter


def _fallback_climate(country: Country, lat: float | None = None, years: int = 10) -> list[dict]:
    rng = random.Random(f"aquastate-{country.iso2}")
    latitude = country.lat if lat is None else lat
    today = date.today()
    start = today - timedelta(days=365 * years)
    records = []
    day = start
    wetness = 0.35
    while day <= today:
        probability = _seasonal_rain_probability(day, latitude)
        rain = 0.0
        if rng.random() < probability:
            rain = rng.gammavariate(1.4, 5.5)
            if rng.random() < 0.16:
                rain += rng.uniform(8, 32)
        wetness = clamp(wetness * 0.97 + min(rain / 60.0, 0.08) - 0.0009, 0.05, 0.95)
        records.append(
            {
                "date": day,
                "precip_mm": round(rain, 2),
                "soil_surface": round(clamp(wetness + rng.uniform(-0.025, 0.025), 0.03, 0.97), 4),
                "soil_root": round(clamp(wetness * 0.95 + 0.05 + rng.uniform(-0.02, 0.02), 0.03, 0.97), 4),
                "et0_mm": round(storage._et0_estimate(day, latitude), 2),
                "source": "Synthetic fallback",
                "fetched_at": timezone.now(),
            }
        )
        day += timedelta(days=1)
    return records


def _fallback_forecast(country: Country, lat: float, lon: float, days: int = 16) -> list[dict]:
    rng = random.Random(f"aquastate-forecast-{country.iso2}-{lat:.2f}-{lon:.2f}-{date.today()}")
    records = []
    for index in range(days):
        day = date.today() + timedelta(days=index)
        probability = _seasonal_rain_probability(day, lat)
        rain = 0.0
        if rng.random() < probability * 1.35:
            rain = rng.gammavariate(1.2, 4.2)
        records.append(
            {
                "date": day,
                "precip_mm": round(rain, 2),
                "et0_mm": round(storage._et0_estimate(day, lat), 2),
                "temp_max_c": None,
                "source": "Synthetic fallback",
                "fetched_at": timezone.now(),
            }
        )
    return records


def _replace_climate(country: Country, records: list[dict]) -> None:
    with transaction.atomic():
        ClimateDay.objects.filter(country=country).delete()
        ClimateDay.objects.bulk_create(
            [
                ClimateDay(
                    country=country,
                    date=row["date"],
                    precip_mm=row.get("precip_mm") or 0.0,
                    soil_surface=row.get("soil_surface"),
                    soil_root=row.get("soil_root"),
                    et0_mm=row.get("et0_mm"),
                    source=row.get("source", "NASA POWER / MERRA-2"),
                    fetched_at=row.get("fetched_at") or timezone.now(),
                )
                for row in records
            ],
            batch_size=1000,
        )


def _replace_forecast(country: Country, by_location: dict[str, list[dict]]) -> None:
    with transaction.atomic():
        ForecastDay.objects.filter(country=country).delete()
        rows = []
        for reservoir in country.reservoirs.all():
            records = by_location.get(f"res:{reservoir.id}") or by_location.get("country") or []
            for record in records:
                rows.append(
                    ForecastDay(
                        country=country,
                        reservoir=reservoir,
                        date=record["date"],
                        precip_mm=record.get("precip_mm") or 0.0,
                        et0_mm=record.get("et0_mm"),
                        temp_max_c=record.get("temp_max_c"),
                        source=record.get("source", "Open-Meteo"),
                        fetched_at=record.get("fetched_at") or timezone.now(),
                    )
                )
        if not rows:
            for record in by_location.get("country", []):
                rows.append(
                    ForecastDay(
                        country=country,
                        reservoir=None,
                        date=record["date"],
                        precip_mm=record.get("precip_mm") or 0.0,
                        et0_mm=record.get("et0_mm"),
                        temp_max_c=record.get("temp_max_c"),
                        source=record.get("source", "Synthetic fallback"),
                        fetched_at=record.get("fetched_at") or timezone.now(),
                    )
                )
        ForecastDay.objects.bulk_create(rows, batch_size=1000)


def is_stale(country: Country) -> bool:
    if not country.last_refresh:
        return True
    age = timezone.now() - country.last_refresh
    return age > timedelta(hours=settings.DATA_CACHE_HOURS)


def _hydrologic_centroid(country: Country) -> tuple[float, float]:
    """Demand/capacity-weighted centre of the reservoir system.

    A country centroid can sit in a desert while every dam is in a wetter
    upland. The climate point should follow the water system, not the flag.
    """
    rows = list(country.reservoirs.all())
    if not rows:
        return country.lat, country.lon
    weights = [max(0.01, row.demand_mm3_day or row.capacity_mm3 / 365.0) for row in rows]
    total = sum(weights)
    if total <= 0:
        return country.lat, country.lon
    lat = sum(row.lat * weight for row, weight in zip(rows, weights)) / total
    lon = sum(row.lon * weight for row, weight in zip(rows, weights)) / total
    return round(lat, 4), round(lon, 4)


def refresh_country(
    country: Country,
    *,
    allow_network: bool = True,
    force: bool = False,
) -> dict:
    """Ensure inventory + climate + forecast; label every source honestly."""
    storage.seed_reservoirs(country)
    climate_lat, climate_lon = _hydrologic_centroid(country)
    country.profile = dict(country.profile or {})
    country.profile["hydrologic_centroid"] = {"lat": climate_lat, "lon": climate_lon}
    country.save(update_fields=["profile"])
    if not force and not is_stale(country):
        if country.climate_days.exists() and country.forecast_days.exists():
            return {
                "status": "cached",
                "refreshed": False,
                "errors": [],
                "climate_source": country.climate_days.first().source,
                "forecast_source": country.forecast_days.first().source,
                "hydrologic_centroid": country.profile["hydrologic_centroid"],
            }

    errors: list[str] = []
    live = False

    # --- climate ---------------------------------------------------------
    climate_records: list[dict] = []
    if allow_network and settings.LIVE_DATA_ENABLED:
        climate_records, error = open_data.fetch_nasa_climate(climate_lat, climate_lon)
        if error:
            errors.append(f"NASA POWER: {error}")
    if not climate_records:
        climate_records = _fallback_climate(country, climate_lat)
        climate_live = False
    else:
        climate_live = True
        live = True
        for row in climate_records:
            if row.get("et0_mm") is None:
                row["et0_mm"] = round(storage._et0_estimate(row["date"], climate_lat), 2)
    _replace_climate(country, climate_records)

    # --- forecast --------------------------------------------------------
    reservoirs = list(country.reservoirs.all())
    locations: list[tuple[str, float, float]] = [("country", climate_lat, climate_lon)]
    locations += [(f"res:{row.id}", row.lat, row.lon) for row in reservoirs]
    by_location: dict[str, list[dict]] = {}
    forecast_error = None
    if allow_network and settings.LIVE_DATA_ENABLED:
        by_location, forecast_error = open_data.fetch_forecast(locations)
        if forecast_error:
            errors.append(f"Open-Meteo: {forecast_error}")
    forecast_live = bool(by_location)
    if by_location:
        live = True
    else:
        for key, lat, lon in locations:
            by_location[key] = _fallback_forecast(country, lat, lon)
        forecast_error = forecast_error or "forecast unavailable; synthetic fallback"
    _replace_forecast(country, by_location)

    # --- storage reconstruction -----------------------------------------
    storage_rows = storage.refresh_storage(country)

    if climate_live and forecast_live:
        country.data_mode = "live"
    elif climate_live or forecast_live:
        country.data_mode = "cached"
    else:
        country.data_mode = "fallback"
    country.last_refresh = timezone.now()
    country.save(update_fields=["data_mode", "last_refresh"])

    return {
        "status": country.data_mode,
        "refreshed": True,
        "errors": errors,
        "climate_source": climate_records[0]["source"] if climate_records else "none",
        "forecast_source": (by_location.get("country") or [{}])[0].get("source", "none"),
        "climate_rows": len(climate_records),
        "forecast_rows": sum(len(rows) for rows in by_location.values()),
        "reservoirs": len(storage_rows),
        "storage": [
            {
                "name": row["reservoir"].name,
                "model_pct": row["model_pct"],
                "final_pct": row["final_pct"],
                "source": row["source"],
            }
            for row in storage_rows
        ],
    }


def ensure_profile(country: Country, allow_network: bool = True) -> dict:
    storage.seed_reservoirs(country)
    if not country.climate_days.exists() or not country.forecast_days.exists() or is_stale(country):
        return refresh_country(country, allow_network=allow_network)
    return {"status": "cached", "refreshed": False, "errors": []}


def source_ledger(country: Country) -> list[dict]:
    climate = country.climate_days.order_by("-date").first()
    forecast = country.forecast_days.order_by("-fetched_at").first()
    inventory_live = any(not row.is_reference_pool for row in country.reservoirs.all())
    rows = [
        {
            "key": "climate",
            "name": "NASA POWER / MERRA-2",
            "what": "10-year precipitation and soil wetness at the demand-weighted reservoir centroid",
            "kind": "live" if climate and climate.source.startswith("NASA") else "fallback",
            "source": climate.source if climate else "not loaded",
            "fetched_at": climate.fetched_at.isoformat() if climate else None,
            "url": "https://power.larc.nasa.gov/",
        },
        {
            "key": "forecast",
            "name": "Open-Meteo",
            "what": "16-day precipitation, ET0 and temperature forecast",
            "kind": "live" if forecast and forecast.source.startswith("Open-Meteo") else "fallback",
            "source": forecast.source if forecast else "not loaded",
            "fetched_at": forecast.fetched_at.isoformat() if forecast else None,
            "url": "https://open-meteo.com/",
        },
        {
            "key": "inventory",
            "name": "Public dam inventory",
            "what": "Reservoir names, locations and screening capacities",
            "kind": "reference" if inventory_live else "synthetic",
            "source": "Curated public table" if inventory_live else "National reference pool",
            "fetched_at": None,
            "url": "https://en.wikipedia.org/wiki/List_of_dams_and_reservoirs_in_Algeria",
        },
        {
            "key": "storage",
            "name": "Mass-balance reconstruction",
            "what": "Current live storage and annual end-of-year history",
            "kind": "modeled",
            "source": "NASA POWER precipitation + allocated demand + ET0",
            "fetched_at": country.last_refresh.isoformat() if country.last_refresh else None,
            "url": "/methodology/",
        },
        {
            "key": "outline",
            "name": "Natural Earth 1:110m",
            "what": "Country outline for the map and offline fallback",
            "kind": "reference",
            "source": "Natural Earth public domain",
            "fetched_at": None,
            "url": "https://www.naturalearthdata.com/",
        },
    ]
    return rows


def import_osm_reservoirs(country: Country) -> dict:
    """Best-effort community inventory import for countries without a curated list."""
    if country.reservoirs.exclude(is_reference_pool=True).exists() and country.iso2 not in {"DZ", "TN"}:
        return {"ok": False, "message": "A reservoir inventory is already loaded."}
    rows, error = open_data.fetch_osm_reservoirs(country.bbox)
    if error:
        return {"ok": False, "message": f"OpenStreetMap unavailable: {error}"}
    if not rows:
        return {"ok": False, "message": "No named reservoirs returned for this country."}
    rows = rows[:24]
    country.reservoirs.all().delete()
    weights = storage.demand_weights(
        [
            {"capacity_mm3": max(20.0, country.reservoir_demand_mm3_day * 30.0 / len(rows))}
            for _ in rows
        ]
    )
    estimate = max(20.0, country.reservoir_demand_mm3_day * 30.0 / len(rows))
    for row, weight in zip(rows, weights):
        Reservoir.objects.create(
            country=country,
            name=row["name"],
            lat=row["lat"],
            lon=row["lon"],
            capacity_mm3=estimate,
            storage_mm3=estimate * 0.30,
            dead_storage_mm3=estimate * 0.10,
            surface_area_km2=storage.estimated_surface_area(estimate),
            inflow_mm3_day=storage.estimated_inflow(estimate),
            demand_mm3_day=country.reservoir_demand_mm3_day * weight,
            reference_storage_pct=0,
            storage_source="osm",
            source_name="OpenStreetMap / Overpass",
            metadata={
                "osm_id": row.get("osm_id"),
                "tags": row.get("tags", {}),
                "note": "Location and name from OSM; capacity is a screening estimate because OSM rarely stores live capacity.",
            },
        )
    refresh_country(country, allow_network=True, force=True)
    return {"ok": True, "message": f"Imported {len(rows)} reservoirs from OpenStreetMap.", "count": len(rows)}
