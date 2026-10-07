"""Join and bucket rules (brief §4–5). Pure: plain data in, plain data out."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from .ledger import Entry, Problem, ProviderUsage, Snapshot, branch_key, parse_ledger

DIRECT = "direct"  # <default>.jsonl: commits made straight to the default branch
UNJOINED = "unjoined"  # every other branch, when no pull requests were read
PR = "pr"  # matched to a pull request
UNMATCHED = "unmatched"  # no pull request: unseen renames, deleted branches, fork PRs, detached
PARTIAL = "partial"  # a branch row whose entries are only partly in pull requests

_NEVER = datetime.max.replace(tzinfo=timezone.utc)  # when an open PR stops taking work

# Provider rows may not add up to an entry's usd exactly. Past this, the rest gets its own row.
_TOLERANCE = 1e-6


@dataclass(frozen=True)
class PullRequest:
    """A pull request as the git host reports it: the join's second input."""

    number: int
    title: str
    url: str
    state: str  # "open" or "closed", as the host reports it
    head: str  # the head branch's name
    created_at: str
    merged_at: str | None
    closed_at: str | None
    fork: bool  # the head branch lives in another repository

    @property
    def status(self) -> str:
        if self.merged_at:
            return "merged"
        return "open" if self.state == "open" else "closed"


@dataclass(frozen=True)
class PrRow:
    number: int
    title: str
    url: str
    status: str  # "merged", "open" or "closed" (without merging)
    merged_at: str | None
    branch: str
    entries: int
    usd: float  # the PR's whole cost, install backlog included: it is in the totals
    backlog_usd: float  # the install backlog inside usd; per-PR views leave it out


@dataclass(frozen=True)
class MergeWeek:
    week: str
    merged: int
    with_cost: int


@dataclass(frozen=True)
class Coverage:
    """How much delivered work carries cost data (spec §5.4)."""

    since: str  # YYYY-MM-DD: merged PRs count from the first recorded usage
    merged: int
    with_cost: int
    weekly: tuple[MergeWeek, ...]


@dataclass(frozen=True)
class BranchRow:
    branch: str
    bucket: str
    entries: int
    usd: float
    backlog_usd: float
    prs: tuple[int, ...] = ()  # the pull requests its spend went into, ascending


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
    pr: int | None = None  # the pull request this entry's spend went into


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
    prs: tuple[PrRow, ...] = ()  # most expensive first; empty when no PRs were read


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
    coverage: Coverage | None = None  # None when no pull requests were read


def build_dataset(
    snapshot: Snapshot, generated_at: str, prs: list[PullRequest] | None = None
) -> tuple[Dataset, list[Problem]]:
    entries: list[Entry] = []
    problems: list[Problem] = []
    for path in sorted(snapshot.files):
        found, issues = parse_ledger(path, snapshot.files[path])
        entries.extend(found)
        problems.extend(issues)
    default_key = branch_key(snapshot.default_branch)
    matches = None if prs is None else _match(entries, prs, default_key)
    by_currency: dict[str, list[Entry]] = defaultdict(list)
    for e in entries:
        by_currency[e.currency].append(e)
    views = sorted(
        (_view(currency, items, default_key, matches) for currency, items in by_currency.items()),
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
        coverage=None if prs is None or matches is None else _coverage(entries, prs, matches),
    )
    return dataset, problems


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


def _instant(stamp: str | None) -> datetime | None:
    if not stamp:
        return None
    try:
        moment = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _end(pr: PullRequest) -> datetime:
    return _instant(pr.merged_at or pr.closed_at) or _NEVER


def _match(
    entries: list[Entry], prs: list[PullRequest], default_key: str
) -> dict[tuple[str, int], PullRequest]:
    """Each entry's pull request, keyed by (ledger path, line). Spec §4."""
    index: dict[str, list[PullRequest]] = defaultdict(list)
    for pr in prs:
        key = branch_key(pr.head)
        if pr.fork or key == default_key:  # forks are unmatched; main is the direct bucket
            continue
        index[key].append(pr)
    for candidates in index.values():
        candidates.sort(key=lambda p: (_end(p), p.number))
    found = {}
    for e in entries:
        candidates = index.get(e.branch, [])
        when = _instant(e.when)
        if when is None:  # undated: only an unambiguous PR will do
            pick = candidates[0] if len(candidates) == 1 else None
        else:  # the earliest PR still taking work when the usage ended
            pick = next((p for p in candidates if _end(p) >= when), None)
        if pick is not None:
            found[(e.path, e.line)] = pick
    return found


def _coverage(
    entries: list[Entry], prs: list[PullRequest], matches: dict[tuple[str, int], PullRequest]
) -> Coverage:
    days = []
    for e in entries:
        try:
            days.append(date.fromisoformat((e.when or "")[:10]).isoformat())
        except ValueError:
            continue
    since = min(days, default="")
    costed = {p.number for p in matches.values()}
    merged = [p for p in prs if p.merged_at and p.merged_at[:10] >= since]
    weekly: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for p in merged:
        row = weekly[week_of(p.merged_at)]
        row[0] += 1
        row[1] += p.number in costed
    return Coverage(
        since=since,
        merged=len(merged),
        with_cost=sum(p.number in costed for p in merged),
        weekly=tuple(MergeWeek(w, n, c) for w, (n, c) in sorted(weekly.items())),
    )


def _view(
    currency: str,
    entries: list[Entry],
    default_key: str,
    matches: dict[tuple[str, int], PullRequest] | None,
) -> CurrencyView:
    def pr_of(e: Entry) -> PullRequest | None:
        return None if matches is None else matches.get((e.path, e.line))

    def bucket(e: Entry) -> str:
        if e.branch == default_key:
            return DIRECT
        if matches is None:
            return UNJOINED
        return PR if pr_of(e) else UNMATCHED

    total = _sum(entries)
    by_branch: dict[str, list[Entry]] = defaultdict(list)
    by_week: dict[str, list[Entry]] = defaultdict(list)
    by_pr: dict[int, list[Entry]] = defaultdict(list)
    pulls: dict[int, PullRequest] = {}
    for e in entries:
        by_branch[e.branch].append(e)
        by_week[week_of(e.when)].append(e)
        pr = pr_of(e)
        if pr is not None:
            by_pr[pr.number].append(e)
            pulls[pr.number] = pr
    branches = []
    for name, items in by_branch.items():
        kinds = {bucket(e) for e in items}
        branches.append(
            BranchRow(
                branch=name,
                bucket=kinds.pop() if len(kinds) == 1 else PARTIAL,
                entries=len(items),
                usd=_sum(items),
                backlog_usd=_sum(e for e in items if e.backlog),
                prs=tuple(sorted({pr.number for e in items if (pr := pr_of(e))})),
            )
        )
    branches.sort(key=lambda row: (-row.usd, row.branch))
    weeks = [
        WeekRow(week, len(items), _sum(items))
        for week, items in sorted(by_week.items(), key=lambda kv: (kv[0] == "unknown", kv[0]))
    ]
    prs = sorted(
        (
            PrRow(
                number=n,
                title=pulls[n].title,
                url=pulls[n].url,
                status=pulls[n].status,
                merged_at=pulls[n].merged_at,
                branch=branch_key(pulls[n].head),
                entries=len(items),
                usd=_sum(items),
                backlog_usd=_sum(e for e in items if e.backlog),
            )
            for n, items in by_pr.items()
        ),
        key=lambda row: (-row.usd, row.number),
    )
    keys = (DIRECT, UNJOINED) if matches is None else (DIRECT, PR, UNMATCHED)
    audit = []
    for e in entries:
        pr = pr_of(e)
        audit.append(
            AuditRow(
                e.branch,
                bucket(e),
                e.at,
                e.since,
                e.until,
                e.parent,
                e.usd,
                e.backlog,
                e.providers,
                pr=pr.number if pr else None,
            )
        )
    return CurrencyView(
        currency=currency,
        total=total,
        entries=len(entries),
        backlog_usd=_sum(e for e in entries if e.backlog),
        backlog_entries=sum(1 for e in entries if e.backlog),
        buckets={k: _sum(e for e in entries if bucket(e) == k) for k in keys},
        branches=tuple(branches),
        models=_models(entries, total),
        weeks=tuple(weeks),
        audit=tuple(audit),
        prs=tuple(prs),
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
