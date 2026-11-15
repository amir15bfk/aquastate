from __future__ import annotations

import json
from datetime import timedelta

from django.conf import settings
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from hydro.ai import ensure_slots, reserved_slots_payload, run_ai_layer
from hydro.models import Country, IndexSnapshot
from hydro.services import data_service
from hydro.services.gazetteer import all_countries, country_row, ensure_country
from hydro.services.index_engine import compute_index, make_scenario


def _resolve_country(iso2: str) -> Country:
    row = country_row(iso2)
    if not row:
        raise Http404(f"Unknown country code: {iso2}")
    country = ensure_country(iso2)
    if not country:
        raise Http404(f"Unknown country code: {iso2}")
    return country


def _scenario_from_request(request):
    return make_scenario(
        request.GET.get("rain", "forecast"),
        request.GET.get("demand", 1.0),
        request.GET.get("horizon", settings.DEFAULT_HORIZON_DAYS),
    )


def _should_persist(country: Country, scenario) -> bool:
    if scenario.hypothetical or scenario.rain != "forecast":
        return False
    if scenario.demand != 1.0 or scenario.horizon != settings.DEFAULT_HORIZON_DAYS:
        return False
    latest = country.snapshots.first()
    return latest is None or timezone.now() - latest.created_at > timedelta(hours=1)


def _build_result(country: Country, scenario, *, persist: bool = False) -> dict:
    result = compute_index(country, scenario, persist=False)
    result["sources"] = data_service.source_ledger(country)
    result["inventory_note"] = data_service.storage.country_inventory_note(country)
    result = run_ai_layer(result)
    result["reservoir_count"] = len(result["reservoirs"])
    result["major_reservoir_count"] = len(
        [row for row in result["horizon"].get("reservoirs", []) if row.get("major")]
    )
    result["freshness"] = {
        "last_refresh": country.last_refresh.isoformat() if country.last_refresh else None,
        "mode": country.data_mode,
        "is_stale": data_service.is_stale(country),
        "cache_hours": settings.DATA_CACHE_HOURS,
    }
    if persist:
        from hydro.services.index_engine import store_snapshot

        store_snapshot(country, result)
    return result


@ensure_csrf_cookie
def dashboard(request, iso2: str = "DZ"):
    country = _resolve_country(iso2)
    try:
        data_service.ensure_profile(country, allow_network=settings.LIVE_DATA_ENABLED)
    except Exception:
        # The fallback path inside ensure_profile is normally enough; never
        # take the page down because a public API changed shape.
        pass
    scenario = _scenario_from_request(request)
    result = _build_result(country, scenario, persist=_should_persist(country, scenario))
    pillar_map = {row["key"]: row for row in result["pillars"]}
    context = {
        "result": result,
        "result_json": json.dumps(result, ensure_ascii=False),
        "country": country,
        "countries": all_countries(),
        "scenario": scenario,
        "is_stale": data_service.is_stale(country),
        "snapshot": country.snapshots.first(),
        "ai": reserved_slots_payload(),
        "pillar_map": pillar_map,
        "trend_pillar": pillar_map.get("trend", {}),
        "soil_pillar": pillar_map.get("soil", {}),
        "groundwater_pillar": pillar_map.get("groundwater", {}),
        "forecast_pillar": pillar_map.get("forecast", {}),
        "buffer_pillar": pillar_map.get("buffer", {}),
    }
    return render(request, "hydro/dashboard.html", context)


@require_GET
def api_country(request, iso2: str):
    country = _resolve_country(iso2)
    try:
        data_service.ensure_profile(country, allow_network=settings.LIVE_DATA_ENABLED)
    except Exception:
        pass
    scenario = _scenario_from_request(request)
    result = _build_result(country, scenario, persist=_should_persist(country, scenario))
    return JsonResponse(result)


@require_GET
def api_audit(request, iso2: str):
    country = _resolve_country(iso2)
    scenario = _scenario_from_request(request)
    result = _build_result(country, scenario, persist=False)
    latest = country.snapshots.first()
    return JsonResponse(
        {
            "product": "AquaState",
            "version": settings.INDEX_VERSION,
            "country": result["country"],
            "scenario": result["scenario"],
            "generated_at": result["meta"]["generated_at"],
            "formula": result["index"]["aggregation_formula"],
            "weights": result["index"]["weights"],
            "base_index": result["index"]["base_value"],
            "horizon_gate": result["index"]["horizon_gate"],
            "pillars": result["pillars"],
            "horizon": result["horizon"],
            "narrative": result["narrative"],
            "data_quality": result["data_quality"],
            "sources": result["sources"],
            "ai": reserved_slots_payload(),
            "ai_trace": result["ai_trace"],
            "latest_snapshot": {
                "id": latest.id,
                "created_at": latest.created_at.isoformat(),
                "base_index": latest.base_index,
                "final_index": latest.final_index,
                "status": latest.status,
                "verdict": latest.verdict,
            }
            if latest
            else None,
        }
    )


@require_GET
def api_countries(request):
    rows = all_countries()
    loaded = {row.iso2: row for row in Country.objects.all()}
    payload = []
    for row in rows:
        country = loaded.get(row["iso2"])
        payload.append(
            {
                "iso2": row["iso2"],
                "iso3": row.get("iso3"),
                "name": row["name"],
                "region": row.get("region"),
                "subregion": row.get("subregion"),
                "curated": row["iso2"] in {"DZ", "TN"},
                "loaded": bool(country),
                "data_mode": country.data_mode if country else "pending",
            }
        )
    return JsonResponse({"count": len(payload), "countries": payload})


@require_GET
def api_ai_slots(request):
    return JsonResponse(reserved_slots_payload())


@require_POST
def refresh_country(request, iso2: str):
    country = _resolve_country(iso2)
    report = data_service.refresh_country(country, allow_network=True, force=True)
    scenario = _scenario_from_request(request)
    result = _build_result(country, scenario, persist=True)
    return JsonResponse({"ok": True, "refresh": report, "result": result})


@require_POST
def import_osm(request, iso2: str):
    country = _resolve_country(iso2)
    report = data_service.import_osm_reservoirs(country)
    if not report.get("ok"):
        return JsonResponse({"ok": False, "message": report.get("message", "Import failed.")}, status=422)
    scenario = _scenario_from_request(request)
    result = _build_result(country, scenario, persist=True)
    return JsonResponse({"ok": True, "import": report, "result": result})


def index(request):
    return redirect("/")


@require_GET
def switch_country(request):
    iso2 = (request.GET.get("iso2") or "DZ").upper()
    if not country_row(iso2):
        raise Http404(f"Unknown country code: {iso2}")
    query = request.GET.copy()
    query.pop("iso2", None)
    suffix = f"?{query.urlencode()}" if query else ""
    return redirect(f"/water/{iso2}/{suffix}")


@ensure_csrf_cookie
def methodology(request):
    ensure_slots()
    country = Country.objects.filter(iso2="DZ").first()
    return render(
        request,
        "hydro/methodology.html",
        {
            "weights": settings.INDEX_WEIGHTS,
            "version": settings.INDEX_VERSION,
            "countries": all_countries(),
            "country": country,
        },
    )


@ensure_csrf_cookie
def sources_page(request):
    country = Country.objects.filter(iso2="DZ").first()
    sources = data_service.source_ledger(country) if country else []
    return render(
        request,
        "hydro/sources.html",
        {
            "sources": sources,
            "country": country,
            "countries": all_countries(),
        },
    )


@require_GET
def health(request):
    return JsonResponse(
        {
            "ok": True,
            "version": settings.INDEX_VERSION,
            "ai_agents_enabled": bool(settings.AI_AGENTS_ENABLED),
            "live_data_enabled": bool(settings.LIVE_DATA_ENABLED),
            "countries_in_gazetteer": len(all_countries()),
            "countries_loaded": Country.objects.count(),
            "snapshots": IndexSnapshot.objects.count(),
            "server_time": timezone.now().isoformat(),
        }
    )
