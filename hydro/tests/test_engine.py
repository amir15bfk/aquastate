from __future__ import annotations

from datetime import date, timedelta

from django.test import TestCase
from django.utils import timezone

from hydro.models import ClimateDay, Country, ForecastDay, Reservoir, StorageYear
from hydro.services.index_engine import compute_index, make_scenario
from hydro.services.storage import estimated_inflow, estimated_surface_area


class EngineFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.country = Country.objects.create(
            iso2="ZZ",
            iso3="ZZZ",
            name="Testland",
            region="Test",
            subregion="Fixture",
            lat=36.5,
            lon=3.0,
            bbox=[0, 30, 8, 38],
            has_outline=False,
            population=5_000_000,
            area_km2=100_000,
            reservoir_demand_mm3_day=2.0,
            data_mode="fallback",
            profile={"hydrologic_centroid": {"lat": 36.5, "lon": 3.0}},
        )
        cls.reservoir = Reservoir.objects.create(
            country=cls.country,
            name="Test Dam",
            lat=36.4,
            lon=3.1,
            capacity_mm3=1000,
            storage_mm3=140,
            dead_storage_mm3=100,
            surface_area_km2=estimated_surface_area(1000),
            inflow_mm3_day=0.1,
            demand_mm3_day=2.0,
            reference_storage_pct=14,
            storage_source="blended",
            source_name="Test fixture",
        )
        today = date.today()
        climate = []
        for offset in range(365 * 10):
            day = today - timedelta(days=365 * 10 - offset)
            climate.append(
                ClimateDay(
                    country=cls.country,
                    date=day,
                    precip_mm=0.0,
                    soil_surface=0.25,
                    soil_root=0.25,
                    et0_mm=4.0,
                    source="Test fixture",
                    fetched_at=timezone.now(),
                )
            )
        ClimateDay.objects.bulk_create(climate, batch_size=1000)
        ForecastDay.objects.bulk_create(
            [
                ForecastDay(
                    country=cls.country,
                    reservoir=cls.reservoir,
                    date=today + timedelta(days=offset),
                    precip_mm=0.0,
                    et0_mm=4.0,
                    source="Test forecast",
                    fetched_at=timezone.now(),
                )
                for offset in range(16)
            ]
        )
        StorageYear.objects.bulk_create(
            [
                StorageYear(
                    reservoir=cls.reservoir,
                    year=2016 + index,
                    end_storage_pct=70 - index * 2,
                    source="Test fixture",
                )
                for index in range(11)
            ]
        )


class IndexEngineTests(EngineFixture):
    def test_weights_sum_to_one(self):
        result = compute_index(self.country)
        self.assertAlmostEqual(sum(result["index"]["weights"].values()), 1.0, places=6)

    def test_buffer_anchor_30_days_is_about_39(self):
        self.assertAlmostEqual(100 * (30 / 90) ** 0.85, 39.3, places=1)

    def test_five_pillars_and_contributions_reconcile(self):
        result = compute_index(self.country)
        self.assertEqual(len(result["pillars"]), 5)
        weighted = sum(row["weight"] * row["value"] for row in result["pillars"])
        self.assertAlmostEqual(weighted, result["index"]["weighted_sum"], places=1)
        self.assertAlmostEqual(
            result["index"]["weighted_sum"] - result["index"]["bottleneck_penalty"],
            result["index"]["base_value"],
            places=1,
        )

    def test_whatif_is_horizon_secured_and_does_not_rewrite_score(self):
        result = compute_index(self.country, make_scenario("whatif", 1.0, 14))
        self.assertEqual(result["horizon"]["state"], "secured")
        self.assertEqual(result["index"]["headline_label"], "OK until rain")
        self.assertLess(result["index"]["value"], 60)
        self.assertEqual(result["index"]["value"], result["index"]["base_value"])
        self.assertFalse(result["index"]["horizon_gate"]["applied"])
        self.assertTrue(result["index"]["horizon_gate"]["secured"])
        self.assertEqual(len(result["horizon"]["runway"]), 30)
        self.assertTrue(result["horizon"]["covered_to_relief"])
        self.assertTrue(result["horizon"]["post_relief_ok"])

    def test_dry_and_forecast_without_rain_are_exposed(self):
        for rain in ("forecast", "dry"):
            result = compute_index(self.country, make_scenario(rain, 1.0, 14))
            self.assertEqual(result["horizon"]["state"], "exposed")
            self.assertEqual(result["horizon"]["days_to_rain"], None)
            self.assertNotEqual(result["index"]["headline_label"], "OK until rain")

    def test_demand_stress_reduces_runway(self):
        normal = compute_index(self.country, make_scenario("whatif", 1.0, 14))
        stressed = compute_index(self.country, make_scenario("whatif", 1.3, 14))
        self.assertLess(stressed["horizon"]["cover_days"], normal["horizon"]["cover_days"])
        self.assertLessEqual(stressed["index"]["value"], normal["index"]["value"])

    def test_horizon_horizon_seven_days_still_secures(self):
        result = compute_index(self.country, make_scenario("whatif", 1.0, 7))
        self.assertEqual(result["horizon"]["state"], "secured")
        self.assertLessEqual(result["horizon"]["days_to_rain"], 7)

    def test_no_reservoir_returns_empty_state(self):
        other = Country.objects.create(iso2="YY", name="Empty", lat=10, lon=10)
        result = compute_index(other)
        self.assertEqual(result["index"]["status_label"], "No data")
        self.assertEqual(result["reservoirs"], [])

    def test_ai_off_by_default_and_core_unchanged(self):
        result = compute_index(self.country, make_scenario("whatif", 1.0, 14))
        self.assertFalse(result["ai_trace"]["enabled"])
        before = result["index"]["value"]
        result["ai_trace"]["contributions"] = []
        self.assertEqual(result["index"]["value"], before)
