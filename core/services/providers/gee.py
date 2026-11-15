"""Google Earth Engine adapter scaffold. No live call exists in the MVP."""
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


class GEEProvider(BaseProvider):
    name = "gee"
    data_mode = "gee_live_candidate"

    def __init__(self):
        self.service_account = os.environ.get("GEE_SERVICE_ACCOUNT", "").strip()
        self.key_file = os.environ.get("GEE_PRIVATE_KEY_FILE", "").strip()
        if not (self.service_account and self.key_file):
            raise ProviderUnavailable(
                "GEE credentials are not configured; the MVP remains on seeded data"
            )

    def _not_live(self):
        raise ProviderUnavailable(
            "GEE live ingestion is scaffolded but not enabled in this MVP"
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
