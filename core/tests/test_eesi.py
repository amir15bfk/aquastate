import datetime as dt
import math

import pytest

from core.services.contracts import (
    BasinSnapshot,
    BathymetryPointData,
    ClimateDay,
    ClimatologyBinData,
    ClimateWindow,
    DamSnapshot,
    IndexContext,
)
from core.services.indices.eesi import EESIProvider

AS_OF = dt.date(2026, 11, 13)


def bathymetry():
    return [
        BathymetryPointData(0.0, 1.0, 0.0, 0),
        BathymetryPointData(10.0, 1.0, 10_000_000.0, 1),
    ]


def base_bins(evap_center=0.001):
    esi = [0.05 + 0.01 * i for i in range(26)]
    evap = [evap_center * (0.5 + 0.04 * i) for i in range(26)]
    lst = [-2.0 + 0.24 * i for i in range(26)]
    return {
        "eesi_esi": {46: ClimatologyBinData("eesi_esi", 46, esi, 26)},
        "eesi_evap_ratio": {
            46: ClimatologyBinData("eesi_evap_ratio", 46, evap, 26)
        },
        "eesi_lst_anom": {46: ClimatologyBinData("eesi_lst_anom", 46, lst, 26)},
    }


def make_context(
    *,
    pet=5.0,
    et=0.5,
    lst=314.0,
    volume=5_000_000.0,
    dead=0.0,
    capacity=10_000_000.0,
    bins=None,
    metadata=None,
):
    dam = DamSnapshot(
        slug="test-dam",
        name="Test Dam",
        country_iso3="DZA",
        lat=36.0,
        lon=6.0,
        capacity_m3=capacity,
        dead_storage_m3=dead,
        basin_area_km2=1_000.0,
        bathymetry=bathymetry(),
        current_volume_m3=volume,
        observation_date=AS_OF,
        metadata={"lst_mean_k": 313.0, **(metadata or {})},
    )
    basin = BasinSnapshot(
        basin_id=1, country_iso3="DZA", name="Test Basin", area_km2=1_000.0
    )
    latest = ClimateDay(
        date=AS_OF,
        precip_mm=0.0,
        et_mm=et,
        pet_mm=pet,
        lst_k=lst,
        soil_moisture_m3m3=0.25,
    )
    return IndexContext(
        dam=dam,
        basin=basin,
        climate=ClimateWindow(days=[latest]),
        climatology=bins or base_bins(),
        as_of=AS_OF,
        week=46,
    )


def test_eesi_pet_units_are_mm_per_day_not_metres():
    result = EESIProvider().compute(make_context())
    # 1 km² × 5 mm/day = 5,000 m³/day, not 5×10⁶.
    assert result.components["pet_mm_day"] == pytest.approx(5.0)
    assert result.components["a_surface_m2"] == pytest.approx(1_000_000.0)
    assert result.components["e_loss_m3_day"] == pytest.approx(5_000.0)


def test_eesi_neutral_inputs_score_fifty():
    result = EESIProvider().compute(make_context(et=0.875))
    assert result.available is True
    assert result.score == pytest.approx(50.0)
    assert result.components["p_esi"] == pytest.approx(50.0)
    assert result.components["p_evap"] == pytest.approx(50.0)
    assert result.components["p_lst"] == pytest.approx(50.0)


def test_eesi_lst_missing_reweights_and_lowers_confidence():
    bins = base_bins()
    bins.pop("eesi_lst_anom")
    result = EESIProvider().compute(make_context(et=2.5, lst=None, bins=bins))
    assert result.available is True
    assert result.components["weights"] == [0.65, 0.35]
    assert result.score == pytest.approx(0.65 * result.components["p_esi"] + 0.35 * result.components["p_evap"])
    assert result.confidence < 1.0


def test_eesi_esi_above_one_is_flagged():
    result = EESIProvider().compute(make_context(et=6.0, pet=5.0))
    assert result.components["esi"] == pytest.approx(1.2)
    assert result.components["esi_flagged"] is True
    assert result.components["esi_scored"] == pytest.approx(1.0)
    assert result.confidence < 1.0


def test_eesi_zero_usable_volume_uses_floor_without_division_by_zero():
    result = EESIProvider().compute(make_context(volume=0.0, dead=0.0))
    assert result.available is True
    assert math.isfinite(result.components["evap_ratio"])
    assert result.components["v_floor_m3"] == pytest.approx(10.0)
    assert math.isfinite(result.score)


def test_eesi_missing_pet_is_no_data():
    result = EESIProvider().compute(make_context(pet=None))
    assert result.available is False
    assert result.data_status == "NO_DATA"
