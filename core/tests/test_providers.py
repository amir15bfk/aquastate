import datetime as dt

import pytest
from django.core.management import call_command

from core.services.contracts import IndexContext
from core.services.exceptions import ProviderUnavailable
from core.services.providers.composite import CompositeProvider
from core.services.providers.earthdata import EarthdataProvider
from core.services.providers.gee import GEEProvider
from core.services.providers.registry import get_provider
from core.services.providers.seeded import SeededProvider


@pytest.fixture
def seeded_db(db):
    call_command(
        "seed_hydro_data",
        reset=True,
        as_of="2026-11-13",
        country="DZA",
        years=3,
        dams="beni-haroun",
        seed=42,
        verbosity=0,
    )


def test_seeded_provider_builds_complete_context(seeded_db):
    provider = SeededProvider()
    ctx = provider.build_context("beni-haroun", dt.date(2026, 11, 13))

    assert isinstance(ctx, IndexContext)
    assert ctx.dam.slug == "beni-haroun"
    assert ctx.dam.country_iso3 == "DZA"
    assert ctx.dam.usable_capacity_m3 == pytest.approx(90_000_000.0)
    assert ctx.dam.current_fill_pct == pytest.approx(18.0)
    assert ctx.dam.current_volume_m3 == pytest.approx(26_200_000.0)
    assert len(ctx.dam.bathymetry) == 8
    assert ctx.basin.area_km2 == pytest.approx(2_000.0)
    assert len(ctx.climate.days) > 90
    assert len(ctx.forecast.days) == 14
    assert all(day.precip_mm is not None for day in ctx.forecast.days)
    assert len(ctx.grace.months) > 0
    assert len(ctx.demand.days) == 365
    assert ctx.week == 46
    assert ctx.data_mode == "seeded"
    assert len(ctx.climatology_values("ssi_fill_pct")) == 26
    assert len(ctx.climatology_values("cmi_p30")) == 26
    assert set(ctx.climatology) >= {
        "ssi_fill_pct",
        "cmi_p90",
        "cmi_p30",
        "dry_spell",
        "srri_c_ref",
        "sai_gwsa",
        "eesi_esi",
        "eesi_evap_ratio",
        "eesi_lst_anom",
    }


@pytest.mark.django_db
def test_live_adapters_require_credentials(monkeypatch):
    monkeypatch.delenv("EARTHDATA_USERNAME", raising=False)
    monkeypatch.delenv("EARTHDATA_PASSWORD", raising=False)
    monkeypatch.delenv("GEE_SERVICE_ACCOUNT", raising=False)
    monkeypatch.delenv("GEE_PRIVATE_KEY_FILE", raising=False)

    with pytest.raises(ProviderUnavailable):
        EarthdataProvider()
    with pytest.raises(ProviderUnavailable):
        GEEProvider()
    with pytest.raises(ProviderUnavailable):
        get_provider("earthdata")
    with pytest.raises(ProviderUnavailable):
        get_provider("gee")


def test_composite_falls_back_to_seeded(seeded_db):
    class Broken:
        name = "broken"
        data_mode = "live"

        def get_dam_snapshot(self, *args, **kwargs):
            raise ProviderUnavailable("no credentials")

    fallback = SeededProvider()
    composite = CompositeProvider(Broken(), fallback)
    ctx = composite.build_context("beni-haroun", dt.date(2026, 11, 13))
    assert ctx.data_mode == "seeded"
    assert composite.data_mode == "seeded"
    assert ctx.dam.slug == "beni-haroun"


def test_unknown_provider_is_configuration_error():
    from core.services.exceptions import ConfigurationError

    with pytest.raises(ConfigurationError):
        get_provider("not-a-provider")


def test_no_network_call_in_seeded_context(seeded_db, monkeypatch):
    calls = []

    def forbidden(*args, **kwargs):
        calls.append(args)
        raise AssertionError("the seeded path must not touch the network")

    monkeypatch.setattr("requests.get", forbidden)
    monkeypatch.setattr("requests.post", forbidden)
    ctx = SeededProvider().build_context("beni-haroun", dt.date(2026, 11, 13))
    assert ctx.dam.slug == "beni-haroun"
    assert calls == []
