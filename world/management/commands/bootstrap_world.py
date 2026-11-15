"""Build the world layer: live sources -> WCRI -> snapshots -> map payload."""
from __future__ import annotations

import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone as dt_timezone

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from hydro.models import Country
from hydro.services.gazetteer import all_countries, ensure_country
from world.models import (
    CountryIndexSnapshot,
    CountryProfile,
    DamAtlas,
    HazardCountryScore,
    HazardEvent,
    RefreshRun,
    SourceStatus,
    WorldSnapshot,
)
from world.services import sources
from world.services.country_index import compute_country, status_for
from world.services.geo import country_for_point


def _parse_dt(value: str | None):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, dt_timezone.utc)
        return parsed
    except ValueError:
        return None


def _distance_deg(lat1, lon1, lat2, lon2):
    dlat = lat1 - lat2
    dlon = (lon1 - lon2) * math.cos(math.radians((lat1 + lat2) / 2.0))
    return math.sqrt(dlat * dlat + dlon * dlon)


def _nearest_country(event, points):
    contained = country_for_point(event["lat"], event["lon"])
    if contained:
        return contained
    best = None
    best_dist = 999.0
    for point in points:
        dist = _distance_deg(event["lat"], event["lon"], point["lat"], point["lon"])
        if dist < best_dist:
            best_dist = dist
            best = point
    return best["iso2"] if best and best_dist <= 8.0 else ""


class Command(BaseCommand):
    help = "Fetch live world data and compute WCRI-2.0 for all countries."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=0, help="Limit countries for a smoke run.")
        parser.add_argument("--offline", action="store_true", help="Do not fetch; use cached data only.")
        parser.add_argument("--force", action="store_true", help="Bypass source caches.")
        parser.add_argument("--workers", type=int, default=6)
        parser.add_argument("--skip-bank", action="store_true")
        parser.add_argument("--skip-eonet", action="store_true")
        parser.add_argument("--skip-nasa", action="store_true")
        parser.add_argument("--json", action="store_true", help="Print the summary as JSON.")

    def handle(self, *args, **options):
        started = time.time()
        run = RefreshRun.objects.create(trigger="bootstrap")
        summary = {"countries": 0, "scored": 0, "events": 0, "errors": []}
        rows = [
            row
            for row in all_countries()
            if row.get("lat") is not None
            and row.get("lon") is not None
            and abs(float(row["lat"])) < 85.0
            and not (float(row["lat"]) == 0.0 and float(row["lon"]) == 0.0)
        ]
        if options["limit"]:
            rows = rows[: options["limit"]]
        self.stdout.write(f"Preparing {len(rows)} countries...")
        for row in rows:
            ensure_country(row["iso2"])
        points = [
            {
                "iso2": row["iso2"],
                "iso3": row.get("iso3", ""),
                "name": row["name"],
                "lat": float(row.get("lat") or 0.0),
                "lon": float(row.get("lon") or 0.0),
                "display_lat": float(row.get("lat") or 0.0),
                "display_lon": float(row.get("lon") or 0.0),
                "bbox": row.get("bbox") or [],
            }
            for row in rows
        ]
        # For countries with a monitored dam inventory, sample the climate at
        # the capacity-weighted dam centroid rather than the flag centroid.
        dam_points: dict[str, list[tuple[float, float, float]]] = {}
        for dam in DamAtlas.objects.filter(is_monitored=True).exclude(country_iso2=""):
            dam_points.setdefault(dam.country_iso2, []).append(
                (dam.lat, dam.lon, max(1.0, dam.capacity_m3 or 1.0))
            )
        for point in points:
            dams = dam_points.get(point["iso2"])
            if not dams:
                continue
            total = sum(weight for _, _, weight in dams)
            if total <= 0:
                continue
            point["lat"] = round(sum(lat * weight for lat, _, weight in dams) / total, 4)
            point["lon"] = round(sum(lon * weight for _, lon, weight in dams) / total, 4)

        # --- World Bank ---------------------------------------------------
        if options["skip_bank"]:
            bank = {}
        else:
            try:
                bank = sources.fetch_world_bank(force=options["force"])
                summary["bank"] = len(bank)
                self._source("world_bank", "live", len(bank), int((time.time() - started) * 1000))
            except Exception as exc:
                bank = {}
                summary["errors"].append(f"World Bank: {exc}")
                self._source("world_bank", "error", 0, 0, str(exc))

        # --- Open-Meteo forecast / flood ---------------------------------
        try:
            forecast = sources.fetch_forecast(points, force=options["force"])
            self._source("open_meteo_forecast", "live", sum(len(v) for v in forecast.values()), 0)
        except Exception as exc:
            forecast = {}
            summary["errors"].append(f"Open-Meteo forecast: {exc}")
            self._source("open_meteo_forecast", "error", 0, 0, str(exc))
        try:
            flood = sources.fetch_flood(points, force=options["force"])
            self._source("open_meteo_flood", "live", sum(len(v) for v in flood.values()), 0)
        except Exception as exc:
            flood = {}
            summary["errors"].append(f"Open-Meteo flood: {exc}")
            self._source("open_meteo_flood", "error", 0, 0, str(exc))

        # --- NASA POWER monthly ------------------------------------------
        monthly: dict[str, list[dict]] = {}
        if not options["skip_nasa"]:
            def fetch_one(point):
                try:
                    return point["iso2"], sources.fetch_nasa_monthly(
                        point["lat"], point["lon"], force=options["force"]
                    ), None
                except Exception as exc:
                    return point["iso2"], [], str(exc)

            with ThreadPoolExecutor(max_workers=max(1, options["workers"])) as pool:
                futures = {pool.submit(fetch_one, p): p for p in points}
                for index, future in enumerate(as_completed(futures), start=1):
                    iso2, data, error = future.result()
                    if data:
                        monthly[iso2] = data
                    elif error:
                        summary["errors"].append(f"NASA {iso2}: {error}")
                    if index % 25 == 0:
                        self.stdout.write(f"  NASA POWER {index}/{len(points)}")
            self._source("nasa_power", "live", sum(len(v) for v in monthly.values()), 0)

        # --- EONET events -------------------------------------------------
        events = []
        if not options["skip_eonet"]:
            try:
                events = sources.fetch_eonet(force=options["force"])
                summary["events"] = len(events)
                self._source("eonet", "live", len(events), 0)
            except Exception as exc:
                summary["errors"].append(f"EONET: {exc}")
                self._source("eonet", "error", 0, 0, str(exc))
        event_counts: dict[str, int] = {}
        for event in events:
            iso2 = _nearest_country(event, points)
            event["country_iso2"] = iso2
            if iso2:
                key = f"{iso2}:{event['category']}"
                event_counts[key] = event_counts.get(key, 0) + 1
        for event in events:
            HazardEvent.objects.update_or_create(
                eonet_id=event["eonet_id"],
                defaults={
                    "category": event["category"],
                    "title": event["title"],
                    "lat": event["lat"],
                    "lon": event["lon"],
                    "event_date": _parse_dt(event.get("event_date")),
                    "source": event["source"],
                    "source_url": event.get("source_url") or "",
                    "country_iso2": event.get("country_iso2") or "",
                    "magnitude": event.get("magnitude"),
                    "metadata": event.get("metadata") or {},
                },
            )

        # --- Compute WCRI -------------------------------------------------
        computed = []
        for point in points:
            result = compute_country(
                iso2=point["iso2"],
                iso3=point["iso3"],
                country_name=point["name"],
                lat=point["lat"],
                monthly=monthly.get(point["iso2"], []),
                forecast_rows=forecast.get(point["iso2"], []),
                flood_rows=flood.get(point["iso2"], []),
                bank=bank,
                event_counts=event_counts,
            )
            result["lon"] = point["lon"]
            computed.append(result)
        scored = [row for row in computed if row["score"] is not None]
        scored.sort(key=lambda row: (-row["score"], row["name"]))
        for index, row in enumerate(scored, start=1):
            row["rank"] = index
        for row in computed:
            row.setdefault("rank", None)
        if not options["limit"]:
            computed_iso = [row["iso2"] for row in computed]
            CountryProfile.objects.exclude(iso2__in=computed_iso).delete()
            HazardCountryScore.objects.exclude(iso2__in=computed_iso).delete()

        today = date.today()
        with transaction.atomic():
            for row in computed:
                country = Country.objects.get(iso2=row["iso2"])
                profile, _ = CountryProfile.objects.update_or_create(
                    country=country,
                    defaults={
                        "iso2": row["iso2"],
                        "iso3": row["iso3"],
                        "region": next((r.get("region", "") for r in rows if r["iso2"] == row["iso2"]), ""),
                        "subregion": next((r.get("subregion", "") for r in rows if r["iso2"] == row["iso2"]), ""),
                        "population": int(row["bank"].get("population") or 0),
                        "area_km2": next((r.get("area_km2") or 0 for r in rows if r["iso2"] == row["iso2"]), 0),
                        "climate": row["climate"],
                        "hazards": row["hazards"],
                        "index": {
                            "score": row["score"],
                            "status": row["status"],
                            "status_label": row["status_label"],
                            "confidence": row["confidence"],
                            "coverage": row["coverage"],
                            "pillars": row["pillars"],
                            "aggregation": row["aggregation"],
                            "version": row["version"],
                        },
                        "score": row["score"],
                        "status": row["status"],
                        "confidence": row["confidence"],
                        "coverage": row["coverage"],
                        "rank": row.get("rank"),
                        "as_of": today,
                        "data_mode": "live" if row["coverage"] >= 0.4 else "partial",
                    },
                )
                CountryIndexSnapshot.objects.update_or_create(
                    country=country,
                    as_of=today,
                    defaults={
                        "iso2": row["iso2"],
                        "score": row["score"],
                        "status": row["status"],
                        "confidence": row["confidence"],
                        "coverage": row["coverage"],
                        "rank": row.get("rank"),
                        "pillars": row["pillars"],
                        "hazards": row["hazards"],
                        "index": row["index"] if "index" in row else {},
                        "version": settings.WCRI_VERSION,
                    },
                )
                for category, hazard in row["hazards"].items():
                    if hazard.get("pressure") is None:
                        continue
                    HazardCountryScore.objects.update_or_create(
                        iso2=row["iso2"],
                        category=category,
                        defaults={
                            "pressure": hazard.get("pressure") or 0,
                            "value": hazard.get("value"),
                            "unit": hazard.get("unit", ""),
                            "confidence": hazard.get("confidence") or 0,
                            "source": hazard.get("source", ""),
                            "as_of": today,
                            "metadata": hazard.get("inputs") or {},
                        },
                    )

        # --- World snapshot ----------------------------------------------
        payload_rows = [
            {
                "iso2": row["iso2"],
                "iso3": row["iso3"],
                "name": row["name"],
                "lat": next((p["display_lat"] for p in points if p["iso2"] == row["iso2"]), row["lat"]),
                "lon": next((p["display_lon"] for p in points if p["iso2"] == row["iso2"]), row["lon"]),
                "score": row["score"],
                "status": row["status"],
                "status_label": row["status_label"],
                "confidence": row["confidence"],
                "coverage": row["coverage"],
                "rank": row.get("rank"),
                "pillars": {k: v.get("value") for k, v in row["pillars"].items()},
                "hazards": {k: v.get("pressure") for k, v in row["hazards"].items()},
                "aridity": row["climate"].get("aridity_index"),
                "trend": row["climate"].get("precip_trend_pct_per_year"),
            }
            for row in computed
        ]
        bands = {"resilient": 0, "stable": 0, "watch": 0, "stressed": 0, "critical": 0, "no_data": 0}
        for row in computed:
            bands[row["status"]] = bands.get(row["status"], 0) + 1
        average = round(sum(row["score"] for row in scored) / len(scored), 1) if scored else None
        version = f"wcri-{timezone.now():%Y%m%d%H%M%S}"
        WorldSnapshot.objects.filter(is_current=True).update(is_current=False)
        WorldSnapshot.objects.create(
            version=version,
            as_of=timezone.now(),
            payload={"countries": payload_rows},
            summary={
                "countries": len(computed),
                "scored": len(scored),
                "average": average,
                "bands": bands,
                "events": len(events),
                "version": version,
                "elapsed_seconds": round(time.time() - started, 1),
            },
            is_current=True,
        )
        run.finished_at = timezone.now()
        run.status = "ok" if not summary["errors"] else "partial"
        run.sources = {"bank": len(bank), "forecast": len(forecast), "flood": len(flood), "nasa": len(monthly), "eonet": len(events)}
        run.countries_updated = len(computed)
        run.errors = summary["errors"]
        run.metadata = summary
        run.save()

        summary.update(
            {
                "countries": len(computed),
                "scored": len(scored),
                "average": average,
                "bands": bands,
                "version": version,
                "elapsed_seconds": round(time.time() - started, 1),
            }
        )
        if options["json"]:
            import json

            self.stdout.write(json.dumps(summary, indent=2))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"WCRI {version}: {len(scored)}/{len(computed)} scored, "
                f"average {average}, {len(events)} events, {round(time.time() - started, 1)}s"
            ))
            if summary["errors"]:
                self.stdout.write(self.style.WARNING(f"{len(summary['errors'])} source errors"))

    @staticmethod
    def _source(key, kind, records, latency_ms, error=""):
        labels = {
            "nasa_power": "NASA POWER / MERRA-2",
            "open_meteo_forecast": "Open-Meteo forecast",
            "open_meteo_flood": "Open-Meteo GloFAS",
            "eonet": "NASA EONET",
            "world_bank": "World Bank",
        }
        SourceStatus.objects.update_or_create(
            key=key,
            defaults={
                "label": labels.get(key, key.replace("_", " ").title()),
                "kind": kind,
                "last_attempt": timezone.now(),
                "last_success": timezone.now() if kind == "live" else None,
                "last_error": error,
                "records": records,
                "latency_ms": latency_ms,
                "ttl_seconds": 1800,
            },
        )
