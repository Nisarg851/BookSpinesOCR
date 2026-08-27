from rest_framework import serializers

from .models import (
    CatalogBook,
    DetectedSpine,
    LibraryEntry,
    MatchResult,
    ShelfPhoto,
)
from .vlm import extract_vlm_note


class CatalogBookSerializer(serializers.ModelSerializer):
    class Meta:
        model = CatalogBook
        fields = [
            "id",
            "title",
            "author",
            "alt_titles",
            "isbn13",
            "publisher",
            "year",
            "edition",
        ]


class MatchResultSerializer(serializers.ModelSerializer):
    catalog_book = CatalogBookSerializer(read_only=True)

    class Meta:
        model = MatchResult
        fields = [
            "id",
            "catalog_book",
            "confidence",
            "status",
        ]
        read_only_fields = fields


class DetectedSpineSerializer(serializers.ModelSerializer):
    crop_url = serializers.SerializerMethodField()
    vlm_note = serializers.SerializerMethodField()
    match = MatchResultSerializer(read_only=True)

    class Meta:
        model = DetectedSpine
        fields = [
            "id",
            "x1",
            "y1",
            "x2",
            "y2",
            "confidence",
            "crop_url",
            "vlm_status",
            "vlm_title",
            "vlm_author",
            "vlm_note",
            "match",
        ]
        read_only_fields = fields

    def get_crop_url(self, obj: DetectedSpine) -> str | None:
        if not obj.crop:
            return None
        request = self.context.get("request")
        url = obj.crop.url
        if request is not None:
            return request.build_absolute_uri(url)
        return url

    def get_vlm_note(self, obj: DetectedSpine) -> str:
        return extract_vlm_note(obj.vlm_raw_response, obj.vlm_status)


class ShelfPhotoDetailSerializer(serializers.ModelSerializer):
    spines = DetectedSpineSerializer(many=True, read_only=True)
    latency = serializers.SerializerMethodField()

    class Meta:
        model = ShelfPhoto
        fields = [
            "id",
            "uploaded_at",
            "detection_ms",
            "vlm_ms",
            "matching_ms",
            "latency",
            "spines",
        ]
        read_only_fields = fields

    def get_latency(self, obj: ShelfPhoto) -> dict:
        detection = obj.detection_ms or 0
        vlm = obj.vlm_ms or 0
        matching = obj.matching_ms or 0
        # Prefer wall-clock total from pipeline context when present.
        total = self.context.get("total_ms")
        if total is None:
            total = detection + vlm + matching
        return {
            "detection_ms": obj.detection_ms,
            "vlm_ms": obj.vlm_ms,
            "matching_ms": obj.matching_ms,
            "total_ms": total,
        }


class LibraryEntrySerializer(serializers.ModelSerializer):
    catalog_book = CatalogBookSerializer(read_only=True)
    crop_url = serializers.SerializerMethodField()

    class Meta:
        model = LibraryEntry
        fields = [
            "id",
            "title",
            "author",
            "catalog_book",
            "match_result",
            "crop_url",
            "created_at",
        ]
        read_only_fields = fields

    def get_crop_url(self, obj: LibraryEntry) -> str | None:
        match = obj.match_result
        if match is None or not getattr(match, "spine", None) or not match.spine.crop:
            return None
        request = self.context.get("request")
        url = match.spine.crop.url
        if request is not None:
            return request.build_absolute_uri(url)
        return url
