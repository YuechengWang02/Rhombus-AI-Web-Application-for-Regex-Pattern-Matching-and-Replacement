"""LLM-driven creative transformations: date standardization & phone normalization.

Each transform is a two-stage operation that mirrors the regex flow:

  1. The LLM turns a natural-language instruction (+ column samples) into a small
     structured *spec* (see ``llm.infer_date_spec`` / ``llm.infer_phone_spec``).
  2. This module applies that spec **deterministically** with pandas, so the
     actual data mutation is predictable and testable (the LLM never touches the
     cell values directly).

The spec can also be supplied explicitly by the caller to skip/override the LLM.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd

from config.exceptions import ValidationError

# Sentinel matching diffing._NA so NaN compares equal when counting changes.
_NA = "\x00__na__\x00"


@dataclass
class ColumnResult:
    """Outcome of a creative transform on one column."""

    new_series: pd.Series
    changed_count: int
    info: dict = field(default_factory=dict)


def _count_changes(before: pd.Series, after: pd.Series) -> int:
    mask = before.fillna(_NA).astype(object) != after.fillna(_NA).astype(object)
    return int(mask.sum())


# --- Date standardization -----------------------------------------------------

DEFAULT_DATE_SPEC = {"dayfirst": False, "target_format": "%Y-%m-%d"}


def apply_dates(series: pd.Series, spec: dict) -> ColumnResult:
    """Parse mixed-format dates and reformat them to ``spec['target_format']``.

    Unparseable values are left unchanged so the transform is non-destructive.
    """
    target_format = spec.get("target_format") or "%Y-%m-%d"
    dayfirst = bool(spec.get("dayfirst", False))

    parsed = pd.to_datetime(
        series, errors="coerce", dayfirst=dayfirst, format="mixed"
    )
    formatted = parsed.dt.strftime(target_format)
    # Keep the original value wherever parsing failed (NaT).
    new_series = formatted.where(parsed.notna(), series)

    return ColumnResult(
        new_series=new_series,
        changed_count=_count_changes(series, new_series),
        info={
            "parsed": int(parsed.notna().sum()),
            "unparsed": int(parsed.isna().sum() - series.isna().sum()),
            "target_format": target_format,
            "dayfirst": dayfirst,
        },
    )


# --- Phone normalization ------------------------------------------------------

# Default: clean, area-code-aware national formatting that does NOT assume a
# country code (numbers may come from anywhere). Explicit formats (e164/dashes/
# parens) remain available via the spec.
DEFAULT_PHONE_SPEC = {"target_format": "national", "default_country_code": "1"}


def _group_national(digits: str) -> str:
    """Format a bare national number with spaces (area code preserved)."""
    if len(digits) == 11 and digits[0] == "1":
        digits = digits[1:]  # drop a domestic NANP trunk/country '1'
    if len(digits) == 10:  # has an area code
        return f"{digits[:3]} {digits[3:6]} {digits[6:]}"
    if len(digits) == 7:  # local number, no area code
        return f"{digits[:3]} {digits[3:]}"
    return digits  # unknown length: just stripped of punctuation/brackets


def _format_national(value):
    """Clean a phone number: strip brackets/punctuation, keep the area code,
    space the groups, and only retain a country code if the original had one.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return value
    text = str(value)
    digits = re.sub(r"\D", "", text)
    if not digits:
        return value  # nothing phone-like; leave as-is

    if text.lstrip().startswith("+"):
        # Keep the international country code the user provided.
        if len(digits) > 10:
            cc, national = digits[:-10], digits[-10:]
            return f"+{cc} {_group_national(national)}"
        return "+" + digits
    return _group_national(digits)


def _normalize_phone(value, target_format: str, country_code: str):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return value
    text = str(value)
    digits = re.sub(r"\D", "", text)
    if not digits:
        return value  # no phone content; leave as-is

    if text.lstrip().startswith("+"):
        full = digits  # already includes the country code
    else:
        full = country_code + digits

    national = full[len(country_code):] if full.startswith(country_code) else full

    if target_format == "e164":
        return "+" + full
    # National formats only make clean sense for 10-digit (NANP) numbers;
    # otherwise fall back to E.164 to avoid mangling international numbers.
    if len(national) == 10:
        area, mid, last = national[:3], national[3:6], national[6:]
        if target_format == "dashes":
            return f"{area}-{mid}-{last}"
        if target_format == "parens":
            return f"({area}) {mid}-{last}"
    return "+" + full


def apply_phones(series: pd.Series, spec: dict) -> ColumnResult:
    """Normalize phone numbers per *spec*.

    ``national`` (default) cleans formatting, preserves the area code, and never
    invents a country code. ``e164``/``dashes``/``parens`` are explicit formats
    that do use ``default_country_code``.
    """
    target_format = (spec.get("target_format") or "national").lower()
    if target_format not in {"national", "e164", "dashes", "parens"}:
        raise ValidationError(
            "Invalid phone target_format. Use 'national', 'e164', 'dashes', or 'parens'."
        )
    country_code = "".join(
        c for c in str(spec.get("default_country_code") or "1") if c.isdigit()
    ) or "1"

    if target_format == "national":
        new_series = series.map(_format_national)
    else:
        new_series = series.map(
            lambda v: _normalize_phone(v, target_format, country_code)
        )
    return ColumnResult(
        new_series=new_series,
        changed_count=_count_changes(series, new_series),
        info={"target_format": target_format, "default_country_code": country_code},
    )


# --- Dispatch -----------------------------------------------------------------

APPLIERS = {
    "dates": apply_dates,
    "phones": apply_phones,
}


def apply(kind: str, series: pd.Series, spec: dict) -> ColumnResult:
    """Apply a creative transform by kind ("dates" | "phones")."""
    try:
        return APPLIERS[kind](series, spec)
    except KeyError as exc:
        raise ValidationError(f"Unknown transform kind: {kind!r}.") from exc
