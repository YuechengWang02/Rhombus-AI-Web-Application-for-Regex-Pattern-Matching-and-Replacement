"""History of replacement operations applied to a dataset.

Each committed replacement creates a :class:`Transformation` row, giving an
audit trail and enabling single-step undo of the most recent change.
"""

from __future__ import annotations

import uuid

from django.db import models

from datasets.models import Dataset


class Transformation(models.Model):
    """One committed transformation on a dataset column.

    Covers both regex find-and-replace and the LLM-driven creative transforms
    (date standardization, phone normalization). ``kind`` disambiguates, and
    ``params`` stores the structured spec used for the non-regex kinds.
    """

    class Kind(models.TextChoices):
        REGEX = "regex", "Regex replacement"
        DATES = "dates", "Date standardization"
        PHONES = "phones", "Phone normalization"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dataset = models.ForeignKey(
        Dataset, related_name="transformations", on_delete=models.CASCADE
    )
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.REGEX)
    column = models.CharField(max_length=255)
    nl_description = models.TextField(blank=True)
    # Regex-specific fields (blank for creative transforms).
    regex_pattern = models.TextField(blank=True)
    flags = models.CharField(max_length=8, blank=True)
    replacement = models.TextField(blank=True)
    # Structured spec for creative transforms (e.g. target date/phone format).
    params = models.JSONField(default=dict, blank=True)
    match_count = models.PositiveIntegerField(default=0)
    is_undone = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.column}: /{self.regex_pattern}/ -> {self.replacement!r}"
