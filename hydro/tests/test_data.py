from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings

from hydro.models import Country
from hydro.services import data_service
from hydro.services.gazetteer import default_demand, ensure_country
from hydro.services.index_engine import compute_index, make_scenario


class DataLifecycleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", "--offline", verbosity=0, stdout=StringIO())

    def test_fallback_profile_has_labeled_sources(self):
        country = Country.objects.get(iso2="DZ")
        report = data_service.refresh_country(country, allow_network=False, force=True)
        self.assertEqual(report["status"], "fallback")
        self.assertEqual(country.data_mode, "fallback")
        self.assertTrue(country.climate_days.exists())
        self.assertTrue(country.forecast_days.exists())
        ledger = data_service.source_ledger(country)
        kinds = {row["key"]: row["kind"] for row in ledger}
        self.assertEqual(kinds["climate"], "fallback")
        self.assertEqual(kinds["forecast"], "fallback")
        self.assertEqual(kinds["inventory"], "reference")
        self.assertEqual(kinds["storage"], "modeled")

    def test_hydrologic_centroid_follows_the_dams(self):
        country = Country.objects.get(iso2="DZ")
        data_service.refresh_country(country, allow_network=False, force=True)
        country.refresh_from_db()
        centroid = country.profile["hydrologic_centroid"]
        self.assertGreater(abs(centroid["lat"] - country.lat), 2)
        self.assertGreater(centroid["lat"], 34)

    def test_storage_rows_and_history_are_created(self):
        country = Country.objects.get(iso2="TN")
        data_service.refresh_country(country, allow_network=False, force=True)
        self.assertEqual(country.reservoirs.count(), 12)
        self.assertTrue(all(reservoir.storage_years.exists() for reservoir in country.reservoirs.all()))
        result = compute_index(country, make_scenario("forecast", 1.0, 14))
        self.assertEqual(len(result["series"]["storage_history"]), 11)

    @override_settings(LIVE_DATA_ENABLED=False)
    def test_ensure_profile_never_calls_network_when_disabled(self):
        country = Country.objects.get(iso2="DZ")
        data_service.refresh_country(country, allow_network=False, force=True)
        result = data_service.ensure_profile(country, allow_network=True)
        self.assertEqual(result["status"], "cached")

    def test_default_demand_has_physical_units(self):
        demand = default_demand({"population": 1_000_000, "area_km2": 1000})
        self.assertAlmostEqual(demand, 0.3, places=4)

    def test_uncurated_country_gets_a_reference_pool(self):
        country = ensure_country("FR")
        self.assertIsNotNone(country)
        self.assertGreater(country.population, 50_000_000)
        self.assertTrue(country.has_outline)
        data_service.refresh_country(country, allow_network=False, force=True)
        self.assertEqual(country.reservoirs.count(), 1)
        pool = country.reservoirs.first()
        self.assertTrue(pool.is_reference_pool)
        self.assertGreater(pool.capacity_mm3, 1000)
        result = compute_index(country)
        self.assertEqual(len(result["reservoirs"]), 1)
        self.assertGreater(result["hydrologic_centroid"]["lat"], 40)
