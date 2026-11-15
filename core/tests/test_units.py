import math

import pytest

from core.services.units import (
    frustum_delta_volume_m3,
    km2_to_m2,
    level_to_volume_m3,
    m3_to_mm_over_km2,
    mm_over_km2_to_m3,
    surface_area_at_volume_m2,
    volume_to_level_m,
)


def _points():
    return [
        {"elevation_m": 0.0, "area_km2": 0.0, "volume_m3": 0.0, "order": 0},
        {"elevation_m": 10.0, "area_km2": 1.0, "volume_m3": 5_000_000.0, "order": 1},
        {"elevation_m": 20.0, "area_km2": 2.0, "volume_m3": 20_000_000.0, "order": 2},
    ]


def test_one_mm_over_one_km2_is_one_thousand_m3():
    assert mm_over_km2_to_m3(1.0, 1.0) == pytest.approx(1_000.0)
    assert km2_to_m2(1.0) == pytest.approx(1_000_000.0)


def test_m3_to_mm_round_trip():
    volume = mm_over_km2_to_m3(37.5, 2_000.0)
    assert m3_to_mm_over_km2(volume, 2_000.0) == pytest.approx(37.5)


def test_frustum_cylinder_limit():
    assert frustum_delta_volume_m3(0.0, 2.0, 100.0, 100.0) == pytest.approx(200.0)


def test_frustum_zero_top_area_is_cone():
    # Cone volume = (1/3) * base area * height.
    assert frustum_delta_volume_m3(0.0, 3.0, 300.0, 0.0) == pytest.approx(300.0)


def test_level_volume_round_trip():
    points = _points()
    volume = level_to_volume_m3(15.0, points)
    assert volume == pytest.approx(12_500_000.0)
    assert volume_to_level_m(volume, points) == pytest.approx(15.0)


def test_surface_area_between_levels():
    points = _points()
    area = surface_area_at_volume_m2(12_500_000.0, points)
    assert area == pytest.approx(1_500_000.0)


def test_levels_clamp_to_bathymetry_ends():
    points = _points()
    assert level_to_volume_m3(-5.0, points) == 0.0
    assert level_to_volume_m3(99.0, points) == pytest.approx(20_000_000.0)
    assert volume_to_level_m(-1.0, points) == 0.0
    assert volume_to_level_m(99_000_000.0, points) == pytest.approx(20.0)
