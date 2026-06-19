"""Generate the large/complex sample dataset (support_tickets.csv).

Produces a realistic customer-support export where personally identifiable
information (PII) is scattered across *multiple* columns AND embedded in
free-text fields — the hardest redaction case within the task frame:

    ticket_id, customer_name, email, phone, priority, created_at,
    message (free text w/ emails, phones, cards, money),
    internal_notes (free text w/ IPs, SSNs)

Deterministic (seeded) so tests and the demo stay reproducible.

Usage:  python scripts/generate_sample_data.py [num_rows]
"""

from __future__ import annotations

import csv
import os
import random
import sys

SEED = 42
DEFAULT_ROWS = 1000

FIRST = [
    "John", "Jane", "Alice", "Bob", "Carol", "David", "Emma", "Frank", "Grace",
    "Henry", "Ivy", "Jack", "Karen", "Leo", "Mona", "Nate", "Olivia", "Paul",
    "Quinn", "Rosa", "Sam", "Tina", "Uma", "Victor", "Wendy", "Xander",
]
LAST = [
    "Doe", "Smith", "Brown", "Martin", "White", "Lee", "Davis", "Moore", "Kim",
    "Clark", "Nguyen", "Wilson", "Patel", "Garcia", "Rossi", "Khan", "Singh",
    "Lopez", "Murphy", "Chen", "Ali", "Novak", "Silva", "Haas", "Ortiz",
]
EMAIL_DOMAINS = ["example.com", "mail.net", "corp.io", "webmail.org", "fastmail.co"]
PRIORITIES = ["Low", "Medium", "High", "Critical"]


def make_phone(rng: random.Random) -> str:
    n = lambda k: "".join(rng.choice("0123456789") for _ in range(k))
    fmt = rng.choice(
        [
            "{a}-{b}-{c}",
            "({a}) {b}-{c}",
            "{a}.{b}.{c}",
            "+1 {a} {b} {c}",
            "+1-{a}-{b}-{c}",
        ]
    )
    return fmt.format(a=n(3), b=n(3), c=n(4))


def make_card(rng: random.Random) -> str:
    groups = ["".join(rng.choice("0123456789") for _ in range(4)) for _ in range(4)]
    sep = rng.choice([" ", "-", ""])
    return sep.join(groups)


def make_ssn(rng: random.Random) -> str:
    n = lambda k: "".join(rng.choice("0123456789") for _ in range(k))
    return f"{n(3)}-{n(2)}-{n(4)}"


def make_ip(rng: random.Random) -> str:
    return ".".join(str(rng.randint(1, 254)) for _ in range(4))


def make_money(rng: random.Random) -> str:
    amount = rng.randint(5, 250000)
    cents = rng.randint(0, 99)
    return f"${amount:,}.{cents:02d}"


MESSAGE_TEMPLATES = [
    "Customer reported a failed charge of {money} on card {card}. Reach them at {email} or {phone}.",
    "Refund of {money} requested; confirmation should go to {email}.",
    "Duplicate transaction of {money} on card {card}. Call back at {phone}.",
    "Disputed payment {money}. Alternate contact: {email}, mobile {phone}.",
    "Card {card} was declined for a {money} purchase. Please email {email}.",
    "Account locked after a {money} transfer. Verify via {phone} or {email}.",
]

NOTES_TEMPLATES = [
    "Verified identity, SSN {ssn}. Login originated from {ip}.",
    "Escalated. Agent session IP {ip}; customer SSN on file {ssn}.",
    "Flagged SSN {ssn} mismatch. Suspicious login from {ip}.",
    "KYC check passed for SSN {ssn}. Last access IP {ip}.",
    "Manual review: IP {ip} flagged, SSN {ssn} confirmed by phone.",
]


def generate(num_rows: int, out_path: str) -> None:
    rng = random.Random(SEED)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "ticket_id", "customer_name", "email", "phone", "priority",
                "created_at", "message", "internal_notes",
            ]
        )
        for i in range(1, num_rows + 1):
            first, last = rng.choice(FIRST), rng.choice(LAST)
            name = f"{first} {last}"
            email = f"{first.lower()}.{last.lower()}@{rng.choice(EMAIL_DOMAINS)}"
            phone = make_phone(rng)
            created = f"2024-{rng.randint(1,12):02d}-{rng.randint(1,28):02d}"
            message = rng.choice(MESSAGE_TEMPLATES).format(
                money=make_money(rng),
                card=make_card(rng),
                email=f"{first.lower()}{rng.randint(1,99)}@{rng.choice(EMAIL_DOMAINS)}",
                phone=make_phone(rng),
            )
            notes = rng.choice(NOTES_TEMPLATES).format(
                ssn=make_ssn(rng), ip=make_ip(rng)
            )
            writer.writerow(
                [f"TCK-{i:05d}", name, email, phone, rng.choice(PRIORITIES),
                 created, message, notes]
            )


def main() -> None:
    rows = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_ROWS
    here = os.path.dirname(os.path.abspath(__file__))
    out_path = os.path.join(here, "..", "sample_data", "support_tickets.csv")
    generate(rows, out_path)
    print(f"Wrote {rows} rows -> {os.path.normpath(out_path)}")


if __name__ == "__main__":
    main()
