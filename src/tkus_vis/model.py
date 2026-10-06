"""Join and bucket rules (brief §4–5). Pure: plain data in, plain data out."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from .ledger import Entry, Problem, ProviderUsage, Snapshot, branch_key, parse_ledger

DIRECT = "direct"  # <default>.jsonl: commits made straight to the default branch
UNJOINED = "unjoined"  # every other branch; milestone 2 splits it into PR-attributed and unmatched

# Provider rows may not add up to an entry's usd exactly. Past this, the rest gets its own row.
_TOLERANCE = 1e-6


@dataclass(frozen=True)
class BranchRow:
    branch: str
    bucket: str
    entries: int
    usd: float
    backlog_usd: float


@dataclass(frozen=True)
class ModelRow:
    provider: str
    model: str
    reqs: int
    usd: float


@dataclass(frozen=True)
class WeekRow:
    week: str  # Monday (UTC) that starts the week, YYYY-MM-DD, or "unknown"
    entries: int
    usd: float


@dataclass(frozen=True)
class AuditRow:
    """One ledger entry, for the dataset file. Carries no identity (brief §6)."""

    branch: str
    bucket: str
    at: str | None
    since: str | None
    until: str | None
    parent: str | None
    usd: float
    backlog: bool
    providers: tuple[ProviderUsage, ...]


@dataclass(frozen=True)
class CurrencyView:
    currency: str
    total: float
    entries: int
    backlog_usd: float
    backlog_entries: int
    buckets: dict[str, float]  # sums to total
    branches: tuple[BranchRow, ...]  # most expensive first
    models: tuple[ModelRow, ...]  # most expensive first
    weeks: tuple[WeekRow, ...]  # oldest first, "unknown" last
    audit: tuple[AuditRow, ...]


@dataclass(frozen=True)
class Dataset:
    repo: str
    ref: str
    commit: str
    default_branch: str
    generated_at: str
    ledger_files: int
    problems: int
    views: tuple[CurrencyView, ...]  # one per currency, never summed across


def build_dataset(snapshot: Snapshot, generated_at: str) -> tuple[Dataset, list[Problem]]:
    entries: list[Entry] = []
    problems: list[Problem] = []
    for path in sorted(snapshot.files):
        found, issues = parse_ledger(path, snapshot.files[path])
        entries.extend(found)
        problems.extend(issues)
    default_key = branch_key(snapshot.default_branch)
    by_currency: dict[str, list[Entry]] = defaultdict(list)
    for e in entries:
        by_currency[e.currency].append(e)
    views = sorted(
        (_view(currency, items, default_key) for currency, items in by_currency.items()),
        key=lambda v: (-v.total, v.currency),
    )
    dataset = Dataset(
        repo=snapshot.repo,
        ref=snapshot.ref,
        commit=snapshot.commit,
        default_branch=snapshot.default_branch,
        generated_at=generated_at,
        ledger_files=len(snapshot.files),
        problems=len(problems),
        views=tuple(views),
    )
    return dataset, problems


def bucket_of(branch: str, default_key: str) -> str:
    return DIRECT if branch == default_key else UNJOINED


def week_of(stamp: str | None) -> str:
    """The Monday starting stamp's UTC week.

    Ledger timestamps are UTC ISO 8601, so the date is the first ten characters,
    which is how `tkus rollup --by date` reads them.
    """
    try:
        day = date.fromisoformat((stamp or "")[:10])
    except ValueError:
        return "unknown"
    return (day - timedelta(days=day.weekday())).isoformat()


def _sum(entries: Iterable[Entry]) -> float:
    return math.fsum(e.usd for e in entries)


def _view(currency: str, entries: list[Entry], default_key: str) -> CurrencyView:
    total = _sum(entries)
    by_branch: dict[str, list[Entry]] = defaultdict(list)
    by_week: dict[str, list[Entry]] = defaultdict(list)
    for e in entries:
        by_branch[e.branch].append(e)
        by_week[week_of(e.when)].append(e)
    branches = sorted(
        (
            BranchRow(
                branch=name,
                bucket=bucket_of(name, default_key),
                entries=len(items),
                usd=_sum(items),
                backlog_usd=_sum(e for e in items if e.backlog),
            )
            for name, items in by_branch.items()
        ),
        key=lambda row: (-row.usd, row.branch),
    )
    weeks = [
        WeekRow(week, len(items), _sum(items))
        for week, items in sorted(by_week.items(), key=lambda kv: (kv[0] == "unknown", kv[0]))
    ]
    return CurrencyView(
        currency=currency,
        total=total,
        entries=len(entries),
        backlog_usd=_sum(e for e in entries if e.backlog),
        backlog_entries=sum(1 for e in entries if e.backlog),
        buckets={
            bucket: _sum(e for e in entries if bucket_of(e.branch, default_key) == bucket)
            for bucket in (DIRECT, UNJOINED)
        },
        branches=tuple(branches),
        models=_models(entries, total),
        weeks=tuple(weeks),
        audit=tuple(
            AuditRow(
                e.branch,
                bucket_of(e.branch, default_key),
                e.at,
                e.since,
                e.until,
                e.parent,
                e.usd,
                e.backlog,
                e.providers,
            )
            for e in entries
        ),
    )


def _models(entries: list[Entry], total: float) -> tuple[ModelRow, ...]:
    usd: dict[tuple[str, str], list[float]] = defaultdict(list)
    reqs: dict[tuple[str, str], int] = defaultdict(int)
    for e in entries:
        for p in e.providers:
            usd[(p.provider, p.model)].append(p.usd)
            reqs[(p.provider, p.model)] += p.reqs
    rows = [
        ModelRow(provider, model, reqs[(provider, model)], math.fsum(values))
        for (provider, model), values in usd.items()
    ]
    rest = total - math.fsum(row.usd for row in rows)
    if abs(rest) > _TOLERANCE:
        rows.append(ModelRow("(none)", "(not broken down by model)", 0, rest))
    return tuple(sorted(rows, key=lambda row: (-row.usd, row.provider, row.model)))
