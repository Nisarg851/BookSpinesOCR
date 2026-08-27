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
            "uploaded_at",
            "detection_ms",
            "vlm_ms",
            "matching_ms",
        ]
        read_only_fields = fields


class DetectedSpineSerializer(serializers.ModelSerializer):
    crop_url = serializers.SerializerMethodField()

    class Meta:
        model = DetectedSpine
        fields = [
            "id",
            "photo",
            "x1",
            "y1",
            "x2",
            "y2",
            "confidence",
            "crop",
            "crop_url",
            "vlm_title",
            "vlm_author",
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
