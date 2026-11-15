"""Deterministic pilot-data seed.

The default 26-year run writes ~100k climate rows for ten dams. Every random
draw is derived from `seed ^ crc32(dam.slug)`, so the same command produces the
same current fill on every machine. Beni Haroun additionally receives the
signed-off Case B climatology fixture.
"""
from __future__ import annotations

import datetime as dt
import math
import zlib
from collections import defaultdict
from typing import Iterable

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.data.pilot_dams import (
    PILOT_COUNTRIES,
    PILOT_DAMS_BY_SLUG,
    DamSeedSpec,
)
from core.models import (
    Basin,
    BathymetryPoint,
    ClimateObservation,
    ClimatologyBin,
    Country,
    Dam,
    DemandObservation,
    ForecastObservation,
    GraceObservation,
    ReservoirObservation,
)
from core.services.stats import week_bin
from core.services.units import surface_area_at_volume_m2

METRICS = (
    "ssi_fill_pct",
    "cmi_p90",
    "cmi_p30",
    "dry_spell",
    "srri_c_ref",
    "sai_gwsa",
    "eesi_esi",
    "eesi_evap_ratio",
    "eesi_lst_anom",
    "analog_fill_pct",
    "analog_storage_anomaly",
)

SSI_W46 = [18, 22, 24, 26, 28, 30, 32, 34, 35, 36, 37, 38, 39, 40, 41, 42,
           43, 44, 45, 46, 48, 50, 52, 55, 58, 60]
SSI_W48 = [20, 24, 27, 30, 32, 34, 36, 38, 39, 40, 41, 42, 43, 44, 45, 46,
           47, 48, 49, 50, 52, 54, 56, 58, 60, 62]
CMI_P30 = [8.0 * n for n in range(1, 27)]
CMI_P90 = [16.0 + 8.0 * n for n in range(26)]
DRY_BASE = [float(n) for n in range(1, 14)] + [13.0] + [float(n) for n in range(15, 27)]
C_REF_BASE = [round(0.02 * n, 2) for n in range(0, 21)] + [0.52, 0.54, 0.56, 0.58, 0.60]


def _median(values: Iterable[float]) -> float:
    clean = sorted(float(v) for v in values if v is not None and math.isfinite(float(v)))
    if not clean:
        return 0.0
    mid = len(clean) // 2
    if len(clean) % 2:
        return clean[mid]
    return 0.5 * (clean[mid - 1] + clean[mid])


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _build_bathymetry(spec: DamSeedSpec) -> list[dict]:
    levels = spec.bathymetry.levels_m
    fractions = spec.bathymetry.area_fractions
    max_area_m2 = spec.bathymetry.max_area_km2 * 1_000_000.0
    areas_m2 = [f * max_area_m2 for f in fractions]

    def raw_volumes(areas: list[float]) -> list[float]:
        volumes = [0.0]
        for index in range(1, len(levels)):
            h1, h2 = levels[index - 1], levels[index]
            a1, a2 = areas[index - 1], areas[index]
            delta = (h2 - h1) / 3.0 * (a1 + a2 + math.sqrt(a1 * a2))
            volumes.append(volumes[-1] + max(0.0, delta))
        return volumes

    raw = raw_volumes(areas_m2)
    if raw[-1] <= 0:
        raise CommandError(f"bathymetry for {spec.slug} has zero volume")
    scale = spec.capacity_m3 / raw[-1]
    areas_m2 = [area * scale for area in areas_m2]
    volumes = raw_volumes(areas_m2)
    return [
        {
            "elevation_m": levels[i],
            "area_km2": areas_m2[i] / 1_000_000.0,
            "volume_m3": volumes[i],
            "order": i,
        }
        for i in range(len(levels))
    ]


def _seasonal_rain_weight(month: int, wet_months: tuple[int, ...]) -> float:
    return 2.4 if month in wet_months else 0.28


def _seasonal_pet_weight(month: int) -> float:
    # Northern-hemisphere summer peak, winter trough.
    return 1.0 + 0.30 * math.cos(2.0 * math.pi * (month - 7) / 12.0)


def _generate_daily_climate(
    spec: DamSeedSpec, dates: list[dt.date], rng
) -> list[dict]:
    soil = spec.climate.soil_saturation
    mean_wet = max(1.0, spec.climate.annual_rain_mm / spec.climate.rain_days_per_year)
    rows: list[dict] = []
    for date in dates:
        month = date.month
        wet_weight = _seasonal_rain_weight(month, spec.climate.wet_months)
        rain_probability = min(
            0.95, spec.climate.rain_days_per_year / 365.0 * wet_weight
        )
        if rng.random() < rain_probability:
            precip = max(0.2, rng.expovariate(1.0 / mean_wet))
            if rng.random() < 0.08:
                precip *= 2.5
        else:
            precip = 0.0
        soil = _clamp(soil + 0.045 * precip - 0.012, 0.03, 0.98)
        pet = max(
            0.2,
            spec.climate.pet_mean_mm_day
            * _seasonal_pet_weight(month)
            + rng.gauss(0.0, 0.35),
        )
        et = max(
            0.0,
            pet
            * spec.climate.et_pet_ratio
            * (0.72 + 0.55 * soil)
            + rng.gauss(0.0, 0.08),
        )
        lst = (
            spec.climate.lst_mean_k
            + 3.0 * math.cos(2.0 * math.pi * (month - 7) / 12.0)
            + rng.gauss(0.0, 0.45)
        )
        rows.append(
            {
                "date": date,
                "precip_mm": round(precip, 4),
                "et_mm": round(et, 4),
                "pet_mm": round(pet, 4),
                "lst_k": round(lst, 4),
                "soil_moisture_m3m3": round(soil, 5),
            }
        )
    return rows


def _beni_current_window(as_of: dt.date) -> list[dict]:
    """Trailing 90 days calibrated to the signed Case B fixture.

    Rain at −13/−14/−15 days totals 108 mm and stays inside the projected
    30-day window after the 14-day forecast (+65 mm = 173 mm). One 8 mm event
    at −36 days makes the 90-day total 116 mm (→ 181 mm projected).
    """
    rows: list[dict] = []
    for offset in range(90, -1, -1):
        date = as_of - dt.timedelta(days=offset)
        ago = offset
        precip = 0.0
        if ago == 13:
            precip = 40.0
        elif ago == 14:
            precip = 40.0
        elif ago == 15:
            precip = 28.0
        elif ago == 36:
            precip = 8.0
        soil = 0.85 if ago < 15 else 0.62
        pet = 4.0
        et = 0.54 if ago == 0 else 0.54 + 0.004 * (15 - min(15, ago))
        lst = 315.0 if ago == 0 else 313.4 + 0.006 * (15 - min(15, ago))
        rows.append(
            {
                "date": date,
                "precip_mm": precip,
                "et_mm": round(et, 4),
                "pet_mm": pet,
                "lst_k": round(lst, 4),
                "soil_moisture_m3m3": soil,
            }
        )
    return rows


def _fill_values(
    spec: DamSeedSpec, rng, years: list[int]
) -> dict[int, dict[int, float]]:
    """year → week → fill_pct (baseline years only)."""
    values: dict[int, dict[int, float]] = defaultdict(dict)
    low, high = 3.0, 95.0
    for index, year in enumerate(years):
        for week in range(1, 53):
            phase = 2.0 * math.pi * (week - 8) / 52.0
            base = 42.0 + 16.0 * math.cos(phase) + rng.gauss(0.0, 4.0)
            values[year][week] = round(_clamp(base, low, high), 3)
        if spec.slug == "beni-haroun":
            values[year][46] = float(SSI_W46[index])
            values[year][48] = float(SSI_W48[index])
    return values


def _weekly_dates(year: int) -> list[dt.date]:
    start = dt.date(year, 1, 1)
    return [start + dt.timedelta(days=7 * week) for week in range(52)]


def _compute_weekly_climate_bins(
    spec: DamSeedSpec,
    years: list[int],
    climate_by_date: dict[dt.date, dict],
) -> dict[str, dict[int, list[float]]]:
    metrics: dict[str, dict[int, list[float]]] = {
        metric: defaultdict(list) for metric in METRICS
    }
    for year in years:
        for week in range(1, 53):
            d = dt.date(year, 1, 1) + dt.timedelta(days=7 * (week - 1) + 3)
            window_30 = [
                climate_by_date[day]
                for day in (
                    d - dt.timedelta(days=offset) for offset in range(30)
                )
                if day in climate_by_date
            ]
            window_90 = [
                climate_by_date[day]
                for day in (
                    d - dt.timedelta(days=offset) for offset in range(90)
                )
                if day in climate_by_date
            ]
            p30 = sum(row["precip_mm"] for row in window_30)
            p90 = sum(row["precip_mm"] for row in window_90)
            metrics["cmi_p30"][week].append(round(p30, 4))
            metrics["cmi_p90"][week].append(round(p90, 4))

            dry = 0
            for offset in range(180):
                day = d - dt.timedelta(days=offset)
                row = climate_by_date.get(day)
                if row is None:
                    break
                if row["precip_mm"] > 5.0:
                    break
                dry += 1
            metrics["dry_spell"][week].append(float(min(180, dry)))

            latest = climate_by_date.get(d, {})
            pet = latest.get("pet_mm", spec.climate.pet_mean_mm_day)
            et = latest.get("et_mm", pet * spec.climate.et_pet_ratio)
            metrics["eesi_esi"][week].append(round(et / pet if pet > 0 else 0.0, 5))
            anomaly = latest.get("lst_k", spec.climate.lst_mean_k) - spec.climate.lst_mean_k
            metrics["eesi_lst_anom"][week].append(round(anomaly, 4))
    return metrics


def _c_ref_at_week(
    spec: DamSeedSpec, week: int, soil: float, p_ref: float
) -> float:
    cn_ii = _clamp(spec.climate.cn_ii, 1.0, 99.0)
    cn_i = _clamp(4.2 * cn_ii / (10.0 - 0.058 * cn_ii), 1.0, 100.0)
    cn_iii = _clamp(23.0 * cn_ii / (10.0 + 0.13 * cn_ii), 1.0, 100.0)
    saturation = _clamp((soil - 0.12) / (0.32 - 0.12), 0.0, 1.0)
    cn_eff = cn_i + saturation * (cn_iii - cn_i)
    storage = max(1.0, 25400.0 / cn_eff - 254.0)
    if p_ref <= 0.2 * storage:
        return 0.0
    runoff = (p_ref - 0.2 * storage) ** 2 / (p_ref + 0.8 * storage)
    return runoff / p_ref


class Command(BaseCommand):
    help = "Seed deterministic pilot countries, dams, climate, GRACE, forecasts, and bins."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true")
        parser.add_argument("--as-of", default="2026-11-13")
        parser.add_argument("--country", default="DZA,TUN")
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument("--years", type=int, default=26)
        parser.add_argument("--dams", default="")

    def handle(self, *args, **options):
        as_of = self._parse_date(options["as_of"])
        countries = {c.strip().upper() for c in options["country"].split(",") if c.strip()}
        unknown = countries - set(PILOT_COUNTRIES)
        if unknown:
            raise CommandError(f"unknown pilot countries: {sorted(unknown)}")
        dam_filter = {d.strip() for d in options["dams"].split(",") if d.strip()}

        years = max(1, int(options["years"]))
        baseline_end_year = as_of.year - 1
        baseline_start_year = baseline_end_year - years + 1
        selected = [
            spec
            for spec in PILOT_DAMS_BY_SLUG.values()
            if spec.country_iso3 in countries
            and (not dam_filter or spec.slug in dam_filter)
        ]
        if not selected:
            raise CommandError("no pilot dams matched the filters")

        with transaction.atomic():
            if options["reset"]:
                # Dam.basin is PROTECT, so remove dams first; their observations
                # cascade, then the country/basin tree can be rebuilt cleanly.
                Dam.objects.filter(country__iso3__in=countries).delete()
                Country.objects.filter(iso3__in=countries).delete()
            for iso3 in sorted(countries):
                country_spec = PILOT_COUNTRIES[iso3]
                Country.objects.update_or_create(
                    iso3=iso3,
                    defaults={
                        "name": country_spec.name,
                        "bbox": list(country_spec.bbox),
                        "timezone": country_spec.timezone,
                        "baseline_start": dt.date(baseline_start_year, 1, 1),
                        "baseline_end": dt.date(baseline_end_year, 12, 31),
                        "data_provider": "seeded",
                        "metadata": {
                            "baseline_years": years,
                            "seed": options["seed"],
                            "data_mode": "seeded",
                        },
                    },
                )
            for spec in selected:
                self._seed_dam(spec, as_of, baseline_start_year, baseline_end_year,
                               int(options["seed"]), years)
        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {len(selected)} dams across {len(countries)} countries "
                f"({baseline_start_year}–{baseline_end_year} baseline, as-of {as_of})."
            )
        )

    @staticmethod
    def _parse_date(value: str) -> dt.date:
        try:
            return dt.date.fromisoformat(value)
        except ValueError as exc:
            raise CommandError(f"invalid --as-of date: {value}") from exc

    def _seed_dam(
        self,
        spec: DamSeedSpec,
        as_of: dt.date,
        baseline_start_year: int,
        baseline_end_year: int,
        seed: int,
        years: int,
    ) -> None:
        # Freeze the year range onto a shallow copy so generator helpers can
        # read it without threading another argument through every call.
        country = Country.objects.get(iso3=spec.country_iso3)
        basin, _ = Basin.objects.update_or_create(
            country=country,
            hydrosheds_id=spec.hydrosheds_id,
            defaults={
                "name": spec.basin_name,
                "area_km2": spec.basin_area_km2,
                "geometry": self._basin_polygon(spec),
                "centroid_lat": spec.lat,
                "centroid_lon": spec.lon,
                "source": "seeded",
                "metadata": {"calibration": "approx polygon", "seed": seed},
            },
        )
        max_area = spec.max_surface_area_km2
        dam, _ = Dam.objects.update_or_create(
            slug=spec.slug,
            defaults={
                "country": country,
                "basin": basin,
                "name": spec.name,
                "name_ar": spec.name_ar,
                "name_fr": spec.name_fr,
                "lat": spec.lat,
                "lon": spec.lon,
                "capacity_m3": spec.capacity_m3,
                "dead_storage_m3": spec.dead_storage_m3,
                "max_surface_area_km2": max_area,
                "dam_type": spec.dam_type,
                "year_built": spec.year_built,
                "purposes": list(spec.purposes),
                "source_ids": ["seeded", "literature"],
                "metadata": {
                    **spec.metadata,
                    "capacity_confidence": spec.capacity_confidence,
                    "baseline_years": years,
                    "seed": seed,
                    "not_for_operational_decisions": True,
                },
            },
        )
        bathymetry = _build_bathymetry(spec)
        dam.bathymetry.all().delete()
        BathymetryPoint.objects.bulk_create(
            [BathymetryPoint(dam=dam, **point) for point in bathymetry],
            batch_size=500,
        )

        rng = __import__("random").Random(seed ^ zlib.crc32(spec.slug.encode("utf-8")))
        years_list = list(range(baseline_start_year, baseline_end_year + 1))

        ClimateObservation.objects.filter(basin=basin).delete()
        ReservoirObservation.objects.filter(dam=dam).delete()
        ForecastObservation.objects.filter(basin=basin).delete()
        GraceObservation.objects.filter(basin=basin).delete()
        DemandObservation.objects.filter(dam=dam).delete()
        ClimatologyBin.objects.filter(scope_type="dam", scope_id=spec.slug).delete()

        climate_by_date: dict[dt.date, dict] = {}
        climate_rows: list[dict] = []
        baseline_start = dt.date(baseline_start_year, 1, 1)
        baseline_end = dt.date(baseline_end_year, 12, 31)
        all_days = (baseline_end - baseline_start).days + 1
        dates = [baseline_start + dt.timedelta(days=i) for i in range(all_days)]
        for row in _generate_daily_climate(spec, dates, rng):
            climate_by_date[row["date"]] = row
            climate_rows.append({**row, "basin_id": basin.id, "source": "seeded"})

        if spec.slug == "beni-haroun":
            current_rows = _beni_current_window(as_of)
        else:
            current_dates = [as_of - dt.timedelta(days=i) for i in range(90, -1, -1)]
            current_rows = _generate_daily_climate(spec, current_dates, rng)
        for row in current_rows:
            climate_by_date[row["date"]] = row
            climate_rows.append({**row, "basin_id": basin.id, "source": "seeded"})

        ClimateObservation.objects.bulk_create(
            [ClimateObservation(**row) for row in climate_rows], batch_size=2000
        )

        fills = _fill_values(spec, rng, years_list)
        reservoir_rows: list[ReservoirObservation] = []
        for year in years_list:
            for week, date in enumerate(_weekly_dates(year), start=1):
                fill = fills[year][week]
                volume = spec.dead_storage_m3 + fill / 100.0 * (
                    spec.capacity_m3 - spec.dead_storage_m3
                )
                reservoir_rows.append(
                    ReservoirObservation(
                        dam=dam,
                        date=date,
                        fill_pct=fill,
                        volume_m3=volume,
                        water_area_km2=surface_area_at_volume_m2(
                            volume, bathymetry
                        )
                        / 1_000_000.0,
                        source="seeded",
                        quality="OK",
                    )
                )
        current_volume = spec.dead_storage_m3 + spec.current.fill_pct / 100.0 * (
            spec.capacity_m3 - spec.dead_storage_m3
        )
        reservoir_rows.append(
            ReservoirObservation(
                dam=dam,
                date=as_of,
                fill_pct=spec.current.fill_pct,
                volume_m3=current_volume,
                water_area_km2=surface_area_at_volume_m2(current_volume, bathymetry)
                / 1_000_000.0,
                source="seeded",
                quality="OK",
            )
        )
        ReservoirObservation.objects.bulk_create(reservoir_rows, batch_size=2000)

        forecast_rows = self._forecast_rows(spec, as_of, rng)
        ForecastObservation.objects.bulk_create(
            [ForecastObservation(basin=basin, **row) for row in forecast_rows],
            batch_size=500,
        )

        current_area_m2 = surface_area_at_volume_m2(current_volume, bathymetry)
        current_evap_loss = (
            current_area_m2 * spec.climate.pet_mean_mm_day * 1e-3
        )
        effective_release = max(
            0.0, spec.current.demand_m3_day - current_evap_loss
        )

        demand_rows = []
        for offset in range(365, -1, -1):
            date = as_of - dt.timedelta(days=offset)
            if offset == 0:
                value = effective_release
            else:
                season = 1.12 if date.month in (6, 7, 8, 9) else 0.92
                value = max(
                    0.0,
                    effective_release * season
                    + rng.gauss(0.0, spec.current.demand_m3_day * 0.02),
                )
            demand_rows.append(
                DemandObservation(
                    dam=dam,
                    date=date,
                    demand_m3_day=round(value, 2),
                    source="seeded",
                )
            )
        DemandObservation.objects.bulk_create(demand_rows, batch_size=1000)

        grace_rows = self._grace_rows(spec, as_of, baseline_start_year)
        GraceObservation.objects.bulk_create(
            [GraceObservation(basin=basin, **row) for row in grace_rows], batch_size=1000
        )

        weekly = _compute_weekly_climate_bins(spec, years_list, climate_by_date)
        bins = self._build_bins(
            spec, dam, bathymetry, years_list, fills, weekly, as_of, current_volume, rng
        )
        ClimatologyBin.objects.bulk_create(
            [ClimatologyBin(scope_type="dam", scope_id=spec.slug, **row) for row in bins],
            batch_size=2000,
        )

        # Persist the projected-state hints used by the HRI synthesizer.
        if spec.slug == "beni-haroun":
            projected_volume = 69_800_000.0
            projected_pet, _ratio_projected = self._projected_evap_state(
                spec, bathymetry, current_volume
            )
            dam.metadata.update(
                {
                    "projected_pet_mm_day": round(projected_pet, 4),
                    "projected_et_pet_ratio": 0.18,
                    "projected_lst_anomaly_k": 0.0,
                    "projected_volume_m3": projected_volume,
                }
            )
        else:
            dam.metadata.update(
                {
                    "projected_pet_mm_day": round(spec.climate.pet_mean_mm_day, 4),
                    "projected_et_pet_ratio": round(spec.climate.et_pet_ratio, 4),
                    "projected_lst_anomaly_k": round(spec.current.lst_anomaly_k * 0.5, 4),
                }
            )
        dam.metadata.update(
            {
                "lst_mean_k": spec.climate.lst_mean_k,
                "et_pet_ratio": spec.climate.et_pet_ratio,
                "cn_ii": spec.climate.cn_ii,
                "theta_wp": 0.12,
                "theta_fc": 0.32,
                "design_storm_mm": spec.current.design_storm_mm,
                "base_release_m3_day": round(effective_release, 2),
                "evap_loss_current_m3_day": round(current_evap_loss, 2),
                "projected_soil_moisture": (
                    0.85 if spec.slug == "beni-haroun"
                    else round(min(0.98, spec.climate.soil_saturation * 1.05), 4)
                ),
            }
        )
        dam.save(update_fields=["metadata"])

    def _forecast_rows(self, spec: DamSeedSpec, as_of: dt.date, rng) -> list[dict]:
        issued_at = timezone.make_aware(
            dt.datetime.combine(as_of, dt.time(12, 0)), dt.timezone.utc
        )
        rows: list[dict] = []
        for day in range(1, 15):
            date = as_of + dt.timedelta(days=day)
            if spec.slug == "beni-haroun":
                precip = 16.25 if day <= 4 else 0.0
            elif spec.current.storm_total_mm > 0 and day <= spec.current.storm_days:
                precip = spec.current.storm_total_mm / max(1, spec.current.storm_days)
            elif day in (3, 4) and rng.random() < 0.4:
                precip = round(rng.uniform(8.0, 28.0), 2)
            else:
                precip = 0.0
            rows.append(
                {
                    "issued_at": issued_at,
                    "date": date,
                    "precip_mm": round(float(precip), 3),
                    "source": "seeded",
                    "confidence": 0.9 if spec.slug == "beni-haroun" else 0.75,
                }
            )
        return rows

    def _grace_rows(
        self, spec: DamSeedSpec, as_of: dt.date, baseline_start_year: int
    ) -> list[dict]:
        rows = []
        month = dt.date(baseline_start_year, 1, 1)
        rng = __import__("random").Random(zlib.crc32(f"grace:{spec.slug}".encode()))
        while month <= as_of:
            skip = (
                (month.year == 2000 or month.year == 2001)
                or (month.year == 2017 or month.year == 2018)
            )
            if not skip:
                years_in = month.year + (month.month - 1) / 12.0 - baseline_start_year
                gwsa = (
                    spec.current.grace_trend_mm_yr * years_in
                    + 6.0 * math.sin(2.0 * math.pi * (month.month - 3) / 12.0)
                    + rng.gauss(0.0, 2.5)
                )
                twsa = gwsa / 0.80
                rows.append(
                    {
                        "month": month,
                        "twsa_mm": round(twsa, 4),
                        "smsa_mm": round(twsa * 0.15, 4),
                        "swsa_mm": round(twsa * 0.05, 4),
                        "source": "seeded",
                    }
                )
            month = (
                dt.date(month.year + 1, 1, 1)
                if month.month == 12
                else dt.date(month.year, month.month + 1, 1)
            )
        return rows

    def _build_bins(
        self,
        spec: DamSeedSpec,
        dam: Dam,
        bathymetry: list[dict],
        years: list[int],
        fills: dict[int, dict[int, float]],
        weekly: dict[str, dict[int, list[float]]],
        as_of: dt.date,
        current_volume: float,
        rng,
    ) -> list[dict]:
        per_metric: dict[str, dict[int, list[float]]] = {
            metric: defaultdict(list) for metric in METRICS
        }
        p_ref = spec.current.design_storm_mm or 25.0
        for year in years:
            for week in range(1, 53):
                fill = fills[year][week]
                per_metric["ssi_fill_pct"][week].append(fill)
                per_metric["analog_fill_pct"][week].append(fill)
                volume = spec.dead_storage_m3 + fill / 100.0 * (
                    spec.capacity_m3 - spec.dead_storage_m3
                )
                usable = max(1.0, volume - spec.dead_storage_m3)
                area_m2 = surface_area_at_volume_m2(volume, bathymetry)
                pet = spec.climate.pet_mean_mm_day
                evap_ratio = area_m2 * pet * 1e-3 / usable
                per_metric["eesi_evap_ratio"][week].append(round(evap_ratio, 8))
                soil = 0.12 + 0.20 * (0.35 + 0.65 * fill / 100.0)
                per_metric["srri_c_ref"][week].append(
                    round(_c_ref_at_week(spec, week, soil, p_ref), 6)
                )
        for metric in ("cmi_p30", "cmi_p90", "dry_spell", "eesi_esi", "eesi_lst_anom"):
            for week, values in weekly[metric].items():
                per_metric[metric][week] = list(values)

        # SAI regional diagnostic bins (monthly GWSA mapped to weeks).
        grace = list(
            GraceObservation.objects.filter(basin=dam.basin).order_by("month")
        )
        for row in grace:
            gwsa = (row.twsa_mm or 0.0) - (row.smsa_mm or 0.0) - (row.swsa_mm or 0.0)
            for week in range(1, 53):
                per_metric["sai_gwsa"][week].append(round(gwsa, 4))

        if spec.slug == "beni-haroun":
            per_metric["ssi_fill_pct"][46] = list(SSI_W46)
            per_metric["ssi_fill_pct"][48] = list(SSI_W48)
            per_metric["analog_fill_pct"][46] = list(SSI_W46)
            per_metric["analog_fill_pct"][48] = list(SSI_W48)
            per_metric["cmi_p30"][46] = list(CMI_P30)
            per_metric["cmi_p30"][48] = list(CMI_P30)
            per_metric["cmi_p90"][46] = list(CMI_P90)
            per_metric["cmi_p90"][48] = list(CMI_P90)
            per_metric["dry_spell"][46] = list(DRY_BASE)
            per_metric["dry_spell"][48] = list(DRY_BASE)
            per_metric["srri_c_ref"][46] = list(C_REF_BASE)
            per_metric["srri_c_ref"][48] = list(C_REF_BASE)

            current_area = surface_area_at_volume_m2(current_volume, bathymetry)
            ratio_current = current_area * 4.0e-3 / max(
                1.0, current_volume - spec.dead_storage_m3
            )
            _pet_projected, ratio_projected = self._projected_evap_state(
                spec, bathymetry, current_volume
            )
            midpoint = 0.5 * (ratio_current + ratio_projected)
            evap_base = (
                [ratio_current * (0.5 + 0.45 * i / 12.0) for i in range(13)]
                + [midpoint]
                + [ratio_projected * (1.05 + 0.45 * i / 11.0) for i in range(12)]
            )
            base_esi = (
                [0.06 + 0.07 * i / 12.0 for i in range(13)]
                + [0.14 + 0.03 * i / 7.0 for i in range(7)]
                + [0.19 + 0.11 * i / 5.0 for i in range(6)]
            )
            base_lst = (
                [-3.0 + 2.5 * i / 10.0 for i in range(11)]
                + [0.5, 1.5]
                + [2.2 + 1.8 * i / 12.0 for i in range(13)]
            )
            for week in (46, 48):
                per_metric["eesi_evap_ratio"][week] = [round(v, 8) for v in evap_base]
                per_metric["eesi_esi"][week] = [round(v, 5) for v in base_esi]
                per_metric["eesi_lst_anom"][week] = [round(v, 4) for v in base_lst]

        for week in range(1, 53):
            fills_for_week = per_metric["analog_fill_pct"][week]
            baseline_median = _median(fills_for_week)
            per_metric["analog_storage_anomaly"][week] = [
                round(value - baseline_median, 4) for value in fills_for_week
            ]

        rows: list[dict] = []
        for metric in METRICS:
            for week in range(1, 53):
                values = per_metric[metric][week]
                clean = [float(v) for v in values if v is not None and math.isfinite(float(v))]
                rows.append(
                    {
                        "metric": metric,
                        "week": week,
                        "values": clean,
                        "n": len(clean),
                        "mean": round(sum(clean) / len(clean), 6) if clean else None,
                        "std": round(
                            (
                                sum((v - sum(clean) / len(clean)) ** 2 for v in clean)
                                / len(clean)
                            )
                            ** 0.5,
                            6,
                        )
                        if clean
                        else None,
                    }
                )
        return rows

    @staticmethod
    def _projected_evap_state(
        spec: DamSeedSpec, bathymetry: list[dict], current_volume: float
    ) -> tuple[float, float]:
        """Return (projected PET mm/day, projected E_loss/V_u ratio).

        Beni Haroun's upper-basin widening alone does not outrun volume growth,
        so the projected PET is raised enough to make the ratio 20% above the
        current one. The same pair feeds the baseline and the provider metadata.
        """
        if spec.slug != "beni-haroun":
            area = surface_area_at_volume_m2(current_volume, bathymetry)
            usable = max(1.0, current_volume - spec.dead_storage_m3)
            pet = spec.climate.pet_mean_mm_day
            return pet, area * pet * 1e-3 / usable
        projected_volume = 69_800_000.0
        area = surface_area_at_volume_m2(projected_volume, bathymetry)
        usable = max(1.0, projected_volume - spec.dead_storage_m3)
        current_area = surface_area_at_volume_m2(current_volume, bathymetry)
        current_usable = max(1.0, current_volume - spec.dead_storage_m3)
        current_ratio = current_area * 4.0e-3 / current_usable
        pet = 6.5
        ratio = area * pet * 1e-3 / usable
        if ratio <= current_ratio:
            pet = current_ratio * 1.20 * usable / max(1.0, area) * 1_000.0
            ratio = current_ratio * 1.20
        return pet, ratio

    @staticmethod
    def _basin_polygon(spec: DamSeedSpec) -> dict:
        d = 0.22
        return {
            "type": "Polygon",
            "coordinates": [
                [
                    [round(spec.lon - d, 4), round(spec.lat - d, 4)],
                    [round(spec.lon + d, 4), round(spec.lat - d, 4)],
                    [round(spec.lon + d, 4), round(spec.lat + d, 4)],
                    [round(spec.lon - d, 4), round(spec.lat + d, 4)],
                    [round(spec.lon - d, 4), round(spec.lat - d, 4)],
                ]
            ],
        }
