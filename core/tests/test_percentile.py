import math

import pytest

from core.services.stats import (
    empirical_spi,
    ols_slope,
    percentile_score,
    week_bin,
)


def test_midrank_percentile_fixture():
    result = percentile_score(list(range(1, 27)), 13.5)
    assert result.score == pytest.approx(50.0)
    assert result.rank == pytest.approx(0.5)
    assert result.n == 26
    assert result.data_status == "OK"


def test_empty_baseline_is_no_data_not_fifty_truth():
    result = percentile_score([], 12.0)
    assert result.score == 50.0
    assert result.available is False
    assert result.confidence == 0.0
    assert result.data_status == "NO_DATA"


def test_degenerate_baseline_three_branches():
    baseline = [18.0] * 26
    low = percentile_score(baseline, 17.0)
    equal = percentile_score(baseline, 18.0)
    high = percentile_score(baseline, 19.0)
    assert low.score == pytest.approx(3.571, abs=1e-3)
    assert equal.score == pytest.approx(50.0)
    assert high.score == pytest.approx(96.429, abs=1e-3)
    assert low.confidence == 0.5


def test_lower_is_better_inverts_the_score():
    higher = percentile_score([1, 2, 3, 4, 5], 5.0, higher_is_better=True)
    lower = percentile_score([1, 2, 3, 4, 5], 5.0, higher_is_better=False)
    assert higher.score > 50
    assert lower.score == pytest.approx(100.0 - higher.score)


def test_week_bins():
    assert week_bin(1) == 1
    assert week_bin(7) == 1
    assert week_bin(8) == 2
    assert week_bin(357) == 51
    assert week_bin(358) == 52
    assert week_bin(366) == 52


def test_empirical_spi_uses_raw_totals_once():
    values = [10.0, 20.0, 30.0, 40.0, 50.0]
    spi = empirical_spi(values, 35.0)
    assert spi.score == pytest.approx(400.0 / 7.0)
    assert spi.data_status == "OK"


def test_ols_slope_direction():
    slope, intercept, r2 = ols_slope([0, 1, 2, 3], [1.0, 3.0, 5.0, 7.0])
    assert slope == pytest.approx(2.0)
    assert intercept == pytest.approx(1.0)
    assert r2 == pytest.approx(1.0)
