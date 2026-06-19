"""Tests for the LLM-driven creative transforms (dates + phones).

API tests pass an explicit ``params`` spec so they exercise the full HTTP flow
without calling the LLM; a separate test monkeypatches the inferer to confirm
the LLM path is wired up.
"""

import pandas as pd
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from transforms.services import creative, llm

DATES_CSV = "id,d\n1,01/02/2020\n2,2020-03-04\n3,13/05/2021\n"
PHONES_CSV = "id,phone\n1,(555) 123-4567\n2,555.123.4567\n3,+44 20 7946 0958\n"


# --- Service-level tests ------------------------------------------------------

def test_apply_dates_dayfirst():
    series = pd.Series(["01/02/2020", "2020-03-04", "13/05/2021"])
    result = creative.apply_dates(series, {"target_format": "%Y-%m-%d", "dayfirst": True})
    assert result.new_series.tolist() == ["2020-02-01", "2020-03-04", "2021-05-13"]
    assert result.info["parsed"] == 3


def test_apply_dates_leaves_unparseable():
    series = pd.Series(["not a date", "2020-01-01"])
    result = creative.apply_dates(series, creative.DEFAULT_DATE_SPEC)
    assert result.new_series.iloc[0] == "not a date"
    assert result.new_series.iloc[1] == "2020-01-01"
    assert result.changed_count == 0


def test_apply_phones_national_is_default():
    """Default 'national' keeps the area code, spaces groups, and never adds +1."""
    series = pd.Series(
        ["(555) 123-4567", "555.123.4567", "1-415-555-0132", "123-4567", "+44 20 7946 0958"]
    )
    out = creative.apply_phones(series, {})  # no target_format -> national default
    assert out.new_series.tolist() == [
        "555 123 4567",   # brackets removed, area code kept, spaced
        "555 123 4567",   # dots removed
        "415 555 0132",   # leading domestic '1' dropped, no forced +1
        "123 4567",       # 7-digit local: just the number, no area code
        "+44 207 946 0958",  # explicit '+' country code preserved
    ]


def test_apply_phones_explicit_formats():
    series = pd.Series(["(555) 123-4567", "555.123.4567", "+44 20 7946 0958"])
    e164 = creative.apply_phones(series, {"target_format": "e164", "default_country_code": "1"})
    assert e164.new_series.tolist() == [
        "+15551234567",
        "+15551234567",
        "+442079460958",
    ]
    dashes = creative.apply_phones(series, {"target_format": "dashes", "default_country_code": "1"})
    assert dashes.new_series.iloc[0] == "555-123-4567"


# --- API-level tests ----------------------------------------------------------

@pytest.fixture
def client():
    return APIClient()


def _upload(client, name, content):
    up = SimpleUploadedFile(name, content.encode(), content_type="text/csv")
    resp = client.post("/api/uploads/", {"file": up}, format="multipart")
    assert resp.status_code == 201, resp.content
    return resp.json()["dataset"]["id"]


@pytest.mark.django_db
def test_dates_preview_and_apply_with_params(client):
    dataset_id = _upload(client, "dates.csv", DATES_CSV)
    body = {"columns": ["d"], "params": {"target_format": "%Y-%m-%d", "dayfirst": True}}

    preview = client.post(
        f"/api/uploads/{dataset_id}/transform/dates/preview/", body, format="json"
    )
    assert preview.status_code == 200, preview.content
    assert preview.json()["changed_count"] >= 2

    applied = client.post(
        f"/api/uploads/{dataset_id}/transform/dates/apply/", body, format="json"
    )
    assert applied.status_code == 201, applied.content
    values = [r["d"] for r in applied.json()["rows"]]
    assert values == ["2020-02-01", "2020-03-04", "2021-05-13"]
    assert applied.json()["transformation"]["kind"] == "dates"


@pytest.mark.django_db
def test_phones_apply_and_undo(client):
    dataset_id = _upload(client, "phones.csv", PHONES_CSV)
    body = {"columns": ["phone"], "params": {"target_format": "e164", "default_country_code": "1"}}

    applied = client.post(
        f"/api/uploads/{dataset_id}/transform/phones/apply/", body, format="json"
    )
    assert applied.status_code == 201, applied.content
    transform_id = applied.json()["transformation"]["id"]
    assert applied.json()["rows"][0]["phone"] == "+15551234567"

    undo = client.post(
        f"/api/uploads/{dataset_id}/transforms/{transform_id}/undo/", format="json"
    )
    assert undo.status_code == 200, undo.content
    assert undo.json()["rows"][0]["phone"] == "(555) 123-4567"


@pytest.mark.django_db
def test_creative_uses_llm_when_no_params(client, monkeypatch):
    dataset_id = _upload(client, "dates.csv", DATES_CSV)
    called = {}

    def fake_infer(description, samples=None):
        called["yes"] = True
        return {"dayfirst": True, "target_format": "%Y-%m-%d", "explanation": "x"}

    monkeypatch.setattr(llm, "infer_date_spec", fake_infer)
    resp = client.post(
        f"/api/uploads/{dataset_id}/transform/dates/preview/",
        {"columns": ["d"], "description": "standardize to ISO"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    assert called.get("yes") is True
    assert resp.json()["spec"]["source"] == "llm"


@pytest.mark.django_db
def test_unknown_kind_rejected(client):
    dataset_id = _upload(client, "dates.csv", DATES_CSV)
    resp = client.post(
        f"/api/uploads/{dataset_id}/transform/bogus/preview/",
        {"columns": ["d"], "params": {}},
        format="json",
    )
    assert resp.status_code == 400
