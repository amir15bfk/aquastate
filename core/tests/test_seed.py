import datetime as dt
import math

import pytest
from django.core.management import call_command

from core.models import (
    Basin,
    ClimateObservation,
    ClimatologyBin,
    Country,
    Dam,
    ForecastObservation,
    ReservoirObservation,
)


@pytest.mark.django_db
def test_seed_small_profile_is_deterministic():
    options = dict(
        reset=True,
        as_of="2026-11-13",
        country="DZA",
        years=3,
        dams="beni-haroun,keddara,bakhadda",
        seed=42,
        verbosity=0,
    )
    call_command("seed_hydro_data", **options)

    assert Country.objects.filter(iso3="DZA").exists()
    assert Basin.objects.count() == 3
    assert Dam.objects.count() == 3
    assert ReservoirObservation.objects.count() > 0
    assert ClimateObservation.objects.count() > 0

    beni = Dam.objects.get(slug="beni-haroun")
    assert ForecastObservation.objects.filter(basin=beni.basin).count() == 14
    assert beni.capacity_m3 == pytest.approx(100_000_000.0)
    assert beni.usable_capacity_m3 == pytest.approx(90_000_000.0)

    current = ReservoirObservation.objects.filter(dam=beni).order_by("-date").first()
    assert current.date == dt.date(2026, 11, 13)
    assert current.fill_pct == pytest.approx(18.0)
    first_fill = current.fill_pct

    for row in ClimateObservation.objects.all()[:200]:
        for field in ("precip_mm", "et_mm", "pet_mm", "lst_k", "soil_moisture_m3m3"):
            value = getattr(row, field)
            assert value is None or math.isfinite(value)

    call_command("seed_hydro_data", **options)
    beni = Dam.objects.get(slug="beni-haroun")
    again = (
        ReservoirObservation.objects.filter(dam=beni)
        .order_by("-date")
        .first()
    )
    assert again.fill_pct == pytest.approx(first_fill)
    assert Dam.objects.count() == 3


@pytest.mark.django_db
def test_seed_baseline_excludes_current_year():
    call_command(
        "seed_hydro_data",
        reset=True,
        as_of="2026-11-13",
        country="TUN",
        years=3,
        seed=7,
        verbosity=0,
    )
    # 2026 is the current year, not baseline; only the trailing current window
    # is stored so current-state math has observations to read.
    assert not ClimateObservation.objects.filter(
        date__year=2026, date__month__lt=8
    ).exists()
    assert ClimateObservation.objects.filter(date__year=2026).exists()
    assert ClimateObservation.objects.filter(date__year=2023).exists()
    assert Country.objects.filter(iso3="TUN").exists()
    assert Dam.objects.count() == 4

    tune = Dam.objects.get(slug="sidi-salem")
    bucket = ClimatologyBin.objects.get(
        scope_type="dam", scope_id=tune.slug, metric="cmi_p30", week=46
    )
    assert bucket.n <= 3
