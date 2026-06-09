"""
helpers.py
==========
Small shared utilities used across the web layer, PDF, and CSV export.
Keeping them here avoids circular imports between models / templates / export.
"""

from __future__ import annotations

import re

from config import ComplianceStatus


def mask_ssn(ssn: str | None) -> str:
    """Return an SSN masked to the last four digits: ***-**-1234.

    Accepts digits-only or dashed input. Used everywhere the SSN is *displayed*.
    The full SSN is only ever emitted into the DISS export CSV.
    """
    if not ssn:
        return "\u2014"
    digits = re.sub(r"\D", "", ssn)
    if len(digits) != 9:
        return "***-**-****"
    return f"***-**-{digits[-4:]}"


def format_ssn(ssn: str | None) -> str:
    """Return a fully formatted SSN ###-##-#### (used only in the DISS export)."""
    if not ssn:
        return ""
    digits = re.sub(r"\D", "", ssn)
    if len(digits) != 9:
        return digits
    return f"{digits[:3]}-{digits[3:5]}-{digits[5:]}"


# Maps a compliance status to a CSS class used by the Jinja templates so the
# badge colors stay consistent between the dashboard and the rest of the UI.
STATUS_BADGE_CLASS = {
    ComplianceStatus.ON_TIME.value: "badge badge-ontime",
    ComplianceStatus.WARNING.value: "badge badge-warning",
    ComplianceStatus.LATE.value: "badge badge-late",
    ComplianceStatus.PENDING_REVIEW.value: "badge badge-pending",
}


def status_badge_class(status: str) -> str:
    return STATUS_BADGE_CLASS.get(status, "badge badge-pending")
