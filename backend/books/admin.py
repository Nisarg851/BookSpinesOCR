from django.contrib import admin

from .models import (
    CatalogBook,
    DetectedSpine,
    LibraryEntry,
    MatchResult,
    ShelfPhoto,
)


@admin.register(CatalogBook)
class CatalogBookAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "author", "year", "edition", "isbn13")
    search_fields = ("title", "author", "alt_titles", "isbn13")
    list_filter = ("year",)


class DetectedSpineInline(admin.TabularInline):
    model = DetectedSpine
    extra = 0
    fields = (
        "x1",
        "y1",
        "x2",
        "y2",
        "crop",
        "vlm_title",
        "vlm_author",
    )
    readonly_fields = ("vlm_raw_response",)


@admin.register(ShelfPhoto)
class ShelfPhotoAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "uploaded_at",
        "detection_ms",
        "vlm_ms",
        "matching_ms",
    )
    readonly_fields = ("uploaded_at",)
    inlines = [DetectedSpineInline]


@admin.register(DetectedSpine)
class DetectedSpineAdmin(admin.ModelAdmin):
    list_display = ("id", "photo", "vlm_title", "vlm_author", "x1", "y1", "x2", "y2")
    search_fields = ("vlm_title", "vlm_author")
    raw_id_fields = ("photo",)


@admin.register(MatchResult)
class MatchResultAdmin(admin.ModelAdmin):
    list_display = ("id", "spine", "catalog_book", "confidence", "status")
    list_filter = ("status",)
    raw_id_fields = ("spine", "catalog_book")


@admin.register(LibraryEntry)
class LibraryEntryAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "author", "catalog_book", "created_at")
    search_fields = ("title", "author")
    raw_id_fields = ("catalog_book", "match_result")
    readonly_fields = ("created_at",)
