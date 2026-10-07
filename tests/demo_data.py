"""A believable demo repository for looking at the joined slides (not for pinning numbers).

files, prs = demo()   # about 12 weeks, ~30 merged PRs, open and closed PRs, a fork PR,
                      # a branch with no PR, install backlog, and direct commits to main
"""

import random
from datetime import datetime, timedelta, timezone

from helpers import entry, ledger
from synthetic import pr

TITLES = [
    "Add SSO login",
    "Fix flaky checkout test",
    "Speed up search index",
    "Refactor billing",
    "Add CSV export",
    "Upgrade React",
    "Fix timezone bug",
    "Rate-limit the API",
    "Add audit log",
    "Improve onboarding copy",
    "Cache product images",
    "Fix memory leak",
]


def demo(seed: int = 7):
    rng = random.Random(seed)
    start = datetime(2026, 7, 6, tzinfo=timezone.utc)  # a Monday
    files: dict[str, list[str]] = {}
    prs = []

    def stamp(t):
        return t.strftime("%Y-%m-%dT%H:%M:%SZ")

    def add(identity, branch, usd, when, **kw):
        files.setdefault(f".tkus/{identity}/{branch}.jsonl", []).append(
            entry(round(usd, 4), until=stamp(when), **kw)
        )

    add("alice", "main", 41.0, start + timedelta(hours=3), since=None)  # install backlog
    for n in range(36):
        opened = start + timedelta(days=rng.uniform(0, 80))
        title = TITLES[n % len(TITLES)]
        branch = f"feature/{title.lower().replace(' ', '-')}-{n}"
        who = rng.choice(["alice", "bob", "carol", "dan"])
        work = opened
        for _ in range(rng.randint(1, 6)):
            work += timedelta(hours=rng.uniform(2, 30))
            add(who, branch, rng.lognormvariate(1.2, 0.9), work)
        done = work + timedelta(hours=rng.uniform(1, 48))
        state = "open" if n >= 33 else ("closed" if n == 32 else "merged")
        prs.append(
            pr(
                100 + n,
                branch,
                title,
                merged=stamp(done) if state == "merged" else None,
                closed=stamp(done) if state == "closed" else None,
                created=stamp(opened),
            )
        )
    for _ in range(14):  # direct commits to main
        add(
            "alice",
            "main",
            rng.lognormvariate(0.8, 0.6),
            start + timedelta(days=rng.uniform(0, 84)),
        )
    add("bob", "spike/renamed-away", 12.0, start + timedelta(days=40))  # no PR: unmatched
    fork_merged = stamp(start + timedelta(days=30))
    prs.append(pr(99, "patch-1", "Fix typo (from a fork)", merged=fork_merged, fork=True))
    return {path: ledger(*lines) for path, lines in files.items()}, prs
