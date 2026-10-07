import pytest
import synthetic
from helpers import entry, ledger

from tkus_vis.ledger import Snapshot
from tkus_vis.model import build_dataset
from tkus_vis.story import Bar, slides_for

SOURCE = (
    "Source: tkus ledger in acme/widgets at main (ccccccc). Costs are recorded list "
    "prices in USD: notional for subscription users, not what was billed."
)
BACKLOG = (
    "Includes $0.50 of install backlog: usage from before tkus was installed, "
    "recorded on its first commit."
)
LEFT_OUT = "Leaves out $0.50 of install backlog, which is in the totals."


def deck_for(prs):
    snapshot = Snapshot(synthetic.REPO, "main", "c" * 40, "main", synthetic.FILES)
    dataset, _ = build_dataset(snapshot, "t", prs)
    return {s.slug.split("-", 1)[1]: s for s in slides_for(dataset, dataset.views[0])}


@pytest.fixture(scope="module")
def deck():
    return deck_for(synthetic.PRS)


def test_the_joined_deck_order(deck):
    assert list(deck) == [
        "headline",
        "cost-per-pr",
        "top-prs",
        "spend-and-prs",
        "spend-by-model",
        "where-spend-sits",
    ]


def test_headline_leads_with_coverage_and_the_median(deck):
    s = deck["headline"]
    assert s.title == "acme/widgets: $49.50 of AI agent spend over 5 weeks"
    assert s.figures == (
        ("4", "merged PRs with AI usage"),
        ("$5.50", "median cost per merged PR"),
        ("67%", "of merged PRs carry cost data"),
    )
    assert s.footnotes == (BACKLOG + " Per-PR figures leave out $0.50 of it.", SOURCE)


def three_merged_prs(files):
    """Branches a, b and c, each merged as its own PR after the usage."""
    snapshot = Snapshot(synthetic.REPO, "main", "c" * 40, "main", files)
    prs = [
        synthetic.pr(n, b, b.upper(), merged="2026-09-10T00:00:00Z") for n, b in enumerate("abc")
    ]
    dataset, _ = build_dataset(snapshot, "t", prs)
    return dataset, {s.slug.split("-", 1)[1]: s for s in slides_for(dataset, dataset.views[0])}


def test_a_pr_holding_only_install_backlog_is_left_out_and_marked():
    # The PR that installs tkus often carries nothing but the backlog entry (spec §5.6).
    _, deck = three_merged_prs(
        {
            ".tkus/dev/a.jsonl": ledger(entry(3.0)),
            ".tkus/dev/b.jsonl": ledger(entry(5.0)),
            ".tkus/dev/c.jsonl": ledger(entry(40.0, since=None)),
        }
    )
    assert deck["headline"].figures == (
        ("2", "merged PRs with AI usage"),
        ("$4.00", "median cost per merged PR"),
        ("100%", "of merged PRs carry cost data"),
    )
    assert deck["headline"].footnotes[0] == (
        "Includes $40.00 of install backlog: usage from before tkus was installed, recorded on "
        "its first commit. Per-PR figures leave out $40.00 of it."
    )
    assert deck["cost-per-pr"].values == (5.0, 3.0)
    assert deck["cost-per-pr"].footnotes == (
        "Leaves out $40.00 of install backlog, which is in the totals.",
        SOURCE,
    )


def test_when_every_merged_pr_holds_only_backlog_the_headline_still_marks_it():
    _, deck = three_merged_prs({".tkus/dev/c.jsonl": ledger(entry(40.0, since=None))})
    assert deck["headline"].figures == (
        ("0", "merged PRs with AI usage"),
        ("–", "median cost per merged PR"),
        ("33%", "of merged PRs carry cost data"),
    )
    assert deck["headline"].footnotes[0].endswith(" Per-PR figures leave out $40.00 of it.")


def test_the_headline_counts_only_prs_with_cost_in_its_currency():
    dataset, deck = three_merged_prs(
        {
            ".tkus/dev/a.jsonl": ledger(entry(3.0)),
            ".tkus/dev/b.jsonl": ledger(entry(5.0)),
            ".tkus/dev/c.jsonl": ledger(entry(4.0, currency="EUR")),
        }
    )
    assert dataset.views[0].currency == "USD"
    assert deck["headline"].figures[:2] == (
        ("2", "merged PRs with AI usage"),
        ("$4.00", "median cost per merged PR"),
    )


def test_cost_per_merged_pr(deck):
    s = deck["cost-per-pr"]
    assert s.kind == "histogram"
    assert s.title == "The median merged PR cost $5.50 in AI usage"
    assert s.subtitle == (
        "Half cost between $4.38 and $6.50. Each PR's whole AI cost, for PRs merged since Sep 1."
    )
    assert s.values == (8.0, 6.0, 5.0, 2.5)  # #13's $0.50 of backlog left out
    assert s.rule == (5.5, "median $5.50")
    assert s.footnotes == (LEFT_OUT, SOURCE)


def test_most_expensive_prs(deck):
    s = deck["top-prs"]
    assert s.title == "The 3 most expensive PRs took 88% of merged-PR spend"
    assert s.subtitle == "AI cost per merged PR, for PRs merged since Sep 1"
    assert [(b.label, b.value) for b in s.bars] == [
        ("#10 Add login", "$8.00"),
        ("#14 Fix crash again", "$6.00"),
        ("#11 Fix crash", "$5.00"),
        ("#13 Odd branch name", "$2.50 †"),
    ]
    assert s.footnotes == ("† " + LEFT_OUT, SOURCE)


def test_where_spend_sits_by_bucket(deck):
    s = deck["where-spend-sits"]
    assert s.title == "44% of spend went into merged pull requests"
    assert s.bars == (
        Bar("Merged pull requests", 22.0, "$22.00 · 44% †", "accent"),
        Bar("Open pull requests", 7.0, "$7.00 · 14%", "rest"),
        Bar("Committed straight to main", 2.0, "$2.00 · 4%", "rest"),
        Bar("No pull request found", 18.5, "$18.50 · 37%", "rest"),
    )
    assert s.legend == (("accent", "Merged pull requests"), ("rest", "Everything else"))
    assert s.footnotes == (
        "† " + BACKLOG,
        "No pull request found: branches renamed where tkus couldn't see it, deleted "
        "branches, PRs from forks, and detached commits.",
        SOURCE,
    )


def test_with_no_merged_prs_the_deck_says_so():
    deck = deck_for([synthetic.pr(15, "wip", "Work in progress")])
    assert list(deck) == ["headline", "weekly-spend", "spend-by-model", "where-spend-sits"]
    assert "No pull requests were merged since Sep 1." in deck["headline"].footnotes
    # Only #15 (open) matches: unmatched = 49.50 - 2.00 direct - 7.00 open = 40.50, or 82%.
    assert deck["where-spend-sits"].title == "82% of spend has no pull request"


def test_spend_and_merged_prs_by_week(deck):
    s = deck["spend-and-prs"]
    assert s.kind == "throughput"
    assert s.title == "6 PRs merged in 5 weeks, at most 3 in a week"
    assert s.subtitle == (
        "Spend counted when each commit's usage window ended; PRs counted when merged "
        "(weeks start Monday, UTC)"
    )
    assert [(b.label, b.usd, b.value) for b in s.bars] == [
        ("Aug 31", 15.0, ""),
        ("Sep 7", 20.0, "$20.00 †"),  # the peak, and the backlog week
        ("Sep 14", 6.0, ""),
        ("Sep 21", 7.0, ""),
        ("Sep 28", 1.5, ""),
    ]
    assert s.merges == (
        ("2026-08-31", "Aug 31", 2, 0),
        ("2026-09-07", "Sep 7", 1, 2),
        ("2026-09-14", "Sep 14", 0, 0),
        ("2026-09-21", "Sep 21", 1, 0),
        ("2026-09-28", "Sep 28", 0, 0),
    )
    assert s.footnotes == (
        "† " + BACKLOG,
        "Gray: merged PRs with no cost data, such as PRs from forks or from branches "
        "tkus didn't record.",
        SOURCE,
    )


def test_a_tie_for_the_busiest_week_names_no_single_week():
    deck = deck_for([p for p in synthetic.PRS if p.number in (10, 13)])  # Aug 31 and Sep 7
    assert deck["spend-and-prs"].title == "2 PRs merged in 5 weeks, at most 1 in a week"


def test_merges_within_one_week_need_no_weekly_peak():
    _, deck = three_merged_prs({f".tkus/dev/{b}.jsonl": ledger(entry(1.0)) for b in "abc"})
    assert deck["spend-and-prs"].title == "3 PRs merged in 1 week"
