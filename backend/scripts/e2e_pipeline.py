"""End-to-end redaction pipeline over the sample datasets (LIVE LLM).

Drives the real HTTP API in-process (Django test client — no separate server
needed) through the full workflow for each scenario:

    upload  ->  generate regex (Claude)  ->  preview  ->  apply  ->  download

Prints a per-operation report (generated regex, cells changed, sample diff) and
writes the redacted output to sample_data/output/. Requires ANTHROPIC_API_KEY.

Usage:  python scripts/e2e_pipeline.py
"""

from __future__ import annotations

import json
import os
import sys

# Make the backend root importable when run as `python scripts/e2e_pipeline.py`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.conf import settings  # noqa: E402
from django.test import Client  # noqa: E402

settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ["testserver"]

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "..", "sample_data")
OUT_DIR = os.path.join(DATA_DIR, "output")

# Each op = a natural-language redaction request against one column.
SCENARIOS = [
    {
        "name": "Contact book",
        "file": "contacts.csv",
        "ops": [
            ("email", "find email addresses", "[REDACTED EMAIL]"),
            ("phone", "find phone numbers", "[REDACTED PHONE]"),
            ("notes", "find email addresses", "[REDACTED EMAIL]"),
        ],
    },
    {
        "name": "Bank data",
        "file": "bank.csv",
        "ops": [
            ("email", "find email addresses", "[EMAIL]"),
            ("phone", "find phone numbers", "[PHONE]"),
            ("card_number", "find 16 digit credit card numbers", "[CARD]"),
            ("ssn", "find US social security numbers like 123-45-6789", "[SSN]"),
            ("balance", "find dollar money amounts", "[AMOUNT]"),
        ],
    },
    {
        "name": "Support tickets (large, multi-column)",
        "file": "support_tickets.csv",
        "ops": [
            ("email", "find email addresses", "[EMAIL]"),
            ("phone", "find phone numbers", "[PHONE]"),
            ("message", "find email addresses", "[EMAIL]"),
            ("message", "find credit card numbers", "[CARD]"),
            ("message", "find dollar amounts of money", "[AMOUNT]"),
            ("internal_notes", "find IP addresses", "[IP]"),
            ("internal_notes", "find US social security numbers", "[SSN]"),
        ],
    },
]


def _post_json(client, url, body):
    return client.post(url, data=json.dumps(body), content_type="application/json")


def run_scenario(client, scenario) -> bool:
    print("\n" + "=" * 72)
    print(f"SCENARIO: {scenario['name']}  ({scenario['file']})")
    print("=" * 72)

    path = os.path.join(DATA_DIR, scenario["file"])
    with open(path, "rb") as f:
        resp = client.post("/api/uploads/", {"file": f})
    if resp.status_code != 201:
        print(f"  UPLOAD FAILED ({resp.status_code}): {resp.content[:200]}")
        return False
    data = resp.json()
    dataset_id = data["dataset"]["id"]
    print(f"  Uploaded: {data['total_rows']} rows, "
          f"columns = {[c['name'] for c in data['dataset']['columns']]}")

    total_changed = 0
    for column, description, replacement in scenario["ops"]:
        gen = _post_json(client, "/api/regex/generate/",
                         {"description": description, "dataset_id": dataset_id, "columns": [column]})
        if gen.status_code != 200:
            print(f"  [{column}] GENERATE FAILED ({gen.status_code}): {gen.content[:160]}")
            return False
        regex = gen.json()["regex"]

        body = {"columns": [column], "regex": regex, "replacement": replacement,
                "description": description}
        prev = _post_json(client, f"/api/uploads/{dataset_id}/preview/", body)
        changed = prev.json().get("changed_count", 0) if prev.status_code == 200 else 0
        sample = ""
        diffs = prev.json().get("diffs", []) if prev.status_code == 200 else []
        if diffs:
            d = diffs[0]
            sample = f"  e.g. {d['before']!r} -> {d['after']!r}"

        app = _post_json(client, f"/api/uploads/{dataset_id}/apply/", body)
        if app.status_code != 201:
            print(f"  [{column}] APPLY FAILED ({app.status_code}): {app.content[:160]}")
            return False
        matches = app.json()["match_count"]
        total_changed += changed
        print(f"  [{column:<15}] {description:<42} regex={regex}")
        print(f"  {'':<17} matches={matches:<5} cells changed={changed}{sample}")

    # Download the redacted result.
    os.makedirs(OUT_DIR, exist_ok=True)
    dl = client.get(f"/api/uploads/{dataset_id}/download/?format=csv")
    out_path = os.path.join(OUT_DIR, scenario["file"].replace(".csv", "_redacted.csv"))
    with open(out_path, "wb") as f:
        f.write(dl.content)
    print(f"  -> total cells changed: {total_changed}")
    print(f"  -> wrote {os.path.normpath(out_path)}")
    return total_changed > 0


def main() -> None:
    if not settings.ANTHROPIC_API_KEY:
        raise SystemExit("ANTHROPIC_API_KEY is not set — add it to backend/.env first.")
    client = Client()
    results = {s["name"]: run_scenario(client, s) for s in SCENARIOS}

    print("\n" + "=" * 72)
    print("SUMMARY")
    print("=" * 72)
    for name, ok in results.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if not all(results.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
