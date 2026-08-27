from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from books.vlm import read_spine


class Command(BaseCommand):
    help = "Call the hosted VLM on one or more spine crop images (no mocks)."

    def add_arguments(self, parser):
        parser.add_argument(
            "images",
            nargs="+",
            help="Paths to spine crop JPEGs",
        )

    def handle(self, *args, **options):
        paths = [Path(p) for p in options["images"]]
        missing = [str(p) for p in paths if not p.is_file()]
        if missing:
            raise CommandError(f"Missing image(s): {', '.join(missing)}")

        total_cost = 0.0
        total_ms = 0
        for path in paths:
            self.stdout.write(self.style.MIGRATE_HEADING(f"=== {path} ==="))
            result = read_spine(path)
            total_cost += result.estimated_cost_usd
            total_ms += result.elapsed_ms
            self.stdout.write(f"status={result.status}")
            self.stdout.write(f"elapsed_ms={result.elapsed_ms}")
            self.stdout.write(f"title={result.title!r}")
            self.stdout.write(f"author={result.author!r}")
            self.stdout.write(f"confidence_note={result.confidence_note!r}")
            self.stdout.write(f"est_cost_usd={result.estimated_cost_usd:.6f}")
            self.stdout.write("raw_text=")
            self.stdout.write(result.raw_text)
            self.stdout.write("")

        self.stdout.write(
            self.style.SUCCESS(
                f"done crops={len(paths)} total_ms={total_ms} "
                f"total_est_cost_usd={total_cost:.6f}"
            )
        )
