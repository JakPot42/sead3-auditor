"""
main.py
=======
FastAPI application: routes, Jinja2 rendering, and the API endpoints.

Run with:
    uvicorn main:app --reload --port 8000
Then open http://127.0.0.1:8000/

Route map
---------
GET  /                     Employee submission form
POST /parse                Run the heuristic parser -> confirmation screen
POST /submit               Validate + persist + assess compliance
GET  /dashboard            FSO admin dashboard (filterable)
POST /toggle-approve/{id}  Toggle a record's FSO-approved flag
GET  /pdf/{id}             Stream the ReportLab compliance brief
POST /diss-export          Stream the DISS bulk-upload CSV for selected records
POST /seed                 (dev) insert a few demo records
"""

from __future__ import annotations

import datetime as _dt
import io
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

import diss_export
from compliance_engine import assess_compliance, parse_event_text
from config import (
    APP_TITLE,
    CLASSIFICATION_BANNER,
    DEMO_BANNER,
    DEMO_MODE,
    ORG_NAME,
    ComplianceStatus,
    EventType,
)
from database import SessionLocal, get_db, init_db
from helpers import mask_ssn, status_badge_class
from models import Employee, EventLog, ParseRequest, SubmitRequest
from pdf_generator import build_compliance_brief

def _load_seed_data(db: Session) -> None:
    today = _dt.date.today()
    demo = [
        ("Dana Whitfield", "123456789", _dt.date(1988, 4, 12), "X1234567",
         EventType.FOREIGN_TRAVEL, today + _dt.timedelta(days=47),
         today + _dt.timedelta(days=54), "United Kingdom",
         "Traveling to London for a family wedding."),
        ("Ortega, Sam", "987654321", _dt.date(1979, 11, 3), None,
         EventType.FOREIGN_TRAVEL, today + _dt.timedelta(days=9),
         today + _dt.timedelta(days=16), "France",
         "Last-minute trip to Paris next week."),
        ("Priya Nair", "555443333", _dt.date(1992, 1, 22), "P7654321",
         EventType.FOREIGN_BANK_ACCOUNT, today - _dt.timedelta(days=18), None,
         None, "Opened a foreign brokerage account."),
    ]
    for name, ssn, dob, passport, etype, edate, rdate, dest, text in demo:
        if db.scalar(select(Employee).where(Employee.ssn == ssn)):
            continue
        emp = Employee(full_name=name, ssn=ssn, date_of_birth=dob, passport_number=passport)
        db.add(emp)
        db.flush()
        res = assess_compliance(etype, edate)
        db.add(EventLog(
            employee_id=emp.id, raw_input=text, event_type=etype.value,
            event_date=edate, return_date=rdate, destination_country=dest,
            details=text, submission_date=today,
            reporting_deadline=res.reporting_deadline,
            compliance_status=res.status.value, days_delta=res.days_delta,
            approved=(etype == EventType.FOREIGN_TRAVEL),
        ))
    db.commit()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Create tables on startup (idempotent). Replaces the deprecated on_event hook.
    init_db()
    db = SessionLocal()
    try:
        _load_seed_data(db)
    finally:
        db.close()
    yield


app = FastAPI(title=APP_TITLE, lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")
# expose helpers to every template
templates.env.globals.update(
    app_title=APP_TITLE,
    org_name=ORG_NAME,
    classification_banner=CLASSIFICATION_BANNER,
    demo_mode=DEMO_MODE,
    demo_banner=DEMO_BANNER,
    event_types=[e.value for e in EventType],
)
templates.env.filters["mask_ssn"] = mask_ssn
templates.env.filters["status_badge"] = status_badge_class


# --------------------------------------------------------------------------- #
# Employee submission flow
# --------------------------------------------------------------------------- #
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {})


@app.post("/parse", response_class=HTMLResponse)
def parse(
    request: Request,
    full_name: str = Form(...),
    ssn: str = Form(...),
    raw_input: str = Form(...),
    passport_number: str = Form(""),
    date_of_birth: str = Form(""),
    badge_id: str = Form(""),
):
    """Validate identity fields, run the parser, and show the confirmation
    screen with structured, editable fields pre-filled from the guess."""
    try:
        req = ParseRequest(
            full_name=full_name,
            ssn=ssn,
            raw_input=raw_input,
            passport_number=passport_number or None,
            date_of_birth=_dt.date.fromisoformat(date_of_birth) if date_of_birth else None,
            badge_id=badge_id or None,
        )
    except (ValidationError, ValueError) as exc:
        return templates.TemplateResponse(
            request, "index.html",
            {"error": str(exc),
             "form": {"full_name": full_name, "ssn": ssn, "raw_input": raw_input,
                      "passport_number": passport_number,
                      "date_of_birth": date_of_birth, "badge_id": badge_id}},
            status_code=400,
        )

    parsed = parse_event_text(req.raw_input)

    # Pre-compute a provisional compliance read so the user sees the stakes even
    # before submitting (recomputed authoritatively on /submit).
    provisional = None
    if parsed.event_type and parsed.event_date:
        provisional = assess_compliance(parsed.event_type, parsed.event_date)

    return templates.TemplateResponse(
        request, "confirm.html",
        {
            "req": req,
            "parsed": parsed,
            "provisional": provisional,
            "today": _dt.date.today().isoformat(),
        },
    )


@app.post("/submit")
def submit(
    request: Request,
    full_name: str = Form(...),
    ssn: str = Form(...),
    raw_input: str = Form(...),
    event_type: str = Form(...),
    event_date: str = Form(...),
    return_date: str = Form(""),
    destination_country: str = Form(""),
    details: str = Form(""),
    passport_number: str = Form(""),
    date_of_birth: str = Form(""),
    badge_id: str = Form(""),
    db: Session = Depends(get_db),
):
    """Persist the (user-verified) structured record and assess compliance."""
    try:
        req = SubmitRequest(
            full_name=full_name,
            ssn=ssn,
            raw_input=raw_input,
            event_type=EventType(event_type),
            event_date=_dt.date.fromisoformat(event_date),
            return_date=_dt.date.fromisoformat(return_date) if return_date else None,
            destination_country=destination_country or None,
            details=details or None,
            passport_number=passport_number or None,
            date_of_birth=_dt.date.fromisoformat(date_of_birth) if date_of_birth else None,
            badge_id=badge_id or None,
        )
    except (ValidationError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    submission_date = _dt.date.today()
    result = assess_compliance(req.event_type, req.event_date, submission_date)

    # Reuse an existing employee row (match on SSN) or create a new one.
    employee = db.scalar(select(Employee).where(Employee.ssn == req.ssn))
    if employee is None:
        employee = Employee(
            full_name=req.full_name, ssn=req.ssn,
            date_of_birth=req.date_of_birth,
            passport_number=req.passport_number, badge_id=req.badge_id,
        )
        db.add(employee)
        db.flush()
    else:
        # keep the latest identity details fresh
        employee.full_name = req.full_name
        if req.passport_number:
            employee.passport_number = req.passport_number
        if req.date_of_birth:
            employee.date_of_birth = req.date_of_birth

    log = EventLog(
        employee_id=employee.id,
        raw_input=req.raw_input,
        event_type=req.event_type.value,
        event_date=req.event_date,
        return_date=req.return_date,
        destination_country=req.destination_country,
        details=req.details,
        submission_date=submission_date,
        reporting_deadline=result.reporting_deadline,
        compliance_status=result.status.value,
        days_delta=result.days_delta,
    )
    db.add(log)
    db.commit()

    return RedirectResponse(url=f"/dashboard?highlight={log.id}", status_code=303)


# --------------------------------------------------------------------------- #
# FSO dashboard
# --------------------------------------------------------------------------- #
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    status: str = "All",
    highlight: int | None = None,
    db: Session = Depends(get_db),
):
    """List all logs, optionally filtered by compliance status."""
    stmt = select(EventLog).order_by(EventLog.created_at.desc())

    valid_filters = {
        "All": None,
        "Late": ComplianceStatus.LATE.value,
        "Warning": ComplianceStatus.WARNING.value,
        "On-Time": ComplianceStatus.ON_TIME.value,
        "Pending Review": ComplianceStatus.PENDING_REVIEW.value,
    }
    if status not in valid_filters:
        status = "All"
    if valid_filters[status] is not None:
        stmt = stmt.where(EventLog.compliance_status == valid_filters[status])

    logs = db.scalars(stmt).all()

    # summary counts for the stat cards
    all_logs = db.scalars(select(EventLog)).all()
    counts = {
        "total": len(all_logs),
        "late": sum(1 for x in all_logs if x.compliance_status == ComplianceStatus.LATE.value),
        "warning": sum(1 for x in all_logs if x.compliance_status == ComplianceStatus.WARNING.value),
        "ontime": sum(1 for x in all_logs if x.compliance_status == ComplianceStatus.ON_TIME.value),
    }

    return templates.TemplateResponse(
        request, "dashboard.html",
        {
            "logs": logs,
            "counts": counts,
            "active_filter": status,
            "filters": list(valid_filters.keys()),
            "highlight": highlight,
            "travel_type": EventType.FOREIGN_TRAVEL.value,
        },
    )


@app.post("/toggle-approve/{log_id}")
def toggle_approve(log_id: int, status: str = Form("All"), db: Session = Depends(get_db)):
    log = db.get(EventLog, log_id)
    if log is None:
        raise HTTPException(status_code=404, detail="Record not found.")
    log.approved = not log.approved
    db.commit()
    return RedirectResponse(url=f"/dashboard?status={status}", status_code=303)


# --------------------------------------------------------------------------- #
# PDF compliance brief
# --------------------------------------------------------------------------- #
@app.get("/pdf/{log_id}")
def pdf_brief(log_id: int, db: Session = Depends(get_db)):
    log = db.get(EventLog, log_id)
    if log is None:
        raise HTTPException(status_code=404, detail="Record not found.")

    # rebuild the human-readable explanation for the memo
    result = assess_compliance(
        EventType(log.event_type), log.event_date, log.submission_date
    )
    pdf_bytes = build_compliance_brief(
        employee_name=log.employee.full_name,
        ssn=log.employee.ssn,
        event_type=log.event_type,
        event_date=log.event_date,
        submission_date=log.submission_date,
        reporting_deadline=log.reporting_deadline,
        compliance_status=log.compliance_status,
        days_delta=log.days_delta,
        destination_country=log.destination_country,
        details=log.details,
        explanation=result.explanation,
        record_id=log.id,
    )
    filename = f"SEAD3_Brief_{log.id:05d}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


# --------------------------------------------------------------------------- #
# DISS bulk export
# --------------------------------------------------------------------------- #
@app.post("/diss-export")
def diss_export_route(
    selected_ids: list[int] = Form(default=[]),
    db: Session = Depends(get_db),
):
    """Export selected approved travel records as a DISS bulk-upload CSV.

    On any hard validation failure the entire export aborts with a 400 so a
    malformed file is never delivered.
    """
    if not selected_ids:
        raise HTTPException(status_code=400, detail="No records selected.")

    logs = db.scalars(
        select(EventLog).where(EventLog.id.in_(selected_ids))
    ).all()

    try:
        csv_text, _results = diss_export.export_csv(logs)
    except diss_export.DISSValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    stamp = _dt.date.today().strftime("%Y%m%d")
    filename = f"DISS_MassForeignTravel_{stamp}.csv"
    return StreamingResponse(
        io.BytesIO(csv_text.encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --------------------------------------------------------------------------- #
# Dev convenience: seed demo data
# --------------------------------------------------------------------------- #
@app.post("/seed")
def seed(db: Session = Depends(get_db)):
    """Insert illustrative demo records (idempotent)."""
    _load_seed_data(db)
    return RedirectResponse(url="/dashboard", status_code=303)
