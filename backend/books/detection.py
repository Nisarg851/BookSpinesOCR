"""
Local book/spine detection.

Model: Ultralytics YOLOv8n (`yolov8n.pt`), pretrained on COCO, run on CPU.
This is off-the-shelf: we load published COCO weights and never train or
fine-tune. COCO includes a "book" class, so we can filter detections to books
without a custom dataset.

Known limitation: COCO's "book" class is a general book-like object, not a
spine detector. On a tightly packed shelf it often returns one box around a
cluster of spines (or misses thin spines) rather than one box per book.
That is acceptable for this exercise as long as we handle zero/partial
detections in the UI instead of overselling accuracy.
"""

from __future__ import annotations

import io
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from django.conf import settings
from PIL import Image, UnidentifiedImageError

ErrorCode = Literal[
    "ok",
    "zero_detections",
    "unreadable_image",
    "model_load_failed",
    "timeout",
]


@dataclass
class BoundingBox:
    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float


@dataclass
class DetectionResult:
    status: ErrorCode
    boxes: list[BoundingBox] = field(default_factory=list)
    detection_ms: int = 0
    message: str = ""


_model = None
_model_error: str | None = None


def _load_model():
    """Load YOLO once. Subsequent calls reuse the in-process model."""
    global _model, _model_error
    if _model is not None:
        return _model
    if _model_error is not None:
        raise RuntimeError(_model_error)

    try:
        from ultralytics import YOLO

        weights_dir = Path(settings.SPINE_DETECTION_WEIGHTS_DIR)
        weights_dir.mkdir(parents=True, exist_ok=True)
        weights = weights_dir / settings.SPINE_DETECTION_MODEL
        if weights.is_file():
            _model = YOLO(str(weights))
        else:
            # First run: Ultralytics downloads into CWD; we relocate into weights_dir.
            _model = YOLO(settings.SPINE_DETECTION_MODEL)
            downloaded = Path(settings.SPINE_DETECTION_MODEL)
            if downloaded.is_file():
                downloaded.replace(weights)
            elif Path.cwd().joinpath(settings.SPINE_DETECTION_MODEL).is_file():
                Path.cwd().joinpath(settings.SPINE_DETECTION_MODEL).replace(weights)
        return _model
    except Exception as exc:
        _model_error = str(exc)
        raise


def _open_image(image_path: str | Path) -> Image.Image | None:
    path = Path(image_path)
    if not path.is_file():
        return None
    try:
        with Image.open(path) as img:
            img.load()
            return img.convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError):
        return None


def _run_yolo(image_path: str) -> list[BoundingBox]:
    model = _load_model()
    conf = float(settings.SPINE_DETECTION_CONFIDENCE)
    results = model.predict(
        source=image_path,
        device="cpu",
        conf=conf,
        verbose=False,
    )
    boxes: list[BoundingBox] = []
    names = model.names
    for result in results:
        if result.boxes is None:
            continue
        for box in result.boxes:
            cls_id = int(box.cls[0])
            label = names.get(cls_id, "") if isinstance(names, dict) else names[cls_id]
            if label != "book":
                continue
            x1, y1, x2, y2 = (float(v) for v in box.xyxy[0].tolist())
            score = float(box.conf[0])
            boxes.append(
                BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2, confidence=score)
            )
    boxes.sort(key=lambda b: b.x1)
    return boxes


def detect_spines(image_path: str | Path) -> DetectionResult:
    """
    Run CPU YOLO inference. Never raises to the caller.

    Returns a DetectionResult whose status is one of: ok, zero_detections,
    unreadable_image, model_load_failed, timeout.
    """
    import time

    path = Path(image_path)
    image = _open_image(path)
    if image is None:
        return DetectionResult(
            status="unreadable_image",
            message=f"Could not open image: {path}",
        )
    image.close()

    timeout_s = int(settings.SPINE_DETECTION_TIMEOUT_S)
    started = time.perf_counter()
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_run_yolo, str(path))
            boxes = future.result(timeout=timeout_s)
    except FuturesTimeout:
        elapsed = int((time.perf_counter() - started) * 1000)
        return DetectionResult(
            status="timeout",
            detection_ms=elapsed,
            message=f"Detection exceeded {timeout_s}s timeout",
        )
    except Exception as exc:
        elapsed = int((time.perf_counter() - started) * 1000)
        return DetectionResult(
            status="model_load_failed",
            detection_ms=elapsed,
            message=str(exc) or "YOLO model failed to load or run",
        )

    elapsed = int((time.perf_counter() - started) * 1000)
    if not boxes:
        return DetectionResult(
            status="zero_detections",
            detection_ms=elapsed,
            message="No book detections above the confidence threshold",
        )
    return DetectionResult(status="ok", boxes=boxes, detection_ms=elapsed)


def crop_boxes(
    image_path: str | Path,
    boxes: list[BoundingBox],
    dest_dir: Path,
) -> list[Path]:
    """Write JPEG crops for each box. dest_dir is created if needed."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    image = _open_image(image_path)
    if image is None:
        return []

    width, height = image.size
    saved: list[Path] = []
    for index, box in enumerate(boxes):
        left = max(0, min(width, int(box.x1)))
        upper = max(0, min(height, int(box.y1)))
        right = max(left + 1, min(width, int(box.x2)))
        lower = max(upper + 1, min(height, int(box.y2)))
        crop = image.crop((left, upper, right, lower))
        out = dest_dir / f"{index}.jpg"
        crop.save(out, format="JPEG", quality=90)
        saved.append(out)
    image.close()
    return saved


def save_spines_for_photo(photo, image_path: str | Path, boxes: list[BoundingBox]):
    """
    Persist DetectedSpine rows + crop files under MEDIA_ROOT/crops/<photo_id>/.
    Does not store the original shelf photo (caller uses a temp file).
    """
    from .models import DetectedSpine

    media_root = Path(settings.MEDIA_ROOT)
    dest_dir = media_root / "crops" / str(photo.pk)
    crop_paths = crop_boxes(image_path, boxes, dest_dir)
    spines = []
    for index, (box, crop_path) in enumerate(zip(boxes, crop_paths)):
        spine = DetectedSpine.objects.create(
            photo=photo,
            x1=box.x1,
            y1=box.y1,
            x2=box.x2,
            y2=box.y2,
            confidence=box.confidence,
            crop=f"crops/{photo.pk}/{crop_path.name}",
        )
        spines.append(spine)
    return spines
