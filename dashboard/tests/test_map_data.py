import json
import math
from pathlib import Path

import pytest
from django.core.management import call_command
from django.test import Client

pytestmark = pytest.mark.django_db


@pytest.fixture
def seeded(db):
    call_command(
        "seed_hydro_data",
        reset=True,
        as_of="2026-11-13",
        country="DZA,TUN",
        years=3,
        seed=42,
        verbosity=0,
    )


def test_api_map_has_ten_dams_and_valid_coordinates(seeded):
    response = Client().get("/api/pilot/dams/beni-haroun/map/")
    assert response.status_code == 200
    body = json.loads(response.content)
    assert body["type"] == "FeatureCollection"
    assert len(body["features"]) == 10
    for feature in body["features"]:
        lon, lat = feature["geometry"]["coordinates"]
        assert math.isfinite(lon) and math.isfinite(lat)
        assert feature["properties"]["slug"]
        assert feature["properties"]["name"]
    assert {f["properties"]["country"] for f in body["features"]} == {"DZA", "TUN"}


def test_map_endpoint_has_no_nan_or_inf(seeded):
    body = json.loads(Client().get("/api/pilot/dams/beni-haroun/map/").content)

    def walk(value):
        if isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, float):
            assert math.isfinite(value)

    walk(body)


def test_map_js_reads_the_api_and_has_a_fallback():
    path = Path(__file__).resolve().parents[2] / "static" / "js" / "map.js"
    source = path.read_text(encoding="utf-8")
    assert "/api/pilot/dams/" in source
    assert "map-fallback" in source
    assert "maplibre" in source.lower()
