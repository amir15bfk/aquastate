"""Screening reservoir inventory and mass-balance storage reconstruction.

The reconstruction is deliberately simple and fully documented. It turns ten
years of NASA POWER precipitation into a monthly live-storage trajectory using
a capacity-scaled rainfall response, allocated demand, evaporation and base
inflow. It is a model, not telemetry.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date

from hydro.data.curated import CURATED_COUNTRIES, RESERVOIRS
from hydro.models import ClimateDay, Country, Reservoir, StorageYear


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def estimated_surface_area(capacity_mm3: float) -> float:
    return clamp(capacity_mm3 * 0.05, 2.0, 140.0)


def estimated_inflow(capacity_mm3: float) -> float:
    # A small baseline inflow so a reservoir does not drain to dead storage
    # solely because the screening model has no upstream river gauge.
    return capacity_mm3 / 3650.0 * 0.20


def demand_weights(reservoirs: list[dict]) -> list[float]:
    raw = [max(0.0, row["capacity_mm3"]) ** 0.80 for row in reservoirs]
    total = sum(raw)
    if total <= 0:
        return [1.0 / len(reservoirs)] * len(reservoirs) if reservoirs else []
    return [value / total for value in raw]


def seed_reservoirs(country: Country) -> list[Reservoir]:
    """Create a curated inventory, or one clearly-labelled national pool."""
    existing = list(country.reservoirs.all())
    if existing:
        if len(existing) == 1 and existing[0].is_reference_pool:
            pool = existing[0]
            capacity = clamp(
                country.population * 0.00005 + country.area_km2 * 0.0015, 80.0, 12000.0
            )
            demand = max(0.2, country.reservoir_demand_mm3_day)
            capacity_changed = abs(pool.capacity_mm3 - capacity) > max(1.0, capacity * 0.02)
            if capacity_changed or abs(pool.demand_mm3_day - demand) > 0.001:
                if capacity_changed:
                    pool.capacity_mm3 = capacity
                    pool.dead_storage_mm3 = capacity * 0.10
                    pool.storage_mm3 = capacity * 0.35
                    pool.surface_area_km2 = estimated_surface_area(capacity)
                    pool.inflow_mm3_day = estimated_inflow(capacity)
                pool.demand_mm3_day = demand
                pool.save(
                    update_fields=[
                        "capacity_mm3",
                        "dead_storage_mm3",
                        "storage_mm3",
                        "surface_area_km2",
                        "inflow_mm3_day",
                        "demand_mm3_day",
                        "updated_at",
                    ]
                )
        return existing

    curated = RESERVOIRS.get(country.iso2)
    if curated:
        rows = [
            {
                "name": name,
                "lat": lat,
                "lon": lon,
                "capacity_mm3": capacity,
                "reference_storage_pct": reference,
                "source_slug": slug,
            }
            for name, lat, lon, capacity, reference, slug in curated
        ]
        weights = demand_weights(rows)
        created = []
        for row, weight in zip(rows, weights):
            created.append(
                Reservoir.objects.create(
                    country=country,
                    name=row["name"],
                    lat=row["lat"],
                    lon=row["lon"],
                    capacity_mm3=row["capacity_mm3"],
                    storage_mm3=row["capacity_mm3"] * row["reference_storage_pct"] / 100.0,
                    dead_storage_mm3=row["capacity_mm3"] * 0.10,
                    surface_area_km2=estimated_surface_area(row["capacity_mm3"]),
                    inflow_mm3_day=estimated_inflow(row["capacity_mm3"]),
                    demand_mm3_day=country.reservoir_demand_mm3_day * weight,
                    reference_storage_pct=row["reference_storage_pct"],
                    storage_source="blended",
                    source_name="Public dam inventory (screening)",
                    source_url=f"https://en.wikipedia.org/wiki/{row['source_slug']}",
                    metadata={
                        "note": "Capacity is a public screening value; storage is a blended model/reference estimate.",
                        "curated": True,
                    },
                )
            )
        return created

    # Country-agnostic fallback: one screening pool, explicitly not a dam.
    population = max(0, country.population)
    capacity = clamp(population * 0.00005 + country.area_km2 * 0.0015, 80.0, 12000.0)
    pool = Reservoir.objects.create(
        country=country,
        name="National reference storage pool",
        lat=country.lat,
        lon=country.lon,
        capacity_mm3=capacity,
        storage_mm3=capacity * 0.35,
        dead_storage_mm3=capacity * 0.10,
        surface_area_km2=estimated_surface_area(capacity),
        inflow_mm3_day=estimated_inflow(capacity),
        demand_mm3_day=max(0.2, country.reservoir_demand_mm3_day),
        reference_storage_pct=0,
        storage_source="synthetic",
        is_reference_pool=True,
        source_name="AquaState national screening pool",
        metadata={
            "note": "No open reservoir inventory loaded. This is a national screening construct, not a physical dam."
        },
    )
    return [pool]


def _et0_estimate(day: date, lat: float) -> float:
    """A simple latitude/season ET0 proxy used only when no measured ET0 exists."""
    month_angle = 2.0 * math.pi * (day.month - 7) / 12.0
    season = math.cos(month_angle) if lat >= 0 else -math.cos(month_angle)
    return clamp(3.0 + 2.0 * abs(lat) / 35.0 + 1.5 * season, 1.0, 9.0)


def monthly_climate(records: list[dict] | list[ClimateDay]) -> dict[tuple[int, int], dict]:
    buckets: dict[tuple[int, int], dict] = defaultdict(
        lambda: {"precip": 0.0, "et0_sum": 0.0, "et0_days": 0, "days": 0}
    )
    for record in records:
        if isinstance(record, ClimateDay):
            day = record.date
            precip = record.precip_mm or 0.0
            et0 = record.et0_mm
            lat = 0.0
        else:
            day = record["date"]
            precip = record.get("precip_mm") or 0.0
            et0 = record.get("et0_mm")
            lat = 0.0
        key = (day.year, day.month)
        bucket = buckets[key]
        bucket["precip"] += precip
        bucket["days"] += 1
        if et0 is not None:
            bucket["et0_sum"] += float(et0)
            bucket["et0_days"] += 1
    return buckets


def reconstruct_storage(
    country: Country,
    reservoir: Reservoir,
    climate: list[dict] | list[ClimateDay],
    initial_pct: float = 0.55,
) -> dict:
    """Run a monthly mass balance and return current + annual end-of-year pct."""
    if not climate:
        return {
            "current_pct": reservoir.reference_storage_pct or 35.0,
            "years": [],
            "months": 0,
            "source": "Fallback reference",
        }

    et0_fallback = _et0_estimate(date.today(), reservoir.lat or country.lat)
    buckets = monthly_climate(climate)
    capacity = max(0.001, reservoir.capacity_mm3)
    dead = max(0.0, reservoir.dead_storage_mm3)
    area = reservoir.surface_area_km2 or estimated_surface_area(capacity)
    storage = clamp(capacity * initial_pct, dead, capacity)
    years: list[dict] = []
    last_year = None

    for (year, month) in sorted(buckets):
        bucket = buckets[(year, month)]
        days = max(1, bucket["days"])
        et0 = (
            bucket["et0_sum"] / bucket["et0_days"]
            if bucket["et0_days"]
            else et0_fallback
        )
        precip = bucket["precip"]
        inflow = precip * (capacity / 300.0) + reservoir.inflow_mm3_day * days
        evaporation = et0 * area * 0.001 * 0.70 * days
        demand = reservoir.demand_mm3_day * days
        storage = clamp(storage + inflow - demand - evaporation, dead, capacity)
        if last_year is not None and year != last_year:
            years.append({"year": last_year, "end_storage_pct": 100.0 * storage / capacity})
        last_year = year

    if last_year is not None:
        years.append({"year": last_year, "end_storage_pct": 100.0 * storage / capacity})
    return {
        "current_pct": 100.0 * storage / capacity,
        "years": years,
        "months": len(buckets),
        "source": "Mass-balance reconstruction from NASA POWER",
    }


def refresh_storage(country: Country) -> list[dict]:
    """Recompute storage for every reservoir and persist the annual history."""
    climate = list(country.climate_days.all())
    if not climate:
        climate = []
    results = []
    for reservoir in country.reservoirs.all():
        result = reconstruct_storage(country, reservoir, climate)
        model = result["current_pct"]
        reference = reservoir.reference_storage_pct or 0
        if reservoir.is_reference_pool:
            final_pct = model
            source = "Modeled reconstruction"
        elif reference > 0:
            final_pct = 0.60 * reference + 0.40 * model
            source = "Blended reference + reconstruction"
        else:
            final_pct = model
            source = "Modeled reconstruction"
        final_pct = clamp(final_pct, 1.0, 98.0)
        reservoir.storage_mm3 = reservoir.capacity_mm3 * final_pct / 100.0
        if not reservoir.is_reference_pool:
            reservoir.storage_source = "blended" if reference > 0 else "modeled"
        reservoir.save(update_fields=["storage_mm3", "storage_source", "updated_at"])

        StorageYear.objects.filter(reservoir=reservoir).delete()
        StorageYear.objects.bulk_create(
            [
                StorageYear(
                    reservoir=reservoir,
                    year=row["year"],
                    end_storage_pct=round(row["end_storage_pct"], 2),
                    source="Modeled reconstruction",
                )
                for row in result["years"]
                if 2000 <= row["year"] <= date.today().year + 1
            ]
        )
        results.append(
            {
                "reservoir": reservoir,
                "model_pct": round(model, 2),
                "final_pct": round(final_pct, 2),
                "source": source,
                "months": result["months"],
            }
        )
    return results


def country_inventory_note(country: Country) -> str:
    if country.iso2 in CURATED_COUNTRIES:
        return CURATED_COUNTRIES[country.iso2]["note"]
    return (
        "No open reservoir inventory is loaded for this country. A labelled "
        "national reference pool supplies a screening estimate; live soil, "
        "rain and ET0 still drive the index."
    )
