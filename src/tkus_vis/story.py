"""What each infographic says: its numbers and its one-sentence takeaway. Pure.

Every sentence is generated from the dataset, so tests pin the wording against
the real tkus ledger. Charts and templates only place what this module decides.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import date, timedelta

from .model import DIRECT, CurrencyView, Dataset, WeekRow, week_of

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
    if 99 < share < 100:  # rounding would claim the whole
        return ">99%"
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


@dataclass(frozen=True)
class Bar:
    label: str
    usd: float
    value: str = ""  # text placed at the bar's end; "" places none
    group: str = "accent"  # "accent" (the subject) or "rest" (gray context)


@dataclass(frozen=True)
class Slide:
    slug: str  # file name stem, numbered by slides_for, e.g. "01-headline"
    kind: str  # "headline", "columns" or "bars"
    title: str  # the takeaway, one sentence
    subtitle: str
    currency: str
    hero: str = ""
    hero_label: str = ""
    figures: tuple[tuple[str, str], ...] = ()  # (value, label) tiles under the hero
    bars: tuple[Bar, ...] = ()
    legend: tuple[tuple[str, str], ...] = ()  # (group, label); drawn when 2+ groups
    footnotes: tuple[str, ...] = ()


def slides_for(dataset: Dataset, view: CurrencyView) -> list[Slide]:
    """The slides for one currency, numbered in reading order."""
    source = (
        f"Source: tkus ledger in {dataset.repo} at {dataset.ref} ({dataset.commit[:7]}). "
        f"Costs are recorded list prices in {view.currency}: notional for subscription "
        "users, not what was billed."
    )
    weeks = week_series(view)
    slides = [_headline(dataset, view, weeks, source)]
    if weeks:
        slides.append(_weekly(view, weeks, source))
    slides += [_models(view, source), _where(dataset, view, source)]
    return [replace(s, slug=f"{n:02d}-{s.slug}") for n, s in enumerate(slides, start=1)]


def _noun(count: int, singular: str, plural: str) -> str:
    return singular if count == 1 else plural


def _backlog(view: CurrencyView) -> str:
    if not view.backlog_entries:
        return ""
    return (
        f"Includes {money(view.backlog_usd, view.currency)} of install backlog: usage "
        "from before tkus was installed, recorded on its first commit."
    )


def _dates(view: CurrencyView) -> list[date]:
    days = []
    for row in view.audit:
        try:
            days.append(date.fromisoformat((row.until or row.at or "")[:10]))
        except ValueError:
            continue
    return sorted(days)


def _share(usd: float, view: CurrencyView) -> str:
    return f"{money(usd, view.currency)} · {percent(usd, view.total)}"


def _headline(dataset: Dataset, view: CurrencyView, weeks: list[WeekRow], source: str) -> Slide:
    days = _dates(view)
    models = [m for m in view.models if m.provider != "(none)"]
    over = f" over {len(weeks)} {_noun(len(weeks), 'week', 'weeks')}" if weeks else ""
    return Slide(
        slug="headline",
        kind="headline",
        title=f"{dataset.repo}: {money(view.total, view.currency)} of AI agent spend{over}",
        subtitle="Recorded by tkus" + (f", {period(days[0], days[-1])}" if days else ""),
        currency=view.currency,
        hero=money(view.total, view.currency),
        hero_label="recorded AI agent spend",
        figures=(
            (str(view.entries), _noun(view.entries, "commit", "commits") + " with AI usage"),
            (
                str(len(view.branches)),
                _noun(len(view.branches), "branch", "branches") + " with spend",
            ),
            (str(len(models)), _noun(len(models), "model", "models") + " used"),
        ),
        footnotes=tuple(note for note in (_backlog(view), source) if note),
    )


def _weekly(view: CurrencyView, weeks: list[WeekRow], source: str) -> Slide:
    backlog_weeks = {week_of(row.until or row.at) for row in view.audit if row.backlog}
    peak = max(weeks, key=lambda w: w.usd)  # the earliest of equal peaks
    labelled = (peak.week, weeks[-1].week)
    bars = []
    for w in weeks:
        value = money(w.usd, view.currency) if w.usd and w.week in labelled else ""
        if w.week in backlog_weeks:
            value = f"{value} †".strip()
        bars.append(Bar(day(date.fromisoformat(w.week)), w.usd, value))
    if len(weeks) > 1:
        title = (
            f"Spend peaked in the week of {day(date.fromisoformat(peak.week))} "
            f"at {money(peak.usd, view.currency)}"
        )
    else:
        title = f"All spend fell in the week of {day(date.fromisoformat(peak.week))}"
    notes = []
    if backlog_weeks & {w.week for w in weeks}:
        notes.append("† " + _backlog(view))
    undated = math.fsum(w.usd for w in view.weeks if w.week == "unknown")
    if undated:
        notes.append(f"{money(undated, view.currency)} of spend has no date and is not shown.")
    notes.append(source)
    return Slide(
        slug="weekly-spend",
        kind="columns",
        title=title,
        subtitle="AI agent spend per week (weeks start Monday, UTC)",
        currency=view.currency,
        bars=tuple(bars),
        footnotes=tuple(notes),
    )


def _fold(bars: list[Bar], noun: str, view: CurrencyView) -> list[Bar]:
    """Keep the biggest MAX_BARS - 1 bars and fold the rest into one "Other" bar."""
    if len(bars) <= MAX_BARS:
        return bars
    keep, tail = bars[: MAX_BARS - 1], bars[MAX_BARS - 1 :]
    usd = math.fsum(b.usd for b in tail)
    return keep + [Bar(f"Other ({len(tail)} {noun})", usd, _share(usd, view), "rest")]


def _models(view: CurrencyView, source: str) -> Slide:
    named = [m for m in view.models if m.provider != "(none)"]
    providers = sorted({m.provider for m in named})

    def name(m) -> str:
        return m.model if len(providers) <= 1 else f"{m.model} ({m.provider})"

    bars = _fold([Bar(name(m), m.usd, _share(m.usd, view)) for m in named], "models", view)
    bars += [
        Bar("Not broken down by model", m.usd, _share(m.usd, view), "rest")
        for m in view.models
        if m.provider == "(none)"
    ]
    if not named:
        title = "No spend is broken down by model"
    elif len(named) == 1 and len(bars) == 1:
        title = f"All spend was on {name(named[0])}"
    else:
        title = f"{name(named[0])} accounts for {percent(named[0].usd, view.total)} of spend"
    via = f", via {' and '.join(providers)}" if providers else ""
    return Slide(
        slug="spend-by-model",
        kind="bars",
        title=title,
        subtitle="AI agent spend by model" + via,
        currency=view.currency,
        bars=tuple(bars),
        footnotes=(source,),
    )


def _where(dataset: Dataset, view: CurrencyView, source: str) -> Slide:
    rows = list(view.branches)  # most expensive first
    shown, tail = rows, []
    if len(rows) > MAX_BARS:
        shown, tail = rows[: MAX_BARS - 1], rows[MAX_BARS - 1 :]
        default = next((r for r in tail if r.bucket == DIRECT), None)
        if default is not None:  # the default branch is the story: always show it
            shown, tail = (
                shown[:-1] + [default],
                [r for r in tail if r is not default] + [shown[-1]],
            )
            shown.sort(key=lambda r: -r.usd)
    bars = [
        Bar(r.branch, r.usd, _share(r.usd, view), "accent" if r.bucket == DIRECT else "rest")
        for r in shown
    ]
    if tail:
        usd = math.fsum(r.usd for r in tail)
        bars.append(Bar(f"Other ({len(tail)} branches)", usd, _share(usd, view), "rest"))
    direct = view.buckets[DIRECT]
    if direct >= view.total / 2:
        title = (
            f"{percent(direct, view.total)} of spend was committed straight "
            f"to {dataset.default_branch}"
        )
    else:
        title = (
            f"{percent(view.total - direct, view.total)} of spend was on branches "
            f"other than {dataset.default_branch}"
        )
    groups = {b.group for b in bars}
    legend = (("accent", f"Committed to {dataset.default_branch}"), ("rest", "Other branches"))
    return Slide(
        slug="where-spend-sits",
        kind="bars",
        title=title,
        subtitle="AI agent spend by branch. Branches are not yet matched to pull requests.",
        currency=view.currency,
        bars=tuple(bars),
        legend=legend if len(groups) > 1 else (),
        footnotes=(source,),
    )
