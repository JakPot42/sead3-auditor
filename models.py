"""
models.py
=========
ORM models (SQLAlchemy) and request/response schemas (Pydantic v2).

PRIVACY NOTE
------------
EventLog stores the full SSN because the DISS bulk-upload export legitimately
requires it. In a real deployment this column MUST be encrypted at rest and the
database file access-controlled; the bundled SQLite file is plaintext and is
NOT production-safe on its own. The UI masks the SSN everywhere except the DISS
CSV (see helpers.mask_ssn / the export module).
"""

from __future__ import annotations

import datetime as _dt
import re

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from config import ComplianceStatus, EventType
from database import Base


# --------------------------------------------------------------------------- #
# ORM models
# --------------------------------------------------------------------------- #
class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    # Stored as digits only (no dashes); see SSN validator in schemas below.
    ssn: Mapped[str] = mapped_column(String(9), nullable=False)
    date_of_birth: Mapped[_dt.date | None] = mapped_column(Date, nullable=True)
    passport_number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    badge_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[_dt.datetime] = mapped_column(
        DateTime, default=_dt.datetime.utcnow
    )

    events: Mapped[list["EventLog"]] = relationship(
        back_populates="employee", cascade="all, delete-orphan"
    )


class EventLog(Base):
    __tablename__ = "event_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id"), nullable=False
    )

    raw_input: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    event_date: Mapped[_dt.date] = mapped_column(Date, nullable=False)
    return_date: Mapped[_dt.date | None] = mapped_column(Date, nullable=True)
    destination_country: Mapped[str | None] = mapped_column(String(80), nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)

    submission_date: Mapped[_dt.date] = mapped_column(Date, nullable=False)
    reporting_deadline: Mapped[_dt.date] = mapped_column(Date, nullable=False)
    compliance_status: Mapped[str] = mapped_column(
        String(30), default=ComplianceStatus.PENDING_REVIEW.value
    )
    days_delta: Mapped[int] = mapped_column(Integer, default=0)  # +early / -late

    # FSO marks records approved before they are eligible for DISS export.
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[_dt.datetime] = mapped_column(
        DateTime, default=_dt.datetime.utcnow
    )

    employee: Mapped["Employee"] = relationship(back_populates="events")


# --------------------------------------------------------------------------- #
# Pydantic schemas
# --------------------------------------------------------------------------- #
_SSN_RE = re.compile(r"^\d{3}-?\d{2}-?\d{4}$")


class ParseRequest(BaseModel):
    """Free-text the employee typed, plus their identifying info."""
    full_name: str = Field(min_length=2, max_length=120)
    ssn: str
    raw_input: str = Field(min_length=3, max_length=2000)
    passport_number: str | None = Field(default=None, max_length=40)
    date_of_birth: _dt.date | None = None
    badge_id: str | None = Field(default=None, max_length=40)

    @field_validator("ssn")
    @classmethod
    def _validate_ssn(cls, v: str) -> str:
        v = v.strip()
        if not _SSN_RE.match(v):
            raise ValueError("SSN must be 9 digits, optionally formatted ###-##-####.")
        return re.sub(r"\D", "", v)  # normalize to digits only


class SubmitRequest(BaseModel):
    """Structured data after the employee verifies/corrects the parsed fields."""
    full_name: str = Field(min_length=2, max_length=120)
    ssn: str
    raw_input: str = Field(min_length=3, max_length=2000)
    event_type: EventType
    event_date: _dt.date
    return_date: _dt.date | None = None
    destination_country: str | None = Field(default=None, max_length=80)
    details: str | None = Field(default=None, max_length=2000)
    passport_number: str | None = Field(default=None, max_length=40)
    date_of_birth: _dt.date | None = None
    badge_id: str | None = Field(default=None, max_length=40)

    @field_validator("ssn")
    @classmethod
    def _validate_ssn(cls, v: str) -> str:
        v = v.strip()
        if not _SSN_RE.match(v):
            raise ValueError("SSN must be 9 digits, optionally formatted ###-##-####.")
        return re.sub(r"\D", "", v)

    @field_validator("return_date")
    @classmethod
    def _return_after_event(cls, v, info):
        event_date = info.data.get("event_date")
        if v is not None and event_date is not None and v < event_date:
            raise ValueError("Return date cannot be before the event/departure date.")
        return v
