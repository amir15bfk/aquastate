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
        country="DZA",
        years=6,
        dams="beni-haroun",
        seed=42,
        verbosity=0,
    )


def test_panel_partial_has_all_explainability_regions(seeded):
    response = Client().get("/pilot/dashboard/partials/panel/beni-haroun/")
    assert response.status_code == 200
    html = response.content.decode("utf-8")
    for element_id in ("hero", "waterfall", "bridge", "subindices", "simulator", "analogs"):
        assert f'id="{element_id}"' in html
    assert "NO_DATA" in html
    assert "81.0" in html
    assert "NaN" not in html
    assert "undefined" not in html


def test_scenario_post_updates_panel_regions_with_oob_swaps(seeded):
    response = Client().post(
        "/pilot/dashboard/partials/scenario/beni-haroun/",
        {"rain_multiplier": "0"},
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 200
    html = response.content.decode("utf-8")
    assert "SCENARIO" in html
    assert "24.9" in html
    assert "CRITICAL" in html
    assert "81.0" in html
    assert 'hx-swap-oob="true"' in html
    assert "<html" not in html.lower()
    assert "<body" not in html.lower()
    assert 'id="hero"' in html
    assert 'id="waterfall"' in html
    assert 'id="bridge"' in html
    assert "NaN" not in html
    assert "undefined" not in html


def test_default_scenario_does_not_show_banner(seeded):
    response = Client().post(
        "/pilot/dashboard/partials/scenario/beni-haroun/",
        {"rain_multiplier": "1", "demand_multiplier": "1"},
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 200
    html = response.content.decode("utf-8")
    assert 'id="scenario-banner"' not in html


def test_reset_restores_observed_hri(seeded):
    Client().post(
        "/pilot/dashboard/partials/scenario/beni-haroun/",
        {"rain_multiplier": "0"},
        HTTP_HX_REQUEST="true",
    )
    response = Client().get("/pilot/dashboard/partials/panel/beni-haroun/")
    html = response.content.decode("utf-8")
    assert "81.0" in html
    assert "SCENARIO" not in html


def test_invalid_scenario_returns_error_partial(seeded):
    response = Client().post(
        "/pilot/dashboard/partials/scenario/beni-haroun/",
        {"rain_multiplier": "9"},
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 400
    assert "could not" in response.content.decode("utf-8").lower()


def test_analogs_render_up_to_three_matches(seeded):
    response = Client().get("/pilot/dashboard/partials/panel/beni-haroun/")
    html = response.content.decode("utf-8")
    assert html.count('class="analog"') >= 1
    assert html.count('class="analog"') <= 3
    assert "similarity" in html.lower()
    assert "not a forecast" in html.lower()


def test_scenario_url_round_trip_renders_scenario(seeded):
    response = Client().get("/pilot/?rain=0")
    assert response.status_code == 200
    html = response.content.decode("utf-8")
    assert "SCENARIO" in html
    assert "24.9" in html
    assert "CRITICAL" in html
    assert "81.0" in html


def test_scenario_regions_carry_simulated_labels(seeded):
    response = Client().post(
        "/pilot/dashboard/partials/scenario/beni-haroun/",
        {"rain_multiplier": "0"},
        HTTP_HX_REQUEST="true",
    )
    html = response.content.decode("utf-8")
    assert html.count("simulated-tag") >= 4
    assert "HX-Push-Url" in response.headers or "hx-push-url" in response.headers


def test_sai_row_is_explicit_no_data_with_regional_diagnostics(seeded):
    html = Client().get("/pilot/dashboard/partials/panel/beni-haroun/").content.decode("utf-8")
    assert "SAI" in html
    assert "NO_DATA" in html
    assert "Regional GRACE percentile" in html
    assert "display-only diagnostic" in html

