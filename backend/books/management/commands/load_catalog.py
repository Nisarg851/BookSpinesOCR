import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from books.models import CatalogBook

# Repo root: backend/books/management/commands/this_file.py → up 4 levels.
CATALOG_PATH = Path(__file__).resolve().parents[4] / "catalog.csv"


class Command(BaseCommand):
    help = "Upsert CatalogBook rows from repo-root catalog.csv (safe to re-run)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            type=str,
            default=str(CATALOG_PATH),
            help="Path to catalog.csv (default: repo root)",
        )

    def handle(self, *args, **options):
        path = Path(options["path"])
        if not path.is_file():
            raise CommandError(f"Catalog file not found: {path}")

        created = 0
        updated = 0

        with path.open(newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            expected = {
                "id",
                "title",
                "author",
                "alt_titles",
                "isbn13",
                "publisher",
                "year",
                "edition",
            }
            if reader.fieldnames is None or set(reader.fieldnames) != expected:
                raise CommandError(
                    f"Unexpected CSV headers: {reader.fieldnames!r}; "
                    f"expected {sorted(expected)}"
                )

            for row in reader:
                year_raw = (row.get("year") or "").strip()
                year = int(year_raw) if year_raw else None

                _, was_created = CatalogBook.objects.update_or_create(
                    id=int(row["id"]),
                    defaults={
                        "title": row["title"].strip(),
                        "author": row["author"].strip(),
                        "alt_titles": (row.get("alt_titles") or "").strip(),
                        "isbn13": (row.get("isbn13") or "").strip(),
                        "publisher": (row.get("publisher") or "").strip(),
                        "year": year,
                        "edition": (row.get("edition") or "").strip(),
                    },
                )
                if was_created:
                    created += 1
                else:
                    updated += 1

        total = CatalogBook.objects.count()
        self.stdout.write(
            self.style.SUCCESS(
                f"load_catalog done: created={created} updated={updated} total={total}"
            )
        )
