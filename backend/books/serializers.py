from rest_framework import serializers

from .models import (
    CatalogBook,
    DetectedSpine,
    LibraryEntry,
    MatchResult,
    ShelfPhoto,
)


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


class ShelfPhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShelfPhoto
        fields = [
            "id",
            "image",
            "uploaded_at",
            "detection_ms",
            "vlm_ms",
            "matching_ms",
        ]
        read_only_fields = [
            "id",
            "uploaded_at",
            "detection_ms",
            "vlm_ms",
            "matching_ms",
        ]


class DetectedSpineSerializer(serializers.ModelSerializer):
    class Meta:
        model = DetectedSpine
        fields = [
            "id",
            "photo",
            "x1",
            "y1",
            "x2",
            "y2",
            "crop",
            "vlm_title",
            "vlm_author",
            "vlm_raw_response",
        ]
        read_only_fields = fields


class MatchResultSerializer(serializers.ModelSerializer):
    catalog_book = CatalogBookSerializer(read_only=True)

    class Meta:
        model = MatchResult
        fields = [
            "id",
            "spine",
            "catalog_book",
            "confidence",
            "status",
        ]
        read_only_fields = fields


class LibraryEntrySerializer(serializers.ModelSerializer):
    catalog_book = CatalogBookSerializer(read_only=True)

    class Meta:
        model = LibraryEntry
        fields = [
            "id",
            "title",
            "author",
            "catalog_book",
            "match_result",
            "created_at",
        ]
        read_only_fields = fields
