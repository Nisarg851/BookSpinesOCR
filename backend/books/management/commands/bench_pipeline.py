"""
Run detect → VLM → match on every committed sample photo and print a table.

Costs use OpenAI usage.prompt_tokens / completion_tokens × published
gpt-4o-mini list rates ($0.15 / $0.60 per 1M). Cursor fallback reports $0
(no token meter on that API).
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from books.pipeline import process_photo_image
from books.vlm import INPUT_USD_PER_1M, OUTPUT_USD_PER_1M

REPO_ROOT = Path(__file__).resolve().parents[4]
SAMPLES_DIR = REPO_ROOT / "samples"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def _sample_photos() -> list[Path]:
    if not SAMPLES_DIR.is_dir():
        return []
    return sorted(
        p
        for p in SAMPLES_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES
    )


class Command(BaseCommand):
    help = (
        "Bench the full pipeline on samples/*.jpg|webp and print latency/cost."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--image",
            action="append",
            dest="images",
            help="Optional image path (repeatable). Default: all samples/*.",
        )

    def handle(self, *args, **options):
        paths = [Path(p) for p in (options.get("images") or [])]
        if not paths:
            paths = _sample_photos()
        if not paths:
            raise CommandError(f"No sample images found under {SAMPLES_DIR}")

        missing = [str(p) for p in paths if not p.is_file()]
        if missing:
            raise CommandError(f"Missing image(s): {', '.join(missing)}")

        provider = (settings.VLM_PROVIDER or "openai").strip().lower()
        model = settings.VLM_MODEL
        self.stdout.write(
            f"provider={provider} model={model} "
            f"VLM_MAX_SPINES_PER_PHOTO={settings.VLM_MAX_SPINES_PER_PHOTO}"
        )
        self.stdout.write(
            f"cost_basis=OpenAI list rates "
            f"input=${INPUT_USD_PER_1M}/1M output=${OUTPUT_USD_PER_1M}/1M "
            f"(from usage tokens; Cursor calls estimate $0)"
        )
        self.stdout.write("")

        rows: list[dict] = []
        for path in paths:
            self.stdout.write(self.style.MIGRATE_HEADING(f"=== {path.name} ==="))
            result = process_photo_image(path)
            photo = result.photo
            boxes = len(result.detection.boxes)
            row = {
                "photo": path.name,
                "boxes": boxes,
                "vlm_calls": result.vlm_calls,
                "detection_ms": photo.detection_ms or 0,
                "vlm_ms": photo.vlm_ms or 0,
                "matching_ms": photo.matching_ms or 0,
                "total_ms": result.total_ms,
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
                "est_cost_usd": result.est_cost_usd,
                "status": result.detection.status,
            }
            rows.append(row)
            self.stdout.write(
                f"status={row['status']} boxes={boxes} "
                f"vlm_calls={row['vlm_calls']} "
                f"detection_ms={row['detection_ms']} "
                f"vlm_ms={row['vlm_ms']} "
                f"matching_ms={row['matching_ms']} "
                f"total_ms={row['total_ms']} "
                f"est_cost_usd={row['est_cost_usd']:.6f}"
            )
            self.stdout.write("")

        # Markdown-friendly table for pasting into README.
        self.stdout.write("--- paste into README ---")
        header = (
            "| photo | boxes | vlm_calls | detection_ms | vlm_ms | "
            "matching_ms | total_ms | est_cost_usd |"
        )
        sep = (
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"
        )
        self.stdout.write(header)
        self.stdout.write(sep)
        for row in rows:
            self.stdout.write(
                f"| `{row['photo']}` | {row['boxes']} | {row['vlm_calls']} | "
                f"{row['detection_ms']} | {row['vlm_ms']} | "
                f"{row['matching_ms']} | {row['total_ms']} | "
                f"${row['est_cost_usd']:.4f} |"
            )

        tot_cost = sum(r["est_cost_usd"] for r in rows)
        tot_ms = sum(r["total_ms"] for r in rows)
        tot_calls = sum(r["vlm_calls"] for r in rows)
        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"done photos={len(rows)} vlm_calls={tot_calls} "
                f"sum_total_ms={tot_ms} sum_est_cost_usd={tot_cost:.6f}"
            )
        )
        self.stdout.write(
            "Notes: vlm_ms is sum of per-crop elapsed_ms (not wall-clock under "
            "parallelism). total_ms is wall-clock for the whole pipeline. "
            "est_cost_usd uses billed usage tokens × gpt-4o-mini list prices."
        )
