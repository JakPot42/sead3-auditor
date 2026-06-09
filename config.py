"""
config.py
=========
SEAD 3 Security Compliance Auditor -- central configuration.

>>> READ THIS BEFORE OPERATIONAL USE <<<

This file is deliberately the single home for every *regulatory* number in the
application.  The reporting windows below (and the DISS column layout further
down) are NOT universal constants.  SEAD 3 establishes the *categories* of
reportable activity, but the exact advance-notice and post-event reporting
windows are set by your Cognizant Security Agency (CSA) / agency security
office and have changed over time.  Likewise, the DCSA "Mass Foreign Travel"
upload template for DISS is periodically revised.

Treat the values here as sensible defaults / placeholders and confirm each one
against your own SPM, your FSO's guidance, and the current DCSA template before
relying on the tool for real submissions.  Changing a window is a one-line edit
here -- no other file needs to change.
"""

from __future__ import annotations

import datetime as _dt
from enum import Enum


# --------------------------------------------------------------------------- #
# Application metadata (shown in PDF memos and the UI banner)
# --------------------------------------------------------------------------- #
APP_TITLE = "SEAD 3 Security Compliance Auditor"
ORG_NAME = "Acme Defense Systems, LLC"          # <-- set to your cleared facility
CAGE_CODE = "0XXXX"                              # <-- set to your facility CAGE code
FSO_NAME = "Jordan A. Reyes"                     # <-- default "From:" on memos
CLASSIFICATION_BANNER = "CONFIDENTIAL // PRIVACY ACT RECORD"

# Demo mode shows a clear "synthetic data / not for operational use" notice in
# the UI and a watermark on generated PDFs. KEEP THIS True for any public or
# portfolio demo so no one mistakes sample output for a real record.
DEMO_MODE = True
DEMO_BANNER = (
    "DEMONSTRATION ONLY \u2014 SYNTHETIC DATA \u2014 NOT FOR OPERATIONAL USE"
)

# SQLite database location (file-based; runs fully offline / air-gapped).
DATABASE_URL = "sqlite:///./sead3_auditor.db"


# --------------------------------------------------------------------------- #
# Reportable event taxonomy
# --------------------------------------------------------------------------- #
class EventType(str, Enum):
    """Categories of reportable activity under SEAD 3.

    The string values double as human-readable labels in the UI / PDF, so keep
    them presentable.
    """
    FOREIGN_TRAVEL = "Foreign Travel"
    FOREIGN_BANK_ACCOUNT = "Foreign Bank Account"
    FOREIGN_CASH_IMPORT = "Foreign Cash / Currency Import"
    FOREIGN_CONTACT = "Continuing Foreign Contact / Association"
    COHABITATION = "Cohabitation"
    MARRIAGE = "Marriage / Engagement"
    FOREIGN_PROPERTY = "Foreign Property / Financial Interest"
    OTHER = "Other Reportable Activity"


class ReportingDirection(str, Enum):
    """Whether a window is measured BEFORE the event (advance notice) or AFTER."""
    PRE_EVENT = "pre_event"     # deadline = event_date - window
    POST_EVENT = "post_event"   # deadline = event_date + window


class WindowUnit(str, Enum):
    CALENDAR_DAYS = "calendar_days"
    BUSINESS_DAYS = "business_days"


class ComplianceStatus(str, Enum):
    ON_TIME = "On-Time"
    WARNING = "Warning"          # submitted on time but close to the deadline
    LATE = "Late"                # submitted after the deadline -> potential violation
    PENDING_REVIEW = "Pending Review"


# --------------------------------------------------------------------------- #
# Reporting-window rules
# --------------------------------------------------------------------------- #
# Each event type maps to a rule describing how its deadline is computed.
#
#   direction : PRE_EVENT  -> deadline = event_date - window      (advance notice)
#               POST_EVENT -> deadline = event_date + window      (report after)
#   window    : integer number of days
#   unit      : CALENDAR_DAYS or BUSINESS_DAYS
#
# DEFAULTS BELOW ARE PLACEHOLDERS -- VERIFY AGAINST YOUR AGENCY GUIDANCE.
#   * Foreign travel commonly carries a 30-day advance-notification expectation
#     for unofficial foreign travel, but some agencies use a different window
#     or require pre-approval rather than mere notice.
#   * Post-event windows are frequently expressed in business days (often in the
#     5-10 day range) but the exact figure is agency-specific.
# --------------------------------------------------------------------------- #
REPORTING_RULES: dict[EventType, dict] = {
    EventType.FOREIGN_TRAVEL: {
        "direction": ReportingDirection.PRE_EVENT,
        "window": 30,
        "unit": WindowUnit.CALENDAR_DAYS,
    },
    EventType.FOREIGN_BANK_ACCOUNT: {
        "direction": ReportingDirection.POST_EVENT,
        "window": 10,
        "unit": WindowUnit.BUSINESS_DAYS,
    },
    EventType.FOREIGN_CASH_IMPORT: {
        "direction": ReportingDirection.POST_EVENT,
        "window": 5,
        "unit": WindowUnit.BUSINESS_DAYS,
    },
    EventType.FOREIGN_CONTACT: {
        "direction": ReportingDirection.POST_EVENT,
        "window": 10,
        "unit": WindowUnit.BUSINESS_DAYS,
    },
    EventType.COHABITATION: {
        "direction": ReportingDirection.POST_EVENT,
        "window": 10,
        "unit": WindowUnit.BUSINESS_DAYS,
    },
    EventType.MARRIAGE: {
        "direction": ReportingDirection.POST_EVENT,
        "window": 10,
        "unit": WindowUnit.BUSINESS_DAYS,
    },
    EventType.FOREIGN_PROPERTY: {
        "direction": ReportingDirection.POST_EVENT,
        "window": 10,
        "unit": WindowUnit.BUSINESS_DAYS,
    },
    EventType.OTHER: {
        "direction": ReportingDirection.POST_EVENT,
        "window": 10,
        "unit": WindowUnit.BUSINESS_DAYS,
    },
}

# How many days of slack before a deadline still counts as "on time" but should
# be surfaced as a WARNING (i.e., the employee cut it close). Purely a UX aid.
WARNING_BAND_DAYS = 5


# --------------------------------------------------------------------------- #
# Business-day calculation
# --------------------------------------------------------------------------- #
# Business-day math skips weekends and the holidays listed here. This list is
# intentionally small and MUST be maintained for your reporting calendar -- it
# is not an authoritative federal holiday source. Use observed dates.
US_FEDERAL_HOLIDAYS: set[_dt.date] = {
    # 2025
    _dt.date(2025, 1, 1),    # New Year's Day
    _dt.date(2025, 1, 20),   # MLK / Inauguration
    _dt.date(2025, 5, 26),   # Memorial Day
    _dt.date(2025, 6, 19),   # Juneteenth
    _dt.date(2025, 7, 4),    # Independence Day
    _dt.date(2025, 9, 1),    # Labor Day
    _dt.date(2025, 11, 27),  # Thanksgiving
    _dt.date(2025, 12, 25),  # Christmas
    # 2026
    _dt.date(2026, 1, 1),
    _dt.date(2026, 1, 19),
    _dt.date(2026, 5, 25),
    _dt.date(2026, 6, 19),
    _dt.date(2026, 7, 3),    # observed (Jul 4 is a Saturday)
    _dt.date(2026, 9, 7),
    _dt.date(2026, 11, 26),
    _dt.date(2026, 12, 25),
}


# --------------------------------------------------------------------------- #
# DISS "Mass Foreign Travel" bulk-upload column layout
# --------------------------------------------------------------------------- #
# !!! PLACEHOLDER SCHEMA !!!
# The header row below is a best-effort approximation of the fields a foreign
# travel bulk upload requires. The ACTUAL DCSA template column names, order,
# and required/optional flags must be copied verbatim from the current official
# template you obtain from DCSA / your DISS account -- a mismatch will cause the
# upload to reject the file. Replace DISS_COLUMNS with the real header row and
# adjust diss_export.build_row() accordingly. Field order here defines CSV order.
DISS_COLUMNS: list[str] = [
    "Last Name",
    "First Name",
    "SSN",
    "Date of Birth",
    "Passport Number",
    "Destination Country",
    "Departure Date",
    "Return Date",
    "Purpose of Travel",
    "Comments",
]

# DISS requires strict date formatting; standard formatting drift breaks uploads.
DISS_DATE_FORMAT = "%Y/%m/%d"   # -> YYYY/MM/DD

# Default placeholder text written into mandatory DISS fields that the parser
# cannot populate, so the FSO can clearly see what still needs manual entry.
DISS_PLACEHOLDER = "REVIEW-REQUIRED"
