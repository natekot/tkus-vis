"""What each infographic says: its numbers and its one-sentence takeaway. Pure.

Every sentence is generated from the dataset, so tests pin the wording against
the real tkus ledger. Charts and templates only place what this module decides.
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date, timedelta

from .model import DIRECT, PR, UNMATCHED, CurrencyView, Dataset, PrRow, WeekRow, week_of

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
    key: str = ""  # a stable, unique id for the bar's position, e.g. the week's ISO date


@dataclass(frozen=True)
class Slide:
    slug: str  # file name stem, numbered by slides_for, e.g. "01-headline"
    kind: str  # "headline", "columns", "bars" or "figure" (one number, no chart)
    title: str  # the takeaway, one sentence
    subtitle: str
    currency: str
    hero: str = ""
    hero_label: str = ""
    figures: tuple[tuple[str, str], ...] = ()  # (value, label) tiles under the hero
    bars: tuple[Bar, ...] = ()
    legend: tuple[tuple[str, str], ...] = ()  # (group, label); drawn when 2+ groups
    footnotes: tuple[str, ...] = ()
    values: tuple[float, ...] = ()  # a histogram's raw values
    rule: tuple[float, str] | None = None  # a marked value and its label, e.g. the median
    merges: tuple[tuple[str, str, int, int], ...] = ()  # week, label, with cost, without


def slides_for(dataset: Dataset, view: CurrencyView) -> list[Slide]:
    """The slides for one currency, numbered in reading order."""
    source = (
        f"Source: tkus ledger in {dataset.repo} at {dataset.ref} ({dataset.commit[:7]}). "
        f"Costs are recorded list prices in {view.currency}: notional for subscription "
        "users, not what was billed."
    )
    weeks = week_series(view)
    if dataset.coverage is None:
        slides = [_headline(dataset, view, weeks, source)]
        if weeks:
            slides.append(_weekly(view, weeks, source))
        slides += [_models(view, source), _where(dataset, view, source)]
    else:
        merged = _merged(dataset, view)
        slides = [_headline_joined(dataset, view, weeks, merged, source)]
        if len(merged) >= 2:
            slides.append(_cost_per_pr(dataset, view, merged, source))
        if merged:
            slides.append(_top_prs(dataset, view, merged, source))
        if not dataset.coverage.merged and weeks:  # Task 5 adds the throughput slide here
            slides.append(_weekly(view, weeks, source))
        slides += [_models(view, source), _where_joined(dataset, view, source)]
    slides = [
        _figure(s) if s.kind in ("bars", "columns") and len(s.bars) == 1 else s for s in slides
    ]
    return [replace(s, slug=f"{n:02d}-{s.slug}") for n, s in enumerate(slides, start=1)]


def _figure(slide: Slide) -> Slide:
    """One bar is not a chart: show its number instead (dataviz: no one-bar bar charts)."""
    bar = slide.bars[0]
    label = f"week of {bar.label}" if slide.kind == "columns" else bar.label
    if "†" in bar.value:
        label += " †"
    return replace(
        slide,
        kind="figure",
        hero=money(bar.usd, slide.currency),
        hero_label=label,
        bars=(),
        legend=(),
    )


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
        bars.append(Bar(day(date.fromisoformat(w.week)), w.usd, value, key=w.week))
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
    if any(not w.entries for w in weeks):
        notes.append(
            "Weeks at $0 had no commits with AI usage; work in progress is counted "
            "in the week its commit lands."
        )
    undated = math.fsum(w.usd for w in view.weeks if w.week == "unknown")
    if undated:
        notes.append(f"{money(undated, view.currency)} of spend has no date and is not shown.")
    notes.append(source)
    return Slide(
        slug="weekly-spend",
        kind="columns",
        title=title,
        subtitle=(
            "AI agent spend per week, counted when each commit's usage window ended "
            "(weeks start Monday, UTC)"
        ),
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
        footnotes=tuple(note for note in (_backlog(view), source) if note),
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

    def marked(text: str, rows) -> str:
        return f"{text} †" if any(r.backlog_usd for r in rows) else text

    bars = [
        Bar(
            r.branch,
            r.usd,
            marked(_share(r.usd, view), [r]),
            "accent" if r.bucket == DIRECT else "rest",
        )
        for r in shown
    ]
    if tail:
        usd = math.fsum(r.usd for r in tail)
        bars.append(
            Bar(f"Other ({len(tail)} branches)", usd, marked(_share(usd, view), tail), "rest")
        )
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
        footnotes=(("† " + _backlog(view),) if view.backlog_entries else ()) + (source,),
    )


def _cost(p: PrRow) -> float:
    """A PR's cost for per-PR views: whole cost less install backlog (spec §5.6)."""
    return p.usd - p.backlog_usd


def _since(dataset: Dataset) -> str:
    since = dataset.coverage.since if dataset.coverage else ""
    return day(date.fromisoformat(since)) if since else "tkus started recording"


def _merged(dataset: Dataset, view: CurrencyView) -> list[PrRow]:
    since = dataset.coverage.since if dataset.coverage else ""
    return [
        p
        for p in view.prs
        if p.status == "merged" and (p.merged_at or "")[:10] >= since and _cost(p) > 0
    ]


def _left_out(view: CurrencyView, prs: list[PrRow]) -> str:
    backlog = math.fsum(p.backlog_usd for p in prs)
    if not backlog:
        return ""
    return f"Leaves out {money(backlog, view.currency)} of install backlog, which is in the totals."


def _headline_joined(
    dataset: Dataset, view: CurrencyView, weeks: list[WeekRow], merged: list[PrRow], source: str
) -> Slide:
    base = _headline(dataset, view, weeks, source)
    cov = dataset.coverage
    if not cov.merged:
        note = f"No pull requests were merged since {_since(dataset)}."
        return replace(base, footnotes=(*base.footnotes[:-1], note, base.footnotes[-1]))
    costs = [_cost(p) for p in merged]
    median = money(statistics.median(costs), view.currency) if costs else "–"
    return replace(
        base,
        figures=(
            (
                str(cov.with_cost),
                _noun(cov.with_cost, "merged PR", "merged PRs") + " with AI usage",
            ),
            (median, "median cost per merged PR"),
            (percent(cov.with_cost, cov.merged), "of merged PRs carry cost data"),
        ),
    )


def _cost_per_pr(dataset: Dataset, view: CurrencyView, merged: list[PrRow], source: str) -> Slide:
    costs = sorted((_cost(p) for p in merged), reverse=True)
    middle = statistics.median(costs)
    scope = f"Each PR's whole AI cost, for PRs merged since {_since(dataset)}."
    subtitle = scope
    if len(costs) >= 4:
        low, _, high = statistics.quantiles(costs, n=4, method="inclusive")
        spread = f"Half cost between {money(low, view.currency)} and {money(high, view.currency)}."
        subtitle = f"{spread} {scope}"
    return Slide(
        slug="cost-per-pr",
        kind="histogram",
        title=f"The median merged PR cost {money(middle, view.currency)} in AI usage",
        subtitle=subtitle,
        currency=view.currency,
        values=tuple(costs),
        rule=(middle, f"median {money(middle, view.currency)}"),
        footnotes=tuple(n for n in (_left_out(view, merged), source) if n),
    )


def _top_prs(dataset: Dataset, view: CurrencyView, merged: list[PrRow], source: str) -> Slide:
    ranked = sorted(merged, key=lambda p: (-_cost(p), p.number))
    shown = ranked[:MAX_BARS]
    bars = [
        Bar(
            f"#{p.number} {p.title}",
            _cost(p),
            money(_cost(p), view.currency) + (" †" if p.backlog_usd else ""),
            key=str(p.number),
        )
        for p in shown
    ]
    spend = math.fsum(_cost(p) for p in ranked)
    if len(ranked) >= 4:
        top = math.fsum(_cost(p) for p in ranked[:3])
        title = f"The 3 most expensive PRs took {percent(top, spend)} of merged-PR spend"
    elif len(ranked) == 1:
        title = f"#{ranked[0].number} was the only merged PR with AI usage"
    else:
        cost = money(_cost(ranked[0]), view.currency)
        title = f"#{ranked[0].number} was the most expensive merged PR, at {cost}"
    subtitle = f"AI cost per merged PR, for PRs merged since {_since(dataset)}"
    if len(ranked) > len(shown):
        subtitle += f" (the top {len(shown)} of {len(ranked)})"
    marked = _left_out(view, [p for p in shown if p.backlog_usd])
    return Slide(
        slug="top-prs",
        kind="bars",
        title=title,
        subtitle=subtitle,
        currency=view.currency,
        bars=tuple(bars),
        footnotes=(("† " + marked,) if marked else ()) + (source,),
    )


_WHERE = {  # bucket -> (bar label, title phrase), in reading order
    "merged": ("Merged pull requests", "went into merged pull requests"),
    "open": ("Open pull requests", "is in pull requests still open"),
    "closed": ("Closed without merging", "went into pull requests closed without merging"),
    DIRECT: ("Committed straight to {branch}", "was committed straight to {branch}"),
    UNMATCHED: ("No pull request found", "has no pull request"),
}


def _where_joined(dataset: Dataset, view: CurrencyView, source: str) -> Slide:
    status = {p.number: p.status for p in view.prs}
    amounts: dict[str, list[float]] = defaultdict(list)
    backlog = set()
    for row in view.audit:
        key = status[row.pr] if row.bucket == PR and row.pr is not None else row.bucket
        amounts[key].append(row.usd)
        if row.backlog:
            backlog.add(key)
    totals = {k: math.fsum(amounts[k]) for k in _WHERE if amounts.get(k)}
    lead = max(totals, key=lambda k: totals[k])  # the earliest in reading order on a tie

    def name(k: str, which: int) -> str:
        return _WHERE[k][which].format(branch=dataset.default_branch)

    bars = [
        Bar(
            name(k, 0),
            totals[k],
            _share(totals[k], view) + (" †" if k in backlog else ""),
            "accent" if k == lead else "rest",
        )
        for k in totals
    ]
    notes = []
    if backlog:
        notes.append("† " + _backlog(view))
    if UNMATCHED in totals:
        notes.append(
            "No pull request found: branches renamed where tkus couldn't see it, deleted "
            "branches, PRs from forks, and detached commits."
        )
    notes.append(source)
    legend = (("accent", name(lead, 0)), ("rest", "Everything else")) if len(bars) > 1 else ()
    return Slide(
        slug="where-spend-sits",
        kind="bars",
        title=f"{percent(totals[lead], view.total)} of spend {name(lead, 1)}",
        subtitle="AI agent spend by where it ended up",
        currency=view.currency,
        bars=tuple(bars),
        legend=legend,
        footnotes=tuple(notes),
    )
