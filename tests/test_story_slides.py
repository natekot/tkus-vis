import pytest
from helpers import entry, ledger, tkus_ledger_files

from tkus_vis.ledger import Snapshot
from tkus_vis.model import build_dataset
from tkus_vis.story import Bar, slides_for

SOURCE = (
    "Source: tkus ledger in tkus at origin/main (b6fce91). Costs are recorded list "
    "prices in USD: notional for subscription users, not what was billed."
)
BACKLOG = (
    "Includes $0.39 of install backlog: usage from before tkus was installed, "
    "recorded on its first commit."
)


def slides(files, repo="tkus", default="main"):
    snapshot = Snapshot(repo, "origin/main", "b6fce91" + "0" * 33, default, files)
    dataset, _ = build_dataset(snapshot, "t")
    return {s.slug: s for s in slides_for(dataset, dataset.views[0])}


@pytest.fixture(scope="module")
def tkus():
    return slides(tkus_ledger_files())


def test_slides_are_numbered_in_order(tkus):
    assert list(tkus) == [
        "01-headline",
        "02-weekly-spend",
        "03-spend-by-model",
        "04-where-spend-sits",
    ]


def test_headline(tkus):
    s = tkus["01-headline"]
    assert (s.kind, s.currency) == ("headline", "USD")
    assert s.title == "tkus: $66.91 of AI agent spend over 9 weeks"
    assert s.subtitle == "Recorded by tkus, Aug 13 – Oct 6, 2026"
    assert (s.hero, s.hero_label) == ("$66.91", "recorded AI agent spend")
    assert s.figures == (
        ("19", "commits with AI usage"),
        ("4", "branches with spend"),
        ("2", "models used"),
    )
    assert s.footnotes == (BACKLOG, SOURCE)


def test_weekly_spend(tkus):
    s = tkus["02-weekly-spend"]
    assert s.kind == "columns"
    assert s.title == "Spend peaked in the week of Aug 17 at $37.87"
    assert [b.label for b in s.bars] == [
        "Aug 10",
        "Aug 17",
        "Aug 24",
        "Aug 31",
        "Sep 7",
        "Sep 14",
        "Sep 21",
        "Sep 28",
        "Oct 5",
    ]
    # Label selectively: the peak and the latest week, plus a dagger on the backlog week.
    assert {b.label: b.value for b in s.bars if b.value} == {
        "Aug 17": "$37.87",
        "Sep 21": "†",
        "Oct 5": "$5.97",
    }
    assert [round(b.usd, 2) for b in s.bars][2:4] == [0.0, 0.0]
    assert s.footnotes == ("† " + BACKLOG, SOURCE)


def test_spend_by_model(tkus):
    s = tkus["03-spend-by-model"]
    assert s.kind == "bars"
    assert s.title == "claude-opus-5 accounts for 87% of spend"
    assert s.subtitle == "AI agent spend by model, via claude-code"
    assert [(b.label, b.value, b.group) for b in s.bars] == [
        ("claude-opus-5", "$58.03 · 87%", "accent"),
        ("claude-opus-5-5", "$8.88 · 13%", "accent"),
    ]
    assert s.legend == ()


def test_where_spend_sits(tkus):
    s = tkus["04-where-spend-sits"]
    assert s.title == "82% of spend was committed straight to main"
    assert [(b.label, b.value, b.group) for b in s.bars] == [
        ("main", "$54.82 · 82%", "accent"),
        ("add-tkus-log", "$10.82 · 16%", "rest"),
        ("price-opus-5-5", "$0.89 · 1%", "rest"),
        ("fix-amend-rename-attribution", "$0.39 · <1%", "rest"),
    ]
    assert s.legend == (("accent", "Committed to main"), ("rest", "Other branches"))


def test_mostly_feature_branch_spend_is_phrased_that_way():
    s = slides(
        {
            ".tkus/a/main.jsonl": ledger(entry(1.0)),
            ".tkus/a/feature.jsonl": ledger(entry(3.0)),
        }
    )["04-where-spend-sits"]
    assert s.title == "75% of spend was on branches other than main"


def test_many_branches_fold_into_other_and_keep_the_default_branch():
    files = {f".tkus/a/b{i}.jsonl": ledger(entry(float(i + 1))) for i in range(10)}
    files[".tkus/a/main.jsonl"] = ledger(entry(0.5))
    bars = slides(files)["04-where-spend-sits"].bars
    assert [b.label for b in bars] == [
        "b9",
        "b8",
        "b7",
        "b6",
        "b5",
        "b4",
        "main",
        "Other (4 branches)",
    ]
    assert bars[-1] == Bar("Other (4 branches)", 10.0, "$10.00 · 18%", "rest")


def test_many_models_fold_into_other():
    rows = [{"provider": "claude-code", "model": f"m{i}", "usd": float(i + 1)} for i in range(9)]
    s = slides({".tkus/a/main.jsonl": ledger(entry(45.0, providers=rows))})["03-spend-by-model"]
    assert [b.label for b in s.bars] == [
        "m8",
        "m7",
        "m6",
        "m5",
        "m4",
        "m3",
        "m2",
        "Other (2 models)",
    ]
    assert s.bars[-1].group == "rest"


def test_one_model_and_several_providers_are_named_plainly():
    one = slides({".tkus/a/main.jsonl": ledger(entry(1.0))})["03-spend-by-model"]
    assert one.title == "All spend was on claude-opus-5"
    two = slides(
        {
            ".tkus/a/main.jsonl": ledger(
                entry(
                    3.0,
                    providers=[
                        {"provider": "claude-code", "model": "x", "usd": 2.0},
                        {"provider": "copilot", "model": "y", "usd": 1.0},
                    ],
                )
            )
        }
    )["03-spend-by-model"]
    assert [b.label for b in two.bars] == ["x (claude-code)", "y (copilot)"]
    assert two.subtitle == "AI agent spend by model, via claude-code and copilot"


def test_spend_not_broken_down_by_model_gets_a_gray_bar():
    s = slides(
        {
            ".tkus/a/main.jsonl": ledger(
                entry(5.0, providers=[{"provider": "claude-code", "model": "x", "usd": 4.0}])
            )
        }
    )["03-spend-by-model"]
    assert s.bars[-1] == Bar("Not broken down by model", 1.0, "$1.00 · 20%", "rest")


def test_without_dates_there_is_no_weekly_slide():
    s = slides({".tkus/a/main.jsonl": ledger(entry(1.0, until=None))})
    assert list(s) == ["01-headline", "02-spend-by-model", "03-where-spend-sits"]
    assert s["01-headline"].title == "tkus: $1.00 of AI agent spend"
    assert s["01-headline"].subtitle == "Recorded by tkus"


def test_one_commit_uses_singular_labels():
    s = slides({".tkus/a/main.jsonl": ledger(entry(1.0))})["01-headline"]
    assert s.figures == (
        ("1", "commit with AI usage"),
        ("1", "branch with spend"),
        ("1", "model used"),
    )
