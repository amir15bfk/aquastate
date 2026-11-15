"""Background builds of a country's region layers, with progress, for the Map Viewer.

The first visit to a country downloads its ADM1 boundaries and samples the live sources at every region
(tens of NASA POWER calls), which takes from a few seconds to about a minute. That runs in a thread so the
page can show progress; results are stored as a RegionSnapshot and served from the database afterwards.

Job state lives in this process (fine for the dev server and a single worker). With several workers each
keeps its own job table; the snapshot itself is shared through the database.
"""
from __future__ import annotations

import threading
import time

from django.db import close_old_connections, transaction
from django.utils import timezone

_JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()
_SLOTS = threading.BoundedSemaphore(2)  # at most two countries build at once (polite to the public APIs)
STAGE_LABEL = {
    "queued": "Waiting for a free slot",
    "boundaries": "Downloading regional boundaries",
    "forecast": "Fetching Open-Meteo forecast",
    "flood": "Fetching GloFAS river discharge",
    "climate": "Fetching NASA POWER climate records",
    "events": "Matching NASA EONET events",
    "dams": "Placing catalogued dams",
    "compute": "Computing the layers",
    "saving": "Saving",
}


def status(iso2: str) -> dict | None:
    job = _JOBS.get(iso2.upper())
    if not job:
        return None
    out = dict(job)
    out["label"] = STAGE_LABEL.get(job.get("stage", ""), job.get("stage", ""))
    return out


def save_snapshot(iso2: str, payload: dict, keep: int = 20):
    from world.models import RegionSnapshot

    version = f"{iso2.lower()}-{timezone.now():%Y%m%d%H%M%S}"
    with transaction.atomic():
        RegionSnapshot.objects.filter(region=iso2, is_current=True).update(is_current=False)
        RegionSnapshot.objects.create(region=iso2, version=version, payload=payload, is_current=True)
        stale = RegionSnapshot.objects.filter(region=iso2).order_by("-created_at")[keep:]
        RegionSnapshot.objects.filter(id__in=[s.id for s in stale]).delete()
    return version


def start(iso2: str, *, force: bool = False) -> dict:
    """Start a build unless one is already running. Returns the job status."""
    iso2 = iso2.upper()
    with _LOCK:
        job = _JOBS.get(iso2)
        if job and job["state"] == "running":
            return status(iso2)
        _JOBS[iso2] = {"iso2": iso2, "state": "running", "stage": "queued", "done": 0, "total": 0,
                       "error": None, "started": time.time()}
    threading.Thread(target=_run, args=(iso2, force), daemon=True, name=f"regions-{iso2}").start()
    return status(iso2)


def _run(iso2: str, force: bool):
    from world.services.regions import build_payload

    job = _JOBS[iso2]

    def progress(stage, done=0, total=0):
        job.update(stage=stage, done=done, total=total)

    close_old_connections()
    try:
        with _SLOTS:
            payload = build_payload(iso2, force=force, progress=progress)
            payload["elapsed_seconds"] = round(time.time() - job["started"], 1)
            progress("saving")
            save_snapshot(iso2, payload)
        job.update(state="done", stage="done")
    except Exception as exc:  # surfaced to the UI as a readable error
        job.update(state="error", error=f"{type(exc).__name__}: {exc}")
    finally:
        close_old_connections()
