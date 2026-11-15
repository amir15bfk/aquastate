import datetime as dt

import pytest

from core.services.contracts import (
    BasinSnapshot,
    BathymetryPointData,
    ClimatologyBinData,
    DamSnapshot,
    IndexContext,
)
from core.services.indices.ssi import SSIProvider

SSI_W46 = [18, 22, 24, 26, 28, 30, 32, 34, 35, 36, 37, 38, 39, 40, 41, 42,
           43, 44, 45, 46, 48, 50, 52, 55, 58, 60]


def bathymetry():
    return [
        BathymetryPointData(0.0, 0.0, 0.0, 0),
        BathymetryPointData(20.0, 1.0, 10_000_000.0, 1),
        BathymetryPointData(40.0, 2.0, 40_000_000.0, 2),
    ]


def make_context(
    *,
    fill_values=None,
    capacity_m3=100_000_000.0,
    dead_storage_m3=10_000_000.0,
    volume_m3=26_200_000.0,
    water_level_m=None,
    observation_date=dt.date(2026, 11, 13),
    as_of=dt.date(2026, 11, 13),
    points=None,
):
    dam = DamSnapshot(
        slug="beni-haroun",
        name="Beni Haroun",
        country_iso3="DZA",
        lat=36.552,
        lon=6.283,
        capacity_m3=capacity_m3,
        dead_storage_m3=dead_storage_m3,
        basin_area_km2=2_000.0,
        bathymetry=points or bathymetry(),
        as_of=as_of,
        current_volume_m3=volume_m3,
        current_level_m=water_level_m,
        observation_date=observation_date,
    )
    basin = BasinSnapshot(
        basin_id=1,
        country_iso3="DZA",
        name="Beni Haroun Basin",
        area_km2=2_000.0,
    )
    bins = {}
    if fill_values is not None:
        bins["ssi_fill_pct"] = {
            46: ClimatologyBinData(
                metric="ssi_fill_pct", week=46, values=list(fill_values),
                n=len(fill_values),
            )
        }
    return IndexContext(
        dam=dam,
        basin=basin,
        climatology=bins,
        as_of=as_of,
        week=46,
    )


def test_ssi_signed_fill_fixture():
    result = SSIProvider().compute(make_context(fill_values=SSI_W46))
    assert result.index_id == "SSI"
    assert result.available is True
    assert result.data_status == "OK"
    assert result.score == pytest.approx(5.357, abs=1e-3)
    assert result.components["fill_pct"] == pytest.approx(18.0)
    assert result.components["baseline_n"] == 26
    assert result.proof_steps
    assert result.explanation


def test_ssi_cylinder_geometry_uses_level():
    cylinder = [
        BathymetryPointData(0.0, 1.0, 0.0, 0),
        BathymetryPointData(20.0, 1.0, 20_000_000.0, 1),
    ]
    context = make_context(
        fill_values=[10, 20, 30],
        capacity_m3=20_000_000.0,
        dead_storage_m3=5_000_000.0,
        volume_m3=None,
        water_level_m=10.0,
        points=cylinder,
    )
    result = SSIProvider().compute(context)
    # 1 km² × 10 m = 10 Mm³; usable = 5 Mm³ of 15 Mm³ = 33.333%.
    assert result.components["volume_m3"] == pytest.approx(10_000_000.0)
    assert result.components["fill_pct"] == pytest.approx(100.0 / 3.0)


def test_ssi_invalid_when_usable_capacity_is_zero():
    result = SSIProvider().compute(
        make_context(
            fill_values=SSI_W46,
            capacity_m3=100_000_000.0,
            dead_storage_m3=100_000_000.0,
            volume_m3=100_000_000.0,
        )
    )
    assert result.available is False
    assert result.data_status == "INVALID"
    assert result.status == "NO_DATA"
    assert result.score == 0.0
    assert result.confidence == 0.0


def test_ssi_no_data_when_baseline_is_empty():
    result = SSIProvider().compute(make_context(fill_values=[]))
    assert result.available is False
    assert result.data_status == "NO_DATA"
    assert result.status == "NO_DATA"


def test_ssi_stale_observation_reduces_confidence():
    result = SSIProvider().compute(
        make_context(
            fill_values=SSI_W46,
            observation_date=dt.date(2026, 9, 1),
        )
    )
    assert result.data_status == "OK"
    assert result.confidence == pytest.approx(0.5)


def test_ssi_missing_observation_is_no_data():
    result = SSIProvider().compute(
        make_context(fill_values=SSI_W46, volume_m3=None)
    )
    assert result.available is False
    assert result.data_status == "NO_DATA"
    assert result.score == 0.0


def test_ssi_default_agent_slot_is_deterministic():
    result = SSIProvider().compute(make_context(fill_values=SSI_W46))
    assert result.agent_slot_status == "DETERMINISTIC_MVP"
    assert result.agent_id is None
