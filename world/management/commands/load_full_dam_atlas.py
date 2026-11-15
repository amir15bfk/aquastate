"""Load the full Wikidata dam corpus into DamAtlas without touching monitored rows."""
from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from hydro.services.gazetteer import all_countries
from world.models import DamAtlas


class Command(BaseCommand):
    help = "Bulk-load the full Wikidata dam corpus seed."

    def add_arguments(self, parser):
        parser.add_argument("--seed", default=str(Path(settings.WORLD_DATA_DIR) / "dam_atlas_full.json"))

    def handle(self, *args, **options):
        seed = Path(options["seed"])
        if not seed.exists():
            self.stderr.write(f"Seed not found: {seed}")
            return
        rows = json.loads(seed.read_text(encoding="utf-8"))
        by_iso = {row["iso2"]: row["name"] for row in all_countries()}
        existing = set(DamAtlas.objects.values_list("wikidata_id", flat=True))
        batch = []
        new = 0
        for row in rows:
            qid = row["wikidata_id"]
            if qid in existing:
                continue
            iso2 = (row.get("country_iso2") or "").upper()
            batch.append(
                DamAtlas(
                    wikidata_id=qid,
                    name=(row.get("name") or qid)[:240],
                    country_iso2=iso2,
                    country_name=(by_iso.get(iso2) or "")[:160],
                    lat=row["lat"],
                    lon=row["lon"],
                    capacity_m3=row.get("capacity_m3"),
                    installed_mw=row.get("installed_mw"),
                    height_m=row.get("height_m"),
                    year_built=row.get("year_built"),
                    source=row.get("source", "Wikidata full corpus"),
                    source_url=row.get("source_url", ""),
                    is_monitored=False,
                    metadata={},
                )
            )
            new += 1
            if len(batch) >= 1000:
                DamAtlas.objects.bulk_create(batch, batch_size=1000, ignore_conflicts=True)
                batch = []
        if batch:
            DamAtlas.objects.bulk_create(batch, batch_size=1000, ignore_conflicts=True)
        self.stdout.write(
            self.style.SUCCESS(
                f"Full corpus loaded: new={new} total={DamAtlas.objects.count()} "
                f"monitored={DamAtlas.objects.filter(is_monitored=True).count()} "
                f"countries={DamAtlas.objects.exclude(country_iso2='').values('country_iso2').distinct().count()}"
            )
        )
