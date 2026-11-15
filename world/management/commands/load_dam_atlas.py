"""Load the global notable-dam seed and link monitored dams."""
from __future__ import annotations

import json
import math
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils.text import slugify

from core.models import Dam
from hydro.models import Reservoir
from hydro.services.gazetteer import all_countries
from world.models import DamAtlas


def _distance_deg(lat1, lon1, lat2, lon2):
    dlat = lat1 - lat2
    dlon = (lon1 - lon2) * math.cos(math.radians((lat1 + lat2) / 2.0))
    return math.sqrt(dlat * dlat + dlon * dlon)


def _normalise(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum())


class Command(BaseCommand):
    help = "Load the Wikidata/Wikipedia notable-dam atlas and link monitored dams."

    def add_arguments(self, parser):
        parser.add_argument("--seed", default=str(Path(settings.WORLD_DATA_DIR) / "dam_atlas_seed.json"))
        parser.add_argument("--reset", action="store_true", help="Clear the atlas before reloading.")

    def handle(self, *args, **options):
        seed_path = Path(options["seed"])
        if not seed_path.exists():
            self.stderr.write(f"Seed not found: {seed_path}")
            return
        if options["reset"]:
            # Rebuild the notable/pilot/curated layer without deleting the
            # full Wikidata corpus loaded by load_full_dam_atlas.
            from django.db.models import Q

            deleted, _ = DamAtlas.objects.filter(
                Q(source__startswith="Wikidata / Wikipedia")
                | Q(source__startswith="Curated public dam inventory")
                | Q(source__startswith="AquaState pilot inventory")
                | Q(wikidata_id__startswith="curated:")
                | Q(wikidata_id__startswith="pilot:")
            ).delete()
            self.stdout.write(f"Notable/pilot/curated rows cleared: {deleted}")
        rows = json.loads(seed_path.read_text(encoding="utf-8"))
        countries = [
            row
            for row in all_countries()
            if row.get("lat") is not None and row.get("lon") is not None
        ]
        by_iso = {row["iso2"]: row for row in countries}

        existing = set(DamAtlas.objects.values_list("wikidata_id", flat=True))
        batch = []
        created = 0
        for row in rows:
            if row["wikidata_id"] in existing:
                continue
            iso2 = (row.get("country_iso2") or "").upper()
            if not iso2:
                best = None
                best_dist = 99.0
                for country in countries:
                    dist = _distance_deg(row["lat"], row["lon"], country["lat"], country["lon"])
                    if dist < best_dist:
                        best_dist = dist
                        best = country["iso2"]
                if best and best_dist <= 8.0:
                    iso2 = best
            country_name = by_iso.get(iso2, {}).get("name", "")
            batch.append(
                DamAtlas(
                    wikidata_id=row["wikidata_id"],
                    name=row["name"][:240],
                    country_iso2=iso2,
                    country_name=country_name[:160],
                    lat=row["lat"],
                    lon=row["lon"],
                    installed_mw=row.get("installed_mw"),
                    height_m=row.get("height_m"),
                    year_built=row.get("year_built"),
                    source=row.get("source", "Wikidata / Wikipedia"),
                    source_url=row.get("source_url", ""),
                    metadata={"coordinates": row.get("coordinates", 1), "inception": row.get("inception")},
                )
            )
            created += 1
        DamAtlas.objects.bulk_create(batch, batch_size=500, ignore_conflicts=True)
        self.stdout.write(f"Atlas rows loaded: {len(rows)} (new {created})")

        # Link pilot dams by name and mark them monitored.
        pilot_links = 0
        for dam in Dam.objects.select_related("country").all():
            iso2 = "DZ" if dam.country.iso3 == "DZA" else ("TN" if dam.country.iso3 == "TUN" else dam.country.iso3[:2])
            target = _normalise(dam.name)
            match = DamAtlas.objects.filter(country_iso2=iso2, is_monitored=False)
            linked = None
            for item in match:
                if _normalise(item.name) == target or target in _normalise(item.name) or _normalise(item.name) in target:
                    linked = item
                    break
            if linked:
                linked.is_monitored = True
                linked.pilot_slug = dam.slug
                linked.metadata = {**(linked.metadata or {}), "pilot": True, "capacity_m3": dam.capacity_m3}
                linked.save(update_fields=["is_monitored", "pilot_slug", "metadata"])
                pilot_links += 1
            else:
                DamAtlas.objects.update_or_create(
                    wikidata_id=f"pilot:{dam.slug}",
                    defaults={
                        "name": dam.name,
                        "country_iso2": iso2,
                        "country_name": getattr(dam.country, "name", ""),
                        "lat": dam.lat,
                        "lon": dam.lon,
                        "capacity_m3": dam.capacity_m3,
                        "is_monitored": True,
                        "pilot_slug": dam.slug,
                        "source": "AquaState pilot inventory",
                        "source_url": "",
                        "metadata": {"pilot": True, "basin": dam.basin.name if dam.basin else ""},
                    },
                )
                pilot_links += 1
        self.stdout.write(f"Pilot dams linked: {pilot_links}")

        # Add curated hydro reservoirs as monitored atlas rows.
        curated = 0
        for reservoir in Reservoir.objects.select_related("country").all():
            qid = f"curated:{reservoir.country.iso2}:{slugify(reservoir.name)[:40]}"
            DamAtlas.objects.update_or_create(
                wikidata_id=qid,
                defaults={
                    "name": reservoir.name,
                    "country_iso2": reservoir.country.iso2,
                    "country_name": reservoir.country.name,
                    "lat": reservoir.lat,
                    "lon": reservoir.lon,
                    "capacity_m3": reservoir.capacity_mm3 * 1_000_000.0,
                    "is_monitored": True,
                    "source": "Curated public dam inventory",
                    "source_url": reservoir.source_url,
                    "metadata": {
                        "storage_source": reservoir.storage_source,
                        "reference_storage_pct": reservoir.reference_storage_pct,
                    },
                },
            )
            curated += 1
        self.stdout.write(f"Curated reservoirs linked: {curated}")
        self.stdout.write(
            self.style.SUCCESS(
                f"DamAtlas total={DamAtlas.objects.count()} monitored={DamAtlas.objects.filter(is_monitored=True).count()} "
                f"countries={DamAtlas.objects.exclude(country_iso2='').values('country_iso2').distinct().count()}"
            )
        )
