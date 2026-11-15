"""Composite provider: prefer live data, fall back to deterministic seed."""
from __future__ import annotations

import datetime as dt

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
from core.services.exceptions import HydroDataError
from core.services.providers.base import BaseProvider


class CompositeProvider(BaseProvider):
    name = "composite"

    def __init__(self, primary, fallback):
        self.primary = primary
        self.fallback = fallback
        self.data_mode = getattr(primary, "data_mode", "unknown")

    def _fallback(self, method: str, *args, **kwargs):
        result = getattr(self.fallback, method)(*args, **kwargs)
        self.data_mode = self.fallback.data_mode
        return result

    def _call(self, method: str, *args, **kwargs):
        try:
            result = getattr(self.primary, method)(*args, **kwargs)
            self.data_mode = self.primary.data_mode
            return result
        except (HydroDataError, AttributeError, NotImplementedError):
            return self._fallback(method, *args, **kwargs)

    def build_context(
        self, dam_slug: str, as_of: dt.date | None = None
    ) -> IndexContext:
        try:
            ctx = self.primary.build_context(dam_slug, as_of)
            self.data_mode = getattr(self.primary, "data_mode", "unknown")
            return ctx
        except (HydroDataError, AttributeError, NotImplementedError):
            ctx = self.fallback.build_context(dam_slug, as_of)
            self.data_mode = self.fallback.data_mode
            ctx.data_mode = self.fallback.data_mode
            return ctx

    def get_dam_snapshot(self, dam_slug: str, as_of: dt.date | None = None) -> DamSnapshot:
        return self._call("get_dam_snapshot", dam_slug, as_of)

    def get_basin_snapshot(self, dam_slug: str) -> BasinSnapshot:
        return self._call("get_basin_snapshot", dam_slug)

    def get_climate_window(self, dam_slug: str, as_of: dt.date, days: int = 400) -> ClimateWindow:
        return self._call("get_climate_window", dam_slug, as_of, days)

    def get_forecast(self, dam_slug: str, as_of: dt.date) -> ForecastWindow:
        return self._call("get_forecast", dam_slug, as_of)

    def get_grace_window(self, dam_slug: str, as_of: dt.date) -> GraceWindow:
        return self._call("get_grace_window", dam_slug, as_of)

    def get_et_window(self, dam_slug: str, as_of: dt.date, days: int = 90) -> ETWindow:
        return self._call("get_et_window", dam_slug, as_of, days)

    def get_demand_window(self, dam_slug: str, as_of: dt.date, days: int = 365) -> DemandWindow:
        return self._call("get_demand_window", dam_slug, as_of, days)

    def get_climatology(
        self, dam_slug: str
    ) -> dict[str, dict[int, ClimatologyBinData]]:
        return self._call("get_climatology", dam_slug)
