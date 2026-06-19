"""Reading uploaded files and exporting processed data.

This module is the single place that knows how to turn an uploaded CSV/Excel
file into a :class:`pandas.DataFrame`, how to describe its columns, and how to
serialize a DataFrame back out for download. Keeping it isolated means the rest
of the app never touches pandas I/O details directly.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import chardet
import pandas as pd

from config.exceptions import ValidationError

# Extensions we accept, mapped to the Dataset.FileType value.
SUPPORTED_EXTENSIONS = {
    ".csv": "csv",
    ".xlsx": "xlsx",
    ".xls": "xlsx",
}


@dataclass
class ParsedFile:
    """Result of parsing an upload: the data plus derived metadata."""

    dataframe: pd.DataFrame
    file_type: str
    columns: list[dict]
    row_count: int


def detect_file_type(filename: str) -> str:
    """Return the Dataset.FileType for *filename* or raise ValidationError."""
    lowered = filename.lower()
    for ext, file_type in SUPPORTED_EXTENSIONS.items():
        if lowered.endswith(ext):
            return file_type
    raise ValidationError(
        "Unsupported file type. Please upload a .csv, .xlsx, or .xls file."
    )


def _describe_columns(df: pd.DataFrame) -> list[dict]:
    """Build column metadata, flagging which columns are text-replaceable."""
    columns = []
    for name in df.columns:
        dtype = str(df[name].dtype)
        # object/string columns are the ones regex replacement can target.
        is_text = pd.api.types.is_object_dtype(df[name]) or pd.api.types.is_string_dtype(
            df[name]
        )
        columns.append({"name": str(name), "dtype": dtype, "is_text": bool(is_text)})
    return columns


def _read_csv(raw: bytes) -> pd.DataFrame:
    """Read CSV bytes, detecting encoding and falling back across delimiters."""
    detected = chardet.detect(raw[:100_000]) or {}
    encoding = detected.get("encoding") or "utf-8"
    try:
        # sep=None + engine="python" lets pandas sniff the delimiter.
        return pd.read_csv(io.BytesIO(raw), encoding=encoding, sep=None, engine="python")
    except UnicodeDecodeError:
        # Last-resort permissive decode.
        return pd.read_csv(io.BytesIO(raw), encoding="latin-1", sep=None, engine="python")
    except pd.errors.EmptyDataError as exc:
        raise ValidationError("The uploaded CSV file is empty.") from exc
    except Exception as exc:  # noqa: BLE001 - surface a clean parse error
        raise ValidationError(f"Could not parse CSV file: {exc}") from exc


def _read_excel(raw: bytes) -> pd.DataFrame:
    try:
        return pd.read_excel(io.BytesIO(raw), engine="openpyxl")
    except Exception as exc:  # noqa: BLE001
        raise ValidationError(f"Could not parse Excel file: {exc}") from exc


def parse_upload(filename: str, raw: bytes) -> ParsedFile:
    """Parse uploaded *raw* bytes into a ParsedFile, validating as we go."""
    if not raw:
        raise ValidationError("The uploaded file is empty.")

    file_type = detect_file_type(filename)
    df = _read_csv(raw) if file_type == "csv" else _read_excel(raw)

    if df.empty or len(df.columns) == 0:
        raise ValidationError("The uploaded file contains no data.")

    # Normalize column names to strings (Excel can yield ints/timestamps).
    df.columns = [str(c) for c in df.columns]

    return ParsedFile(
        dataframe=df,
        file_type=file_type,
        columns=_describe_columns(df),
        row_count=int(len(df)),
    )


def dataframe_to_bytes(df: pd.DataFrame, fmt: str) -> tuple[bytes, str]:
    """Serialize *df* to ``fmt`` ("csv" or "xlsx"). Returns (bytes, content_type)."""
    if fmt == "csv":
        return df.to_csv(index=False).encode("utf-8"), "text/csv"
    if fmt == "xlsx":
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df.to_excel(writer, index=False)
        return (
            buffer.getvalue(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    raise ValidationError("Unsupported download format. Use 'csv' or 'xlsx'.")
