"""Totals reconcile with `tkus rollup --json` (brief §5, rule 5).

tkus runs as a subprocess oracle, from source at $TKUS_SRC (default ../tkus).
It is never imported. `rollup` reads the worktree of tracked files, so every
repo here is a clean checkout of the ref tkus-vis reads.
"""

import json
import math
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import pytest
from helpers import GIT_ENV, entry, git, ledger, tkus_ledger_files

from tkus_vis.collect import read_local
from tkus_vis.model import build_dataset

TKUS_SRC = Path(os.environ.get("TKUS_SRC", Path(__file__).resolve().parents[2] / "tkus"))

pytestmark = pytest.mark.skipif(
    not (TKUS_SRC / "tkus" / "__main__.py").is_file(),
    reason=f"tkus source not found at {TKUS_SRC}; set TKUS_SRC to a tkus checkout",
)


def rollup(repo: Path) -> dict:
    proc = subprocess.run(
        [sys.executable, "-m", "tkus", "rollup", "--json", "--by", "branch"],
        cwd=repo,
        env={**GIT_ENV, "PYTHONPATH": str(TKUS_SRC)},
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(proc.stdout)


def ours(repo: Path, **kwargs) -> tuple[float, dict[str, tuple[int, float]]]:
    dataset, _ = build_dataset(read_local(str(repo), **kwargs), "t")
    for v in dataset.views:
        assert math.fsum(v.buckets.values()) == pytest.approx(v.total, abs=1e-9)
    # rollup sums every currency together, so compare like with like here only.
    groups: dict[str, list] = defaultdict(lambda: [0, 0.0])
    for v in dataset.views:
        for b in v.branches:
            groups[b.branch][0] += b.entries
            groups[b.branch][1] += b.usd
    return math.fsum(v.total for v in dataset.views), {k: (n, u) for k, (n, u) in groups.items()}


def assert_reconciles(repo: Path, **kwargs) -> None:
    total, groups = ours(repo, **kwargs)
    expected = rollup(repo)
    assert total == pytest.approx(expected["total"], abs=1e-6)
    assert {k: n for k, (n, _) in groups.items()} == {
        g["name"]: g["entries"] for g in expected["groups"]
    }
    assert {k: u for k, (_, u) in groups.items()} == pytest.approx(
        {g["name"]: g["usd"] for g in expected["groups"]}, abs=1e-6
    )


def test_real_tkus_ledger(make_repo):
    assert_reconciles(make_repo(tkus_ledger_files()).path, default_branch="main")


def test_edge_cases(make_repo):
    repo = make_repo(
        {
            ".tkus/alice/feature/x.jsonl": ledger(
                entry(1.0), "{corrupt", entry(2.0, extra_field=1)
            ),
            ".tkus/bob/feature/x.jsonl": ledger(entry(4.0, since=None)),
            ".tkus/bob/main.jsonl": ledger(entry(0.5)).replace("\n", "\r\n"),
            ".tkus/carol/eu.jsonl": ledger(entry(7.0, currency="EUR")),
            ".tkus/stray.jsonl": ledger(entry(0.25)),
            ".tkus/dave/notes.txt": "ignored\n",
        }
    )
    assert_reconciles(repo.path, default_branch="main")


def test_history_is_not_summed_after_a_rename(make_repo):
    first = [entry(1.0, until="2026-09-01T00:00:00Z"), entry(2.0, until="2026-09-02T00:00:00Z")]
    repo = make_repo({".tkus/alice/old-name.jsonl": ledger(*first)})
    git(repo.path, "mv", ".tkus/alice/old-name.jsonl", ".tkus/alice/new-name.jsonl")
    repo.write(
        {".tkus/alice/new-name.jsonl": ledger(*first, entry(4.0, until="2026-09-03T00:00:00Z"))}
    )
    repo.commit("rename")
    assert_reconciles(repo.path, default_branch="main")
    total, groups = ours(repo.path, default_branch="main")
    assert total == pytest.approx(7.0) and list(groups) == ["new-name"]


def test_live_tkus_repository():
    if git(TKUS_SRC, "status", "--porcelain", "--", ".tkus").strip():
        pytest.skip("tkus has uncommitted ledger changes, and rollup reads the worktree")
    assert_reconciles(TKUS_SRC, ref="HEAD", default_branch="main")


@pytest.mark.xfail(
    strict=True,
    reason=(
        "tkus 0.10.0's rollup lists files with `git ls-files` without -z, so a non-ASCII "
        "path comes back quoted and is skipped. tkus-vis reads it. Report upstream."
    ),
)
def test_non_ascii_paths_reconcile(make_repo):
    repo = make_repo(
        {
            ".tkus/zoë/fix/ünïcode.jsonl": ledger(entry(1.0)),
            ".tkus/alice/main.jsonl": ledger(entry(2.0)),
        }
    )
    assert_reconciles(repo.path, default_branch="main")
