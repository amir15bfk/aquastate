"""Bundled 250-country gazetteer and lazy Country rows."""
from __future__ import annotations

import json
from functools import lru_cache

from django.conf import settings

from hydro.data.curated import CURATED_COUNTRIES
from hydro.models import Country


@lru_cache(maxsize=1)
def _gazetteer() -> dict[str, dict]:
    payload = json.loads(settings.COUNTRIES_FILE.read_text(encoding="utf-8"))
    return {row["iso2"].upper(): row for row in payload}


def all_countries() -> list[dict]:
    rows = list(_gazetteer().values())
    rows.sort(key=lambda row: row["name"])
    return rows


def country_row(iso2: str) -> dict | None:
    return _gazetteer().get((iso2 or "").strip().upper())


def default_demand(profile: dict) -> float:
    """Screening reservoir-fed demand, Mm3/day.

    Curated countries use a public inventory allocation; elsewhere a
    population-based municipal/irrigation proxy keeps the model usable.
    """
    population = int(profile.get("population") or 0)
    area = float(profile.get("area_km2") or 0)
    if population > 0:
        # 0.3 m3/person/day = 0.0000003 Mm3/day.
        return max(0.25, population * 0.0000003)
    return max(0.20, area * 0.00002)


def ensure_country(iso2: str) -> Country | None:
    iso2 = (iso2 or "").strip().upper()
    if not iso2:
        return None
    row = country_row(iso2)
    if not row:
        return None
    curated = CURATED_COUNTRIES.get(iso2, {})
    existing = Country.objects.filter(iso2=iso2).first()
    if existing:
        updates = {}
        for field, value in (
            ("name", row["name"]),
            ("official_name", row.get("official", "")),
            ("continent", row.get("continent", "")),
            ("region", row.get("region", "")),
            ("subregion", row.get("subregion", "")),
            ("area_km2", row.get("area_km2", 0)),
            ("population", row.get("population", 0)),
            ("lat", row.get("lat", 0)),
            ("lon", row.get("lon", 0)),
            ("bbox", row.get("bbox", [])),
            ("has_outline", bool(row.get("has_outline"))),
        ):
            if getattr(existing, field) != value:
                updates[field] = value
        if updates:
            for field, value in updates.items():
                setattr(existing, field, value)
            if not curated:
                demand = default_demand(row)
                if existing.reservoir_demand_mm3_day != demand:
                    existing.reservoir_demand_mm3_day = demand
                    updates["reservoir_demand_mm3_day"] = demand
            existing.save(update_fields=list(updates.keys()))
        elif not curated:
            demand = default_demand(row)
            if existing.reservoir_demand_mm3_day != demand:
                existing.reservoir_demand_mm3_day = demand
                existing.save(update_fields=["reservoir_demand_mm3_day"])
        return existing
    country = Country.objects.create(
        iso2=row["iso2"],
        iso3=row.get("iso3", ""),
        name=row["name"],
        official_name=row.get("official", ""),
        continent=row.get("continent", ""),
        region=row.get("region", ""),
        subregion=row.get("subregion", ""),
        area_km2=row.get("area_km2", 0),
        population=row.get("population", 0),
        lat=row.get("lat", 0),
        lon=row.get("lon", 0),
        bbox=row.get("bbox", []),
        has_outline=bool(row.get("has_outline")),
        reservoir_demand_mm3_day=curated.get("demand_mm3_day", default_demand(row)),
        profile={
            "gazetteer": row,
            "curated": bool(curated),
            "curated_note": curated.get("note", ""),
            "curated_source": curated.get("source", ""),
        },
    )
    return country


def country_payload(country: Country) -> dict:
    return {
        "iso2": country.iso2,
        "iso3": country.iso3,
        "name": country.name,
        "region": country.region,
        "subregion": country.subregion,
        "lat": country.lat,
        "lon": country.lon,
        "bbox": country.bbox,
        "has_outline": country.has_outline,
        "population": country.population,
        "area_km2": country.area_km2,
        "demand_mm3_day": round(country.reservoir_demand_mm3_day, 3),
        "data_mode": country.data_mode,
        "last_refresh": country.last_refresh.isoformat() if country.last_refresh else None,
    }
