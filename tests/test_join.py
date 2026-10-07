import math
from dataclasses import replace

import pytest
import synthetic
from helpers import branch_table, entry, ledger, tkus_ledger_files

from tkus_vis.ledger import Snapshot
from tkus_vis.model import (
    DIRECT,
    PARTIAL,
    PR,
    UNJOINED,
    UNMATCHED,
    Coverage,
    MergeWeek,
    build_dataset,
)
from tkus_vis.render import render_html


def joined(files=synthetic.FILES, prs=synthetic.PRS):
    snapshot = Snapshot(synthetic.REPO, "main", "c" * 40, "main", files)
    return build_dataset(snapshot, "t", prs)[0]


@pytest.fixture(scope="module")
def usd():
    return joined().views[0]


def test_buckets_split_into_pr_direct_and_unmatched(usd):
    assert usd.total == pytest.approx(49.5)
    assert usd.buckets == pytest.approx({DIRECT: 2.0, PR: 29.0, UNMATCHED: 18.5})


def test_per_pr_costs_sum_to_the_pr_bucket_with_nothing_counted_twice(usd):
    assert math.fsum(p.usd for p in usd.prs) == pytest.approx(usd.buckets[PR])
    assert [(p.number, p.status, p.usd, p.backlog_usd, p.entries) for p in usd.prs] == [
        (10, "merged", 8.0, 0.0, 3),
        (15, "open", 7.0, 0.0, 1),
        (14, "merged", 6.0, 0.0, 1),
        (11, "merged", 5.0, 0.0, 1),
        (13, "merged", 3.0, 0.5, 2),
    ]


def test_identities_on_one_branch_join_one_pr(usd):
    assert {a.pr for a in usd.audit if a.branch == "feature/login"} == {10}


def test_a_reused_branch_name_goes_to_the_pr_open_at_the_time(usd):
    assert [a.pr for a in usd.audit if a.branch == "fix"] == [11, 14, None]
    assert {b.branch: b.bucket for b in usd.branches}["fix"] == PARTIAL


def test_pr_heads_are_sanitised_before_matching(usd):
    assert {a.pr for a in usd.audit if a.branch == "odd-name"} == {13}


def test_fork_prs_and_branches_without_prs_are_unmatched(usd):
    buckets = {b.branch: b.bucket for b in usd.branches}
    assert (buckets["patch-1"], buckets["old-name"], buckets["wip"]) == (UNMATCHED, UNMATCHED, PR)


def test_the_default_branch_is_never_a_pr():
    files = {".tkus/a/main.jsonl": ledger(entry(1.0))}
    prs = [synthetic.pr(1, "main", "Release", merged="2026-09-09T00:00:00Z")]
    view = joined(files, prs).views[0]
    assert view.buckets == pytest.approx({DIRECT: 1.0, PR: 0.0, UNMATCHED: 0.0})


def test_an_undated_entry_matches_only_an_unambiguous_pr():
    files = {
        ".tkus/a/solo.jsonl": ledger(entry(1.0, until=None)),
        ".tkus/a/twice.jsonl": ledger(entry(2.0, until=None)),
    }
    prs = [
        synthetic.pr(1, "solo", "One", merged="2026-09-09T00:00:00Z"),
        synthetic.pr(2, "twice", "First", merged="2026-09-01T00:00:00Z"),
        synthetic.pr(3, "twice", "Second", merged="2026-09-09T00:00:00Z"),
    ]
    audit = joined(files, prs).views[0].audit
    assert {a.branch: a.pr for a in audit} == {"solo": 1, "twice": None}


def test_coverage_counts_merged_prs_since_the_first_recorded_usage():
    assert joined().coverage == Coverage(
        since="2026-09-01",
        merged=6,
        with_cost=4,
        weekly=(
            MergeWeek("2026-08-31", 2, 2),
            MergeWeek("2026-09-07", 3, 1),
            MergeWeek("2026-09-21", 1, 1),
        ),
    )


def test_without_prs_nothing_changes():
    dataset, _ = build_dataset(Snapshot("r", "main", "c" * 40, "main", tkus_ledger_files()), "t")
    assert dataset.coverage is None and dataset.views[0].prs == ()
    assert set(dataset.views[0].buckets) == {DIRECT, UNJOINED}


def test_each_branch_lists_the_prs_its_spend_went_into(usd):
    assert {b.branch: b.prs for b in usd.branches} == {
        "main": (),
        "feature/login": (10,),
        "fix": (11, 14),
        "wip": (15,),
        "old-name": (),
        "patch-1": (),
        "odd-name": (13,),
    }


def test_the_report_links_branches_to_their_prs():
    html = render_html(joined())
    headers, links = branch_table(html)
    pull = f"https://github.com/{synthetic.REPO}/pull/"
    assert headers == ["Branch", "Cost (USD)"]
    assert links == {
        "fix": [pull + "11", pull + "14"],  # a reused name lists each PR
        "patch-1": [],  # from a fork
        "feature/login": [pull + "10"],
        "old-name": [],
        "wip": [pull + "15"],
        "odd-name": [pull + "13"],  # head "odd:name"
        "main": [],
    }
    assert (
        f'<a href="{pull}10" title="#10 Add login (merged)"><code>feature/login</code></a>' in html
    )
    assert "<code>fix</code> (<a " in html
    assert "Each branch links to the pull request" in html


def test_the_report_names_the_joined_buckets():
    html = render_html(joined())
    assert "In pull requests" in html and "No pull request found" in html
    assert "Partly in pull requests" not in html


@pytest.mark.parametrize("url", ["", "javascript:alert(1)"])
def test_only_web_addresses_become_links(url):
    files = {".tkus/a/topic.jsonl": ledger(entry(1.0, until="2026-09-02T10:00:00Z"))}
    merged = synthetic.pr(1, "topic", "Topic", merged="2026-09-03T00:00:00Z")
    dataset = joined(files, [replace(merged, url=url)])
    assert dataset.views[0].branches[0].prs == (1,)
    html = render_html(dataset)
    assert branch_table(html)[1] == {"topic": []}
    assert "<a " not in html
