import datetime as dt
import math

import pytest
from django.core.management import call_command
from pydantic import ValidationError

from core.services.hri import HRISynthesizer
from core.services.providers.seeded import SeededProvider
from core.services.scenario import ScenarioOverrides, ScenarioService

AS_OF = dt.date(2026, 11, 13)


@pytest.fixture
def beni_context(db):
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
    return SeededProvider().build_context("beni-haroun", AS_OF)


def test_rain_zero_drops_to_critical(beni_context):
    service = ScenarioService()
    outcome = service.apply(beni_context, ScenarioOverrides(rain_multiplier=0.0))
    assert outcome.observed_hri == pytest.approx(81.05, abs=0.02)
    assert outcome.scenario_hri == pytest.approx(24.9, abs=0.05)
    assert outcome.scenario_result.status == "CRITICAL"
    assert outcome.is_scenario is True
    assert outcome.delta < 0


def test_rain_doubled_restores_recharging(beni_context):
    service = ScenarioService()
    outcome = service.apply(beni_context, ScenarioOverrides(rain_multiplier=2.0))
    assert outcome.scenario_hri > outcome.observed_hri - 5
    # Doubling the signed 65 mm storm pushes the projected CMI and SSI to their
    # ceilings, so the result may legitimately cross the ≥85 SURPLUS line.
    assert outcome.scenario_result.status in {"RECHARGING", "SURPLUS"}
    assert outcome.scenario_hri >= 55.0
    assert outcome.scenario_hri <= 100.0


def test_demand_multiplier_changes_autonomy(beni_context):
    baseline = HRISynthesizer().compute(beni_context)
    service = ScenarioService()
    outcome = service.apply(beni_context, ScenarioOverrides(demand_multiplier=2.0))
    assert (
        outcome.scenario_result.components["buffer"]["d_autonomy_days"]
        < baseline.components["buffer"]["d_autonomy_days"]
    )
    assert outcome.scenario_result.components["buffer"]["q_out_m3_day"] > 600_000.0


def test_soil_and_storm_overrides_are_applied(beni_context):
    service = ScenarioService()
    outcome = service.apply(
        beni_context,
        ScenarioOverrides(soil_saturation=0.2, storm_arrival_day=10),
    )
    assert outcome.scenario_result.available is True
    assert outcome.scenario_result.components["buffer"]["d_until_rain_days"] == 10


def test_validation_rejects_out_of_range_and_non_finite():
    with pytest.raises(ValidationError):
        ScenarioOverrides(rain_multiplier=4.0)
    with pytest.raises(ValidationError):
        ScenarioOverrides(rain_multiplier=-0.1)
    with pytest.raises(ValidationError):
        ScenarioOverrides(demand_multiplier=0.4)
    with pytest.raises(ValidationError):
        ScenarioOverrides(soil_saturation=1.5)
    with pytest.raises(ValidationError):
        ScenarioOverrides(storm_arrival_day=15)
    with pytest.raises(ValidationError):
        ScenarioOverrides(rain_multiplier=float("nan"))
    with pytest.raises(ValidationError):
        ScenarioOverrides(demand_multiplier=float("inf"))


def test_url_serialization_round_trip():
    overrides = ScenarioOverrides(
        rain_multiplier=0.0,
        demand_multiplier=1.2,
        soil_saturation=0.8,
        storm_arrival_day=3,
    )
    query = overrides.to_query()
    assert "rain=0" in query
    assert "demand=1.2" in query
    restored = ScenarioOverrides.from_query(query)
    assert restored == overrides
    assert ScenarioOverrides.from_query("") == ScenarioOverrides()


def test_scenario_math_is_finite(beni_context):
    outcome = ScenarioService().apply(
        beni_context,
        ScenarioOverrides(rain_multiplier=0.0, demand_multiplier=2.0),
    )
    assert math.isfinite(outcome.scenario_hri)
    assert math.isfinite(outcome.observed_hri)
    assert 0.0 <= outcome.scenario_hri <= 100.0
