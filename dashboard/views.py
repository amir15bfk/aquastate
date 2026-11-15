from __future__ import annotations

import datetime as dt

from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from pydantic import ValidationError

from core.models import Country, Dam, ScenarioRun
from core.services.exceptions import MissingDataError
from core.services.scenario import ScenarioOverrides
from core.services.snapshots import (
    compute_dam_state,
    compute_scenario_state,
)


def _scenario_overrides(request) -> ScenarioOverrides:
    return ScenarioOverrides.from_query(request.GET.urlencode())


def _state_for_request(dam: Dam, as_of, request):
    overrides = _scenario_overrides(request)
    if not overrides.is_default():
        observed_state, state, delta = compute_scenario_state(
            dam.slug, overrides, as_of
        )
        return state, observed_state, True, overrides.model_dump(), delta
    state = compute_dam_state(dam.slug, as_of)
    return state, state, False, {}, None


def _country_or_default(iso3: str | None) -> Country | None:
    if iso3:
        return Country.objects.filter(iso3=iso3.upper()).first()
    return Country.objects.filter(iso3="DZA").first() or Country.objects.first()


def _map_dams() -> list[dict]:
    dams = list(Dam.objects.select_related("country").order_by("country__iso3", "name"))
    if not dams:
        return []
    lons = [dam.lon for dam in dams]
    lats = [dam.lat for dam in dams]
    min_lon, max_lon = min(lons), max(lons)
    min_lat, max_lat = min(lats), max(lats)
    span_lon = max(max_lon - min_lon, 0.01)
    span_lat = max(max_lat - min_lat, 0.01)
    return [
        {
            "slug": dam.slug,
            "name": dam.name,
            "country": dam.country.iso3,
            "lat": dam.lat,
            "lon": dam.lon,
            "x": round(10 + 80 * (dam.lon - min_lon) / span_lon, 2),
            "y": round(10 + 80 * (max_lat - dam.lat) / span_lat, 2),
        }
        for dam in dams
    ]


@ensure_csrf_cookie
def dashboard(request):
    countries = list(Country.objects.all())
    country = _country_or_default(request.GET.get("country"))
    if country is None:
        return render(
            request,
            "dashboard/index.html",
            {"empty": True, "countries": [], "map_dams": []},
        )
    dams = list(country.dams.select_related("basin").order_by("name"))
    if not dams:
        return render(
            request,
            "dashboard/index.html",
            {"empty": True, "countries": countries, "map_dams": _map_dams()},
        )
    requested = request.GET.get("dam")
    if requested:
        dam = next((item for item in dams if item.slug == requested), None)
        if dam is None:
            raise Http404("dam not found in this country")
    else:
        preferred = {"DZA": "beni-haroun", "TUN": "sidi-salem"}.get(country.iso3)
        dam = next(
            (item for item in dams if item.slug == preferred),
            dams[0],
        )
    as_of = request.GET.get("as_of") or None
    try:
        state, observed_state, is_scenario, overrides, delta = _state_for_request(
            dam, as_of, request
        )
    except ValidationError:
        return HttpResponseBadRequest("scenario override is out of bounds")
    except ValueError as exc:
        return HttpResponseBadRequest(str(exc))
    except MissingDataError as exc:
        return render(
            request,
            "dashboard/index.html",
            {
                "empty": True,
                "error": str(exc),
                "countries": countries,
                "country": country,
                "map_dams": _map_dams(),
            },
        )
    return render(
        request,
        "dashboard/index.html",
        {
            "empty": False,
            "countries": countries,
            "country": country,
            "dams": dams,
            "selected_dam": dam,
            "state": state,
            "observed_state": observed_state,
            "is_scenario": is_scenario,
            "overrides": overrides,
            "delta": delta,
            "map_dams": _map_dams(),
        },
    )


@ensure_csrf_cookie
def panel_partial(request, dam_slug: str):
    dam = Dam.objects.select_related("country", "basin").filter(slug=dam_slug).first()
    if dam is None:
        raise Http404("dam not found")
    try:
        state, observed_state, is_scenario, overrides, delta = _state_for_request(
            dam, request.GET.get("as_of") or None, request
        )
    except ValidationError:
        return HttpResponseBadRequest("scenario override is out of bounds")
    response = render(
        request,
        "dashboard/partials/_panel.html",
        {
            "state": state,
            "observed_state": observed_state,
            "is_scenario": is_scenario,
            "overrides": overrides,
            "delta": delta,
            "selected_dam": dam,
            "country": dam.country,
        },
    )
    query = ScenarioOverrides.model_validate(overrides).to_query()
    base = f"/pilot/?country={dam.country.iso3}&dam={dam.slug}"
    response["HX-Push-Url"] = base + (f"&{query}" if query else "")
    return response


def scenario_partial(request, dam_slug: str):
    dam = Dam.objects.select_related("country", "basin").filter(slug=dam_slug).first()
    if dam is None:
        raise Http404("dam not found")
    raw = {}
    for field in (
        "rain_multiplier",
        "demand_multiplier",
        "soil_saturation",
        "storm_arrival_day",
    ):
        value = request.POST.get(field)
        if value not in (None, ""):
            raw[field] = value
    try:
        overrides = ScenarioOverrides.model_validate(raw)
    except ValidationError:
        return render(
            request,
            "dashboard/partials/_error.html",
            {"message": "Scenario overrides are out of bounds; the observed state was not changed."},
            status=400,
        )

    observed_state, scenario_state, delta = compute_scenario_state(
        dam_slug, overrides
    )
    if not request.session.session_key:
        request.session.save()
    ScenarioRun.objects.create(
        dam=dam,
        as_of=dt.date.fromisoformat(scenario_state["as_of"]),
        overrides=overrides.model_dump(),
        result=scenario_state,
        session_key=request.session.session_key or "",
    )
    response = render(
        request,
        "dashboard/partials/_scenario_response.html",
        {
            "state": scenario_state,
            "observed_state": observed_state,
            "is_scenario": not overrides.is_default(),
            "overrides": overrides.model_dump(),
            "delta": delta,
            "selected_dam": dam,
            "country": dam.country,
        },
    )
    query = overrides.to_query()
    base = f"/pilot/?country={dam.country.iso3}&dam={dam.slug}"
    response["HX-Push-Url"] = base + (f"&{query}" if query else "")
    return response


def country_partial(request, iso3: str):
    country = Country.objects.filter(iso3=iso3.upper()).first()
    if country is None:
        raise Http404("country not found")
    return render(
        request,
        "dashboard/partials/_country.html",
        {
            "country": country,
            "dams": list(country.dams.order_by("name")),
            "countries": list(Country.objects.all()),
        },
    )
