"""JSON API for the explainable HRI dashboard."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from pydantic import ValidationError

from core.models import Basin, ClimateObservation, Country, Dam, DemandObservation, ReservoirObservation, ScenarioRun
from core.services.exceptions import MissingDataError
from core.services.providers.registry import get_provider
from core.services.scenario import ScenarioOverrides, ScenarioService
from core.services.serializers import dam_brief_payload, hri_payload, sanitize
from core.services.snapshots import compute_dam_state, latest_snapshot


def _error(code: str, message: str, details=None, status: int = 400) -> JsonResponse:
    return JsonResponse(
        {"error": {"code": code, "message": message, "details": sanitize(details)}},
        status=status,
    )


@require_GET
def health(request):
    return JsonResponse(
        {
            "status": "ok",
            "service": "aquastate",
            "data_mode": "seeded",
            "version": "0.1.0",
        }
    )


@require_GET
def countries(request):
    rows = [
        {
            "iso3": country.iso3,
            "name": country.name,
            "timezone": country.timezone,
            "baseline_start": country.baseline_start.isoformat(),
            "baseline_end": country.baseline_end.isoformat(),
            "dam_count": country.dams.count(),
        }
        for country in Country.objects.all()
    ]
    return JsonResponse({"countries": rows})


@require_GET
def country_dams(request, iso3: str):
    country = Country.objects.filter(iso3=iso3.upper()).first()
    if country is None:
        return _error("not_found", f"unknown country: {iso3}", status=404)
    dams = country.dams.select_related("basin", "country").all()
    return JsonResponse(
        {
            "country": {"iso3": country.iso3, "name": country.name},
            "dams": [dam_brief_payload(dam) for dam in dams],
        }
    )


@require_GET
def dam_detail(request, dam_slug: str):
    as_of = request.GET.get("as_of") or None
    try:
        payload = compute_dam_state(dam_slug, as_of)
    except MissingDataError as exc:
        return _error("not_found", str(exc), status=404)
    except ValueError as exc:
        return _error("invalid_as_of", str(exc), status=400)
    return JsonResponse(payload)


@require_POST
def dam_scenario(request, dam_slug: str):
    dam = Dam.objects.filter(slug=dam_slug).first()
    if dam is None:
        return _error("not_found", f"unknown dam: {dam_slug}", status=404)
    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError as exc:
        return _error("invalid_json", "request body is not valid JSON", str(exc))
    try:
        overrides = ScenarioOverrides.model_validate(body)
    except ValidationError as exc:
        return _error(
            "invalid_scenario",
            "scenario overrides are out of bounds",
            exc.errors(include_url=False),
            status=400,
        )
    provider = get_provider()
    as_of = body.get("as_of") or request.GET.get("as_of")
    try:
        ctx = provider.build_context(dam_slug, as_of)
    except MissingDataError as exc:
        return _error("not_found", str(exc), status=404)
    except ValueError as exc:
        return _error("invalid_as_of", str(exc), status=400)
    outcome = ScenarioService().apply(ctx, overrides)
    if not request.session.session_key:
        request.session.save()
    ScenarioRun.objects.create(
        dam=dam,
        as_of=ctx.as_of,
        overrides=outcome.overrides,
        result=hri_payload(outcome.scenario_result),
        session_key=request.session.session_key or "",
    )
    return JsonResponse(
        sanitize(
            {
                "dam": dam_brief_payload(dam),
                "as_of": ctx.as_of.isoformat() if ctx.as_of else None,
                "observed": hri_payload(outcome.observed_result),
                "scenario": hri_payload(outcome.scenario_result),
                "delta": outcome.delta,
                "overrides": outcome.overrides,
                "is_scenario": outcome.is_scenario,
                "disclaimer": (
                    "Scenario values are simulated; observed values are never "
                    "rewritten by this response."
                ),
            }
        )
    )


@require_GET
def dam_timeseries(request, dam_slug: str):
    dam = Dam.objects.filter(slug=dam_slug).first()
    if dam is None:
        return _error("not_found", f"unknown dam: {dam_slug}", status=404)
    metric = request.GET.get("metric", "fill_pct")
    try:
        days = max(1, min(3650, int(request.GET.get("days", "3650"))))
    except ValueError:
        return _error("invalid_days", "days must be an integer", status=400)
    since = dt.date.today() - dt.timedelta(days=days)
    if metric in {"fill_pct", "volume_m3"}:
        field = metric
        rows = ReservoirObservation.objects.filter(
            dam=dam, date__gte=since
        ).order_by("date")
        unit = "%" if metric == "fill_pct" else "m³"
    elif metric == "precip_mm":
        field = "precip_mm"
        rows = ClimateObservation.objects.filter(
            basin=dam.basin, date__gte=since
        ).order_by("date")
        unit = "mm/day"
    elif metric == "demand_m3_day":
        field = "demand_m3_day"
        rows = DemandObservation.objects.filter(
            dam=dam, date__gte=since
        ).order_by("date")
        unit = "m³/day"
    else:
        return _error(
            "invalid_metric",
            "metric must be fill_pct, volume_m3, precip_mm, or demand_m3_day",
            status=400,
        )
    points = []
    for row in rows:
        value = getattr(row, field)
        if value is None:
            continue
        points.append({"date": row.date.isoformat(), "value": sanitize(float(value))})
    return JsonResponse({"metric": metric, "unit": unit, "points": points})


@require_GET
def dam_map(request, dam_slug: str):
    # The path's slug selects the initially focused dam; the payload still
    # carries every pilot dam so the map can switch without a refetch.
    if not Dam.objects.filter(slug=dam_slug).exists():
        return _error("not_found", f"unknown dam: {dam_slug}", status=404)
    features = []
    for dam in Dam.objects.select_related("basin", "country").all():
        snapshot = latest_snapshot(dam)
        observation = dam.observations.order_by("-date").first()
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [dam.lon, dam.lat],
                },
                "properties": sanitize(
                    {
                        "slug": dam.slug,
                        "name": dam.name,
                        "country": dam.country.iso3,
                        "status": snapshot.status if snapshot else "NO_DATA",
                        "hri": snapshot.hri if snapshot else None,
                        "fill_pct": observation.fill_pct if observation else None,
                        "capacity_m3": dam.capacity_m3,
                    }
                ),
            }
        )
    basins = []
    basin_file = Path(settings.BASE_DIR) / "static" / "data" / "basins.geojson"
    try:
        basins = json.loads(basin_file.read_text(encoding="utf-8")).get("features", [])
    except (OSError, json.JSONDecodeError):
        for basin in Basin.objects.select_related("country").all():
            if basin.geometry:
                basins.append(
                    {
                        "type": "Feature",
                        "geometry": basin.geometry,
                        "properties": {
                            "name": basin.name,
                            "country": basin.country.iso3,
                            "area_km2": basin.area_km2,
                        },
                    }
                )
    countries = []
    country_file = Path(settings.BASE_DIR) / "static" / "data" / "countries.geojson"
    try:
        countries = json.loads(country_file.read_text(encoding="utf-8")).get(
            "features", []
        )
    except (OSError, json.JSONDecodeError):
        for country in Country.objects.all():
            if country.bbox and len(country.bbox) == 4:
                west, south, east, north = country.bbox
                countries.append(
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [
                                [
                                    [west, south], [east, south], [east, north],
                                    [west, north], [west, south],
                                ]
                            ],
                        },
                        "properties": {"iso3": country.iso3, "name": country.name},
                    }
                )
    return JsonResponse(
        sanitize(
            {
                "type": "FeatureCollection",
                "features": features,
                "basins": basins,
                "countries": countries,
                "focus": dam_slug,
            }
        )
    )
