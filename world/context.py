"""Template context shared by every app's base template (site bar + footer)."""
from __future__ import annotations


def _active(path: str) -> str:
    if path == "/":
        return "overview"
    for prefix, key in (
        ("/map/", "map"),
        ("/country/", "country"),
        ("/dams/", "dams"),
        ("/dam/", "dams"),
        ("/hazards/", "hazards"),
        ("/water/", "water"),
        ("/pilot/", "pilot"),
        ("/methodology/", "methodology"),
        ("/sources/", "sources"),
    ):
        if path.startswith(prefix):
            return key
    return ""


def site_nav(request):
    from world.models import WorldSnapshot  # imported lazily: context processors load early

    snap = WorldSnapshot.objects.filter(is_current=True).only("created_at", "summary").first()
    return {
        "nav_active": _active(request.path),
        "site_snapshot_at": snap.created_at if snap else None,
        "site_scored": (snap.summary or {}).get("scored") if snap else None,
    }
