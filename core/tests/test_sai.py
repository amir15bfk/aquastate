import datetime as dt
import math

import pytest

from core.services.contracts import (
    BasinSnapshot,
    ClimatologyBinData,
    DamSnapshot,
    GraceMonth,
    GraceWindow,
    IndexContext,
)
from core.services.indices.sai import SAIProvider

AS_OF = dt.date(2026, 11, 13)


def grace_months(count=300, trend=1.5, missing=False):
    months = []
    start = dt.date(2000, 1, 1)
    for i in range(count):
        year = start.year + (start.month - 1 + i) // 12
        month = (start.month - 1 + i) % 12 + 1
        twsa = trend * (i / 12.0) + 5.0 * math.sin(2 * math.pi * i / 12.0)
        if missing and i == 12:
            twsa = None
        months.append(
            GraceMonth(
                month=dt.date(year, month, 1),
                twsa_mm=twsa,
                smsa_mm=0.0,
                swsa_mm=0.0,
            )
        )
    return months


def make_context(area_km2=2_000.0, kernel_corrected=False, series=None, baseline=None):
    dam = DamSnapshot(
        slug="beni-haroun",
        name="Beni Haroun",
        country_iso3="DZA",
        lat=36.55,
        lon=6.28,
        capacity_m3=100_000_000.0,
        dead_storage_m3=10_000_000.0,
        basin_area_km2=area_km2,
        current_volume_m3=26_200_000.0,
        observation_date=AS_OF,
    )
    basin = BasinSnapshot(
        basin_id=1, country_iso3="DZA", name="Basin", area_km2=area_km2
    )
    bins = {}
    if baseline is not None:
        bins["sai_gwsa"] = {
            46: ClimatologyBinData("sai_gwsa", 46, list(baseline), len(baseline))
        }
    return IndexContext(
        dam=dam,
        basin=basin,
        grace=GraceWindow(
            months=series if series is not None else grace_months(),
            basin_area_km2=area_km2,
            baseline_epoch=dt.date(2000, 1, 1),
            kernel_corrected=kernel_corrected,
        ),
        climatology=bins,
        as_of=AS_OF,
        week=46,
    )


def test_sai_pilot_basin_is_visible_but_no_data():
    result = SAIProvider().compute(make_context(area_km2=2_000.0, baseline=list(range(26))))
    assert result.available is False
    assert result.score == 0.0
    assert result.confidence == 0.0
    assert result.status == "NO_DATA"
    assert result.data_status == "NO_DATA"
    assert result.contributions["SAI"] == 0.0
    assert "regional_percentile" in result.components
    assert math.isfinite(result.components["slope_mm_yr"])


def test_sai_large_basin_without_kernel_correction_is_no_data():
    result = SAIProvider().compute(
        make_context(area_km2=100_000.0, kernel_corrected=False, baseline=list(range(26)))
    )
    assert result.available is False
    assert result.data_status == "NO_DATA"
    assert result.contributions["SAI"] == 0.0


def test_sai_large_corrected_basin_gets_a_full_score():
    series = grace_months(count=300, trend=4.0)
    baseline = [month.gwsa_mm for month in series[-26:]]
    result = SAIProvider().compute(
        make_context(
            area_km2=100_000.0,
            kernel_corrected=True,
            series=series,
            baseline=baseline,
        )
    )
    assert result.available is True
    assert result.data_status == "OK"
    assert 0.0 <= result.score <= 100.0
    assert result.confidence == pytest.approx(1.0)
    assert math.isfinite(result.components["slope_mm_yr"])
    assert result.components["slope_ci_low"] <= result.components["slope_mm_yr"]
    assert result.components["slope_ci_high"] >= result.components["slope_mm_yr"]


def test_sai_missing_grace_months_are_excluded_not_interpolated():
    series = grace_months(count=300, trend=1.0, missing=True)
    result = SAIProvider().compute(
        make_context(
            area_km2=2_000.0,
            series=series,
            baseline=list(range(26)),
        )
    )
    assert result.components["n_months"] == 299
    for key in ("slope_mm_yr", "slope_ci_low", "slope_ci_high", "regional_percentile"):
        assert math.isfinite(result.components[key])


def test_sai_no_nan_or_inf_when_series_is_empty():
    result = SAIProvider().compute(
        make_context(area_km2=100_000.0, kernel_corrected=True, series=[], baseline=[])
    )
    assert result.available is False
    assert result.score == 0.0
    assert result.data_status == "NO_DATA"
