"""Compute and persist HRI snapshots for pilot dams."""
from __future__ import annotations

import datetime as dt

from django.core.management.base import BaseCommand, CommandError

from core.models import Dam
from core.services.exceptions import MissingDataError
from core.services.snapshots import compute_dam_state


class Command(BaseCommand):
    help = "Compute the HRI and persist IndexSnapshot rows for pilot dams."

    def add_arguments(self, parser):
        parser.add_argument("--all", action="store_true", help="compute every dam")
        parser.add_argument("--dam", default="", help="dam slug")
        parser.add_argument("--country", default="", help="ISO3 country filter")
        parser.add_argument("--as-of", default="2026-11-13")

    def handle(self, *args, **options):
        try:
            as_of = dt.date.fromisoformat(options["as_of"])
        except ValueError as exc:
            raise CommandError(f"invalid --as-of: {options['as_of']}") from exc
        dams = Dam.objects.select_related("country", "basin").all()
        if options["dam"]:
            dams = dams.filter(slug=options["dam"])
        if options["country"]:
            dams = dams.filter(country__iso3=options["country"].upper())
        if not options["all"] and not options["dam"] and not options["country"]:
            options["all"] = True
        if options["all"]:
            pass
        dams = list(dams)
        if not dams:
            raise CommandError("no dams matched the filters")
        computed = 0
        for dam in dams:
            try:
                payload = compute_dam_state(dam.slug, as_of)
            except MissingDataError as exc:
                self.stderr.write(self.style.WARNING(str(exc)))
                continue
            computed += 1
            if options["verbosity"]:
                self.stdout.write(
                    f"{dam.country.iso3} {dam.name}: HRI={payload['hri']:.2f} "
                    f"status={payload['status']} phi={payload['phi']:.5f}"
                )
        self.stdout.write(
            self.style.SUCCESS(f"Computed {computed}/{len(dams)} snapshots as-of {as_of}.")
        )
