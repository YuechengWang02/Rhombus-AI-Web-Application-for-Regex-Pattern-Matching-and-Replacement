"""Safe regex compilation and replacement over pandas columns.

The third-party ``regex`` module is used instead of the stdlib ``re`` because it
supports a per-call ``timeout`` — our primary defense against catastrophic
backtracking (ReDoS) on attacker-influenced patterns. Each cell substitution is
bounded by ``settings.REGEX_TIMEOUT_SECONDS``.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import regex
from django.conf import settings

from config.exceptions import UnprocessableError

# Supported inline flag letters -> regex module flag constants.
_FLAG_MAP = {
    "i": regex.IGNORECASE,
    "m": regex.MULTILINE,
    "s": regex.DOTALL,
    "x": regex.VERBOSE,
}


def _build_flags(flags: str | None) -> int:
    value = 0
    for ch in (flags or "").lower():
        if ch in _FLAG_MAP:
            value |= _FLAG_MAP[ch]
    return value


def compile_pattern(pattern: str, flags: str | None = None):
    """Compile *pattern* or raise UnprocessableError with a readable message."""
    if not pattern:
        raise UnprocessableError("The regex pattern is empty.")
    try:
        return regex.compile(pattern, _build_flags(flags))
    except regex.error as exc:
        raise UnprocessableError(f"Invalid regex pattern: {exc}") from exc


@dataclass
class ReplacementResult:
    """Outcome of applying a replacement to a single column."""

    new_series: pd.Series
    match_count: int
    changed_count: int


def apply_replacement(
    series: pd.Series,
    pattern: str,
    replacement: str,
    flags: str | None = None,
    timeout: float | None = None,
) -> ReplacementResult:
    """Apply ``pattern`` -> ``replacement`` to every cell of *series*.

    Uses ``subn`` per cell so we get the exact number of substitutions, and a
    per-cell timeout to guard against pathological patterns. NaN/None cells are
    left untouched.
    """
    compiled = compile_pattern(pattern, flags)
    timeout = settings.REGEX_TIMEOUT_SECONDS if timeout is None else timeout

    total_matches = 0
    changed = 0

    def _replace_cell(value):
        nonlocal total_matches, changed
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return value
        text = str(value)
        try:
            new_text, count = compiled.subn(replacement, text, timeout=timeout)
        except TimeoutError as exc:
            raise UnprocessableError(
                "The regex took too long to evaluate and was stopped "
                "(possible catastrophic backtracking). Try a simpler pattern."
            ) from exc
        if count:
            total_matches += count
            if new_text != text:
                changed += 1
        return new_text

    new_series = series.map(_replace_cell)
    return ReplacementResult(
        new_series=new_series,
        match_count=total_matches,
        changed_count=changed,
    )


def find_sample_matches(
    values: list[str], pattern: str, flags: str | None = None, limit: int = 5
) -> list[str]:
    """Return up to *limit* example substrings matched by *pattern*.

    Used to give the user concrete evidence of what a generated regex matches.
    """
    compiled = compile_pattern(pattern, flags)
    timeout = settings.REGEX_TIMEOUT_SECONDS
    samples: list[str] = []
    for value in values:
        if value is None:
            continue
        try:
            for match in compiled.finditer(str(value), timeout=timeout):
                samples.append(match.group(0))
                if len(samples) >= limit:
                    return samples
        except TimeoutError:
            break
    return samples
