"""Scenario tests over the sample datasets — the automated redaction pipeline.

These exercise the full HTTP workflow (upload -> apply -> verify stored data)
for each sample file, with the LLM monkeypatched to canned regexes so the suite
runs deterministically in CI without an API key.

For each operation we assert two things on the committed data:
  1. the targeted PII pattern has **zero** residual matches in that column, and
  2. the replacement token is actually present.
"""

from __future__ import annotations

import pathlib

import pytest
import regex
from django.conf import settings
from rest_framework.test import APIClient

from datasets.services import storage
from transforms.services import llm

SAMPLE_DIR = pathlib.Path(settings.BASE_DIR) / "sample_data"

# Canonical PII patterns used both as the canned LLM output and the residual check.
EMAIL = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
PHONE = r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}"
CARD16 = r"\b\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{4}\b"
SSN = r"\b\d{3}-\d{2}-\d{4}\b"
MONEY = r"\$\d{1,3}(?:,\d{3})*(?:\.\d{2})?"
IP = r"\b(?:\d{1,3}\.){3}\d{1,3}\b"

# Maps a keyword in the NL description -> the regex the "LLM" should return.
_CANNED = [
    ("email", EMAIL),
    ("phone", PHONE),
    ("credit card", CARD16),
    ("social security", SSN),
    ("ip address", IP),
    ("dollar", MONEY),
    ("money", MONEY),
]

# Each op: (column, nl_description, replacement, residual_pattern_to_verify)
SCENARIOS = {
    "contacts.csv": [
        ("email", "find email addresses", "[EMAIL]", EMAIL),
        ("phone", "find phone numbers", "[PHONE]", PHONE),
        ("notes", "find email addresses", "[EMAIL]", EMAIL),
    ],
    "bank.csv": [
        ("email", "find email addresses", "[EMAIL]", EMAIL),
        ("phone", "find phone numbers", "[PHONE]", PHONE),
        ("card_number", "find 16 digit credit card numbers", "[CARD]", CARD16),
        ("ssn", "find US social security numbers", "[SSN]", SSN),
        ("balance", "find dollar money amounts", "[AMOUNT]", MONEY),
    ],
    "support_tickets.csv": [
        ("email", "find email addresses", "[EMAIL]", EMAIL),
        ("phone", "find phone numbers", "[PHONE]", PHONE),
        ("message", "find email addresses", "[EMAIL]", EMAIL),
        ("message", "find credit card numbers", "[CARD]", CARD16),
        ("message", "find dollar amounts of money", "[AMOUNT]", MONEY),
        ("internal_notes", "find ip addresses", "[IP]", IP),
        ("internal_notes", "find US social security numbers", "[SSN]", SSN),
    ],
}


def _fake_generate(description, samples=None):
    lowered = description.lower()
    for keyword, pattern in _CANNED:
        if keyword in lowered:
            return llm.RegexResult(regex=pattern, flags="", explanation="", confidence=0.9)
    raise AssertionError(f"no canned regex for description: {description!r}")


def _count_matches(series, pattern: str) -> int:
    compiled = regex.compile(pattern)
    return int(series.dropna().map(lambda v: bool(compiled.search(str(v)))).sum())


@pytest.fixture
def client():
    return APIClient()


@pytest.mark.parametrize("filename", list(SCENARIOS))
@pytest.mark.django_db
def test_redaction_scenario(client, monkeypatch, filename):
    monkeypatch.setattr(llm, "generate_regex", _fake_generate)

    path = SAMPLE_DIR / filename
    assert path.exists(), f"missing sample file {path}"

    with path.open("rb") as f:
        up = client.post("/api/uploads/", {"file": f}, format="multipart")
    assert up.status_code == 201, up.content
    dataset_id = up.json()["dataset"]["id"]

    ops = SCENARIOS[filename]
    for column, description, replacement, _ in ops:
        gen = client.post(
            "/api/regex/generate/",
            {"description": description, "dataset_id": dataset_id, "column": column},
            format="json",
        )
        assert gen.status_code == 200, gen.content
        body = {
            "column": column,
            "regex": gen.json()["regex"],
            "replacement": replacement,
            "description": description,
        }
        applied = client.post(f"/api/uploads/{dataset_id}/apply/", body, format="json")
        assert applied.status_code == 201, applied.content

    # Verify the committed data: every targeted pattern is fully redacted.
    df = storage.load_dataframe(dataset_id)
    for column, _description, replacement, residual in ops:
        remaining = _count_matches(df[column], residual)
        assert remaining == 0, f"{filename}:{column} still has {remaining} matches of {residual}"
        token_hits = int(df[column].astype(str).str.contains(regex.escape(replacement)).sum())
        assert token_hits > 0, f"{filename}:{column} has no '{replacement}' tokens"


@pytest.mark.django_db
def test_large_scenario_row_count(client, monkeypatch):
    """The large dataset is genuinely large (multi-column, 1000 rows)."""
    monkeypatch.setattr(llm, "generate_regex", _fake_generate)
    with (SAMPLE_DIR / "support_tickets.csv").open("rb") as f:
        up = client.post("/api/uploads/", {"file": f}, format="multipart")
    assert up.json()["dataset"]["row_count"] == 1000
    # PII spans at least four columns in this dataset.
    text_cols = up.json()["dataset"]["text_columns"]
    for col in ["email", "phone", "message", "internal_notes"]:
        assert col in text_cols
