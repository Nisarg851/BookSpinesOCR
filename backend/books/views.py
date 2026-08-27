import tempfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.core.files.uploadedfile import UploadedFile
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from .models import CatalogBook, DetectedSpine, LibraryEntry, ShelfPhoto
from .pipeline import confirm_spine, process_photo_image
from .serializers import (
    CatalogBookSerializer,
    LibraryEntrySerializer,
    ShelfPhotoDetailSerializer,
)

MAX_DOWNLOAD_BYTES = 15 * 1024 * 1024


@api_view(["GET"])
def health(request):
    """Placeholder so the Expo app can confirm it reaches Django."""
    return Response({"status": "ok", "service": "book-spines-ocr"})


class CatalogBookList(generics.ListAPIView):
    queryset = CatalogBook.objects.all()
    serializer_class = CatalogBookSerializer


class LibraryEntryList(generics.ListAPIView):
    """Confirmed library for the single implicit user."""

    queryset = LibraryEntry.objects.select_related(
        "catalog_book",
        "match_result",
        "match_result__spine",
    ).all()
    serializer_class = LibraryEntrySerializer


def _write_upload_to_temp(upload: UploadedFile) -> Path:
    suffix = Path(upload.name or "upload.jpg").suffix or ".jpg"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    for chunk in upload.chunks():
        tmp.write(chunk)
    tmp.close()
    return Path(tmp.name)


def _download_url_to_temp(url: str) -> tuple[Path | None, str | None]:
    from urllib.parse import urlparse

    raw = (url or "").strip()
    if not raw:
        return None, "Image URL is empty"
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        return None, "Image URL must start with http:// or https://"
    if not parsed.netloc:
        return None, "Image URL is missing a host (e.g. https://example.com/shelf.jpg)"

    try:
        req = Request(raw, headers={"User-Agent": "BookSpinesOCR/0.1"})
        with urlopen(req, timeout=20) as resp:
            content_type = (resp.headers.get("Content-Type") or "").lower()
            if content_type and not content_type.startswith("image/"):
                return None, (
                    f"URL did not return an image (Content-Type: {content_type}). "
                    "Use a direct link to a .jpg/.png/.webp file."
                )
            data = resp.read(MAX_DOWNLOAD_BYTES + 1)
    except HTTPError as exc:
        if exc.code == 403:
            return None, (
                "Download forbidden (HTTP 403) — the host blocked this request "
                "(hotlink protection or private URL)."
            )
        if exc.code == 401:
            return None, "Download unauthorized (HTTP 401) — this image URL requires login."
        if exc.code == 404:
            return None, "Image URL not found (HTTP 404)."
        return None, f"Could not download image URL (HTTP {exc.code})."
    except TimeoutError:
        return None, "Timed out downloading the image URL (20s limit)."
    except URLError as exc:
        reason = str(getattr(exc, "reason", exc) or exc)
        lower = reason.lower()
        if "getaddrinfo" in lower or "name or service not known" in lower or "nodename" in lower:
            return None, f"Could not resolve host for that URL ({parsed.netloc})."
        if "certificate" in lower or "ssl" in lower:
            return None, f"TLS/SSL error downloading the image: {reason}"
        return None, f"Network error downloading the image: {reason}"
    except ValueError as exc:
        return None, f"Invalid image URL: {exc}"

    if len(data) > MAX_DOWNLOAD_BYTES:
        return None, "Image URL exceeds 15MB limit"
    if not data:
        return None, "Image URL returned an empty body"

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
    tmp.write(data)
    tmp.close()
    return Path(tmp.name), None


def _photo_response(request, photo: ShelfPhoto, *, total_ms: int | None = None, extra=None):
    photo = (
        ShelfPhoto.objects.filter(pk=photo.pk)
        .prefetch_related("spines__match__catalog_book")
        .get()
    )
    data = ShelfPhotoDetailSerializer(
        photo,
        context={"request": request, "total_ms": total_ms},
    ).data
    payload = {
        "ok": True,
        "photo": data,
        "photo_id": photo.id,
        "spines": data["spines"],
        "latency": data["latency"],
        "message": (
            f"{len(data['spines'])} spine(s)"
            if data["spines"]
            else "No book spines detected"
        ),
    }
    if extra:
        payload.update(extra)
    return Response(payload)


@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def photo_create(request):
    """
    Upload (or URL) a bookshelf photo and run detect → VLM → match synchronously.

    Zero spines / failed VLMs still return HTTP 200 with an empty or partial
    spine list — never a blank 500 for those cases.
    """
    temp_path: Path | None = None
    try:
        upload = request.FILES.get("image") or request.FILES.get("photo")
        url = (request.data.get("url") or "").strip()

        if upload and url:
            return Response(
                {
                    "ok": False,
                    "message": "Send either an image file or a url, not both",
                    "spines": [],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not upload and not url:
            return Response(
                {
                    "ok": False,
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
                        "message": err or "Download failed",
                        "spines": [],
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        try:
            result = process_photo_image(temp_path)
        except Exception as exc:
            return Response(
                {
                    "ok": False,
                    "message": f"Photo processing failed unexpectedly: {exc}",
                    "spines": [],
                    "detection_status": "pipeline_error",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        det = result.detection

        # Corrupt image / model failure → 422 with structured body.
        # Zero detections → 200 (valid empty result).
        http_status = status.HTTP_200_OK
        if det.status in {"unreadable_image", "model_load_failed", "timeout"}:
            http_status = status.HTTP_422_UNPROCESSABLE_ENTITY

        response = _photo_response(
            request,
            result.photo,
            total_ms=result.total_ms,
            extra={
                "detection_status": det.status,
                "detection_message": det.message,
                "zero_detections": det.status == "zero_detections"
                or len(result.spines) == 0,
            },
        )
        response.status_code = http_status
        if det.status in {"unreadable_image", "model_load_failed", "timeout"}:
            response.data["ok"] = False
            response.data["message"] = det.message or det.status
        return response
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


@api_view(["GET"])
def photo_detail(request, photo_id: int):
    photo = get_object_or_404(ShelfPhoto, pk=photo_id)
    return _photo_response(request, photo)


@api_view(["POST"])
@parser_classes([JSONParser, FormParser])
def spine_confirm(request, spine_id: int):
    spine = get_object_or_404(
        DetectedSpine.objects.select_related("match", "match__catalog_book"),
        pk=spine_id,
    )
    action = request.data.get("action")
    catalog_book_id = request.data.get("catalog_book_id")
    title = request.data.get("title")
    author = request.data.get("author")
    try:
        catalog_book_id_int = (
            int(catalog_book_id) if catalog_book_id is not None else None
        )
    except (TypeError, ValueError):
        return Response(
            {"ok": False, "message": "catalog_book_id must be an integer"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        match, entry = confirm_spine(
            spine,
            action=action,
            catalog_book_id=catalog_book_id_int,
            title=title,
            author=author,
        )
    except ValueError as exc:
        return Response(
            {"ok": False, "message": str(exc)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    payload = {
        "ok": True,
        "match": {
            "id": match.id,
            "status": match.status,
            "confidence": match.confidence,
            "catalog_book_id": match.catalog_book_id,
        },
        "library_entry": None,
    }
    if entry is not None:
        payload["library_entry"] = LibraryEntrySerializer(entry).data
    return Response(payload)


# Back-compat alias used by earlier Expo builds.
detect_books = photo_create
