"""End-to-end API tests covering the upload -> generate -> apply -> undo flow.

The LLM call is monkeypatched so the suite runs without an API key.
"""

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from transforms.services import llm

SAMPLE_CSV = (
    "ID,Name,Email\n"
    "1,John Doe,john.doe@example.com\n"
    "2,Jane Smith,jane_smith@domain.com\n"
    "3,Alice Brown,alice.brown@website.org\n"
)
EMAIL_REGEX = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,7}\b"


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def uploaded(client):
    upload = SimpleUploadedFile("people.csv", SAMPLE_CSV.encode(), content_type="text/csv")
    resp = client.post("/api/uploads/", {"file": upload}, format="multipart")
    assert resp.status_code == 201, resp.content
    return resp.json()


@pytest.mark.django_db
def test_upload_returns_metadata_and_rows(uploaded):
    assert uploaded["dataset"]["row_count"] == 3
    assert "Email" in uploaded["dataset"]["text_columns"]
    assert len(uploaded["rows"]) == 3
    assert uploaded["rows"][0]["Email"] == "john.doe@example.com"


@pytest.mark.django_db
def test_generate_regex_mocked(client, monkeypatch):
    monkeypatch.setattr(
        llm,
        "generate_regex",
        lambda description, samples=None: llm.RegexResult(
            regex=EMAIL_REGEX, flags="", explanation="emails", confidence=0.95
        ),
    )
    resp = client.post(
        "/api/regex/generate/",
        {"description": "find email addresses"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    assert resp.json()["regex"] == EMAIL_REGEX


@pytest.mark.django_db
def test_preview_apply_download_undo(client, uploaded):
    dataset_id = uploaded["dataset"]["id"]
    payload = {"column": "Email", "regex": EMAIL_REGEX, "replacement": "REDACTED"}

    # Preview should report 3 changed rows without mutating data.
    preview = client.post(f"/api/uploads/{dataset_id}/preview/", payload, format="json")
    assert preview.status_code == 200, preview.content
    assert preview.json()["match_count"] == 3
    assert preview.json()["total_changed"] == 3

    # Apply commits the change.
    applied = client.post(f"/api/uploads/{dataset_id}/apply/", payload, format="json")
    assert applied.status_code == 201, applied.content
    assert all(r["Email"] == "REDACTED" for r in applied.json()["rows"])
    transform_id = applied.json()["transformation"]["id"]

    # Download reflects the applied change.
    dl = client.get(f"/api/uploads/{dataset_id}/download/?format=csv")
    assert dl.status_code == 200
    assert b"REDACTED" in dl.content
    assert b"john.doe@example.com" not in dl.content

    # Undo restores the original emails.
    undo = client.post(
        f"/api/uploads/{dataset_id}/transforms/{transform_id}/undo/", format="json"
    )
    assert undo.status_code == 200, undo.content
    assert undo.json()["rows"][0]["Email"] == "john.doe@example.com"


@pytest.mark.django_db
def test_apply_rejects_non_text_column(client, uploaded):
    dataset_id = uploaded["dataset"]["id"]
    resp = client.post(
        f"/api/uploads/{dataset_id}/apply/",
        {"column": "ID", "regex": r"\d", "replacement": "X"},
        format="json",
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "validation_error"
