"""What each infographic says: its numbers and its one-sentence takeaway. Pure.

Every sentence is generated from the dataset, so tests pin the wording against
the real tkus ledger. Charts and templates only place what this module decides.
"""

from __future__ import annotations

from datetime import date, timedelta

from .model import CurrencyView, WeekRow

# Past this many bars, the tail folds into one "Other" bar (the dataviz series ladder).
MAX_BARS = 8


def money(value: float, currency: str) -> str:
    size = abs(value)
    if size < 1000:
        text = f"{size:,.2f}"
    elif size < 1_000_000:
        text = f"{size:,.0f}"
    else:
        text = f"{size / 1_000_000:,.1f}M"
    sign = "-" if value < 0 and text.strip("0.,M") else ""
    return f"{sign}${text}" if currency == "USD" else f"{sign}{text} {currency}"


def percent(part: float, whole: float) -> str:
    if whole <= 0:
        return "–"
    share = 100 * part / whole
    if 0 < share < 1:
        return "<1%"
    return f"{share:.0f}%"


def day(d: date) -> str:
    return f"{d:%b} {d.day}"


def period(first: date, last: date) -> str:
    if first == last:
        return f"{day(first)}, {first.year}"
    if first.year == last.year:
        return f"{day(first)} – {day(last)}, {last.year}"
    return f"{day(first)}, {first.year} – {day(last)}, {last.year}"


def week_series(view: CurrencyView) -> list[WeekRow]:
    """Every week from the first to the last with spend, quiet weeks included as zero.

    A time axis with missing weeks would squeeze time; zero is the honest value for
    a week in which nothing was recorded.
    """
    known = {w.week: w for w in view.weeks if w.week != "unknown"}
    if not known:
        return []
    monday, end = date.fromisoformat(min(known)), date.fromisoformat(max(known))
    weeks = []
    while monday <= end:
        key = monday.isoformat()
        weeks.append(known.get(key, WeekRow(key, 0, 0.0)))
        monday += timedelta(weeks=1)
    return weeks
