"""
Synchronous photo pipeline: detect → VLM → match.

Never raises for empty/unreadable results — callers always get a ShelfPhoto
and a well-formed spine/match list (possibly empty).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.db import transaction

from .detection import DetectionResult, detect_spines, save_spines_for_photo
from .matching import match_against_db
from .models import CatalogBook, DetectedSpine, LibraryEntry, MatchResult, ShelfPhoto
from .vlm import read_spines_for_photo


@dataclass
class PipelineResult:
    photo: ShelfPhoto
    detection: DetectionResult
    spines: list[DetectedSpine]
    total_ms: int


def _match_spines(photo: ShelfPhoto) -> int:
    """
    Run fuzzy matching for every spine; create MatchResult rows.
    AUTO_ACCEPTED also creates a LibraryEntry (direct-add path).
    Returns matching_ms.
    """
    started = time.perf_counter()
    for spine in photo.spines.all():
        try:
            spine.match.delete()
        except MatchResult.DoesNotExist:
            pass

        if spine.vlm_status != DetectedSpine.VlmStatus.OK or not spine.vlm_title:
            MatchResult.objects.create(
                spine=spine,
                catalog_book=None,
                confidence=0.0,
                status=MatchResult.Status.PENDING_REVIEW,
            )
            continue

        decision = match_against_db(spine.vlm_title, spine.vlm_author)
        catalog_book = None
        confidence = 0.0
        if decision.best and decision.suggested:
            confidence = decision.best.confidence
            try:
                catalog_book = CatalogBook.objects.get(pk=decision.best.entry.id)
            except CatalogBook.DoesNotExist:
                catalog_book = None
                confidence = 0.0

        if decision.status == "AUTO_ACCEPTED" and catalog_book is not None:
            match_status = MatchResult.Status.AUTO_ACCEPTED
        else:
            match_status = MatchResult.Status.PENDING_REVIEW
            if not decision.suggested:
                catalog_book = None
                confidence = decision.best.confidence if decision.best else 0.0

        match = MatchResult.objects.create(
            spine=spine,
            catalog_book=catalog_book,
            confidence=confidence,
            status=match_status,
        )

        if match_status == MatchResult.Status.AUTO_ACCEPTED:
            LibraryEntry.objects.create(
                title=catalog_book.title,
                author=catalog_book.author,
                catalog_book=catalog_book,
                match_result=match,
            )

    elapsed = int((time.perf_counter() - started) * 1000)
    photo.matching_ms = elapsed
    photo.save(update_fields=["matching_ms"])
    return elapsed


def process_photo_image(image_path: Path) -> PipelineResult:
    """
    Full pipeline for a local image path. Safe for zero spines / failed VLMs.
    """
    wall_start = time.perf_counter()
    detection = detect_spines(image_path)
    photo = ShelfPhoto.objects.create(detection_ms=detection.detection_ms)

    spines: list[DetectedSpine] = []
    if detection.status == "ok" and detection.boxes:
        spines = save_spines_for_photo(photo, image_path, detection.boxes)
        limit = int(settings.VLM_MAX_SPINES_PER_PHOTO)
        read_spines_for_photo(photo, limit=limit)
        _match_spines(photo)
        spines = list(
            photo.spines.select_related("match", "match__catalog_book").all()
        )
    else:
        photo.vlm_ms = 0
        photo.matching_ms = 0
        photo.save(update_fields=["vlm_ms", "matching_ms"])

    total_ms = int((time.perf_counter() - wall_start) * 1000)
    photo.refresh_from_db()
    return PipelineResult(
        photo=photo,
        detection=detection,
        spines=spines,
        total_ms=total_ms,
    )


def confirm_spine(
    spine: DetectedSpine,
    *,
    action: str,
    catalog_book_id: int | None = None,
    title: str | None = None,
    author: str | None = None,
) -> tuple[MatchResult, LibraryEntry | None]:
    """
    Human-in-the-loop confirm/correct/discard for one spine's MatchResult.
    """
    action = (action or "").strip().lower()
    try:
        match = spine.match
    except MatchResult.DoesNotExist:
        match = MatchResult.objects.create(
            spine=spine,
            catalog_book=None,
            confidence=0.0,
            status=MatchResult.Status.PENDING_REVIEW,
        )

    with transaction.atomic():
        if action == "discard":
            match.status = MatchResult.Status.DISCARDED
            match.save(update_fields=["status"])
            if hasattr(match, "library_entry"):
                match.library_entry.delete()
            return match, None

        if action == "accept":
            if match.catalog_book is None:
                raise ValueError("No suggested catalog match to accept")
            match.status = MatchResult.Status.CONFIRMED
            match.save(update_fields=["status"])
            entry, _ = LibraryEntry.objects.update_or_create(
                match_result=match,
                defaults={
                    "title": match.catalog_book.title,
                    "author": match.catalog_book.author,
                    "catalog_book": match.catalog_book,
                },
            )
            return match, entry

        if action == "correct":
            catalog_book = None
            if catalog_book_id is not None:
                catalog_book = CatalogBook.objects.filter(pk=catalog_book_id).first()
                if catalog_book is None:
                    raise ValueError(f"Unknown catalog_book_id={catalog_book_id}")
                final_title = catalog_book.title
                final_author = catalog_book.author
            else:
                final_title = (title or "").strip()
                final_author = (author or "").strip()
                if not final_title:
                    raise ValueError("correct requires catalog_book_id or title")

            match.catalog_book = catalog_book
            match.status = MatchResult.Status.CORRECTED
            match.save(update_fields=["catalog_book", "status"])
            entry, _ = LibraryEntry.objects.update_or_create(
                match_result=match,
                defaults={
                    "title": final_title,
                    "author": final_author,
                    "catalog_book": catalog_book,
                },
            )
            return match, entry

        raise ValueError(
            'action must be "accept", "correct", or "discard"'
        )
