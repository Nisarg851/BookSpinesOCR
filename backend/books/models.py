from django.db import models


class CatalogBook(models.Model):
    """One row from catalog.csv. PK matches the CSV `id` for stable upserts."""

    id = models.PositiveIntegerField(primary_key=True)
    title = models.CharField(max_length=512)
    author = models.CharField(max_length=512)
    alt_titles = models.TextField(blank=True, default="")
    isbn13 = models.CharField(max_length=13, blank=True, default="")
    publisher = models.CharField(max_length=512, blank=True, default="")
    year = models.IntegerField(null=True, blank=True)
    edition = models.CharField(max_length=256, blank=True, default="")

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.title} — {self.author}"


class ShelfPhoto(models.Model):
    """Uploaded bookshelf photo plus measured pipeline stage latencies."""

    image = models.ImageField(upload_to="shelf_photos/", blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    detection_ms = models.PositiveIntegerField(null=True, blank=True)
    vlm_ms = models.PositiveIntegerField(null=True, blank=True)
    matching_ms = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self) -> str:
        return f"ShelfPhoto {self.pk} @ {self.uploaded_at:%Y-%m-%d %H:%M}"


class DetectedSpine(models.Model):
    """One book spine found in a ShelfPhoto by the local detection model."""

    class VlmStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        OK = "OK", "OK"
        UNREADABLE = "UNREADABLE", "Unreadable"

    photo = models.ForeignKey(
        ShelfPhoto,
        on_delete=models.CASCADE,
        related_name="spines",
    )
    # Bounding box in image pixel coords (left, top, right, bottom).
    x1 = models.FloatField()
    y1 = models.FloatField()
    x2 = models.FloatField()
    y2 = models.FloatField()
    crop = models.ImageField(upload_to="crops/", blank=True)
    confidence = models.FloatField(default=0.0)
    # Filled later by the hosted VLM.
    vlm_status = models.CharField(
        max_length=16,
        choices=VlmStatus.choices,
        default=VlmStatus.PENDING,
    )
    vlm_title = models.CharField(max_length=512, blank=True, default="")
    vlm_author = models.CharField(max_length=512, blank=True, default="")
    vlm_raw_response = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        label = self.vlm_title or f"spine@{self.x1:.0f},{self.y1:.0f}"
        return f"DetectedSpine {self.pk}: {label}"


class MatchResult(models.Model):
    """Fuzzy-match outcome for one DetectedSpine against the catalog."""

    class Status(models.TextChoices):
        PENDING_REVIEW = "PENDING_REVIEW", "Pending review"
        AUTO_ACCEPTED = "AUTO_ACCEPTED", "Auto-accepted"
        CONFIRMED = "CONFIRMED", "Confirmed"
        CORRECTED = "CORRECTED", "Corrected"
        DISCARDED = "DISCARDED", "Discarded"

    spine = models.OneToOneField(
        DetectedSpine,
        on_delete=models.CASCADE,
        related_name="match",
    )
    catalog_book = models.ForeignKey(
        CatalogBook,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="matches",
    )
    confidence = models.FloatField()
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.PENDING_REVIEW,
    )

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        book = self.catalog_book or "no match"
        return f"MatchResult {self.pk}: {book} ({self.confidence:.2f}, {self.status})"


class LibraryEntry(models.Model):
    """User's confirmed library row (single implicit user for this exercise)."""

    title = models.CharField(max_length=512)
    author = models.CharField(max_length=512)
    catalog_book = models.ForeignKey(
        CatalogBook,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="library_entries",
    )
    match_result = models.OneToOneField(
        MatchResult,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="library_entry",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "library entries"

    def __str__(self) -> str:
        return f"{self.title} — {self.author}"
