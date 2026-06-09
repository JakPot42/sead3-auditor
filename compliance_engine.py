"""
compliance_engine.py
=====================
Two responsibilities, kept free of any web/DB dependency so they can be unit
tested in isolation:

  1. parse_event_text()  -- a lightweight, fully-local heuristic parser that
     guesses Event Type, Date, and Destination from an employee's free text.
     It is intentionally simple (regex + keyword matching) and is ALWAYS
     followed by a human confirmation step in the UI, so false guesses are
     cheap to correct.

  2. assess_compliance()  -- the deterministic SEAD 3 deadline math. All the
     regulatory numbers come from config.REPORTING_RULES; nothing is hard-coded
     here. See the docstring on assess_compliance for the exact arithmetic.
"""

from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass, field

from config import (
    REPORTING_RULES,
    US_FEDERAL_HOLIDAYS,
    WARNING_BAND_DAYS,
    ComplianceStatus,
    EventType,
    ReportingDirection,
    WindowUnit,
)


# =========================================================================== #
# 1. PARSING
# =========================================================================== #

# Keyword -> EventType. First matching group wins (most specific first). These
# are heuristics only; the user confirms/corrects everything afterward.
_EVENT_KEYWORDS: list[tuple[EventType, tuple[str, ...]]] = [
    (EventType.FOREIGN_BANK_ACCOUNT,
     ("bank account", "foreign account", "opened an account", "brokerage")),
    (EventType.FOREIGN_CASH_IMPORT,
     ("cash", "currency", "imported", "bring in money", "wire transfer")),
    (EventType.MARRIAGE,
     ("married", "marriage", "engaged", "engagement", "fiancé", "fiancee", "wedding")),
    (EventType.COHABITATION,
     ("cohabit", "moving in", "move in", "living with", "moved in")),
    (EventType.FOREIGN_PROPERTY,
     ("property", "real estate", "bought a house", "purchased land", "investment")),
    (EventType.FOREIGN_CONTACT,
     ("foreign national", "contact", "relationship with", "association")),
    (EventType.FOREIGN_TRAVEL,
     ("travel", "traveling", "travelling", "trip", "flying", "flight",
      "visiting", "visit", "abroad", "overseas", "vacation", "going to")),
]

# A compact city -> country lookup so "London" resolves to "United Kingdom".
# Extend freely; unknown destinations simply pass through as-is.
_CITY_TO_COUNTRY = {
    "london": "United Kingdom", "manchester": "United Kingdom",
    "paris": "France", "nice": "France", "lyon": "France",
    "berlin": "Germany", "munich": "Germany", "frankfurt": "Germany",
    "rome": "Italy", "milan": "Italy", "venice": "Italy",
    "madrid": "Spain", "barcelona": "Spain",
    "tokyo": "Japan", "osaka": "Japan", "kyoto": "Japan",
    "beijing": "China", "shanghai": "China",
    "moscow": "Russia", "dubai": "United Arab Emirates",
    "toronto": "Canada", "vancouver": "Canada", "montreal": "Canada",
    "mexico city": "Mexico", "cancun": "Mexico",
    "amsterdam": "Netherlands", "zurich": "Switzerland", "geneva": "Switzerland",
    "seoul": "South Korea", "singapore": "Singapore", "sydney": "Australia",
}

# A small set of country names recognized directly.
_COUNTRIES = {
    "united kingdom", "uk", "england", "scotland", "france", "germany", "italy",
    "spain", "japan", "china", "russia", "canada", "mexico", "netherlands",
    "switzerland", "south korea", "north korea", "singapore", "australia",
    "india", "brazil", "ireland", "portugal", "greece", "egypt", "israel",
    "united arab emirates", "uae", "saudi arabia", "turkey", "thailand",
    "vietnam", "philippines", "indonesia", "south africa", "kenya", "nigeria",
}

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}


@dataclass
class ParsedEvent:
    """Best-effort structured guess produced by the parser."""
    event_type: EventType | None = None
    event_date: _dt.date | None = None
    destination_country: str | None = None
    details: str | None = None
    confidence_notes: list[str] = field(default_factory=list)


def _extract_date(text: str, today: _dt.date) -> _dt.date | None:
    """Pull the first plausible date out of free text.

    Handles, in priority order:
        * ISO          2025-07-25
        * US numeric   07/25/2025  or  7/25  (year inferred)
        * Month name   July 25th, 2025 / Jul 25 / 25 July
    If no year is present we assume the current year, rolling to next year only
    when that date has already passed (so "July 25th" typed in October means the
    following July). The confirmation UI lets the user fix any wrong guess.
    """
    t = text.lower()

    # ISO: YYYY-MM-DD
    m = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", t)
    if m:
        try:
            return _dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass

    # US numeric: M/D[/YYYY]
    m = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", t)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        year = m.group(3)
        try:
            if year:
                year = int(year)
                if year < 100:           # two-digit year -> 2000s
                    year += 2000
            else:
                year = today.year
            d = _dt.date(year, month, day)
            if not m.group(3) and d < today:
                d = _dt.date(year + 1, month, day)
            return d
        except ValueError:
            pass

    # Month name forms: "july 25th[, 2025]" OR "25 july[ 2025]"
    month_alt = "|".join(_MONTHS.keys())
    m = re.search(
        rf"\b({month_alt})\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s*(\d{{4}}))?\b", t)
    if not m:
        m2 = re.search(
            rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({month_alt})(?:,?\s*(\d{{4}}))?\b", t)
        if m2:
            day, month_name, year = m2.group(1), m2.group(2), m2.group(3)
        else:
            return None
    else:
        month_name, day, year = m.group(1), m.group(2), m.group(3)

    month = _MONTHS[month_name]
    day = int(day)
    try:
        if year:
            return _dt.date(int(year), month, day)
        d = _dt.date(today.year, month, day)
        if d < today:                    # no year given and it's in the past
            d = _dt.date(today.year + 1, month, day)
        return d
    except ValueError:
        return None


def _extract_destination(text: str) -> str | None:
    """Find a destination. Prefers a token right after 'to'/'in', then falls
    back to scanning for any recognized city or country anywhere in the text."""
    t = text.lower()

    # "to London", "in Paris", "to Mexico City"
    m = re.search(r"\b(?:to|in|toward|towards)\s+([a-z][a-z .'-]{1,40})", t)
    if m:
        candidate = m.group(1).strip(" .'-")
        # try progressively shorter prefixes ("mexico city" before "mexico")
        words = candidate.split()
        for n in range(min(3, len(words)), 0, -1):
            phrase = " ".join(words[:n])
            if phrase in _CITY_TO_COUNTRY:
                return _CITY_TO_COUNTRY[phrase]
            if phrase in _COUNTRIES:
                return _normalize_country(phrase)

    # Fallback: any known city/country mentioned anywhere.
    for city, country in _CITY_TO_COUNTRY.items():
        if re.search(rf"\b{re.escape(city)}\b", t):
            return country
    for country in _COUNTRIES:
        if re.search(rf"\b{re.escape(country)}\b", t):
            return _normalize_country(country)
    return None


def _normalize_country(name: str) -> str:
    aliases = {
        "uk": "United Kingdom", "england": "United Kingdom",
        "scotland": "United Kingdom", "uae": "United Arab Emirates",
    }
    return aliases.get(name, name.title())


def _classify_event(text: str, destination: str | None) -> tuple[EventType | None, list[str]]:
    notes: list[str] = []
    t = text.lower()
    for event_type, keywords in _EVENT_KEYWORDS:
        for kw in keywords:
            if kw in t:
                notes.append(f"Matched keyword '{kw}' -> {event_type.value}.")
                return event_type, notes
    # If we found a foreign destination but no keyword, lean toward travel.
    if destination:
        notes.append("No keyword matched but a destination was found; "
                     "defaulting to Foreign Travel.")
        return EventType.FOREIGN_TRAVEL, notes
    notes.append("Could not confidently classify; please select the event type.")
    return None, notes


def parse_event_text(text: str, today: _dt.date | None = None) -> ParsedEvent:
    """Run the full heuristic parse over the employee's free-text input."""
    today = today or _dt.date.today()
    destination = _extract_destination(text)
    event_type, notes = _classify_event(text, destination)
    event_date = _extract_date(text, today)

    if event_date is None:
        notes.append("No date detected; please pick the event date manually.")
    # Destination is only meaningful for travel.
    if event_type != EventType.FOREIGN_TRAVEL:
        destination = None

    return ParsedEvent(
        event_type=event_type,
        event_date=event_date,
        destination_country=destination,
        details=text.strip(),
        confidence_notes=notes,
    )


# =========================================================================== #
# 2. DEADLINE / STATUS MATH
# =========================================================================== #

def add_business_days(start: _dt.date, n: int) -> _dt.date:
    """Return the date n business days after `start`.

    A business day is Mon-Fri that is not in config.US_FEDERAL_HOLIDAYS. We step
    one calendar day at a time and only decrement the counter on a qualifying
    business day. Counting begins the day AFTER the event, which is the usual
    convention for "report within N business days of the event."
    """
    current = start
    remaining = n
    while remaining > 0:
        current += _dt.timedelta(days=1)
        if current.weekday() < 5 and current not in US_FEDERAL_HOLIDAYS:
            remaining -= 1
    return current


@dataclass
class ComplianceResult:
    reporting_deadline: _dt.date
    status: ComplianceStatus
    days_delta: int        # >0 = submitted with N days to spare; <0 = N days late
    explanation: str


def assess_compliance(
    event_type: EventType,
    event_date: _dt.date,
    submission_date: _dt.date | None = None,
) -> ComplianceResult:
    """Compute the reporting deadline and on-time/late status for one event.

    The arithmetic, by rule direction:

      PRE_EVENT  (e.g., foreign travel, 30 days advance notice)
          deadline      = event_date - window
          on time when  submission_date <= deadline
          days_delta    = (deadline - submission_date).days
                          (positive => reported with that many days to spare;
                           negative => that many days past the advance cutoff)

      POST_EVENT (e.g., report a foreign bank account within 10 business days)
          deadline      = event_date + window
          on time when  submission_date <= deadline
          days_delta    = (deadline - submission_date).days

    A submission that is on time but within WARNING_BAND_DAYS of the deadline is
    flagged WARNING so the FSO can coach the employee, while still counting as
    compliant (not a violation).
    """
    submission_date = submission_date or _dt.date.today()
    rule = REPORTING_RULES[event_type]
    direction: ReportingDirection = rule["direction"]
    window: int = rule["window"]
    unit: WindowUnit = rule["unit"]

    # --- 1. compute the deadline date ------------------------------------- #
    if direction == ReportingDirection.PRE_EVENT:
        # Advance-notice windows are conventionally counted in calendar days.
        deadline = event_date - _dt.timedelta(days=window)
        window_desc = f"{window} calendar days before the event"
    else:  # POST_EVENT
        if unit == WindowUnit.BUSINESS_DAYS:
            deadline = add_business_days(event_date, window)
            window_desc = f"{window} business days after the event"
        else:
            deadline = event_date + _dt.timedelta(days=window)
            window_desc = f"{window} calendar days after the event"

    # --- 2. compare against the submission date --------------------------- #
    days_delta = (deadline - submission_date).days

    if days_delta < 0:
        status = ComplianceStatus.LATE
        explanation = (
            f"Reporting deadline was {deadline:%Y-%m-%d} ({window_desc}); "
            f"reported {submission_date:%Y-%m-%d}, i.e. {abs(days_delta)} day(s) "
            f"late. Flag as potential SEAD 3 reporting violation."
        )
    elif days_delta <= WARNING_BAND_DAYS:
        status = ComplianceStatus.WARNING
        explanation = (
            f"Reported on time but only {days_delta} day(s) ahead of the "
            f"{deadline:%Y-%m-%d} deadline ({window_desc}). Compliant; coach for "
            f"earlier reporting."
        )
    else:
        status = ComplianceStatus.ON_TIME
        explanation = (
            f"Reported {days_delta} day(s) ahead of the {deadline:%Y-%m-%d} "
            f"deadline ({window_desc}). Compliant."
        )

    return ComplianceResult(
        reporting_deadline=deadline,
        status=status,
        days_delta=days_delta,
        explanation=explanation,
    )
