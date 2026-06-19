"""Shared helpers for building before/after diffs of a column.

Used by both the regex replacement flow and the creative transforms so the
preview payload shape is identical across all transformation kinds.
"""

from __future__ import annotations

import pandas as pd

# Sentinel used so NaN == NaN compares equal when detecting changes.
_NA = "\x00__na__\x00"


def cell(value):
    """Render a single cell value JSON-safely (None for NaN/None)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return str(value)


def build_diffs(before: pd.Series, after: pd.Series) -> list[dict]:
    """Return [{row, before, after}] for every cell that changed."""
    changed_mask = before.fillna(_NA).astype(object) != after.fillna(_NA).astype(object)
    return [
        {
            "row": int(i),
            "before": cell(before.iloc[i]),
            "after": cell(after.iloc[i]),
        }
        for i in range(len(before))
        if bool(changed_mask.iloc[i])
    ]
