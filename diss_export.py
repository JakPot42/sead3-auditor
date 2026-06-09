"""
diss_export.py
==============
Builds the "DISS Mass Foreign Travel" bulk-upload CSV from a set of approved
foreign-travel EventLog records.

>>> IMPORTANT <<<
The column layout (config.DISS_COLUMNS) is a PLACEHOLDER approximation. Obtain
the current official DCSA bulk-upload template and replace DISS_COLUMNS + the
field mapping in build_row() with the exact headers/order it requires, or the
upload will be rejected. This module's job is to (a) lay rows out in that order
and (b) enforce the formatting rules that most commonly break the upload:

    * every date is rendered strictly as YYYY/MM/DD (config.DISS_DATE_FORMAT)
    * SSNs are validated to be exactly 9 digits and emitted unmasked
    * mandatory fields that the app cannot auto-fill are stamped with a visible
      REVIEW-REQUIRED placeholder rather than left blank, so the FSO can spot
      them before upload
    * only APPROVED, FOREIGN_TRAVEL records are eligible; anything else raises

Returns CSV text plus a list of per-row validation findings.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass

from config import (
    DISS_COLUMNS,
    DISS_DATE_FORMAT,
    DISS_PLACEHOLDER,
    EventType,
)
from helpers import format_ssn


class DISSValidationError(Exception):
    """Raised when a record cannot be safely exported (blocks the whole file)."""


@dataclass
class RowResult:
    record_id: int
    employee_name: str
    warnings: list[str]


def _fmt_date(d) -> str:
    """Render a date strictly as YYYY/MM/DD. None -> placeholder."""
    if d is None:
        return DISS_PLACEHOLDER
    return d.strftime(DISS_DATE_FORMAT)


def _validate_ssn_digits(ssn: str, who: str) -> str:
    digits = re.sub(r"\D", "", ssn or "")
    if len(digits) != 9:
        raise DISSValidationError(
            f"{who}: SSN must be exactly 9 digits for DISS upload "
            f"(got {len(digits)})."
        )
    return digits


def build_row(event) -> tuple[list[str], list[str]]:
    """Map one EventLog (+ its Employee) to a CSV row in DISS_COLUMNS order.

    Returns (row_values, warnings). Hard errors raise DISSValidationError;
    soft issues (placeholder substitution) are returned as warnings so the FSO
    is told exactly what still needs manual entry before the real upload.
    """
    emp = event.employee
    warnings: list[str] = []

    if event.event_type != EventType.FOREIGN_TRAVEL.value:
        raise DISSValidationError(
            f"Record #{event.id} is '{event.event_type}', not Foreign Travel; "
            f"the Mass Foreign Travel upload only accepts travel records."
        )
    if not event.approved:
        raise DISSValidationError(
            f"Record #{event.id} ({emp.full_name}) is not FSO-approved."
        )

    # Hard validation -- SSN must be clean or we refuse the whole file.
    _validate_ssn_digits(emp.ssn, emp.full_name)

    # Split name -> last, first (best effort; comma form "Last, First" honored).
    if "," in emp.full_name:
        last, first = (p.strip() for p in emp.full_name.split(",", 1))
    else:
        parts = emp.full_name.split()
        first = parts[0] if parts else DISS_PLACEHOLDER
        last = parts[-1] if len(parts) > 1 else DISS_PLACEHOLDER

    passport = emp.passport_number or DISS_PLACEHOLDER
    if passport == DISS_PLACEHOLDER:
        warnings.append("Passport Number missing -> REVIEW-REQUIRED.")

    destination = event.destination_country or DISS_PLACEHOLDER
    if destination == DISS_PLACEHOLDER:
        warnings.append("Destination Country missing -> REVIEW-REQUIRED.")

    dob = _fmt_date(emp.date_of_birth)
    if dob == DISS_PLACEHOLDER:
        warnings.append("Date of Birth missing -> REVIEW-REQUIRED.")

    return_date = _fmt_date(event.return_date)
    if return_date == DISS_PLACEHOLDER:
        warnings.append("Return Date missing -> REVIEW-REQUIRED.")

    # The row MUST line up positionally with DISS_COLUMNS.
    row = [
        last,                                 # Last Name
        first,                                # First Name
        format_ssn(emp.ssn),                  # SSN (unmasked, formatted)
        dob,                                  # Date of Birth   YYYY/MM/DD
        passport,                             # Passport Number
        destination,                          # Destination Country
        _fmt_date(event.event_date),          # Departure Date  YYYY/MM/DD
        return_date,                          # Return Date     YYYY/MM/DD
        "Personal" if event.event_type else DISS_PLACEHOLDER,  # Purpose
        (event.details or "")[:200],          # Comments (trimmed)
    ]

    if len(row) != len(DISS_COLUMNS):
        # A guard against the column list and row mapping drifting apart.
        raise DISSValidationError(
            f"Internal mapping error: produced {len(row)} fields but "
            f"DISS_COLUMNS defines {len(DISS_COLUMNS)}."
        )
    return row, warnings


def export_csv(events: list) -> tuple[str, list[RowResult]]:
    """Build the full CSV string from a list of EventLog records.

    Raises DISSValidationError (aborting the entire export) on any hard failure
    so a malformed file is never produced. Returns (csv_text, per_row_results).
    """
    if not events:
        raise DISSValidationError("No records selected for export.")

    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(DISS_COLUMNS)

    results: list[RowResult] = []
    for ev in events:
        row, warnings = build_row(ev)
        writer.writerow(row)
        results.append(RowResult(
            record_id=ev.id, employee_name=ev.employee.full_name, warnings=warnings
        ))

    return out.getvalue(), results
