from __future__ import annotations

from django.test import Client, TestCase
from django.utils import timezone

from hydro.models import Country
from world.models import (
    CountryProfile,
    DamAtlas,
    HazardEvent,
    SourceStatus,
    WorldSnapshot,
)


class WorldPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.country = Country.objects.create(iso2="DZ", iso3="DZA", name="Algeria", lat=28, lon=3)
        cls.profile = CountryProfile.objects.create(
            country=cls.country,
            iso2="DZ",
            iso3="DZA",
            region="Africa",
            subregion="Northern Africa",
            population=47_000_000,
            area_km2=2_381_741,
            climate={
                "annual_precip_mm": 120,
                "annual_pet_mm": 2200,
                "aridity_index": 0.05,
                "precip_trend_pct_per_year": -2.1,
                "annual_series": [{"year": 2024, "precip_mm": 130}, {"year": 2025, "precip_mm": 100}],
                "source": "NASA POWER / MERRA-2 monthly",
            },
            hazards={
                "drought": {"pressure": 62, "value": 38, "confidence": 0.85, "source": "test", "inputs": {}},
                "flood": {"pressure": 10, "value": 90, "confidence": 0.75, "source": "test", "inputs": {}},
                "fire": {"pressure": 27, "value": 73, "confidence": 0.65, "source": "test", "inputs": {}},
                "desertification": {"pressure": 65, "value": 35, "confidence": 0.75, "source": "test", "inputs": {}},
            },
            index={
                "score": 42.3,
                "status": "watch",
                "status_label": "Watch",
                "confidence": 0.72,
                "coverage": 1.0,
                "version": "WCRI-2.0",
                "pillars": {
                    "water": {"key": "water", "label": "Water availability", "value": 16.4, "weight": 0.22, "contribution": -7.4, "confidence": 0.75, "formula": "W", "interpretation": "water", "source_kind": "live"},
                    "drought": {"key": "drought", "label": "Drought & soil", "value": 37.9, "weight": 0.20, "contribution": -2.4, "confidence": 0.85, "formula": "D", "interpretation": "drought", "source_kind": "live"},
                    "flood": {"key": "flood", "label": "Flood resilience", "value": 90, "weight": 0.14, "contribution": 5.6, "confidence": 0.75, "formula": "F", "interpretation": "flood", "source_kind": "live"},
                },
                "aggregation": {"formula": "WCRI = ...", "weights": {"water": 0.22}, "coverage": 1.0},
            },
            score=42.3,
            status="watch",
            confidence=0.72,
            coverage=1.0,
            rank=237,
            as_of=timezone.localdate(),
            data_mode="live",
        )
        cls.dam = DamAtlas.objects.create(
            wikidata_id="QTEST",
            name="Test Dam",
            country_iso2="DZ",
            country_name="Algeria",
            lat=36.0,
            lon=3.0,
            capacity_m3=100_000_000,
            is_monitored=False,
            source="Test inventory",
        )
        HazardEvent.objects.create(
            eonet_id="EONET_TEST",
            category="wildfires",
            title="Test fire",
            lat=36.0,
            lon=3.0,
            event_date=timezone.now(),
            country_iso2="DZ",
        )
        SourceStatus.objects.create(
            key="nasa_power", label="NASA POWER", kind="live", records=100,
            last_success=timezone.now(), ttl_seconds=3600,
        )
        WorldSnapshot.objects.create(
            version="test-version",
            as_of=timezone.now(),
            payload={"countries": [{"iso2": "DZ", "name": "Algeria", "score": 42.3, "status": "watch", "status_label": "Watch", "lat": 28, "lon": 3, "rank": 237, "confidence": 0.72, "coverage": 1.0, "hazards": {"drought": 62, "flood": 10, "fire": 27, "desertification": 65}, "pillars": {}, "aridity": 0.05, "trend": -2.1}]},
            summary={"countries": 1, "scored": 1, "average": 42.3, "bands": {"resilient": 0, "stable": 0, "watch": 1, "stressed": 0, "critical": 0, "no_data": 0}, "events": 1, "version": "test-version"},
            is_current=True,
        )
        cls.client = Client()

    def test_overview_renders_map_and_rank(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("Water is the secret of life", html)
        self.assertIn("world-map", html)
        self.assertIn("Algeria", html)

    def test_world_api_has_country_and_version(self):
        response = self.client.get("/api/world/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["version"], "test-version")
        self.assertEqual(payload["countries"][0]["iso2"], "DZ")
        self.assertEqual(response["ETag"], '"test-version"')

    def test_country_sheet_renders_index_and_hazards(self):
        response = self.client.get("/country/DZ/")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        for phrase in ("Algeria", "Why this score", "Drought", "Desertification", "Water system", "Test Dam"):
            self.assertIn(phrase, html)

    def test_dams_atlas_and_search(self):
        response = self.client.get("/dams/?q=Test")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Test Dam", response.content.decode())
        payload = self.client.get("/api/dams/?q=Test").json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["wikidata_id"], "QTEST")

    def test_inventory_dam_sheet(self):
        response = self.client.get("/dam/QTEST/")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("Test Dam", html)
        self.assertIn("not monitored", html.lower())

    def test_hazards_and_docs_pages(self):
        for path in ("/hazards/", "/methodology/", "/sources/"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
        self.assertIn("Drought is the first domino", self.client.get("/hazards/").content.decode())
        self.assertIn("WCRI-2.0", self.client.get("/methodology/").content.decode())
        self.assertIn("Source ledger", self.client.get("/sources/").content.decode())

    def test_events_api(self):
        payload = self.client.get("/api/events/").json()
        self.assertEqual(payload["type"], "FeatureCollection")
        self.assertEqual(payload["features"][0]["properties"]["title"], "Test fire")

    def test_refresh_is_post_only(self):
        self.assertEqual(self.client.get("/api/world/refresh/").status_code, 405)

    def test_meta_api(self):
        payload = self.client.get("/api/world/meta/").json()
        self.assertEqual(payload["version"], "test-version")
        self.assertIn("sources", payload)
