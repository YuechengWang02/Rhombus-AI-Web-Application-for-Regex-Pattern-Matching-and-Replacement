"""Serializers + JSON-safe row paging for the datasets app."""

from __future__ import annotations

import json

import pandas as pd
from rest_framework import serializers

from .models import Dataset


class DatasetSerializer(serializers.ModelSerializer):
    """Metadata view of a dataset (no row data)."""

    text_columns = serializers.ListField(child=serializers.CharField(), read_only=True)

    class Meta:
        model = Dataset
        fields = [
            "id",
            "original_filename",
            "file_type",
            "row_count",
            "columns",
            "text_columns",
            "created_at",
            "expires_at",
        ]


def page_rows(df: pd.DataFrame, page: int, size: int) -> dict:
    """Return a JSON-safe page of rows plus pagination metadata.

    ``to_json`` is used to coerce NaN -> null and numpy scalars -> native types
    reliably, avoiding manual per-cell conversion.
    """
    page = max(page, 1)
    size = max(min(size, 500), 1)  # clamp page size to a sane range
    total = len(df)
    start = (page - 1) * size
    end = start + size

    window = df.iloc[start:end]
    records = json.loads(window.to_json(orient="records", date_format="iso"))

    return {
        "rows": records,
        "page": page,
        "size": size,
        "total_rows": total,
        "total_pages": (total + size - 1) // size if size else 0,
    }
