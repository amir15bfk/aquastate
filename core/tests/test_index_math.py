import datetime as dt
import math

import pytest
from django.core.management import call_command

from core.services.buffer import estimate_inflow, group_storm_events
from core.services.contracts import (
    BasinSnapshot,
    DamSnapshot,
    DemandDay,
    DemandWindow,
    ForecastDay,
    ForecastWindow,
    IndexContext,
    IndexEvaluationResult,
)
from core.services.hri import HRISynthesizer, smooth_cap

AS_OF = dt.date(2026, 11, 13)


def result(index_id, score, available=True, confidence=1.0, **components):
    return IndexEvaluationResult(
        index_id=index_id,
        score=score,
        available=available,
        confidence=confidence,
        status="OK" if available else "NO_DATA",
        data_status="OK" if available else "NO_DATA",
        components=components,
    )


def case_b_results(sai_available=False):
    now = {
        "SSI": result("SSI", 5.357),
        "CMI": result("CMI", 50.0),
        "SRRI": result("SRRI", 78.571, cn_eff=85.84),
        "EESI": result("EESI", 50.0, e_loss_m3_day=0.0),
        "SAI": result("SAI", 0.0, available=False, confidence=0.0, contributions={"SAI": 0.0}),
    }
    proj = {
        "SSI": result("SSI", 96.429),
        "CMI": result("CMI", 81.786),
        "SRRI": result("SRRI", 78.571, cn_eff=85.84),
        "EESI": result("EESI", 63.75, e_loss_m3_day=0.0),
        "SAI": result("SAI", 0.0, available=False, confidence=0.0, contributions={"SAI": 0.0}),
    }
    if sai_available:
        now["SAI"] = result("SAI", 50.0, confidence=0.02418)
        proj["SAI"] = result("SAI", 50.0, confidence=0.02418)
    return now, proj


def make_context(
    *,
    storm=True,
    storm_total_mm=None,
    storm_days=4,
    demand=600_000.0,
    volume=26_200_000.0,
    capacity=100_000_000.0,
    dead=10_000_000.0,
    area_km2=2_000.0,
):
    dam = DamSnapshot(
        slug="beni-haroun",
        name="Beni Haroun",
        country_iso3="DZA",
        lat=36.552,
        lon=6.283,
        capacity_m3=capacity,
        dead_storage_m3=dead,
        basin_area_km2=area_km2,
        current_volume_m3=volume,
        current_fill_pct=18.0,
        observation_date=AS_OF,
        metadata={"runoff_coefficient": 0.8},
    )
    basin = BasinSnapshot(
        basin_id=1, country_iso3="DZA", name="Beni Haroun", area_km2=area_km2
    )
    forecast_days = []
    for day in range(1, 15):
        if storm_total_mm is not None:
            precip = storm_total_mm / storm_days if day <= storm_days else 0.0
        else:
            precip = 16.25 if storm and day <= 4 else 0.0
        forecast_days.append(
            ForecastDay(date=AS_OF + dt.timedelta(days=day), precip_mm=precip)
        )
    return IndexContext(
        dam=dam,
        basin=basin,
        forecast=ForecastWindow(days=forecast_days),
        demand=DemandWindow(
            days=[DemandDay(date=AS_OF, demand_m3_day=demand)], source="seeded"
        ),
        as_of=AS_OF,
        week=46,
    )


def test_case_a_dry_control_caps_at_24_9():
    now, proj = case_b_results()
    outcome = HRISynthesizer().compute(make_context(storm=False), now, proj)
    assert outcome.components["hri_before_cap"] == pytest.approx(38.616, abs=1e-3)
    assert outcome.hri == pytest.approx(24.9)
    assert outcome.status == "CRITICAL"
    assert outcome.phi == pytest.approx(0.0)


def test_case_b_production_matches_signed_fixture():
    now, proj = case_b_results()
    outcome = HRISynthesizer().compute(make_context(), now, proj)
    assert outcome.components["hri_now"] == pytest.approx(38.616, abs=1e-3)
    assert outcome.components["hri_proj"] == pytest.approx(83.293, abs=1e-3)
    assert outcome.phi == pytest.approx(0.94977, abs=1e-4)
    assert outcome.hri == pytest.approx(81.05, abs=0.01)
    assert outcome.status == "RECHARGING"
    assert outcome.available is True
    assert outcome.data_status == "OK"
    assert outcome.components["weights_effective"]["SSI"] == pytest.approx(0.375)
    assert outcome.components["buffer"]["v_in14_m3"] == pytest.approx(
        52_000_000.0, rel=2e-3
    )
    assert outcome.components["buffer"]["v_proj14_m3"] == pytest.approx(
        59_800_000.0, rel=2e-3
    )
    assert outcome.components["buffer"]["d_autonomy_days"] == pytest.approx(27.0)
    assert outcome.components["buffer"]["d_until_rain_days"] == 1


def test_case_b_confidence_weighted_sai_variant():
    now, proj = case_b_results(sai_available=True)
    outcome = HRISynthesizer().compute(make_context(), now, proj)
    weights = outcome.components["weights_effective"]
    assert weights["SSI"] == pytest.approx(0.37275, abs=1e-4)
    assert weights["CMI"] == pytest.approx(0.24850, abs=1e-4)
    assert weights["SRRI"] == pytest.approx(0.18637, abs=1e-4)
    assert weights["SAI"] == pytest.approx(0.00601, abs=1e-4)
    assert weights["EESI"] == pytest.approx(0.18637, abs=1e-4)
    assert outcome.hri == pytest.approx(80.86, abs=0.02)
    assert outcome.status == "RECHARGING"


def test_case_b_42_day_user_spec_variant():
    now, proj = case_b_results()
    outcome = HRISynthesizer().compute(
        make_context(demand=385_700.0), now, proj
    )
    assert outcome.components["buffer"]["d_autonomy_days"] == pytest.approx(42.0, abs=0.1)
    assert outcome.hri > 80.0
    assert outcome.status == "RECHARGING"


def test_no_storm_control_has_phi_zero_before_sigmoid():
    now, proj = case_b_results()
    outcome = HRISynthesizer().compute(make_context(storm=False), now, proj)
    assert outcome.phi == 0.0
    assert outcome.components["buffer"]["v_in14_m3"] == 0.0
    assert outcome.components["buffer"]["d_until_rain_days"] is None
    assert outcome.hri == pytest.approx(24.9)


def test_case_b_storm_event_grouping():
    forecast = [
        ForecastDay(date=AS_OF + dt.timedelta(days=day), precip_mm=16.25)
        for day in range(1, 5)
    ] + [
        ForecastDay(date=AS_OF + dt.timedelta(days=day), precip_mm=0.0)
        for day in range(5, 15)
    ]
    events = group_storm_events(forecast)
    assert len(events) == 1
    assert sum(events[0]) == pytest.approx(65.0)

    grouped = estimate_inflow(forecast, 2_000.0, cn_eff=85.84, eta=0.8)
    per_day = sum(
        estimate_inflow([day], 2_000.0, cn_eff=85.84, eta=0.8) for day in forecast
    )
    assert grouped == pytest.approx(52_000_000.0, rel=2e-3)
    assert grouped / per_day == pytest.approx(6.5, abs=0.3)


def test_case_b_waterfall_identity_with_sai_excluded_and_override():
    now, proj = case_b_results()
    outcome = HRISynthesizer().compute(make_context(storm=False), now, proj)
    assert sum(outcome.contributions.values()) + 50.0 == pytest.approx(outcome.hri, abs=1e-9)
    assert outcome.contributions["override"] != 0.0


def test_soft_override_is_continuous_at_boundaries():
    low_phi = smooth_cap(50.0, ssi=5.357, phi=0.299999, d_autonomy=27.0)
    high_phi = smooth_cap(50.0, ssi=5.357, phi=0.300001, d_autonomy=27.0)
    low_ssi = smooth_cap(50.0, ssi=19.9999, phi=0.1, d_autonomy=30.0)
    high_ssi = smooth_cap(50.0, ssi=20.0001, phi=0.1, d_autonomy=30.0)
    assert low_phi == pytest.approx(high_phi, abs=0.01)
    assert low_ssi == pytest.approx(high_ssi, abs=0.01)


def test_hri_is_continuous_across_phi_boundary():
    now, proj = case_b_results()
    low = HRISynthesizer().compute(
        make_context(storm_total_mm=22.19, storm_days=1), now, proj
    )
    high = HRISynthesizer().compute(
        make_context(storm_total_mm=22.20, storm_days=1), now, proj
    )
    assert abs(high.hri - low.hri) < 1.0
    assert (low.status == "CRITICAL") == (high.status == "CRITICAL")


def test_phi_has_no_ten_mm_forecast_cliff():
    now, proj = case_b_results()
    below = HRISynthesizer().compute(
        make_context(storm_total_mm=39.6, storm_days=4), now, proj
    )
    above = HRISynthesizer().compute(
        make_context(storm_total_mm=40.0, storm_days=4), now, proj
    )
    assert abs(above.hri - below.hri) < 2.0
    assert below.hri >= 55.0
    assert above.hri >= 55.0


def test_case_c1_all_no_data_is_no_data_not_fifty():
    now = {index: result(index, 0.0, available=False, confidence=0.0)
           for index in ("SSI", "CMI", "SRRI", "SAI", "EESI")}
    outcome = HRISynthesizer().compute(make_context(), now, now)
    assert outcome.available is False
    assert outcome.status == "NO_DATA"
    assert outcome.data_status == "NO_DATA"
    assert outcome.hri == 0.0
    assert math.isfinite(outcome.hri)


def test_case_c2_all_zero_baseline_scores_fifty_without_nan():
    now = {index: result(index, 50.0, confidence=0.5)
           for index in ("SSI", "CMI", "SRRI", "EESI")}
    now["SAI"] = result("SAI", 50.0, confidence=0.0, available=False)
    outcome = HRISynthesizer().compute(make_context(storm=False), now, now)
    assert outcome.hri == pytest.approx(50.0)
    assert outcome.confidence == pytest.approx(0.5)
    assert math.isfinite(outcome.phi)
    assert math.isfinite(outcome.hri)


def test_case_c3_low_autonomy_caps_at_19_9_and_projection_clamps():
    now, proj = case_b_results()
    outcome = HRISynthesizer().compute(
        make_context(storm=False, demand=1_300_000.0), now, proj
    )
    assert outcome.components["buffer"]["d_autonomy_days"] == pytest.approx(12.46, abs=0.02)
    assert outcome.components["buffer"]["v_proj14_m3"] == 0.0
    assert outcome.hri == pytest.approx(19.9)
    assert outcome.status == "CRITICAL"


def test_case_c4_zero_usable_capacity_is_invalid_no_data():
    now, proj = case_b_results()
    outcome = HRISynthesizer().compute(
        make_context(capacity=100_000_000.0, dead=100_000_000.0, volume=100_000_000.0),
        now,
        proj,
    )
    assert outcome.available is False
    assert outcome.status == "NO_DATA"
    assert outcome.data_status == "INVALID"
    assert outcome.hri == 0.0


def test_case_c5_zero_demand_and_pet_guards_no_infinity():
    now, proj = case_b_results()
    outcome = HRISynthesizer().compute(
        make_context(storm=False, demand=0.0, volume=100_000_000.0), now, proj
    )
    buffer = outcome.components["buffer"]
    assert buffer["q_out_m3_day"] > 0
    assert buffer["d_autonomy_days"] == pytest.approx(3650.0)
    assert math.isfinite(buffer["d_autonomy_days"])
    assert math.isfinite(outcome.hri)


def test_case_c6_zero_basin_area_is_guarded():
    now, proj = case_b_results()
    outcome = HRISynthesizer().compute(make_context(area_km2=0.0), now, proj)
    buffer = outcome.components["buffer"]
    assert buffer["v_in14_m3"] == 0.0
    assert buffer["phi"] == 0.0
    assert math.isfinite(outcome.hri)


def test_no_llm_slots_active():
    now, proj = case_b_results()
    outcome = HRISynthesizer().compute(make_context(), now, proj)
    assert outcome.components["agent_slot_status"] == "DETERMINISTIC_MVP"
    assert all(
        item["agent_slot_status"] == "DETERMINISTIC_MVP"
        for item in outcome.components["sub_index_meta"].values()
    )


@pytest.mark.django_db
def test_seeded_case_b_end_to_end_reproduces_signed_fixture():
    from core.services.providers.seeded import SeededProvider

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
    ctx = SeededProvider().build_context("beni-haroun", dt.date(2026, 11, 13))
    outcome = HRISynthesizer().compute(ctx)

    assert outcome.sub_indices["SSI"] == pytest.approx(5.357, abs=1e-3)
    assert outcome.sub_indices["CMI"] == pytest.approx(50.0, abs=1e-3)
    assert outcome.sub_indices["SRRI"] == pytest.approx(78.571, abs=1e-3)
    assert outcome.sub_indices["EESI"] == pytest.approx(50.0, abs=1e-3)
    assert outcome.hri_now == pytest.approx(38.616, abs=1e-3)
    assert outcome.hri_proj == pytest.approx(83.293, abs=1e-3)
    assert outcome.phi == pytest.approx(0.94977, abs=1e-4)
    assert outcome.hri == pytest.approx(81.05, abs=0.01)
    assert outcome.status == "RECHARGING"
    assert outcome.components["scores_proj"]["SSI"] == pytest.approx(96.429, abs=1e-3)
    assert outcome.components["scores_proj"]["CMI"] == pytest.approx(81.786, abs=1e-3)
    assert outcome.components["scores_proj"]["SRRI"] == pytest.approx(78.571, abs=1e-3)
    assert outcome.components["scores_proj"]["EESI"] == pytest.approx(63.75, abs=1e-3)
    assert outcome.sub_indices.get("SAI") is None
