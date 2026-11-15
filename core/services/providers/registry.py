"""Provider registry selected by `HYDRO_DATA_PROVIDER`."""
from __future__ import annotations

import os

from django.conf import settings

from core.services.exceptions import ConfigurationError, ProviderUnavailable
from core.services.providers.base import HydroDataProvider
from core.services.providers.composite import CompositeProvider
from core.services.providers.earthdata import EarthdataProvider
from core.services.providers.gee import GEEProvider
from core.services.providers.seeded import SeededProvider

PROVIDERS = {
    "seeded": SeededProvider,
    "earthdata": EarthdataProvider,
    "gee": GEEProvider,
}


def get_provider(name: str | None = None) -> HydroDataProvider:
    requested = (
        name or os.environ.get("HYDRO_DATA_PROVIDER") or getattr(
            settings, "HYDRO_DATA_PROVIDER", "seeded"
        )
    ).strip().lower()

    if requested == "composite":
        primary = None
        for candidate in (EarthdataProvider, GEEProvider):
            try:
                primary = candidate()
                break
            except ProviderUnavailable:
                continue
        fallback = SeededProvider()
        return CompositeProvider(primary or fallback, fallback)

    factory = PROVIDERS.get(requested)
    if factory is None:
        raise ConfigurationError(
            f"unknown HYDRO_DATA_PROVIDER '{requested}'; choose seeded, earthdata, gee, or composite"
        )
    return factory()
