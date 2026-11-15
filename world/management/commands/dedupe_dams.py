"""Merge duplicate atlas rows by country + normalized name."""
from __future__ import annotations

import re

from django.core.management.base import BaseCommand

from world.models import DamAtlas


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


class Command(BaseCommand):
    help = "Merge duplicate catalogue rows, preferring the monitored/pilot record."

    def handle(self, *args, **options):
        groups: dict[tuple[str, str], list[DamAtlas]] = {}
        for dam in DamAtlas.objects.all():
            groups.setdefault((dam.country_iso2, _norm(dam.name)), []).append(dam)
        merged = 0
        deleted = 0
        for key, rows in groups.items():
            if len(rows) < 2:
                continue
            # Never merge the full Wikidata corpus by name: distinct physical
            # structures can share a generic name. Only merge groups that
            # contain a curated/pilot/monitored row.
            if not any(
                row.is_monitored
                or row.pilot_slug
                or row.wikidata_id.startswith(("curated:", "pilot:"))
                for row in rows
            ):
                continue
            rows.sort(key=lambda row: (row.is_monitored, bool(row.pilot_slug)), reverse=True)
            keep = rows[0]
            for other in rows[1:]:
                if other.capacity_m3 and not keep.capacity_m3:
                    keep.capacity_m3 = other.capacity_m3
                if other.installed_mw and not keep.installed_mw:
                    keep.installed_mw = other.installed_mw
                if other.height_m and not keep.height_m:
                    keep.height_m = other.height_m
                if other.year_built and not keep.year_built:
                    keep.year_built = other.year_built
                if other.source_url and not keep.source_url:
                    keep.source_url = other.source_url
                if other.is_monitored:
                    keep.is_monitored = True
                if other.pilot_slug and not keep.pilot_slug:
                    keep.pilot_slug = other.pilot_slug
                keep.metadata = {**(other.metadata or {}), **(keep.metadata or {})}
                other.delete()
                deleted += 1
            keep.save()
            merged += 1
        self.stdout.write(self.style.SUCCESS(f"merged groups={merged} deleted={deleted} total={DamAtlas.objects.count()} monitored={DamAtlas.objects.filter(is_monitored=True).count()}"))
