"""Backwards-compatible alias: Algeria's wilaya layers (= refresh_regions --country DZ)."""
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Alias of `refresh_regions --country DZ`."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true")
        parser.add_argument("--offline", action="store_true", help="Accepted for compatibility; caches are always used when fresh.")
        parser.add_argument("--workers", type=int, default=4)

    def handle(self, *args, **options):
        extra = ["--force"] if options["force"] else []
        call_command("refresh_regions", "--country", "DZ", "--workers", str(options["workers"]), *extra, stdout=self.stdout, stderr=self.stderr)
