"""The tkus ledger file format ("Ledger format" in the tkus README).

Pure: no git, no I/O. tkus-vis depends on the documented format only, never on
tkus itself, so the path rules are reimplemented here to match tkus's
repoledger._sanitize / _branch_path and __main__._ledger_scope.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass

LEDGER_DIR = ".tkus"

# Characters Windows forbids in filenames. tkus replaces each with "-".
_UNSAFE = re.compile(r'[<>:"\\|?*\x00-\x1f]')


def sanitize_segment(name: str, fallback: str) -> str:
    name = _UNSAFE.sub("-", (name or "").strip())
    name = name.strip(". ")  # Windows rejects leading/trailing dots and spaces
    return name or fallback


def branch_key(name: str) -> str:
    """A branch name as tkus files it: each "/" segment sanitised separately.

    PR head refs and the default branch must pass through this before they are
    compared with ledger paths, or names with forbidden characters never match.
    A blank name files under "detached", as tkus's branch_name does.
    """
    if not name.strip():
        return "detached"
    return "/".join(sanitize_segment(part, "-") for part in name.strip().split("/"))


def split_ledger_path(rel: str) -> tuple[str, str]:
    """(identity, branch) for a path under .tkus/, grouped as `tkus rollup` does."""
    parts = rel.split("/")
    if len(parts) <= 2:
        return "unknown", rel
    return parts[1], "/".join(parts[2:]).rsplit(".jsonl", 1)[0]


@dataclass(frozen=True)
class ProviderUsage:
    provider: str
    model: str
    reqs: int
    usd: float


@dataclass(frozen=True)
class Problem:
    """A ledger line that was skipped or read with a correction."""

    path: str
    line: int
    message: str


@dataclass(frozen=True)
class Entry:
    path: str  # ledger file, e.g. .tkus/alice/feature/x.jsonl
    line: int  # 1-based line number in that file
    identity: str
    branch: str
    at: str | None
    since: str | None
    until: str | None
    parent: str | None
    currency: str
    usd: float
    backlog: bool  # since is null: the first entry after install, may hold weeks of usage
    providers: tuple[ProviderUsage, ...]

    @property
    def when(self) -> str | None:
        """The clock for spend over time: when the entry's usage window ended."""
        return self.until or self.at


@dataclass(frozen=True)
class Snapshot:
    """Every ledger file in one commit of one repository: the collect stage's output."""

    repo: str  # display name
    ref: str  # the ref that was read, e.g. origin/main
    commit: str  # the full SHA it resolved to
    default_branch: str  # as git names it; compare via branch_key()
    files: dict[str, str]  # ledger path -> text, for every .jsonl under .tkus/


def parse_ledger(path: str, text: str) -> tuple[list[Entry], list[Problem]]:
    """Every entry in one ledger file. A corrupt line is reported, never fatal."""
    identity, branch = split_ledger_path(path)
    entries: list[Entry] = []
    problems: list[Problem] = []
    for number, raw in enumerate(text.split("\n"), start=1):
        stripped = raw.strip()  # also drops the \r of CRLF ledgers
        if not stripped:
            continue
        try:
            obj = json.loads(stripped)
        except ValueError:
            problems.append(Problem(path, number, "skipped: not valid JSON"))
            continue
        if not isinstance(obj, dict):
            problems.append(Problem(path, number, "skipped: not a JSON object"))
            continue
        usd, note = _money(obj.get("usd"))
        if note:
            problems.append(Problem(path, number, note))
        entries.append(
            Entry(
                path=path,
                line=number,
                identity=identity,
                branch=branch,
                at=_text(obj.get("at")),
                since=_text(obj.get("since")),
                until=_text(obj.get("until")),
                parent=_text(obj.get("parent")),
                currency=_text(obj.get("currency")) or "USD",  # tkus's own default
                usd=usd,
                backlog=obj.get("since") is None,
                providers=_providers(obj.get("providers")),
            )
        )
    return entries, problems


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _money(value: object) -> tuple[float, str | None]:
    """An entry's usd, read the way `tkus rollup` reads it: float(usd or 0)."""
    if value is None:
        return 0.0, "usd is missing; counted as 0"
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return 0.0, "usd is not a number; counted as 0"
    try:
        number = float(value)
    except ValueError:
        return 0.0, "usd is not a number; counted as 0"
    if not math.isfinite(number):
        return 0.0, "usd is not a finite number; counted as 0"
    return number, ("usd is a string; read as a number" if isinstance(value, str) else None)


def _providers(value: object) -> tuple[ProviderUsage, ...]:
    if not isinstance(value, list):
        return ()
    rows = []
    for row in value:
        if not isinstance(row, dict):
            continue
        reqs = row.get("reqs")
        rows.append(
            ProviderUsage(
                provider=str(row.get("provider") or "unknown"),
                model=str(row.get("model") or "unknown"),
                reqs=reqs if isinstance(reqs, int) and not isinstance(reqs, bool) else 0,
                usd=_money(row.get("usd"))[0],
            )
        )
    return tuple(rows)
