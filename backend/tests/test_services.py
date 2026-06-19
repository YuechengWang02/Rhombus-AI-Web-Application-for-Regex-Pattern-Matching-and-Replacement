"""Unit tests for the pure service layer (no DB / HTTP)."""

import pandas as pd
import pytest

from config.exceptions import UnprocessableError, ValidationError
from datasets.services import file_io
from transforms.services import regex_engine


def test_parse_csv_infers_columns():
    raw = b"ID,Name,Email\n1,John,john@example.com\n2,Jane,jane@x.com\n"
    parsed = file_io.parse_upload("data.csv", raw)
    assert parsed.file_type == "csv"
    assert parsed.row_count == 2
    names = [c["name"] for c in parsed.columns]
    assert names == ["ID", "Name", "Email"]
    # Email column is text -> eligible for replacement.
    email_col = next(c for c in parsed.columns if c["name"] == "Email")
    assert email_col["is_text"] is True


def test_parse_rejects_unknown_extension():
    with pytest.raises(ValidationError):
        file_io.parse_upload("data.txt", b"a,b\n1,2\n")


def test_parse_rejects_empty():
    with pytest.raises(ValidationError):
        file_io.parse_upload("data.csv", b"")


def test_apply_replacement_counts_matches():
    series = pd.Series(["john@example.com", "no-email-here", "a@b.co"])
    result = regex_engine.apply_replacement(
        series,
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,7}\b",
        "REDACTED",
    )
    assert result.match_count == 2
    assert result.changed_count == 2
    assert result.new_series.tolist() == ["REDACTED", "no-email-here", "REDACTED"]


def test_invalid_regex_raises():
    with pytest.raises(UnprocessableError):
        regex_engine.compile_pattern("([")


def test_replacement_preserves_nan():
    series = pd.Series(["x1x", None, "x2x"])
    result = regex_engine.apply_replacement(series, r"\d", "#")
    assert result.new_series.iloc[0] == "x#x"
    assert pd.isna(result.new_series.iloc[1])
