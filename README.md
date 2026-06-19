# Regex Pattern Matching & Replacement

A web application that lets you upload a CSV/Excel file, describe a pattern in
**plain English**, have an **LLM (Anthropic Claude) turn it into a regex**, and
apply a find-and-replace across a text column — with a live before/after preview,
undo, and CSV/Excel export. It also ships two LLM-assisted **creative transforms**
(date standardization and phone-number normalization).

Built with **Django + Django REST Framework** (backend) and **React + TypeScript +
Vite** (frontend).

<!-- Demo video: paste the embed/link here -->
<!-- Live URL: paste the deployed URL here -->

---

## Features

- **Upload** CSV / Excel (`.csv`, `.xlsx`, `.xls`); parsed once and stored
  server-side as a parquet snapshot (keyed by an upload id).
- **Natural language → regex** via Claude, returned with an explanation,
  confidence, and concrete sample matches from your column.
- **Generate → Preview → Apply** flow: nothing is mutated until you confirm. The
  preview shows exactly which cells change.
- **Undo** the most recent transformation (snapshot-based).
- **Creative transforms (bonus):** standardize mixed date formats to `YYYY-MM-DD`,
  and normalize phone numbers to E.164 / national formats — both LLM-configured.
- **Download** the processed data as CSV or Excel.
- **Safety & validation:** file type/size checks, encoding/delimiter sniffing,
  regex compiled & validated server-side, and a per-cell **timeout to prevent
  catastrophic-backtracking (ReDoS)**.

---

## Architecture

```
┌─────────────────────────┐        HTTPS / JSON         ┌──────────────────────────────┐
│  React + TS (Vite SPA)  │ ─────────────────────────▶  │  Django + DRF (REST API)      │
│                         │                             │                               │
│  • Upload dropzone      │  POST /api/uploads/         │  • Upload & parse (pandas)    │
│  • Data grid            │  POST /api/regex/generate/  │  • LLM service (Claude)       │
│  • Pattern panel        │  POST /api/uploads/{id}/... │  • Regex validate + replace   │
│  • Before/after + undo  │  GET  /api/uploads/{id}/... │  • Creative transforms        │
└─────────────────────────┘                             └───────────────┬──────────────┘
                                                                         │
                                    ┌────────────────────────────────────┼───────────────┐
                                    │                                     │               │
                              ┌─────▼──────┐                       ┌──────▼─────┐   ┌─────▼──────┐
                              │ DB (SQLite │                       │ parquet    │   │ Anthropic  │
                              │ / Postgres)│                       │ data store │   │ Claude API │
                              └────────────┘                       └────────────┘   └────────────┘
```

**Key idea:** the dataframe lives server-side. The browser only ever holds one
*page* of rows; transformations run in pandas on the server and are previewed
before they are committed.

---

## Repository structure

```
.
├── README.md
├── backend/                       # Django + DRF API
│   ├── manage.py
│   ├── requirements.txt
│   ├── .env.example
│   ├── config/                    # project: settings, urls, exception handler, wsgi/asgi
│   ├── datasets/                  # app: upload, storage, paginated rows, download
│   │   ├── models.py              #   Dataset (metadata; data stored as parquet)
│   │   ├── serializers.py         #   DatasetSerializer + JSON-safe row paging
│   │   ├── views.py               #   upload / rows / download endpoints
│   │   └── services/
│   │       ├── file_io.py         #   pandas read/write (CSV+Excel), column inference
│   │       └── storage.py         #   parquet save/load + undo snapshots
│   ├── transforms/                # app: LLM + regex + creative transforms
│   │   ├── models.py              #   Transformation history (regex/dates/phones)
│   │   ├── serializers.py         #   request/response serializers
│   │   ├── views.py               #   generate / preview / apply / undo / creative
│   │   └── services/
│   │       ├── llm.py             #   Claude wrapper: NL→regex + transform specs
│   │       ├── regex_engine.py    #   compile/validate + ReDoS-safe apply
│   │       ├── creative.py        #   deterministic date/phone transforms
│   │       └── diffing.py         #   shared before/after diff builder
│   └── tests/                     # pytest: services + full API flow
└── frontend/                      # React + TypeScript + Vite SPA
    ├── package.json
    ├── vite.config.ts
    ├── .env.example
    └── src/
        ├── api/
        │   ├── client.ts          # typed fetch wrapper (normalized errors)
        │   └── types.ts           # response/request types mirroring the API
        ├── components/
        │   ├── FileUpload.tsx     # drag-drop + validation
        │   ├── DataGrid.tsx       # paginated TanStack table
        │   ├── PatternPanel.tsx   # column / NL / regex / replacement controls
        │   ├── RegexPreview.tsx   # generated regex + explanation + matches
        │   ├── BeforeAfter.tsx    # changed-cell diff view
        │   └── TransformHistory.tsx # history list + undo
        ├── App.tsx                # orchestrates the workflow + shared state
        └── *.test.tsx / *.test.ts # Vitest + Testing Library
```

---

## Getting started (local)

### Prerequisites
- Python 3.11+ (developed on 3.13)
- Node.js 18+ (developed on 24)
- An Anthropic API key (for the LLM features)

### 1. Backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate   |   macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # then edit .env and set ANTHROPIC_API_KEY
python manage.py migrate
python manage.py runserver  # http://localhost:8000
```

The API is now at `http://localhost:8000/api/` (health check: `/api/health/`).

### 2. Frontend

```bash
cd frontend
npm install
cp .env.example .env        # VITE_API_BASE_URL defaults to http://localhost:8000
npm run dev                 # http://localhost:5173
```

Open `http://localhost:5173` and upload a file.

---

## Environment variables

**Backend** (`backend/.env`)

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Claude API key (required for LLM features). |
| `LLM_MODEL` | `claude-haiku-4-5-20251001` | Model used for NL→regex / transform specs. |
| `DJANGO_SECRET_KEY` | dev key | Django secret (set in production). |
| `DJANGO_DEBUG` | `True` | Debug mode. |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated allowed hosts. |
| `DATABASE_URL` | SQLite | Set to a `postgres://…` URL in production. |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:5173,…` | Allowed frontend origins. |
| `MAX_UPLOAD_MB` | `25` | Max upload size. |
| `UPLOAD_TTL_HOURS` | `24` | How long uploads are retained. |
| `REGEX_TIMEOUT_SECONDS` | `2` | Per-cell regex timeout (ReDoS guard). |

**Frontend** (`frontend/.env`)

| Variable | Default | Purpose |
|---|---|---|
| `VITE_API_BASE_URL` | `http://localhost:8000` | Backend base URL. |

---

## API reference

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/uploads/` | Upload CSV/Excel; returns metadata + first page of rows. |
| `GET` | `/api/uploads/{id}/rows/?page=&size=` | Paginated rows. |
| `POST` | `/api/regex/generate/` | NL description → `{ regex, flags, explanation, confidence, sample_matches }`. |
| `POST` | `/api/uploads/{id}/preview/` | Before/after for a `{ column, regex, replacement }` (no commit). |
| `POST` | `/api/uploads/{id}/apply/` | Commit the replacement; records history. |
| `POST` | `/api/uploads/{id}/transform/{kind}/preview/` | Preview a creative transform (`kind` = `dates`/`phones`). |
| `POST` | `/api/uploads/{id}/transform/{kind}/apply/` | Commit a creative transform. |
| `GET` | `/api/uploads/{id}/transforms/` | Transformation history. |
| `POST` | `/api/uploads/{id}/transforms/{tid}/undo/` | Undo the most recent transformation. |
| `GET` | `/api/uploads/{id}/download/?format=csv\|xlsx` | Download processed data. |

### Example (the brief's scenario)

Upload:

| ID | Name | Email |
|---|---|---|
| 1 | John Doe | john.doe@example.com |
| 2 | Jane Smith | jane_smith@domain.com |

Natural language: *"Find email addresses and replace them with REDACTED."*
→ Claude returns `\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,7}\b`
→ Apply with replacement `REDACTED`:

| ID | Name | Email |
|---|---|---|
| 1 | John Doe | REDACTED |
| 2 | Jane Smith | REDACTED |

---

## Testing

**Backend** (pytest — services + full API flow):
```bash
cd backend
python -m pytest
```

**Frontend** (Vitest + Testing Library — client, components, App flow):
```bash
cd frontend
npm test
npm run typecheck
```

---

## Design notes

- **Server-side data store.** Uploaded data is parsed once and saved as parquet;
  every operation references the upload id. This keeps payloads small and scales
  to larger files (only a page of rows crosses the wire).
- **Generate → preview → apply.** The three-stage flow means the user always sees
  the regex *and* its effect before any data changes.
- **LLM does specs, pandas does mutations.** For the creative transforms the LLM
  only produces a small structured *spec* (e.g. day-first vs month-first, target
  format); the actual cell changes are deterministic pandas — predictable and
  unit-testable.
- **ReDoS protection.** Patterns are compiled server-side and applied with a
  per-cell timeout via the `regex` module (works cross-platform, unlike
  `signal`-based timeouts).
- **No auth by design.** Uploads are anonymous and TTL-scoped; the assignment
  doesn't call for accounts.

## Tech stack

| Layer | Choice |
|---|---|
| Backend | Django, Django REST Framework |
| Data | pandas, openpyxl, pyarrow (parquet), `regex` |
| DB | SQLite (dev) / Postgres (prod) |
| LLM | Anthropic Claude (`claude-haiku-4-5-20251001`) |
| Frontend | React, TypeScript, Vite, TanStack Table |
| Tests | pytest / Vitest + Testing Library |
