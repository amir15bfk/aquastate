"""Refresh the world layer once or on a loop."""
from __future__ import annotations

import time

from django.core.management import call_command
from django.core.management.base import BaseCommand

from world.services.refresh import refresh_lock


class Command(BaseCommand):
    help = "Refresh world sources, recompute WCRI and write a new snapshot."

    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true", help="Keep running.")
        parser.add_argument("--interval", type=int, default=900, help="Seconds between runs.")
        parser.add_argument("--offline", action="store_true")
        parser.add_argument("--force", action="store_true")
        parser.add_argument("--limit", type=int, default=0)

    def handle(self, *args, **options):
        while True:
            with refresh_lock() as acquired:
                if not acquired:
                    self.stdout.write(self.style.WARNING("Another refresh is running; skipping this cycle."))
                else:
                    started = time.time()
                    try:
                        args = []
                        if options["offline"]:
                            args.append("--offline")
                        if options["force"]:
                            args.append("--force")
                        if options["limit"]:
                            args.extend(["--limit", str(options["limit"])])
                        call_command("bootstrap_world", *args, verbosity=0)
                        # Region layers for the Map Viewer: Algeria plus every country already opened there.
                        try:
                            call_command("refresh_regions", "--country", "DZ", "--existing", *[a for a in args if a == "--force"], verbosity=0)
                        except Exception as exc:  # never let the sub-national layer break the world refresh
                            self.stderr.write(f"Region refresh failed: {exc}")
                        self.stdout.write(
                            self.style.SUCCESS(f"Refresh complete in {round(time.time() - started, 1)}s")
                        )
                    except Exception as exc:
                        self.stderr.write(f"Refresh failed: {exc}")
            if not options["loop"]:
                break
            next_run = time.time() + max(60, options["interval"])
            self.stdout.write(f"Next refresh at {time.strftime('%H:%M:%S', time.localtime(next_run))}")
            try:
                while time.time() < next_run:
                    time.sleep(min(30, max(1, next_run - time.time())))
            except KeyboardInterrupt:
                self.stdout.write("\nStopped.")
                break
