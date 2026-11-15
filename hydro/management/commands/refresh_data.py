from __future__ import annotations

from django.core.management.base import BaseCommand

from hydro.ai import ensure_slots, run_ai_layer
from hydro.services import data_service
from hydro.services.gazetteer import ensure_country
from hydro.services.index_engine import compute_index, store_snapshot


class Command(BaseCommand):
    help = "Refresh live satellite/forecast data and persist a new snapshot."

    def add_arguments(self, parser):
        parser.add_argument("--country", action="append", default=[])
        parser.add_argument("--offline", action="store_true")

    def handle(self, *args, **options):
        ensure_slots()
        codes = [code.upper() for code in (options["country"] or ["DZ", "TN"])]
        for code in codes:
            country = ensure_country(code)
            if not country:
                self.stderr.write(f"Unknown country: {code}")
                continue
            report = data_service.refresh_country(
                country, allow_network=not options["offline"], force=True
            )
            result = run_ai_layer(compute_index(country))
            snapshot = store_snapshot(country, result)
            self.stdout.write(
                self.style.SUCCESS(
                    f"{code}: {report['status']} · WRI {result['index']['value']:.1f} "
                    f"· {result['horizon']['verdict']} · snapshot {snapshot.id}"
                )
            )
            for error in report.get("errors", []):
                self.stdout.write(self.style.WARNING(f"  {error}"))
