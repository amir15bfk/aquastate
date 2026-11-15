import datetime as dt

import pytest

from core.services.analog import AnalogCandidate, AnalogEngine
from core.services.contracts import (
    BasinSnapshot,
    DamSnapshot,
    IndexContext,
)
from core.services.exceptions import ScenarioValidationError

AS_OF = dt.date(2026, 11, 13)


def context(week=46):
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
        current_fill_pct=18.0,
        observation_date=AS_OF,
    )
    basin = BasinSnapshot(
        basin_id=1, country_iso3="DZA", name="Beni Haroun", area_km2=2_000.0
    )
    return IndexContext(dam=dam, basin=basin, as_of=AS_OF, week=week)


def candidate(year, week, *, fill=18.0, spi=0.0, c_ref=0.5, anomaly=0.0,
              trajectory=None, window_available=True):
    return AnalogCandidate(
        year=year,
        week=week,
        features={
            "fill_pct": fill,
            "spi3": spi,
            "c_ref": c_ref,
            "storage_anomaly": anomaly,
        },
        trajectory=trajectory if trajectory is not None else [float(i) for i in range(13)],
        window_available=window_available,
    )


CURRENT = {"fill_pct": 18.0, "spi3": 0.0, "c_ref": 0.5, "storage_anomaly": 0.0}


def test_known_nearest_neighbor_and_unique_years():
    history = [
        candidate(2010, 45, fill=18.0),
        candidate(2010, 46, fill=19.0),
        candidate(2011, 44, fill=30.0),
        candidate(2012, 47, fill=18.2),
    ]
    matches = AnalogEngine.find_analogs(
        context(), CURRENT, top_n=3, history=history
    )
    assert [match.year for match in matches] == [2010, 2012, 2011]
    assert matches[0].week == 45
    assert matches[0].distance < matches[1].distance
    assert len({match.year for match in matches}) == len(matches)


def test_plus_minus_four_week_restriction_and_no_sin_cos():
    history = [
        candidate(2005, 42, fill=18.0),
        candidate(2006, 50, fill=18.0),
        candidate(2007, 41, fill=18.0),
        candidate(2008, 51, fill=18.0),
    ]
    matches = AnalogEngine.find_analogs(
        context(week=46), CURRENT, top_n=4, history=history
    )
    assert {match.year for match in matches} == {2005, 2006}
    # Weeks 42 and 50 are equidistant in the ±4 window; neither circular
    # sin/cos term is allowed to break the tie.
    assert matches[0].distance == pytest.approx(matches[1].distance)


def test_future_window_exclusion():
    history = [
        candidate(2014, 46, fill=18.0, window_available=False),
        candidate(2015, 46, fill=18.0, window_available=True),
    ]
    matches = AnalogEngine.find_analogs(context(), CURRENT, top_n=3, history=history)
    assert [match.year for match in matches] == [2015]


def test_trajectory_length_and_disclaimer():
    history = [candidate(2015, 46, trajectory=[float(i) for i in range(13)])]
    match = AnalogEngine.find_analogs(context(), CURRENT, top_n=1, history=history)[0]
    assert len(match.trajectory) == 13
    assert match.delta_fill_90d == pytest.approx(12.0)
    assert "not a forecast" in match.disclaimer.lower()


def test_analog_validation_rejects_empty_feature_set():
    with pytest.raises(ScenarioValidationError):
        AnalogEngine.find_analogs(context(), {"fill_pct": 18.0}, top_n=3, history=[])
