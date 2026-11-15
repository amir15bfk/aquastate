"""Provider protocol and shared context assembly."""
from __future__ import annotations

import datetime as dt
from typing import Protocol, runtime_checkable

from core.services.contracts import (
    BasinSnapshot,
    ClimatologyBinData,
    ClimateWindow,
    DamSnapshot,
    DemandWindow,
    ETWindow,
    ForecastWindow,
    GraceWindow,
    IndexContext,
)
from core.services.stats import week_bin


@runtime_checkable
class HydroDataProvider(Protocol):
    name: str
    data_mode: str

    def get_dam_snapshot(self, dam_slug: str, as_of: dt.date | None = None) -> DamSnapshot: ...
    def get_basin_snapshot(self, dam_slug: str) -> BasinSnapshot: ...
    def get_climate_window(self, dam_slug: str, as_of: dt.date, days: int = 400) -> ClimateWindow: ...
    def get_forecast(self, dam_slug: str, as_of: dt.date) -> ForecastWindow: ...
    def get_grace_window(self, dam_slug: str, as_of: dt.date) -> GraceWindow: ...
    def get_et_window(self, dam_slug: str, as_of: dt.date, days: int = 90) -> ETWindow: ...
    def get_demand_window(self, dam_slug: str, as_of: dt.date, days: int = 365) -> DemandWindow: ...
    def get_climatology(self, dam_slug: str) -> dict[str, dict[int, ClimatologyBinData]]: ...


class BaseProvider:
    name = "base"
    data_mode = "unknown"

    def build_context(self, dam_slug: str, as_of: dt.date | None = None) -> IndexContext:
        from core.services.providers.seeded import SeededProvider

        if as_of is None:
            as_of = SeededProvider.latest_as_of(dam_slug)
        if isinstance(as_of, str):
            as_of = dt.date.fromisoformat(as_of)
        dam = self.get_dam_snapshot(dam_slug, as_of)
        return IndexContext(
            dam=dam,
            basin=self.get_basin_snapshot(dam_slug),
            climate=self.get_climate_window(dam_slug, as_of),
            forecast=self.get_forecast(dam_slug, as_of),
            grace=self.get_grace_window(dam_slug, as_of),
            et=self.get_et_window(dam_slug, as_of),
            demand=self.get_demand_window(dam_slug, as_of),
            climatology=self.get_climatology(dam_slug),
            as_of=as_of,
            week=week_bin(as_of.timetuple().tm_yday),
            data_mode=self.data_mode,
            provider_name=self.name,
        )
