import datetime as dt

import pytest

from core.models import (
    Basin,
    BathymetryPoint,
    ClimateObservation,
    ClimatologyBin,
    Country,
    Dam,
    DemandObservation,
    ForecastObservation,
    GraceObservation,
    ReservoirObservation,
)
from core.services.hri import HRISynthesizer
from core.services.providers.seeded import SeededProvider

AS_OF = dt.date(2026, 11, 13)


def _bins(dam, values):
    for metric, series in values.items():
        ClimatologyBin.objects.create(
            scope_type="dam",
            scope_id=dam.slug,
            metric=metric,
            week=46,
            values=series,
            n=len(series),
        )


@pytest.mark.django_db
def test_test_only_country_computes_without_country_branching():
    country = Country.objects.create(
        iso3="XYZ",
        name="Testland",
        bbox=[-1, -1, 12, 10],
        timezone="UTC",
        baseline_start=dt.date(2000, 1, 1),
        baseline_end=dt.date(2025, 12, 31),
    )
    basin = Basin.objects.create(
        country=country,
        hydrosheds_id="XYZ-001",
        name="Testland Basin",
        area_km2=1_000.0,
        geometry={"type": "Polygon", "coordinates": []},
        centroid_lat=5.0,
        centroid_lon=5.0,
    )
    dam = Dam.objects.create(
        country=country,
        basin=basin,
        slug="xyz-dam",
        name="XYZ Dam",
        lat=5.0,
        lon=5.0,
        capacity_m3=10_000_000.0,
        dead_storage_m3=1_000_000.0,
        max_surface_area_km2=2.0,
        metadata={
            "cn_ii": 72.5,
            "theta_wp": 0.12,
            "theta_fc": 0.32,
            "design_storm_mm": 40.0,
            "lst_mean_k": 313.0,
            "projected_pet_mm_day": 4.0,
            "projected_et_pet_ratio": 0.2,
            "projected_lst_anomaly_k": 0.0,
            "projected_soil_moisture": 0.5,
        },
    )
    for order, (elevation, area, volume) in enumerate(
        [(0.0, 0.0, 0.0), (10.0, 1.0, 4_000_000.0), (20.0, 2.0, 10_000_000.0)]
    ):
        BathymetryPoint.objects.create(
            dam=dam, order=order, elevation_m=elevation, area_km2=area, volume_m3=volume
        )
    ReservoirObservation.objects.create(
        dam=dam,
        date=AS_OF,
        fill_pct=30.0,
        volume_m3=3_700_000.0,
        water_area_km2=1.0,
        source="seeded",
    )
    for offset in range(90, -1, -1):
        ClimateObservation.objects.create(
            basin=basin,
            date=AS_OF - dt.timedelta(days=offset),
            precip_mm=20.0 if offset in (3, 10, 40) else 0.0,
            et_mm=1.0,
            pet_mm=4.0,
            lst_k=314.0,
            soil_moisture_m3m3=0.35,
        )
    ForecastObservation.objects.create(
        basin=basin,
        issued_at=dt.datetime(2026, 11, 13, 12, tzinfo=dt.timezone.utc),
        date=AS_OF + dt.timedelta(days=1),
        precip_mm=20.0,
    )
    DemandObservation.objects.create(
        dam=dam, date=AS_OF, demand_m3_day=100_000.0, source="seeded"
    )
    GraceObservation.objects.create(
        basin=basin,
        month=dt.date(2026, 1, 1),
        twsa_mm=10.0,
        smsa_mm=2.0,
        swsa_mm=1.0,
        source="seeded",
    )
    _bins(
        dam,
        {
            "ssi_fill_pct": [float(n) for n in range(1, 27)],
            "cmi_p30": [10.0 * n for n in range(1, 27)],
            "cmi_p90": [20.0 * n for n in range(1, 27)],
            "dry_spell": [float(n) for n in range(1, 27)],
            "srri_c_ref": [0.1 + 0.02 * n for n in range(26)],
            "sai_gwsa": [float(n) for n in range(26)],
            "eesi_esi": [0.01 * n for n in range(1, 27)],
            "eesi_evap_ratio": [0.0001 * n for n in range(1, 27)],
            "eesi_lst_anom": [-2.0 + 0.2 * n for n in range(26)],
        },
    )
    ctx = SeededProvider().build_context("xyz-dam", AS_OF)
    result = HRISynthesizer().compute(ctx)
    assert result.available is True
    assert 0.0 <= result.hri <= 100.0
    assert result.status in {
        "CRITICAL", "STRESSED", "WATCH", "STABLE", "RECHARGING", "SURPLUS"
    }
    assert result.components["sub_index_meta"]
