"""
tests/test_compliance.py
========================
Unit tests for the compliance engine. These run without the web server or
database, so they're fast and deterministic.

Run from the project root:
    pip install pytest
    pytest -q
"""

import datetime as dt

import pytest

from compliance_engine import (
    add_business_days,
    assess_compliance,
    parse_event_text,
)
from config import ComplianceStatus, EventType

TODAY = dt.date(2026, 6, 8)


# --------------------------------------------------------------------------- #
# Parser
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "text, exp_type, exp_date, exp_dest",
    [
        ("I am traveling to London on July 25th",
         EventType.FOREIGN_TRAVEL, dt.date(2026, 7, 25), "United Kingdom"),
        ("Trip to Tokyo 2026-09-10",
         EventType.FOREIGN_TRAVEL, dt.date(2026, 9, 10), "Japan"),
        ("I opened a foreign bank account on 03/15/2026",
         EventType.FOREIGN_BANK_ACCOUNT, dt.date(2026, 3, 15), None),
    ],
)
def test_parser_extracts_fields(text, exp_type, exp_date, exp_dest):
    p = parse_event_text(text, today=TODAY)
    assert p.event_type == exp_type
    assert p.event_date == exp_date
    assert p.destination_country == exp_dest


def test_parser_rolls_undated_year_forward():
    # "July 25th" with no year, typed in June, should resolve to this year;
    # a date already past should roll to next year.
    p = parse_event_text("flying to Paris on January 2nd", today=TODAY)
    assert p.event_date == dt.date(2027, 1, 2)  # Jan already passed in June


# --------------------------------------------------------------------------- #
# Deadline math
# --------------------------------------------------------------------------- #
def test_travel_on_time_when_reported_early():
    r = assess_compliance(EventType.FOREIGN_TRAVEL, dt.date(2026, 8, 1), TODAY)
    assert r.status == ComplianceStatus.ON_TIME
    assert r.reporting_deadline == dt.date(2026, 7, 2)  # 30 days before travel
    assert r.days_delta > 0


def test_travel_late_when_inside_window():
    r = assess_compliance(EventType.FOREIGN_TRAVEL, dt.date(2026, 6, 20), TODAY)
    assert r.status == ComplianceStatus.LATE
    assert r.days_delta < 0


def test_warning_band_when_cutting_it_close():
    # deadline exactly 3 days out -> within the 5-day warning band
    travel = TODAY + dt.timedelta(days=33)  # deadline = travel - 30 = TODAY+3
    r = assess_compliance(EventType.FOREIGN_TRAVEL, travel, TODAY)
    assert r.status == ComplianceStatus.WARNING


def test_post_event_business_days():
    # bank account: 10 business days after the event
    r = assess_compliance(EventType.FOREIGN_BANK_ACCOUNT, dt.date(2026, 6, 5), TODAY)
    assert r.status == ComplianceStatus.ON_TIME
    assert r.reporting_deadline > dt.date(2026, 6, 5)


# --------------------------------------------------------------------------- #
# Business-day helper
# --------------------------------------------------------------------------- #
def test_business_days_skip_weekend_and_holiday():
    # Mon Jun 15 2026 + 5 business days, skipping Sat/Sun and Juneteenth (Jun 19)
    assert add_business_days(dt.date(2026, 6, 15), 5) == dt.date(2026, 6, 23)


def test_business_days_zero():
    assert add_business_days(dt.date(2026, 6, 15), 0) == dt.date(2026, 6, 15)
