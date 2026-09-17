"""Week and fiscal-year date helpers. Pure functions; a week is Monday-Sunday, identified by its Monday."""
from datetime import date, timedelta

LOOKAHEAD_WEEKS = 4


def week_start(d: date) -> date:
    """Monday of the week containing d."""
    return d - timedelta(days=d.weekday())


def current_week(today: date) -> date:
    return week_start(today)


def fy_weeks(start: date, end: date) -> list[date]:
    """Every Monday whose week overlaps the fiscal year, oldest first."""
    monday, last = week_start(start), week_start(end)
    weeks = []
    while monday <= last:
        weeks.append(monday)
        monday += timedelta(weeks=1)
    return weeks


def pickable_weeks(start: date, end: date, today: date) -> list[date]:
    """FY weeks up to a few weeks ahead of today, newest first (for the week picker)."""
    horizon = current_week(today) + timedelta(weeks=LOOKAHEAD_WEEKS)
    weeks = [w for w in fy_weeks(start, end) if w <= horizon]
    return sorted(weeks or fy_weeks(start, end)[:1], reverse=True)


def default_week(start: date, end: date, today: date) -> date:
    """Current week when it is inside the FY, otherwise the closest FY week."""
    weeks = fy_weeks(start, end)
    this_week = current_week(today)
    if this_week in weeks:
        return this_week
    return weeks[0] if this_week < weeks[0] else weeks[-1]


def week_label(monday: date) -> str:
    """'Sep 14 – Sep 20, 2026'"""
    sunday = monday + timedelta(days=6)
    return f"{monday:%b} {monday.day} – {sunday:%b} {sunday.day}, {sunday.year}"


def fy_default_dates(label: str) -> tuple[date, date]:
    """'FY26' -> (2025-10-01, 2026-09-30). Raises ValueError when the label has no year."""
    digits = "".join(ch for ch in label if ch.isdigit())
    if not digits:
        raise ValueError(f"Cannot read a year from {label!r}")
    year = int(digits)
    if year < 100:
        year += 2000
    return date(year - 1, 10, 1), date(year, 9, 30)
