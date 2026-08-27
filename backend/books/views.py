import tempfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from rest_framework import generics, status
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from .detection import detect_spines, save_spines_for_photo
from .models import CatalogBook, LibraryEntry, ShelfPhoto
from .serializers import (
    CatalogBookSerializer,
    DetectedSpineSerializer,
    LibraryEntrySerializer,
    ShelfPhotoSerializer,
)
from .vlm import read_spines_for_photo

MAX_DOWNLOAD_BYTES = 15 * 1024 * 1024


@api_view(["GET"])
def health(request):
    """Placeholder so the Expo app can confirm it reaches Django."""
    return Response({"status": "ok", "service": "shelfie"})


class CatalogBookList(generics.ListAPIView):
    """Read-only catalog dump — useful for sanity-checking load_catalog."""

    queryset = CatalogBook.objects.all()
    serializer_class = CatalogBookSerializer


class LibraryEntryList(generics.ListAPIView):
    """Confirmed library for the single implicit user."""

    queryset = LibraryEntry.objects.select_related("catalog_book").all()
    serializer_class = LibraryEntrySerializer


def _write_upload_to_temp(upload: UploadedFile) -> Path:
    suffix = Path(upload.name or "upload.jpg").suffix or ".jpg"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    for chunk in upload.chunks():
        tmp.write(chunk)
    tmp.close()
    return Path(tmp.name)


def _download_url_to_temp(url: str) -> tuple[Path | None, str | None]:
    try:
        req = Request(url, headers={"User-Agent": "Shelfie/0.1"})
        with urlopen(req, timeout=20) as resp:
            content_type = (resp.headers.get("Content-Type") or "").lower()
            if content_type and not content_type.startswith("image/"):
                return None, f"URL did not look like an image ({content_type})"
            data = resp.read(MAX_DOWNLOAD_BYTES + 1)
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        return None, f"Could not download image URL: {exc}"

    if len(data) > MAX_DOWNLOAD_BYTES:
        return None, "Image URL exceeds 15MB limit"
    if not data:
        return None, "Image URL returned empty body"

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
    tmp.write(data)
    tmp.close()
    return Path(tmp.name), None


def _detection_response(request, photo: ShelfPhoto, result, spines, *, vlm_reads=0):
    photo.refresh_from_db()
    photo_data = ShelfPhotoSerializer(photo).data
    spine_data = DetectedSpineSerializer(
        spines, many=True, context={"request": request}
    ).data
    readable = sum(1 for s in spines if s.vlm_status == "OK")
    unreadable = sum(1 for s in spines if s.vlm_status == "UNREADABLE")
    actionable = {
        "ok": result.status == "ok",
        "zero_detections": result.status == "zero_detections",
        "unreadable_image": result.status == "unreadable_image",
        "model_load_failed": result.status == "model_load_failed",
        "timeout": result.status == "timeout",
    }
    message = result.message or (
        f"Detected {len(spines)} book region(s)" if spines else "No book regions found"
    )
    if spines:
        message = (
            f"{message}; VLM read {vlm_reads} crop(s) "
            f"({readable} ok, {unreadable} unreadable), "
            f"vlm_ms={photo.vlm_ms}"
        )
    return Response(
        {
            **actionable,
            "status": result.status,
            "message": message,
            "photo": photo_data,
            "detection_ms": photo.detection_ms,
            "vlm_ms": photo.vlm_ms,
            "vlm_reads": vlm_reads,
            "spines": spine_data,
        }
    )


@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def detect_books(request):
    """
    Run local spine/book detection on an uploaded file or an image URL.

    The original photo is processed from a temp file and is not kept as a
    gallery asset — only crop files + DetectedSpine rows are persisted.
    """
    temp_path: Path | None = None
    try:
        upload = request.FILES.get("image") or request.FILES.get("photo")
        url = (request.data.get("url") or "").strip()

        if upload and url:
            return Response(
                {
                    "ok": False,
                    "status": "bad_request",
                    "message": "Send either an image file or a url, not both",
                    "spines": [],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not upload and not url:
            return Response(
                {
                    "ok": False,
                    "status": "bad_request",
                    "message": "Provide multipart field 'image' or JSON/form field 'url'",
                    "spines": [],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if upload:
            temp_path = _write_upload_to_temp(upload)
        else:
            temp_path, err = _download_url_to_temp(url)
            if err or temp_path is None:
                return Response(
                    {
                        "ok": False,
                        "status": "download_failed",
                        "message": err or "Download failed",
                        "spines": [],
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        result = detect_spines(temp_path)
        photo = ShelfPhoto.objects.create(detection_ms=result.detection_ms)

        spines = []
        vlm_reads = 0
        if result.status == "ok" and result.boxes:
            spines = save_spines_for_photo(photo, temp_path, result.boxes)
            # Hosted VLM on crops (capped — Cursor agent-per-spine is slow).
            limit = int(settings.VLM_MAX_SPINES_PER_PHOTO)
            vlm_results = read_spines_for_photo(photo, limit=limit)
            vlm_reads = len(vlm_results)
            spines = list(photo.spines.all())

        http_status = status.HTTP_200_OK
        if result.status in {"unreadable_image", "model_load_failed", "timeout"}:
            http_status = status.HTTP_422_UNPROCESSABLE_ENTITY

        response = _detection_response(
            request, photo, result, spines, vlm_reads=vlm_reads
        )
        response.status_code = http_status
        return response
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
