import datetime as dt
import json
import math

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


def _json(response):
    return json.loads(response.content.decode("utf-8"))


def test_health(seeded):
    response = Client().get("/api/pilot/health/")
    assert response.status_code == 200
    body = _json(response)
    assert body["status"] == "ok"


def test_countries_include_dza_and_tun(seeded):
    response = Client().get("/api/pilot/countries/")
    assert response.status_code == 200
    body = _json(response)
    iso3 = {country["iso3"] for country in body["countries"]}
    assert {"DZA", "TUN"} <= iso3


def test_country_dam_filter_returns_ten_total(seeded):
    client = Client()
    dza = _json(client.get("/api/pilot/countries/DZA/dams/"))
    tun = _json(client.get("/api/pilot/countries/TUN/dams/"))
    assert len(dza["dams"]) == 6
    assert len(tun["dams"]) == 4
    assert {dam["slug"] for dam in dza["dams"] + tun["dams"]} >= {
        "beni-haroun",
        "sidi-salem",
        "bakhadda",
        "nebhana",
    }


def test_dam_detail_has_explainable_payload(seeded):
    response = Client().get("/api/pilot/dams/beni-haroun/")
    assert response.status_code == 200
    body = _json(response)
    assert body["dam"]["slug"] == "beni-haroun"
    assert body["hri"] == pytest.approx(81.05, abs=0.05)
    assert body["status"] == "RECHARGING"
    assert body["phi"] == pytest.approx(0.94977, abs=1e-4)
    assert set(body["sub_indices"]) >= {"SSI", "CMI", "SRRI", "EESI"}
    assert body["sub_indices"]["SAI"]["available"] is False
    assert body["contributions"]["SSI"] > 0
    assert body["explanation"]
    assert body["proof_steps"]
    assert isinstance(body["analogs"], list)
    assert body["agent_slot_status"] == "DETERMINISTIC_MVP"
    assert body["data_mode"] == "seeded"


def test_every_score_is_in_range_and_finite(seeded):
    body = _json(Client().get("/api/pilot/dams/beni-haroun/"))

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
    for score in body["sub_indices"].values():
        if isinstance(score, dict):
            assert 0.0 <= score["score"] <= 100.0
        else:
            assert 0.0 <= score <= 100.0


def test_scenario_post_200_and_400(seeded):
    client = Client()
    ok = client.post(
        "/api/pilot/dams/beni-haroun/scenario/",
        data=json.dumps({"rain_multiplier": 0.0}),
        content_type="application/json",
    )
    assert ok.status_code == 200
    body = _json(ok)
    assert body["scenario"]["hri"] == pytest.approx(24.9, abs=0.05)
    assert body["scenario"]["status"] == "CRITICAL"
    assert body["is_scenario"] is True
    assert body["delta"] < 0

    bad = client.post(
        "/api/pilot/dams/beni-haroun/scenario/",
        data=json.dumps({"rain_multiplier": 9}),
        content_type="application/json",
    )
    assert bad.status_code == 400
    error = _json(bad)["error"]
    assert error["code"] == "invalid_scenario"
    assert "message" in error


def test_scenario_post_is_csrf_protected(seeded):
    client = Client(enforce_csrf_checks=True)
    response = client.post(
        "/api/pilot/dams/beni-haroun/scenario/",
        data=json.dumps({"rain_multiplier": 0.0}),
        content_type="application/json",
    )
    assert response.status_code == 403


def test_unknown_dam_is_json_404(seeded):
    response = Client().get("/api/pilot/dams/not-a-dam/")
    assert response.status_code == 404
    assert _json(response)["error"]["code"] == "not_found"


def test_timeseries(seeded):
    response = Client().get(
        "/api/pilot/dams/beni-haroun/timeseries/?metric=fill_pct&days=365"
    )
    assert response.status_code == 200
    body = _json(response)
    assert body["metric"] == "fill_pct"
    assert len(body["points"]) > 0
    assert all(0.0 <= point["value"] <= 100.0 for point in body["points"])

    bad = Client().get("/api/pilot/dams/beni-haroun/timeseries/?metric=secret")
    assert bad.status_code == 400


def test_map_payload_is_valid_geojson_with_all_ten_dams(seeded):
    response = Client().get("/api/pilot/dams/beni-haroun/map/")
    assert response.status_code == 200
    body = _json(response)
    assert body["type"] == "FeatureCollection"
    assert len(body["features"]) == 10
    for feature in body["features"]:
        assert feature["geometry"]["type"] in {"Point", "Polygon"}
        assert math.isfinite(feature["geometry"]["coordinates"][0] if feature["geometry"]["type"] == "Point" else feature["geometry"]["coordinates"][0][0][0])


def test_compute_indices_command_persists_snapshot(seeded):
    from core.models import Dam, IndexSnapshot

    call_command("compute_indices", "--all", "--as-of", "2026-11-13", verbosity=0)
    dam = Dam.objects.get(slug="beni-haroun")
    snapshot = IndexSnapshot.objects.filter(dam=dam).order_by("-as_of").first()
    assert snapshot is not None
    assert snapshot.hri == pytest.approx(81.05, abs=0.05)
    assert snapshot.status == "RECHARGING"
    assert snapshot.sub_indices["SSI"] == pytest.approx(5.357, abs=1e-3)
