from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand

from hydro.ai import ensure_slots, run_ai_layer
from hydro.data.curated import AQUIFERS, AQUIFER_COORDS, KM3_YEAR_TO_MM3_DAY
from hydro.models import Aquifer, Country
from hydro.services import data_service, storage
from hydro.services.gazetteer import ensure_country
from hydro.services.index_engine import compute_index, store_snapshot


class Command(BaseCommand):
    help = "Seed curated inventories, live/fallback climate and index snapshots."

    def add_arguments(self, parser):
        parser.add_argument(
            "--country",
            action="append",
            default=[],
            help="ISO2 code(s). Defaults to DZ and TN.",
        )
        parser.add_argument(
            "--offline",
            action="store_true",
            help="Use deterministic fallback climate instead of calling public APIs.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Refresh even when the cache is warm.",
        )

    def handle(self, *args, **options):
        codes = [code.upper() for code in (options["country"] or ["DZ", "TN"])]
        ensure_slots()
        for code in codes:
            country = ensure_country(code)
            if not country:
                self.stderr.write(f"Unknown country: {code}")
                continue
            storage.seed_reservoirs(country)
            self._seed_aquifers(country)
            report = data_service.refresh_country(
                country,
                allow_network=not options["offline"],
                force=True,
            )
            result = run_ai_layer(compute_index(country))
            snapshot = store_snapshot(country, result)
            self.stdout.write("")
            self.stdout.write(
                self.style.SUCCESS(
                    f"{country.name}: WRI {result['index']['value']:.1f} "
                    f"({result['index']['status_label']}) · horizon {result['horizon']['verdict']} "
                    f"· confidence {result['index']['confidence']:.2f}"
                )
            )
            self.stdout.write(
                f"  mode={report.get('status')} reservoirs={report.get('reservoirs')} "
                f"climate_rows={report.get('climate_rows')} forecast_rows={report.get('forecast_rows')}"
            )
            self.stdout.write(
                f"  cover={result['horizon']['cover_days']:.1f}d rain={result['horizon']['days_to_rain']} "
                f"base={result['index']['base_value']:.1f} snapshot={snapshot.id}"
            )
            for pillar in result["pillars"]:
                self.stdout.write(
                    f"    {pillar['label']:<22} {pillar['value']:>6.1f}  ×{pillar['weight']:.2f}"
                )
            if report.get("errors"):
                for error in report["errors"]:
                    self.stdout.write(self.style.WARNING(f"    source warning: {error}"))

    def _seed_aquifers(self, country: Country) -> None:
        for name, volume, recharge_km3, extraction_km3, trend, fossil, shared in AQUIFERS.get(
            country.iso2, []
        ):
            lat, lon = AQUIFER_COORDS.get((country.iso2, name), (country.lat, country.lon))
            Aquifer.objects.update_or_create(
                country=country,
                name=name,
                defaults={
                    "lat": lat,
                    "lon": lon,
                    "volume_km3": volume,
                    "recharge_mm3_day": recharge_km3 * KM3_YEAR_TO_MM3_DAY,
                    "extraction_mm3_day": extraction_km3 * KM3_YEAR_TO_MM3_DAY,
                    "trend_m_per_year": trend,
                    "is_fossil": fossil,
                    "shared_with": shared,
                    "source_name": "SASS / national aquifer reports (screening reference)",
                    "source_url": "https://www.unesco.org/en/water-security",
                    "metadata": {
                        "note": "Screening-level public figures. Not an operational groundwater model.",
                        "recharge_km3_per_year": recharge_km3,
                        "extraction_km3_per_year": extraction_km3,
                    },
                },
            )
