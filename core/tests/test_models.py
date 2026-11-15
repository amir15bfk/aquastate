import datetime as dt

import pytest
from django.db import IntegrityError, transaction

from core.models import (
    Basin,
    ClimateObservation,
    Country,
    Dam,
    IndexSnapshot,
    ReservoirObservation,
)


@pytest.fixture
def country():
    return Country.objects.create(
        iso3="DZA",
        name="Algeria",
        bbox=[-8.7, 18.9, 12.0, 37.1],
        timezone="Africa/Algiers",
        baseline_start=dt.date(2000, 1, 1),
        baseline_end=dt.date(2025, 12, 31),
    )


@pytest.fixture
def basin(country):
    return Basin.objects.create(
        country=country,
        hydrosheds_id="DZA-001",
        name="Beni Haroun Basin",
        area_km2=2000.0,
        geometry={"type": "Polygon", "coordinates": []},
        centroid_lat=36.5,
        centroid_lon=6.3,
    )


@pytest.fixture
def dam(country, basin):
    return Dam.objects.create(
        country=country,
        basin=basin,
        slug="beni-haroun",
        name="Beni Haroun",
        name_ar="بني هارون",
        name_fr="Beni Haroun",
        lat=36.55,
        lon=6.28,
        capacity_m3=100_000_000.0,
        dead_storage_m3=10_000_000.0,
        max_surface_area_km2=12.0,
        dam_type="embankment",
        year_built=2003,
        purposes=["irrigation", "drinking water"],
    )


@pytest.mark.django_db
def test_dam_usable_capacity(dam):
    assert dam.usable_capacity_m3 == pytest.approx(90_000_000.0)


@pytest.mark.django_db
def test_reservoir_observation_unique_per_dam_and_date(dam):
    day = dt.date(2026, 11, 13)
    ReservoirObservation.objects.create(dam=dam, date=day, fill_pct=18.0)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ReservoirObservation.objects.create(dam=dam, date=day, fill_pct=19.0)


@pytest.mark.django_db
def test_climate_observation_unique_per_basin_and_date(basin):
    day = dt.date(2026, 11, 13)
    ClimateObservation.objects.create(basin=basin, date=day, precip_mm=0.0)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ClimateObservation.objects.create(basin=basin, date=day, precip_mm=1.0)


@pytest.mark.django_db
def test_index_snapshot_orders_newest_first(dam):
    older = IndexSnapshot.objects.create(dam=dam, as_of=dt.date(2026, 11, 1), hri=30.0)
    newer = IndexSnapshot.objects.create(dam=dam, as_of=dt.date(2026, 11, 13), hri=81.0)
    assert list(IndexSnapshot.objects.all()) == [newer, older]
