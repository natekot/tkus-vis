"""A small made-up repository for the PR join, with every number worked out by hand.

Totals: direct 2.00 + PR 29.00 + unmatched 18.50 = 49.50 (USD).
Coverage since 2026-09-01: 6 merged PRs (#10, #11, #12 fork, #13, #14, #16); 4 carry cost.
"""

from helpers import entry, ledger

from tkus_vis.model import PullRequest

REPO = "acme/widgets"

FILES = {
    ".tkus/alice/main.jsonl": ledger(entry(2.0, until="2026-09-01T10:00:00Z")),  # direct
    ".tkus/alice/feature/login.jsonl": ledger(  # #10, with bob's file below
        entry(1.0, until="2026-09-02T10:00:00Z"), entry(3.0, until="2026-09-03T10:00:00Z")
    ),
    ".tkus/bob/feature/login.jsonl": ledger(entry(4.0, until="2026-09-03T12:00:00Z")),
    ".tkus/alice/fix.jsonl": ledger(  # reused name: #11, then #14, then no PR
        entry(5.0, until="2026-09-05T10:00:00Z"),
        entry(6.0, until="2026-09-20T10:00:00Z"),
        entry(1.5, until="2026-09-30T10:00:00Z"),
    ),
    ".tkus/alice/wip.jsonl": ledger(entry(7.0, until="2026-09-22T10:00:00Z")),  # #15, open
    ".tkus/alice/old-name.jsonl": ledger(entry(8.0, until="2026-09-08T10:00:00Z")),  # no PR
    ".tkus/carol/patch-1.jsonl": ledger(entry(9.0, until="2026-09-08T11:00:00Z")),  # fork #12
    ".tkus/alice/odd-name.jsonl": ledger(  # #13 has head "odd:name"; first line is backlog
        entry(0.5, since=None, until="2026-09-08T09:00:00Z"),
        entry(2.5, until="2026-09-08T12:00:00Z"),
    ),
}


def pr(number, head, title, merged=None, closed=None, created="2026-08-01T00:00:00Z", fork=False):
    state = "closed" if (merged or closed) else "open"
    return PullRequest(
        number=number,
        title=title,
        url=f"https://github.com/{REPO}/pull/{number}",
        state=state,
        head=head,
        created_at=created,
        merged_at=merged,
        closed_at=closed or merged,
        fork=fork,
    )


PRS = [
    pr(9, "ancient", "Old work", merged="2026-08-01T00:00:00Z"),  # before tkus: not a gap
    pr(10, "feature/login", "Add login", merged="2026-09-04T00:00:00Z"),
    pr(11, "fix", "Fix crash", merged="2026-09-06T00:00:00Z"),
    pr(12, "patch-1", "Typo fix from a fork", merged="2026-09-12T00:00:00Z", fork=True),
    pr(13, "odd:name", "Odd branch name", merged="2026-09-09T00:00:00Z"),
    pr(14, "fix", "Fix crash again", merged="2026-09-21T12:00:00Z", created="2026-09-15T00:00:00Z"),
    pr(15, "wip", "Work in progress"),
    pr(16, "no-ledger", "Merged without tkus", merged="2026-09-10T00:00:00Z"),
    pr(18, "abandoned", "Abandoned idea", closed="2026-09-16T00:00:00Z"),
]
