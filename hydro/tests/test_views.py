from __future__ import annotations

import json
from io import StringIO

from django.core.management import call_command
from django.test import Client, TestCase

from hydro.models import Country, IndexSnapshot


class DashboardViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", "--offline", verbosity=0, stdout=StringIO())
        cls.client = Client()

    def test_dashboard_renders_explainability_and_map(self):
        response = self.client.get("/water/DZ/")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        for phrase in (
            "Algeria water state",
            "Horizon verdict",
            "Water runway",
            "What builds the index",
            "Underground reserve",
            "Storage buffer",
            "Reservoir ledger",
            "What is live, what is modeled, what is reference",
            "data-pillar",
        ):
            self.assertIn(phrase, html)
        self.assertIn('id="map"', html)
        self.assertIn('id="dashboard-data"', html)

    def test_country_switch_and_scenario_render(self):
        response = self.client.get("/water/TN/?rain=whatif&demand=1.2&horizon=14")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("Tunisia water state", html)
        self.assertIn("Rain in 2 days", html)
        self.assertIn("what-if", html)
        self.assertIn("what-if scenario, not a live forecast", html)

    def test_switch_endpoint_redirects(self):
        response = self.client.get("/switch/?iso2=TN")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/water/TN/", response["Location"])

    def test_methodology_and_sources_pages(self):
        for path in ("/methodology/", "/sources/"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
        self.assertIn("WCRI-2.0", self.client.get("/methodology/").content.decode())
        self.assertIn("Source ledger", self.client.get("/sources/").content.decode())

    def test_health(self):
        response = self.client.get("/health/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["version"], "WRI-2.0")
        self.assertFalse(payload["ai_agents_enabled"])
        self.assertGreaterEqual(payload["countries_in_gazetteer"], 200)

    def test_refresh_is_post_only(self):
        response = self.client.get("/api/country/DZ/refresh/")
        self.assertEqual(response.status_code, 405)


class APITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", "--offline", verbosity=0, stdout=StringIO())
        cls.client = Client()

    def test_api_payload_schema(self):
        response = self.client.get("/api/country/DZ/")
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertEqual(payload["meta"]["version"], "WRI-2.0")
        self.assertEqual(payload["country"]["iso2"], "DZ")
        self.assertEqual(len(payload["pillars"]), 5)
        self.assertAlmostEqual(sum(payload["index"]["weights"].values()), 1.0, places=6)
        self.assertEqual(len(payload["horizon"]["runway"]), 30)
        self.assertEqual(len(payload["reservoirs"]), 16)
        self.assertFalse(payload["ai_trace"]["enabled"])
        self.assertGreater(payload["index"]["confidence"], 0)
        self.assertTrue(payload["sources"])
        self.assertTrue(payload["data_quality"]["notes"])
        self.assertIn("hydrologic_centroid", payload)

    def test_api_scenario_changes_horizon_and_does_not_persist(self):
        before = IndexSnapshot.objects.filter(country__iso2="DZ").count()
        response = self.client.get("/api/country/DZ/?rain=dry&demand=1.3&horizon=7")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["scenario"]["rain"], "dry")
        self.assertEqual(payload["scenario"]["demand_factor"], 1.3)
        self.assertEqual(payload["scenario"]["horizon_days"], 7)
        self.assertTrue(payload["scenario"]["hypothetical"] is False)
        self.assertNotEqual(payload["horizon"]["state"], "secured")
        after = IndexSnapshot.objects.filter(country__iso2="DZ").count()
        self.assertEqual(before, after)

    def test_whatif_is_marked_hypothetical(self):
        payload = self.client.get("/api/country/DZ/?rain=whatif").json()
        self.assertTrue(payload["scenario"]["hypothetical"])
        self.assertEqual(payload["index"]["value"], payload["index"]["base_value"])
        self.assertFalse(payload["index"]["horizon_gate"]["applied"])
        self.assertEqual(payload["index"]["headline_label"], "OK until rain")
        self.assertEqual(payload["horizon"]["state"], "secured")

    def test_audit_endpoint(self):
        response = self.client.get("/api/country/DZ/audit/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        for key in ("formula", "weights", "pillars", "horizon", "ai", "ai_trace", "sources"):
            self.assertIn(key, payload)
        self.assertFalse(payload["ai"]["policy"]["enabled"])
        self.assertEqual(len(payload["pillars"]), 5)

    def test_ai_slots_endpoint(self):
        payload = self.client.get("/api/ai/slots/").json()
        self.assertEqual(len(payload["slots"]), 5)
        self.assertTrue(all(not slot["enabled"] for slot in payload["slots"]))
        self.assertEqual(payload["contract"].split(".")[0], "Agent suggestions are advisory only")

    def test_countries_endpoint(self):
        payload = self.client.get("/api/countries/").json()
        self.assertGreaterEqual(payload["count"], 200)
        codes = {row["iso2"] for row in payload["countries"]}
        self.assertIn("DZ", codes)
        self.assertIn("TN", codes)

    def test_unknown_country(self):
        self.assertEqual(self.client.get("/api/country/QQ/").status_code, 404)
        self.assertEqual(self.client.get("/country/QQ/").status_code, 404)

    def test_tunisia_profile_is_curated(self):
        payload = self.client.get("/api/country/TN/").json()
        self.assertEqual(len(payload["reservoirs"]), 12)
        self.assertEqual(len(payload["aquifers"]), 3)
        self.assertTrue(all(not row["is_reference_pool"] for row in payload["reservoirs"]))
        self.assertTrue(Country.objects.filter(iso2="TN").exists())
