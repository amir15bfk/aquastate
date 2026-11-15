"""World observatory pages and JSON APIs."""
from __future__ import annotations

import json
import threading
from datetime import timedelta
from io import StringIO

from django.conf import settings
from django.core.management import call_command
from django.db.models import Avg, Case, Count, IntegerField, Q, Value, When
from django.http import Http404, HttpResponseNotModified, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from core.models import Dam
from core.services.snapshots import compute_dam_state
from hydro.models import Country
from hydro.services.index_engine import compute_index
from world.models import (
    CountryProfile,
    DamAtlas,
    HazardCountryScore,
    HazardEvent,
    SourceStatus,
    WorldSnapshot,
)
from world.services.refresh import refresh_lock

_REFRESH_LOCK = threading.Lock()


def _current_snapshot() -> WorldSnapshot | None:
    return WorldSnapshot.objects.filter(is_current=True).first()


def _snapshot_payload(version: str | None = None) -> dict:
    snapshot = None
    if version:
        snapshot = WorldSnapshot.objects.filter(version=version).first()
    snapshot = snapshot or _current_snapshot()
    if not snapshot:
        return {
            "version": None,
            "updated_at": None,
            "summary": {},
            "countries": [],
        }
    return {
        "version": snapshot.version,
        "updated_at": snapshot.as_of.isoformat(),
        "summary": snapshot.summary,
        "countries": snapshot.payload.get("countries", []),
    }


def _sources() -> list[dict]:
    return [
        {
            "key": source.key,
            "label": source.label,
            "kind": source.kind,
            "last_success": source.last_success.isoformat() if source.last_success else None,
            "last_error": source.last_error,
            "records": source.records,
            "ttl_seconds": source.ttl_seconds,
            "due": source.is_due,
        }
        for source in SourceStatus.objects.all()
    ]


def _event_counts() -> dict:
    return {row["category"]: row["count"] for row in HazardEvent.objects.values("category").annotate(count=Count("id"))}


def _events_geojson(limit: int = 500) -> dict:
    features = []
    for event in HazardEvent.objects.exclude(lat=None).exclude(lon=None)[:limit]:
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [event.lon, event.lat]},
                "properties": {
                    "id": event.id,
                    "eonet_id": event.eonet_id,
                    "category": event.category,
                    "title": event.title,
                    "date": event.event_date.isoformat() if event.event_date else None,
                    "country": event.country_iso2,
                    "url": event.source_url,
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def _profile_payload(profile: CountryProfile | None) -> dict | None:
    if not profile:
        return None
    return {
        "iso2": profile.iso2,
        "iso3": profile.iso3,
        "name": profile.country.name,
        "region": profile.region,
        "subregion": profile.subregion,
        "population": profile.population,
        "area_km2": profile.area_km2,
        "score": profile.score,
        "status": profile.status,
        "confidence": profile.confidence,
        "coverage": profile.coverage,
        "rank": profile.rank,
        "as_of": profile.as_of.isoformat() if profile.as_of else None,
        "data_mode": profile.data_mode,
        "climate": profile.climate,
        "hazards": profile.hazards,
        "index": profile.index,
    }


@ensure_csrf_cookie
def overview(request):
    snapshot = _current_snapshot()
    RANK_EXCLUDE = {"AQ", "BV", "HM", "SJ", "UM", "TF", "GS", "IO"}
    top = list(
        CountryProfile.objects.exclude(score=None)
        .exclude(iso2__in=RANK_EXCLUDE)
        .order_by("rank")[:10]
    )
    bottom = list(
        CountryProfile.objects.exclude(score=None)
        .exclude(iso2__in=RANK_EXCLUDE)
        .order_by("-rank")[:10]
    )
    events = list(HazardEvent.objects.order_by("-event_date")[:6])
    summary = snapshot.summary if snapshot else {}
    hazard_meta = [
        ("drought", "Drought", "الجفاف", "SPI-3, SPI-12 and soil moisture"),
        ("flood", "Flood", "الفيضان", "Forecast discharge vs its 60-day baseline"),
        ("fire", "Wildfire", "حرائق الغابات", "Fire weather coupled to drought"),
        ("desertification", "Desertification", "التصحر", "Aridity, rainfall and soil trends"),
    ]
    hazard_cards = []
    event_category = {"fire": "wildfires", "flood": "floods"}
    for key, label, arabic, blurb in hazard_meta:
        qs = HazardCountryScore.objects.filter(category=key).exclude(pressure=None)
        avg = qs.aggregate(avg=Avg("pressure"))["avg"]
        hazard_cards.append(
            {
                "key": key,
                "label": label,
                "arabic": arabic,
                "blurb": blurb,
                "average": round(avg, 1) if avg is not None else None,
                "top": list(qs.order_by("-pressure")[:5]),
                "events": HazardEvent.objects.filter(category=event_category.get(key, key)).count(),
            }
        )
    return render(
        request,
        "world/overview.html",
        {
            "snapshot": snapshot,
            "world_payload": _snapshot_payload(),
            "summary": summary,
            "top": top,
            "bottom": bottom,
            "events": events,
            "event_counts": _event_counts(),
            "hazard_cards": hazard_cards,
            "sources": _sources(),
            "atlas_total": DamAtlas.objects.count(),
            "atlas_monitored": DamAtlas.objects.filter(is_monitored=True).count(),
            "last_updated": snapshot.created_at if snapshot else None,
            "snapshots": list(WorldSnapshot.objects.values("version", "created_at")[:30]),
            "attention": sum((summary.get("bands") or {}).get(k, 0) or 0 for k in ("watch", "stressed", "critical")),
            "region_snapshot": _region_snapshot("DZ"),
        },
    )


@ensure_csrf_cookie
def country(request, iso2: str):
    iso2 = iso2.upper()
    country_obj = Country.objects.filter(iso2=iso2).first()
    if country_obj is None:
        raise Http404("Unknown country")
    profile = CountryProfile.objects.filter(country=country_obj).first()
    if profile is None:
        raise Http404("No world profile for this country yet")

    wri = None
    if country_obj.reservoirs.exists():
        try:
            wri = compute_index(country_obj)
            wri["reservoir_count"] = len(wri.get("reservoirs", []))
            wri["major_reservoir_count"] = len(
                [row for row in wri.get("horizon", {}).get("reservoirs", []) if row.get("major")]
            )
        except Exception:
            wri = None

    dams = list(
        DamAtlas.objects.filter(country_iso2=iso2)
        .order_by("-is_monitored", "-capacity_m3", "name")[:80]
    )
    dam_count = DamAtlas.objects.filter(country_iso2=iso2).count()
    monitored_count = DamAtlas.objects.filter(country_iso2=iso2, is_monitored=True).count()
    events = list(HazardEvent.objects.filter(country_iso2=iso2).order_by("-event_date")[:10])
    hazard_meta = {
        "drought": ("Drought", "الجفاف", "Rain, soil and dry-spell deficit"),
        "flood": ("Flood", "الفيضان", "Forecast discharge vs its 60-day baseline"),
        "fire": ("Wildfire", "حرائق الغابات", "Fire weather coupled to drought"),
        "desertification": ("Desertification", "التصحر", "Aridity, rainfall and land-cover trend"),
    }
    hazard_cards = []
    for key, (label, arabic, blurb) in hazard_meta.items():
        hazard = (profile.hazards or {}).get(key, {})
        hazard_cards.append(
            {
                "key": key,
                "label": label,
                "arabic": arabic,
                "blurb": blurb,
                "pressure": hazard.get("pressure"),
                "value": hazard.get("value"),
                "confidence": hazard.get("confidence"),
                "source": hazard.get("source"),
                "inputs": hazard.get("inputs") or {},
            }
        )
    pillars = []
    for key, pillar in (profile.index.get("pillars") or {}).items():
        pillars.append(pillar)
    dams_payload = [
        {
            "wikidata_id": dam.wikidata_id,
            "name": dam.name,
            "lat": dam.lat,
            "lon": dam.lon,
            "capacity_m3": dam.capacity_m3,
            "installed_mw": dam.installed_mw,
            "height_m": dam.height_m,
            "year_built": dam.year_built,
            "is_monitored": dam.is_monitored,
            "pilot_slug": dam.pilot_slug,
        }
        for dam in dams
    ]
    events_payload = [
        {
            "title": event.title,
            "category": event.category,
            "lat": event.lat,
            "lon": event.lon,
            "date": event.event_date.isoformat() if event.event_date else None,
            "url": event.source_url,
        }
        for event in events
    ]
    return render(
        request,
        "world/country.html",
        {
            "country": country_obj,
            "profile": profile,
            "profile_data": _profile_payload(profile),
            "wri": wri,
            "wri_data": wri,
            "dams": dams,
            "dams_payload": dams_payload,
            "dam_count": dam_count,
            "monitored_count": monitored_count,
            "events": events,
            "events_payload": events_payload,
            "pillars": pillars,
            "hazard_cards": hazard_cards,
        },
    )


@ensure_csrf_cookie
def dams(request):
    query = (request.GET.get("q") or "").strip()
    country_code = (request.GET.get("country") or "").upper()
    monitored = request.GET.get("monitored") == "1"
    try:
        page = max(1, int(request.GET.get("page") or 1))
    except ValueError:
        page = 1
    page_size = 60
    qs = DamAtlas.objects.all()
    if query:
        qs = qs.filter(Q(name__icontains=query) | Q(country_name__icontains=query))
    if country_code:
        qs = qs.filter(country_iso2=country_code)
    if monitored:
        qs = qs.filter(is_monitored=True)
    qs = qs.annotate(
        blank_country=Case(When(country_iso2="", then=Value(1)), default=Value(0), output_field=IntegerField())
    )
    total = qs.count()
    start = (page - 1) * page_size
    rows = list(qs.order_by("-is_monitored", "blank_country", "country_name", "name")[start : start + page_size])
    country_options = (
        DamAtlas.objects.exclude(country_iso2="")
        .values("country_iso2", "country_name")
        .annotate(count=Count("id"))
        .order_by("-count")[:40]
    )
    return render(
        request,
        "world/dams.html",
        {
            "rows": rows,
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": max(1, (total + page_size - 1) // page_size),
            "query": query,
            "country_code": country_code,
            "monitored": monitored,
            "country_options": country_options,
            "atlas_total": DamAtlas.objects.count(),
            "atlas_monitored": DamAtlas.objects.filter(is_monitored=True).count(),
            "atlas_countries": DamAtlas.objects.exclude(country_iso2="").values("country_iso2").distinct().count(),
        },
    )


@ensure_csrf_cookie
def dam(request, slug: str):
    pilot = Dam.objects.select_related("country", "basin").filter(slug=slug).first()
    atlas = None
    state = None
    if pilot:
        atlas = DamAtlas.objects.filter(pilot_slug=slug).first()
        try:
            state = compute_dam_state(slug)
        except Exception:
            state = None
    else:
        atlas = DamAtlas.objects.filter(wikidata_id=slug).first()
        if atlas is None:
            atlas = DamAtlas.objects.filter(pilot_slug=slug).first()
        if atlas and atlas.pilot_slug:
            pilot = Dam.objects.filter(slug=atlas.pilot_slug).first()
            if pilot:
                try:
                    state = compute_dam_state(pilot.slug)
                except Exception:
                    state = None
    if pilot is None and atlas is None:
        raise Http404("Unknown dam")
    profile = None
    if atlas:
        profile = CountryProfile.objects.filter(iso2=atlas.country_iso2).first()
    return render(
        request,
        "world/dam.html",
        {
            "pilot": pilot,
            "atlas": atlas,
            "state": state,
            "state_data": state,
            "profile": profile,
            "slug": slug,
            "atlas_monitored": DamAtlas.objects.filter(is_monitored=True).count(),
        },
    )


@ensure_csrf_cookie
def hazards(request):
    categories = ["drought", "flood", "fire", "desertification"]
    cards = []
    for category in categories:
        rows = list(
            HazardCountryScore.objects.filter(category=category)
            .exclude(pressure=None)
            .order_by("-pressure")[:10]
        )
        aggregate = HazardCountryScore.objects.filter(category=category).exclude(pressure=None).count()
        avg = (
            HazardCountryScore.objects.filter(category=category)
            .exclude(pressure=None)
            .aggregate(avg=Avg("pressure"))["avg"]
        )
        cards.append(
            {
                "key": category,
                "rows": rows,
                "count": aggregate,
                "average": round(avg, 1) if avg is not None else None,
                "events": HazardEvent.objects.filter(
                    category={"fire": "wildfires", "flood": "floods"}.get(category, category)
                ).count(),
            }
        )
    return render(
        request,
        "world/hazards.html",
        {
            "cards": cards,
            "event_counts": _event_counts(),
            "events": HazardEvent.objects.order_by("-event_date")[:12],
            "sources": _sources(),
        },
    )


@ensure_csrf_cookie
def methodology(request):
    return render(request, "world/methodology.html", {})


@ensure_csrf_cookie
def sources_page(request):
    snapshot = _current_snapshot()
    return render(
        request,
        "world/sources.html",
        {
            "sources": _sources(),
            "snapshot": snapshot,
            "summary": snapshot.summary if snapshot else {},
            "atlas_total": DamAtlas.objects.count(),
            "atlas_monitored": DamAtlas.objects.filter(is_monitored=True).count(),
            "events": HazardEvent.objects.count(),
            "countries": CountryProfile.objects.count(),
            "source_last_error": next((s["last_error"] for s in _sources() if s["last_error"]), ""),
        },
    )


@require_GET
def api_world(request):
    payload = _snapshot_payload(request.GET.get("version"))
    response = JsonResponse(payload)
    response["Cache-Control"] = "public, max-age=60, stale-while-revalidate=120"
    if payload["version"]:
        response["ETag"] = f'"{payload["version"]}"'
        if request.headers.get("If-None-Match") == response["ETag"]:
            return HttpResponseNotModified()
    return response


@require_GET
def api_meta(request):
    snapshot = _current_snapshot()
    next_refresh = None
    if snapshot:
        next_refresh = (snapshot.as_of + timedelta(minutes=settings.WCRI_REFRESH_MINUTES)).isoformat()
    return JsonResponse(
        {
            "version": snapshot.version if snapshot else None,
            "updated_at": snapshot.as_of.isoformat() if snapshot else None,
            "next_refresh": next_refresh,
            "summary": snapshot.summary if snapshot else {},
            "sources": _sources(),
            "refresh_running": _REFRESH_LOCK.locked(),
        }
    )


def _run_refresh(trigger: str) -> None:
    try:
        with refresh_lock() as acquired:
            if not acquired:
                return
            out = StringIO()
            call_command("bootstrap_world", "--json", stdout=out)
    finally:
        _REFRESH_LOCK.release()


@require_POST
def api_refresh(request):
    if not settings.LIVE_DATA_ENABLED:
        return JsonResponse({"ok": False, "message": "Live data is disabled."}, status=503)
    if not _REFRESH_LOCK.acquire(blocking=False):
        return JsonResponse({"ok": False, "status": "busy", "message": "A refresh is already running."}, status=409)
    thread = threading.Thread(target=_run_refresh, args=("manual",), daemon=True)
    thread.start()
    return JsonResponse({"ok": True, "status": "started", "message": "Refresh started. Poll /api/world/meta/."}, status=202)


@require_GET
def api_country(request, iso2: str):
    iso2 = iso2.upper()
    profile = CountryProfile.objects.filter(iso2=iso2).first()
    if profile is None:
        return JsonResponse({"error": {"code": "not_found", "message": "No world profile"}}, status=404)
    country_obj = Country.objects.filter(iso2=iso2).first()
    wri = None
    if country_obj and country_obj.reservoirs.exists():
        try:
            wri = compute_index(country_obj)
        except Exception:
            wri = None
    return JsonResponse(
        {
            "profile": _profile_payload(profile),
            "wri": wri,
            "dams": list(DamAtlas.objects.filter(country_iso2=iso2).values(
                "wikidata_id", "name", "lat", "lon", "capacity_m3", "is_monitored", "pilot_slug"
            )[:500]),
            "events": list(HazardEvent.objects.filter(country_iso2=iso2).values(
                "eonet_id", "category", "title", "lat", "lon", "event_date"
            )[:200]),
        }
    )


@require_GET
def api_dams(request):
    query = (request.GET.get("q") or "").strip()
    country_code = (request.GET.get("country") or "").upper()
    monitored = request.GET.get("monitored") == "1"
    bbox = request.GET.get("bbox")
    try:
        page = max(1, int(request.GET.get("page") or 1))
    except ValueError:
        page = 1
    page_size = min(500, max(1, int(request.GET.get("page_size") or 100)))
    qs = DamAtlas.objects.all()
    if query:
        qs = qs.filter(Q(name__icontains=query) | Q(country_name__icontains=query))
    if country_code:
        qs = qs.filter(country_iso2=country_code)
    if monitored:
        qs = qs.filter(is_monitored=True)
    if bbox:
        try:
            west, south, east, north = [float(part) for part in bbox.split(",")]
            qs = qs.filter(lon__gte=west, lon__lte=east, lat__gte=south, lat__lte=north)
        except ValueError:
            pass
    total = qs.count()
    fields = (
        "wikidata_id", "name", "country_iso2", "country_name", "lat", "lon",
        "capacity_m3", "installed_mw", "height_m", "year_built", "is_monitored", "pilot_slug",
    )
    if bbox:
        # A viewport marker layer needs global coverage, not the first 500 rows
        # by capacity. Sample evenly through the filtered result set so all 82k
        # dams can contribute markers as the map moves.
        if total > page_size:
            ids = list(qs.values_list("id", flat=True))
            step = max(1, len(ids) // page_size)
            sampled = ids[::step][:page_size]
            monitored_ids = list(qs.filter(is_monitored=True).values_list("id", flat=True))
            chosen = monitored_ids + [pk for pk in sampled if pk not in monitored_ids]
            chosen = chosen[:page_size]
            rows = list(qs.filter(id__in=chosen).order_by("id").values(*fields))
        else:
            rows = list(qs.order_by("name").values(*fields))
    else:
        start = (page - 1) * page_size
        rows = list(qs.order_by("-is_monitored", "-capacity_m3", "name")[start : start + page_size].values(*fields))
    return JsonResponse({"count": total, "page": page, "page_size": page_size, "results": rows})


@require_GET
def api_events(request):
    return JsonResponse(_events_geojson())


# ---------------------------------------------------------------------------
# Map Viewer: first-level regions for any country (ADM1)
# ---------------------------------------------------------------------------
REGION_STALE_HOURS = 24


def _region_snapshot(iso2: str = "DZ", version: str | None = None):
    from world.models import RegionSnapshot

    qs = RegionSnapshot.objects.filter(region=(iso2 or "DZ").upper())
    if version:
        return qs.filter(version=version).first()
    return qs.filter(is_current=True).first() or qs.first()


def _region_rows(payload: dict) -> list[dict]:
    # Snapshots written before the worldwide pipeline stored the list under "wilayas".
    return payload.get("regions") or payload.get("wilayas") or []


@require_GET
def api_region_catalog(request):
    from world.models import RegionSnapshot
    from world.services.regions import catalog, term

    built = set(RegionSnapshot.objects.values_list("region", flat=True).distinct())
    rows = []
    for iso2, meta in sorted(catalog().items()):
        rows.append({
            "iso2": iso2, "iso3": meta["iso3"], "units": meta["units"], "release": meta["release"],
            "license": meta["license"], "year": meta["year"], "term": term(iso2)[1], "ready": iso2 in built,
        })
    response = JsonResponse({"count": len(rows), "countries": rows})
    response["Cache-Control"] = "public, max-age=300"
    return response


@require_GET
def api_region_geo(request, iso2: str):
    import requests as _requests

    from world.services.regions import NoBoundaries, boundaries

    try:
        geo = boundaries(iso2)
    except NoBoundaries:
        return JsonResponse({"status": "unavailable", "message": "No first-level boundaries are published for this country."}, status=404)
    except _requests.RequestException as exc:
        return JsonResponse({"status": "error", "message": f"Boundary download failed: {exc}"}, status=502)
    response = JsonResponse(geo)
    response["Cache-Control"] = "public, max-age=86400"
    return response


@require_GET
def api_regions(request, iso2: str):
    """Region layers for a country. Builds them in the background on first use (202 + progress)."""
    from world.models import RegionSnapshot
    from world.services import region_jobs
    from world.services.regions import catalog, term

    iso2 = iso2.upper()
    meta = catalog().get(iso2)
    if not meta:
        return JsonResponse({"status": "unavailable", "iso2": iso2,
                             "message": "geoBoundaries publishes no first-level regions for this country, so there is nothing to map below the national level."}, status=404)
    snapshot = _region_snapshot(iso2, request.GET.get("snapshot"))
    job = region_jobs.status(iso2)
    running = bool(job and job["state"] == "running")
    if request.GET.get("retry") == "1" and not running:
        job = region_jobs.start(iso2)
        running = True
    if snapshot:
        age_h = (timezone.now() - snapshot.created_at).total_seconds() / 3600
        if age_h > REGION_STALE_HOURS and not running and not request.GET.get("snapshot"):
            job = region_jobs.start(iso2)  # stale-while-revalidate
            running = True
        payload = dict(snapshot.payload)
        payload["regions"] = _region_rows(payload)
        payload.pop("wilayas", None)
        singular, plural = term(iso2)
        payload.setdefault("term", singular)
        payload.setdefault("term_plural", plural)
        payload.setdefault("country_name", iso2)
        payload.update({
            "status": "ready", "refreshing": running, "job": job,
            "version": snapshot.version, "created_at": snapshot.created_at.isoformat(),
            "snapshots": [{"version": v, "created_at": c.isoformat()} for v, c in
                          RegionSnapshot.objects.filter(region=iso2).values_list("version", "created_at")[:20]],
        })
        return JsonResponse(payload)
    if job and job["state"] == "error":
        return JsonResponse({"status": "error", "iso2": iso2, "message": job["error"], "job": job})
    if not running:
        job = region_jobs.start(iso2)
    return JsonResponse({"status": "building", "iso2": iso2, "units": meta["units"], "job": job}, status=202)


@require_GET
def api_wilayas(request):
    """Backwards-compatible Algeria endpoint used by the dashboard preview and search."""
    snapshot = _region_snapshot("DZ", request.GET.get("snapshot"))
    if not snapshot:
        return JsonResponse({"wilayas": [], "message": "No wilaya snapshot yet. Run `python manage.py refresh_regions --country DZ`."})
    payload = dict(snapshot.payload)
    payload["wilayas"] = _region_rows(payload)
    payload.pop("regions", None)
    payload.update({"version": snapshot.version, "created_at": snapshot.created_at.isoformat()})
    response = JsonResponse(payload)
    response["Cache-Control"] = "public, max-age=120"
    return response


@ensure_csrf_cookie
def map_viewer(request, iso2: str | None = None):
    code = (iso2 or request.GET.get("c") or "").upper()
    selected = (request.GET.get("w") or "").upper()
    if not code and len(selected) > 3 and selected[2] == "-":
        code = selected[:2]  # legacy links such as /map/?w=DZ-16
    return render(
        request,
        "world/map_viewer.html",
        {"initial_country": code, "initial_region": selected, "initial_layer": request.GET.get("layer") or "drought"},
    )
