import datetime as dt

import pytest

from core.services.contracts import (
    BasinSnapshot,
    ClimateDay,
    ClimateWindow,
    ClimatologyBinData,
    DamSnapshot,
    IndexContext,
)
from core.services.indices.srri import SRRIProvider, display_c_runoff

C_REF_BASE = [round(0.02 * n, 2) for n in range(0, 21)] + [0.52, 0.54, 0.56, 0.58, 0.60]
AS_OF = dt.date(2026, 11, 13)


def make_context(
    *,
    soil=0.85,
    design_storm=65.0,
    baseline=None,
    metadata=None,
    climate=None,
):
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
        metadata={
            "design_storm_mm": design_storm,
            "cn_ii": 72.5,
            "theta_wp": 0.12,
            "theta_fc": 0.32,
            **(metadata or {}),
        },
    )
    basin = BasinSnapshot(
        basin_id=1, country_iso3="DZA", name="Beni Haroun", area_km2=2_000.0
    )
    days = climate or [
        ClimateDay(
            date=AS_OF - dt.timedelta(days=offset),
            precip_mm=0.0,
            soil_moisture_m3m3=soil,
        )
        for offset in range(400, -1, -1)
    ]
    bins = {}
    if baseline is not None:
        bins["srri_c_ref"] = {
            46: ClimatologyBinData(
                "srri_c_ref", 46, list(baseline), len(baseline)
            )
        }
    return IndexContext(
        dam=dam,
        basin=basin,
        climate=ClimateWindow(days=days),
        climatology=bins,
        as_of=AS_OF,
        week=46,
    )


def test_srri_signed_fixture():
    result = SRRIProvider().compute(make_context(baseline=C_REF_BASE))
    assert result.available is True
    assert result.data_status == "OK"
    assert result.score == pytest.approx(78.571, abs=1e-3)
    assert result.components["cn_ii"] == pytest.approx(72.5)
    assert result.components["cn_i"] == pytest.approx(52.545, abs=1e-3)
    assert result.components["cn_iii"] == pytest.approx(85.843, abs=1e-3)
    assert result.components["saturation"] == pytest.approx(1.0)
    assert result.components["c_ref"] == pytest.approx(0.5006, abs=1e-3)
    assert result.components["flood_penalty"] == pytest.approx(0.0)


def test_srri_uses_wet_day_p95_not_all_day_p95():
    days = []
    for offset in range(400, 0, -1):
        days.append(ClimateDay(date=AS_OF - dt.timedelta(days=offset), precip_mm=0.0))
    # 65 wet days of 2..66 mm, followed by 65 dry days.
    for i in range(65):
        days.append(
            ClimateDay(
                date=AS_OF - dt.timedelta(days=64 - i),
                precip_mm=float(i + 2),
                soil_moisture_m3m3=0.30,
            )
        )
    result = SRRIProvider().compute(
        make_context(design_storm=None, climate=days, baseline=C_REF_BASE)
    )
    assert result.components["p_ref_mm"] > 25.0
    assert result.components["p_ref_mm"] > 55.0
    assert result.components["p_ref_mm"] < 70.0


def test_srri_ranks_raw_c_ref_while_display_clamps():
    assert display_c_runoff(1.0) == pytest.approx(0.85)
    assert display_c_runoff(2.0) == pytest.approx(0.85)
    assert display_c_runoff(0.0) == pytest.approx(0.05)

    baseline = [round(0.1 + 0.05 * n, 2) for n in range(26)]
    first = SRRIProvider().compute(
        make_context(design_storm=200.0, baseline=baseline)
    )
    second = SRRIProvider().compute(
        make_context(design_storm=500.0, baseline=baseline)
    )
    assert second.components["c_ref"] > first.components["c_ref"]
    assert second.components["p_c_ref"] > first.components["p_c_ref"]
    assert second.score > first.score


def test_srri_flood_penalty_above_seven_tenths():
    baseline = [round(0.1 * n, 2) for n in range(1, 27)]
    result = SRRIProvider().compute(
        make_context(design_storm=500.0, baseline=baseline)
    )
    assert result.components["c_ref"] > 0.7
    assert result.components["flood_penalty"] > 0.0
    expected = result.components["p_c_ref"] * (
        1.0 - 0.15 * result.components["flood_penalty"]
    )
    assert result.score == pytest.approx(expected, abs=1e-3)


def test_srri_rejects_invalid_soil_water_content_bounds():
    result = SRRIProvider().compute(
        make_context(
            baseline=C_REF_BASE,
            metadata={"theta_wp": 0.40, "theta_fc": 0.20},
        )
    )
    assert result.available is False
    assert result.data_status == "INVALID"


def test_srri_missing_soil_moisture_is_no_data():
    days = [
        ClimateDay(
            date=AS_OF - dt.timedelta(days=offset),
            precip_mm=0.0,
            soil_moisture_m3m3=None,
        )
        for offset in range(400, -1, -1)
    ]
    result = SRRIProvider().compute(
        make_context(baseline=C_REF_BASE, climate=days)
    )
    assert result.available is False
    assert result.data_status == "NO_DATA"
