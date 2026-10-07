import pytest
import synthetic

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
    # Task 5 adds "spend-and-prs" after "top-prs" and updates this list.
    assert list(deck) == [
        "headline",
        "cost-per-pr",
        "top-prs",
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
