import json
from pathlib import Path

import pytest
from django.core.management import call_command
from django.template.loader import render_to_string
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


def test_dashboard_renders_split_screen_with_default_beni_haroun(seeded):
    response = Client().get("/pilot/")
    assert response.status_code == 200
    html = response.content.decode("utf-8")
    assert "Hydrological Resilience Index" in html
    assert "Beni Haroun" in html
    assert 'id="map"' in html
    assert 'id="panel"' in html
    assert "RECHARGING" in html
    assert "SCENARIO" not in html


def test_country_switch_to_tunisia(seeded):
    response = Client().get("/pilot/?country=TUN")
    assert response.status_code == 200
    html = response.content.decode("utf-8")
    assert "Sidi Salem" in html
    assert "TUN" in html


def test_unknown_dam_is_404(seeded):
    assert Client().get("/pilot/?dam=not-a-dam").status_code == 404


def test_panel_and_country_partials(seeded):
    panel = Client().get("/pilot/dashboard/partials/panel/beni-haroun/")
    country = Client().get("/pilot/dashboard/partials/country/TUN/")
    assert panel.status_code == 200
    assert "Hydrological Resilience Index" in panel.content.decode("utf-8")
    assert country.status_code == 200
    assert "Sidi Salem" in country.content.decode("utf-8")


def test_skeleton_empty_and_error_partials_render():
    assert "Loading" in render_to_string("dashboard/partials/_skeleton.html")
    assert "No pilot data" in render_to_string("dashboard/partials/_empty.html")
    assert "could not" in render_to_string(
        "dashboard/partials/_error.html", {"message": "The dam could not be loaded."}
    ).lower()


def test_map_data_static_files_are_valid_geojson():
    base = Path(__file__).resolve().parents[2] / "static" / "data"
    dams = json.loads((base / "dams.geojson").read_text(encoding="utf-8"))
    countries = json.loads((base / "countries.geojson").read_text(encoding="utf-8"))
    basins = json.loads((base / "basins.geojson").read_text(encoding="utf-8"))
    assert dams["type"] == "FeatureCollection"
    assert len(dams["features"]) == 10
    assert {f["properties"]["slug"] for f in dams["features"]} >= {
        "beni-haroun",
        "sidi-salem",
    }
    assert len(countries["features"]) == 2
    assert len(basins["features"]) == 10
    for feature in dams["features"]:
        lon, lat = feature["geometry"]["coordinates"]
        assert -180 <= lon <= 180
        assert -90 <= lat <= 90


def test_page_uses_local_fallback_map_html(seeded):
    html = Client().get("/pilot/").content.decode("utf-8")
    assert "map-fallback" in html
    assert "dams.geojson" in html or "map-data" in html
