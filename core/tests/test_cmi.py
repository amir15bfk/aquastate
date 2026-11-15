import datetime as dt

import pytest

from core.services.contracts import (
    BasinSnapshot,
    ClimateDay,
    ClimateWindow,
    ClimatologyBinData,
    DamSnapshot,
    ForecastDay,
    ForecastWindow,
    IndexContext,
)
from core.services.indices.cmi import CMIProvider

P30_BASE = [8.0 * n for n in range(1, 27)]
P90_BASE = [16.0 + 8.0 * n for n in range(26)]
DRY_BASE = [float(n) for n in range(1, 14)] + [13.0] + [float(n) for n in range(15, 27)]

AS_OF = dt.date(2026, 11, 13)


def climate_days(total_30=108.0, total_90=116.0, missing=False):
    days = []
    for offset in range(89, -1, -1):
        date = AS_OF - dt.timedelta(days=offset)
        precip = 0.0
        if offset == 13:
            precip = 40.0
        elif offset == 14:
            precip = 40.0
        elif offset == 15:
            precip = 28.0
        elif offset == 36:
            precip = max(0.0, total_90 - total_30)
        if missing and offset == 10:
            precip = None
        days.append(ClimateDay(date=date, precip_mm=precip, et_mm=1.0, pet_mm=4.0))
    return days


def make_context(climate=None, forecast=None, projected=False, week=46):
    dam = DamSnapshot(
        slug="beni-haroun",
        name="Beni Haroun",
        country_iso3="DZA",
        lat=36.55,
        lon=6.28,
        capacity_m3=100_000_000.0,
        dead_storage_m3=10_000_000.0,
        basin_area_km2=2_000.0,
        current_volume_m3=26_200_000.0,
        observation_date=AS_OF,
    )
    basin = BasinSnapshot(
        basin_id=1, country_iso3="DZA", name="Beni Haroun", area_km2=2_000.0
    )
    bins = {
        "cmi_p30": {week: ClimatologyBinData("cmi_p30", week, list(P30_BASE), 26)},
        "cmi_p90": {week: ClimatologyBinData("cmi_p90", week, list(P90_BASE), 26)},
        "dry_spell": {week: ClimatologyBinData("dry_spell", week, list(DRY_BASE), 26)},
    }
    return IndexContext(
        dam=dam,
        basin=basin,
        climate=ClimateWindow(days=climate or climate_days()),
        forecast=forecast or ForecastWindow(days=[]),
        climatology=bins,
        as_of=AS_OF + (dt.timedelta(days=14) if projected else dt.timedelta(0)),
        week=week,
        scenario_overrides={"projected": True} if projected else {},
    )


def test_cmi_signed_fixture_is_fifty():
    result = CMIProvider().compute(make_context())
    assert result.available is True
    assert result.score == pytest.approx(50.0)
    assert result.components["p30_total_mm"] == pytest.approx(108.0)
    assert result.components["p90_total_mm"] == pytest.approx(116.0)
    assert result.components["p30"] == pytest.approx(50.0)
    assert result.components["p90"] == pytest.approx(50.0)
    assert result.components["dry_spell_days"] == 13
    assert result.components["spi_method"] == "empirical_26y"


def test_cmi_ranks_raw_totals_once_not_a_percentile_of_percentile():
    result = CMIProvider().compute(make_context())
    # If percentiles were applied twice, p30/p90 would collapse toward 50 only
    # by coincidence; the fixture pins the raw-total ranks explicitly.
    assert result.components["p30"] == pytest.approx(50.0)
    assert result.components["p90"] == pytest.approx(50.0)
    assert result.components["spi3"] == pytest.approx(0.0, abs=1e-9)


def test_cmi_projected_fixture_matches_signed_value():
    projected_climate = climate_days() + [
        ClimateDay(
            date=AS_OF + dt.timedelta(days=day),
            precip_mm=16.25 if day <= 4 else 0.0,
            et_mm=1.0,
            pet_mm=6.5,
        )
        for day in range(1, 15)
    ]
    result = CMIProvider().compute(
        make_context(climate=projected_climate, projected=True, week=48)
    )
    assert result.components["p30_total_mm"] == pytest.approx(173.0)
    assert result.components["p90_total_mm"] == pytest.approx(181.0)
    assert result.score == pytest.approx(81.786, abs=1e-3)


def test_cmi_dry_spell_caps_at_180_and_inverts():
    dry = [ClimateDay(date=AS_OF - dt.timedelta(days=200 - i), precip_mm=0.0)
           for i in range(201)]
    result = CMIProvider().compute(make_context(climate=dry))
    assert result.components["dry_spell_days"] == 180
    assert result.components["p_dry"] == pytest.approx(96.429, abs=1e-3)
    assert result.components["dry_score"] == pytest.approx(3.571, abs=1e-3)


def test_cmi_forecast_does_not_change_current_score():
    storm = ForecastWindow(
        days=[ForecastDay(date=AS_OF + dt.timedelta(days=1), precip_mm=65.0)]
    )
    plain = CMIProvider().compute(make_context())
    with_forecast = CMIProvider().compute(make_context(forecast=storm))
    assert plain.score == pytest.approx(with_forecast.score)


def test_cmi_missing_precipitation_is_no_data():
    result = CMIProvider().compute(make_context(climate=climate_days(missing=True)))
    assert result.available is False
    assert result.data_status == "NO_DATA"
    assert result.status == "NO_DATA"
    assert result.score == 0.0
