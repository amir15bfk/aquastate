"""Compute first-level region layers (Map Viewer) for one, several or all countries."""
from __future__ import annotations

import time

from django.core.management.base import BaseCommand, CommandError

from world.models import RegionSnapshot
from world.services import region_jobs
from world.services.regions import NoBoundaries, build_payload, catalog


class Command(BaseCommand):
    help = "Download ADM1 boundaries and compute water stress, drought, flood, fire and vegetation-moisture layers per region."

    def add_arguments(self, parser):
        parser.add_argument("--country", action="append", default=[], help="ISO2 code (repeatable), e.g. --country DZ --country MA")
        parser.add_argument("--existing", action="store_true", help="Refresh every country that already has a snapshot.")
        parser.add_argument("--all", action="store_true", help="Every country with published boundaries (slow: ~200 countries).")
        parser.add_argument("--force", action="store_true", help="Ignore source caches.")
        parser.add_argument("--workers", type=int, default=4)

    def handle(self, *args, **options):
        codes = [c.upper() for c in options["country"]]
        if options["existing"]:
            codes += list(RegionSnapshot.objects.values_list("region", flat=True).distinct())
        if options["all"]:
            codes += sorted(catalog())
        codes = list(dict.fromkeys(codes))
        if not codes:
            raise CommandError("Pass --country XX, --existing or --all.")
        for iso2 in codes:
            started = time.time()
            try:
                payload = build_payload(iso2, force=options["force"], workers=options["workers"])
            except NoBoundaries:
                self.stderr.write(f"{iso2}: no ADM1 boundaries published by geoBoundaries — skipped")
                continue
            except Exception as exc:
                self.stderr.write(f"{iso2}: failed — {exc}")
                continue
            payload["elapsed_seconds"] = round(time.time() - started, 1)
            version = region_jobs.save_snapshot(iso2, payload)
            cov = payload["coverage"]
            self.stdout.write(self.style.SUCCESS(
                f"{version}: {cov['regions']} {payload['term_plural']}, {cov['with_climate']} with climate, "
                f"{cov['with_flood_signal']} with a flood signal, {len(payload['errors'])} errors, {payload['elapsed_seconds']}s"))
            for err in payload["errors"][:5]:
                self.stderr.write(f"  {err}")
