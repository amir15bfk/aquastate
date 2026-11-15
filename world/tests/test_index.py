from __future__ import annotations

import math
from datetime import date, timedelta

from django.test import SimpleTestCase

from world.services.country_index import compute_country, status_for
from world.services.statistics import hargreaves_pet_mm_day, mid_rank_percentile


def _monthly(years=10):
    rows = []
    start = 2016
    for year in range(start, start + years):
        for month in range(1, 13):
            rows.append(
                {
                    "month": date(year, month, 1),
                    "precip_mm": 20.0 + (month * 3.0) + (year % 5),
                    "tmean": 20.0 + math.sin(month / 12 * 2 * math.pi) * 6,
                    "tmax": 28.0 + math.sin(month / 12 * 2 * math.pi) * 6,
                    "tmin": 12.0 + math.sin(month / 12 * 2 * math.pi) * 4,
                    "soil_root": 0.30 + (month / 100.0),
                    "soil_top": 0.25 + (month / 120.0),
                }
            )
    return rows


def _forecast():
    today = date.today()
    rows = []
    for offset in range(-100, 17):
        rows.append(
            {
                "date": today + timedelta(days=offset),
                "precip_mm": 2.0 if offset % 7 == 0 else 0.0,
                "tmax": 30.0,
                "tmin": 18.0,
                "rh_min": 35.0,
                "wind_max": 12.0,
                "soil_surface": 0.22,
                "soil_root": 0.28,
            }
        )
    return rows


def _flood():
    today = date.today()
    rows = []
    for offset in range(-60, 17):
        rows.append(
            {
                "date": today + timedelta(days=offset),
                "discharge": 100.0 + (offset % 10) * 4.0,
            }
        )
    return rows


class PercentileTests(SimpleTestCase):
    def test_midrank_symmetric_sample_is_50(self):
        result = mid_rank_percentile([1, 2, 3, 4, 5], 3)
        self.assertTrue(result["available"])
        self.assertAlmostEqual(result["score"], 50.0, places=1)

    def test_empty_history_is_unavailable(self):
        result = mid_rank_percentile([], 3)
        self.assertFalse(result["available"])
        self.assertEqual(result["confidence"], 0.0)

    def test_pet_is_positive_and_zero_when_tmax_equals_tmin(self):
        self.assertGreater(hargreaves_pet_mm_day(28, 200, 35, 20, 27.5), 0)
        self.assertEqual(hargreaves_pet_mm_day(28, 200, 20, 20, 20), 0)


class CountryIndexTests(SimpleTestCase):
    def test_full_country_scores_and_weights(self):
        result = compute_country(
            iso2="XX",
            iso3="XXX",
            country_name="Testland",
            lat=28.0,
            monthly=_monthly(),
            forecast_rows=_forecast(),
            flood_rows=_flood(),
            bank={
                "population": {"XXX": {"latest": 1_000_000, "year": 2025}},
                "freshwater_per_capita": {"XXX": {"latest": 4200, "year": 2025}},
                "freshwater_withdrawal_pct": {"XXX": {"latest": 40, "year": 2025}},
                "forest_area_pct": {"XXX": {"latest": 30, "change_pct": -1.5, "year": 2025}},
            },
            event_counts={"XX:wildfires": 1, "XX:floods": 0},
        )
        self.assertIsNotNone(result["score"])
        self.assertGreaterEqual(result["score"], 0)
        self.assertLessEqual(result["score"], 100)
        self.assertEqual(result["version"], "WCRI-2.0")
        self.assertAlmostEqual(sum(result["aggregation"]["weights"].values()), 1.0, places=5)
        self.assertEqual(len(result["pillars"]), 6)
        self.assertGreater(result["coverage"], 0.9)
        for hazard in ("drought", "flood", "fire", "desertification"):
            self.assertIn(hazard, result["hazards"])

    def test_missing_data_is_no_data_not_a_fake_score(self):
        result = compute_country(
            iso2="XX",
            iso3="XXX",
            country_name="Testland",
            lat=0.0,
            monthly=[],
            forecast_rows=[],
            flood_rows=[],
            bank={},
            event_counts={},
        )
        self.assertIsNone(result["score"])
        self.assertEqual(result["status"], "no_data")
        self.assertEqual(result["coverage"], 0.0)

    def test_status_bands(self):
        self.assertEqual(status_for(75)[0], "resilient")
        self.assertEqual(status_for(60)[0], "stable")
        self.assertEqual(status_for(45)[0], "watch")
        self.assertEqual(status_for(30)[0], "stressed")
        self.assertEqual(status_for(10)[0], "critical")
        self.assertEqual(status_for(None)[0], "no_data")
