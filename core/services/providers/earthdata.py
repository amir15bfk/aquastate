"""NASA Earthdata adapter scaffold.

The MVP never claims live data. Construction fails without credentials and all
methods fail with `ProviderUnavailable`; no network request is made from this
module.
"""
from __future__ import annotations

import datetime as dt
import os

from core.services.contracts import (
    BasinSnapshot,
    ClimateWindow,
    DamSnapshot,
    DemandWindow,
    ETWindow,
    ForecastWindow,
    GraceWindow,
)
from core.services.exceptions import ProviderUnavailable
from core.services.providers.base import BaseProvider


class EarthdataProvider(BaseProvider):
    name = "earthdata"
    data_mode = "earthdata_live_candidate"

    def __init__(self):
        self.username = os.environ.get("EARTHDATA_USERNAME", "").strip()
        self.password = os.environ.get("EARTHDATA_PASSWORD", "").strip()
        if not (self.username and self.password):
            raise ProviderUnavailable(
                "Earthdata credentials are not configured; the MVP remains on seeded data"
            )

    def _not_live(self):
        raise ProviderUnavailable(
            "Earthdata live ingestion is scaffolded but not enabled in this MVP"
        )

    def get_dam_snapshot(self, dam_slug: str, as_of: dt.date | None = None) -> DamSnapshot:
        self._not_live()

    def get_basin_snapshot(self, dam_slug: str) -> BasinSnapshot:
        self._not_live()

    def get_climate_window(self, dam_slug: str, as_of: dt.date, days: int = 400) -> ClimateWindow:
        self._not_live()

    def get_forecast(self, dam_slug: str, as_of: dt.date) -> ForecastWindow:
        self._not_live()

    def get_grace_window(self, dam_slug: str, as_of: dt.date) -> GraceWindow:
        self._not_live()

    def get_et_window(self, dam_slug: str, as_of: dt.date, days: int = 90) -> ETWindow:
        self._not_live()

    def get_demand_window(self, dam_slug: str, as_of: dt.date, days: int = 365) -> DemandWindow:
        self._not_live()
