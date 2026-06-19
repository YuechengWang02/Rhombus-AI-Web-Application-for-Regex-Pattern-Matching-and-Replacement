"""Persistence for uploaded datasets.

A :class:`Dataset` row stores *metadata only*; the actual tabular data lives in
a parquet file on disk (path in :attr:`Dataset.storage_path`), keyed by the
dataset's UUID. This keeps the DB small and makes large files cheap to re-read.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


def _default_expiry():
    return timezone.now() + timedelta(hours=settings.UPLOAD_TTL_HOURS)


class Dataset(models.Model):
    """Metadata describing one uploaded CSV/Excel file."""

    class FileType(models.TextChoices):
        CSV = "csv", "CSV"
        XLSX = "xlsx", "Excel"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    original_filename = models.CharField(max_length=255)
    file_type = models.CharField(max_length=8, choices=FileType.choices)
    row_count = models.PositiveIntegerField()
    # List of {"name": str, "dtype": str, "is_text": bool} describing each column.
    columns = models.JSONField(default=list)
    # Absolute path to the parquet snapshot of the (possibly transformed) data.
    storage_path = models.CharField(max_length=512)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=_default_expiry)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.original_filename} ({self.id})"

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def text_columns(self) -> list[str]:
        """Names of columns eligible for regex replacement (text/object)."""
        return [c["name"] for c in self.columns if c.get("is_text")]
