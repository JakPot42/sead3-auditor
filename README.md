# SEAD 3 Security Compliance Auditor

A web application that helps cleared-personnel security teams track **reportable
activities** under **Security Executive Agent Directive 3 (SEAD 3)** — it parses
plain-language self-disclosures, computes reporting deadlines, flags late
submissions, generates official Facility Security Officer (FSO) compliance-brief
PDFs, and exports approved foreign-travel records for DISS bulk upload.

Built with FastAPI + SQLAlchemy + ReportLab. Runs fully offline (SQLite, no
external assets) so it can operate in a closed/air-gapped environment.

> ⚠️ **Demonstration project.** All data is **synthetic**. The compliance
> windows and the DISS file layout are **illustrative placeholders**, not
> verified against any agency's current guidance. This is a portfolio piece, not
> an operational security tool — see *Honest Limitations* below.

---

## Why this project

I'm interested in working in the defense/national-security space, so I built
something that lives in that world rather than a generic CRUD app. Cleared
employees are required to self-report life events — foreign travel, foreign
financial interests, cohabitation, continuing foreign contacts — to their FSO
within specific windows, and missed deadlines are reportable security concerns.
This app models that workflow end to end and shows I understand the domain, not
just the framework.

## What it demonstrates

- **Domain modeling** of a real regulatory workflow (SEAD 3 → FSO → DISS).
- **A heuristic NLP-lite parser** (regex + keyword matching, no external NLP
  dependency) that turns "I'm traveling to London on July 25th" into structured
  fields — always followed by a human verification step.
- **Deterministic, auditable deadline math**, including a business-day
  calculator that skips weekends and holidays, with every regulatory parameter
  isolated in one config file.
- **Document generation** — a polished, branded PDF memo via ReportLab.
- **Data-integrity-focused export** — strict validation (date formatting, SSN
  shape, mandatory-field stamping) that refuses to emit a malformed upload file.
- **Engineering hygiene** — Pydantic validation, a unit-test suite, clean module
  boundaries, and security/privacy considerations called out explicitly.

## Features

| Area | What it does |
|---|---|
| Submission flow | Free-text disclosure → parsed → **user verifies/corrects** → saved |
| Compliance engine | Pre-event (advance-notice) and post-event (business-day) deadline logic; On-Time / Warning / Late |
| FSO dashboard | Filterable register, summary stats, color-coded statuses, approval workflow |
| PDF brief | Official memo: classification banners, meta block, executive summary, color-coded determination |
| DISS export | Validated CSV for approved travel records; strict `YYYY/MM/DD` dates; `REVIEW-REQUIRED` stamps for gaps |

## Tech stack

FastAPI · SQLAlchemy 2.0 · Pydantic v2 · Jinja2 · ReportLab · SQLite · vanilla CSS (no CDN)

## Architecture

```
config.py             single source of truth for every regulatory parameter
compliance_engine.py  parser + deadline math (pure, no web/DB deps -> easily testable)
models.py             SQLAlchemy ORM + Pydantic request schemas
pdf_generator.py      ReportLab memo
diss_export.py        DISS CSV builder + validation guards
main.py               FastAPI routes + Jinja rendering
helpers.py            SSN masking, status->CSS mapping
templates/  static/   UI (Jinja + local stylesheet)
tests/                pytest suite for the compliance engine
```

The compliance engine is intentionally decoupled from the web and database
layers, which is why it can be unit-tested in isolation.

## Running it

**Windows (easiest):** double-click `START_HERE.bat`. It creates a virtual
environment, installs dependencies, and launches the app at
`http://127.0.0.1:8000`.

**Any OS (manual):**
```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```
Then click **Load demo data** on the FSO dashboard to populate sample records.

## Tests
```bash
pip install pytest
pytest -q
```

## Design decisions

- **Every regulatory number lives in `config.py`.** Reporting windows and the
  DISS schema are agency-specific and change over time, so they're isolated for
  one-line edits and clear verification — not scattered through the code.
- **Parse, then make a human confirm.** The parser is a convenience, never an
  authority; nothing is saved until the user verifies the structured fields.
- **The exporter fails loudly.** Rather than emit a CSV with a malformed date or
  a bad SSN that the real DISS upload would silently reject, validation aborts
  the whole export with a clear message.
- **SSNs are masked everywhere but the export.** Display surfaces show
  `***-**-1234`; the full value appears only in the DISS file, which is its one
  legitimate use.

## Honest limitations (what I'd do before this was real)

- **Verify the regulatory parameters.** The 30-day travel window and the
  5/10 business-day post-event windows are reasonable defaults, not confirmed
  against a specific Cognizant Security Agency's guidance.
- **Replace the DISS column layout.** `DISS_COLUMNS` is a best-effort
  placeholder; the real DCSA template headers/order must be substituted or an
  upload would be rejected.
- **Harden data handling.** Real PII would require encryption at rest,
  authentication/authorization (the app currently has none), audit logging, and
  a controlled host — not a local SQLite file.
- **Add auth + an audit trail** before multiple users touch it.

These aren't oversights — they're the line between a portfolio demo and a tool
trusted with real personnel-security data, and knowing where that line is matters
as much as the code.

## License

MIT (sample/educational project).
