"""Seeded provider: reads the deterministic SQLite dataset only."""
from __future__ import annotations

import datetime as dt
import math

from core.models import Dam
from core.services.contracts import (
    BasinSnapshot,
    BathymetryPointData,
    ClimatologyBinData,
    ClimateDay,
    ClimateWindow,
    DamSnapshot,
    DemandDay,
    DemandWindow,
    ETDay,
    ETWindow,
    ForecastDay,
    ForecastWindow,
    GraceMonth,
    GraceWindow,
    IndexContext,
)
from core.services.exceptions import MissingDataError
from core.services.providers.base import BaseProvider
from core.services.stats import week_bin


def _number(value):
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else None


class SeededProvider(BaseProvider):
    name = "seeded"
    data_mode = "seeded"

    @staticmethod
    def latest_as_of(dam_slug: str) -> dt.date:
        dam = Dam.objects.filter(slug=dam_slug).first()
        if dam is None:
            raise MissingDataError(f"unknown dam: {dam_slug}")
        observation = dam.observations.order_by("-date").first()
        if observation is not None:
            return observation.date
        return dt.date.today()

    def _dam(self, dam_slug: str) -> Dam:
        dam = Dam.objects.select_related("basin", "country").filter(slug=dam_slug).first()
        if dam is None:
            raise MissingDataError(f"unknown dam: {dam_slug}")
        return dam

    def get_dam_snapshot(
        self, dam_slug: str, as_of: dt.date | None = None
    ) -> DamSnapshot:
        dam = self._dam(dam_slug)
        as_of = as_of or self.latest_as_of(dam_slug)
        observation = dam.observations.filter(date__lte=as_of).order_by("-date").first()
        bathymetry = [
            BathymetryPointData(
                elevation_m=point.elevation_m,
                area_km2=point.area_km2,
                volume_m3=point.volume_m3,
                order=point.order,
            )
            for point in dam.bathymetry.all()
        ]
        return DamSnapshot(
            slug=dam.slug,
            name=dam.name,
            name_ar=dam.name_ar,
            name_fr=dam.name_fr,
            country_iso3=dam.country.iso3,
            lat=dam.lat,
            lon=dam.lon,
            capacity_m3=dam.capacity_m3,
            dead_storage_m3=dam.dead_storage_m3,
            basin_area_km2=dam.basin.area_km2,
            bathymetry=bathymetry,
            max_surface_area_km2=dam.max_surface_area_km2,
            purposes=list(dam.purposes or []),
            metadata=dict(dam.metadata or {}),
            as_of=as_of,
            current_volume_m3=_number(observation.volume_m3) if observation else None,
            current_level_m=_number(observation.water_level_m) if observation else None,
            current_fill_pct=_number(observation.fill_pct) if observation else None,
            current_surface_area_km2=_number(observation.water_area_km2) if observation else None,
            observation_date=observation.date if observation else None,
            observation_quality=observation.quality if observation else "NO_DATA",
            observation_source=observation.source if observation else "none",
        )

    def get_basin_snapshot(self, dam_slug: str) -> BasinSnapshot:
        dam = self._dam(dam_slug)
        basin = dam.basin
        return BasinSnapshot(
            basin_id=basin.id,
            country_iso3=dam.country.iso3,
            name=basin.name,
            area_km2=basin.area_km2,
            hydrosheds_id=basin.hydrosheds_id,
            geometry=dict(basin.geometry or {}),
            centroid_lat=basin.centroid_lat,
            centroid_lon=basin.centroid_lon,
            metadata=dict(basin.metadata or {}),
        )

    def get_climate_window(
        self, dam_slug: str, as_of: dt.date, days: int = 400
    ) -> ClimateWindow:
        dam = self._dam(dam_slug)
        rows = list(
            dam.basin.climate.filter(date__lte=as_of)
            .order_by("-date")[:days]
        )
        rows.reverse()
        return ClimateWindow(
            days=[
                ClimateDay(
                    date=row.date,
                    precip_mm=_number(row.precip_mm),
                    et_mm=_number(row.et_mm),
                    pet_mm=_number(row.pet_mm),
                    lst_k=_number(row.lst_k),
                    soil_moisture_m3m3=_number(row.soil_moisture_m3m3),
                )
                for row in rows
            ],
            source="seeded",
        )

    def get_forecast(self, dam_slug: str, as_of: dt.date) -> ForecastWindow:
        dam = self._dam(dam_slug)
        rows = list(
            dam.basin.forecasts.filter(
                issued_at__date__lte=as_of, date__gt=as_of
            ).order_by("-issued_at", "date")
        )
        if rows:
            latest_issue = rows[0].issued_at
            rows = [row for row in rows if row.issued_at == latest_issue]
            rows.sort(key=lambda row: row.date)
        return ForecastWindow(
            days=[
                ForecastDay(
                    date=row.date,
                    precip_mm=_number(row.precip_mm),
                    confidence=row.confidence,
                    source=row.source,
                )
                for row in rows
            ],
            issued_at=rows[0].issued_at if rows else None,
            confidence=min((row.confidence for row in rows), default=1.0),
            forecast_type="deterministic_single",
            source="seeded",
        )

    def get_grace_window(self, dam_slug: str, as_of: dt.date) -> GraceWindow:
        dam = self._dam(dam_slug)
        rows = list(
            dam.basin.grace.filter(month__lte=as_of).order_by("month")
        )
        return GraceWindow(
            months=[
                GraceMonth(
                    month=row.month,
                    twsa_mm=_number(row.twsa_mm),
                    smsa_mm=_number(row.smsa_mm),
                    swsa_mm=_number(row.swsa_mm),
                )
                for row in rows
            ],
            basin_area_km2=dam.basin.area_km2,
            baseline_epoch=rows[0].month if rows else None,
            kernel_corrected=False,
            source="seeded",
        )

    def get_et_window(
        self, dam_slug: str, as_of: dt.date, days: int = 90
    ) -> ETWindow:
        climate = self.get_climate_window(dam_slug, as_of, days=days)
        return ETWindow(
            days=[
                ETDay(date=day.date, et_mm=day.et_mm, pet_mm=day.pet_mm, lst_k=day.lst_k)
                for day in climate.days
            ],
            source="seeded",
        )

    def get_demand_window(
        self, dam_slug: str, as_of: dt.date, days: int = 365
    ) -> DemandWindow:
        dam = self._dam(dam_slug)
        rows = list(
            dam.demands.filter(date__lte=as_of).order_by("-date")[:days]
        )
        rows.reverse()
        return DemandWindow(
            days=[DemandDay(date=row.date, demand_m3_day=row.demand_m3_day) for row in rows],
            source="seeded",
        )

    def get_climatology(
        self, dam_slug: str
    ) -> dict[str, dict[int, ClimatologyBinData]]:
        from core.models import ClimatologyBin

        result: dict[str, dict[int, ClimatologyBinData]] = {}
        for row in ClimatologyBin.objects.filter(scope_type="dam", scope_id=dam_slug):
            values = [_number(value) for value in row.values or []]
            clean = [value for value in values if value is not None]
            result.setdefault(row.metric, {})[row.week] = ClimatologyBinData(
                metric=row.metric,
                week=row.week,
                values=clean,
                n=row.n,
                mean=_number(row.mean),
                std=_number(row.std),
            )
        return result

    def build_context(self, dam_slug: str, as_of: dt.date | None = None) -> IndexContext:
        as_of = as_of or self.latest_as_of(dam_slug)
        if isinstance(as_of, str):
            as_of = dt.date.fromisoformat(as_of)
        ctx = super().build_context(dam_slug, as_of)
        ctx.week = week_bin(as_of.timetuple().tm_yday)
        return ctx
