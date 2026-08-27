from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from books.detection import crop_boxes, detect_spines

REPO_ROOT = Path(__file__).resolve().parents[4]


class Command(BaseCommand):
    help = "Run local YOLO book detection on an image and print boxes (no API)."

    def add_arguments(self, parser):
        parser.add_argument(
            "image",
            nargs="?",
            default=str(REPO_ROOT / "samples" / "bookshelf.jpg"),
            help="Path to a bookshelf photo (default: samples/bookshelf.jpg)",
        )

    def handle(self, *args, **options):
        image_path = Path(options["image"])
        if not image_path.is_file():
            raise CommandError(f"Image not found: {image_path}")

        result = detect_spines(image_path)
        self.stdout.write(f"status={result.status}")
        self.stdout.write(f"detection_ms={result.detection_ms}")
        if result.message:
            self.stdout.write(result.message)

        self.stdout.write(f"boxes={len(result.boxes)}")
        for i, box in enumerate(result.boxes):
            self.stdout.write(
                f"  [{i}] x1={box.x1:.1f} y1={box.y1:.1f} "
                f"x2={box.x2:.1f} y2={box.y2:.1f} conf={box.confidence:.3f}"
            )

        if result.boxes:
            dest = REPO_ROOT / "samples" / "crops"
            saved = crop_boxes(image_path, result.boxes, dest)
            self.stdout.write(f"crops_written={len(saved)} -> {dest}")
