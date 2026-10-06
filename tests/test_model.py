import math

import pytest
from helpers import entry, ledger, tkus_ledger_files

from tkus_vis.ledger import Snapshot
from tkus_vis.model import DIRECT, UNJOINED, build_dataset, week_of


def build(files, default="main"):
    dataset, problems = build_dataset(
        Snapshot("repo", "main", "c" * 40, default, files), "2026-10-06T12:00:00Z"
    )
    return dataset, problems


def view(dataset, currency):
    return next(v for v in dataset.views if v.currency == currency)


MIXED = {
    ".tkus/alice/main.jsonl": ledger(
        entry(1.25, until="2026-09-07T23:59:59Z"),
        entry(2.5, since=None, until="2026-09-08T00:00:01Z"),
    ),
    ".tkus/alice/feature/x.jsonl": ledger(entry(3.0, until="2026-09-15T10:00:00Z")),
    ".tkus/bob/feature/x.jsonl": ledger(entry(4.0, until="2026-09-16T10:00:00Z")),
    ".tkus/bob/eu.jsonl": ledger(entry(7.0, currency="EUR")),
    ".tkus/carol/split.jsonl": ledger(
        entry(
            5.0,
            providers=[
                {"provider": "claude-code", "model": "a", "usd": 3.0},
                {"provider": "copilot", "model": "b", "usd": 1.5},
            ],
        )
    ),
}


def test_real_tkus_ledger_is_pinned():
    dataset, problems = build(tkus_ledger_files())
    assert problems == [] and dataset.ledger_files == 5
    [v] = dataset.views
    assert (v.currency, v.entries) == ("USD", 19)
    assert v.total == pytest.approx(66.9073434, abs=1e-6)
    assert {b.branch: b.entries for b in v.branches} == {
        "main": 15,
        "add-tkus-log": 2,
        "price-opus-5-5": 1,
        "fix-amend-rename-attribution": 1,
    }
    assert {b.branch: b.usd for b in v.branches} == pytest.approx(
        {
            "main": 54.8159045,
            "add-tkus-log": 10.8152545,
            "price-opus-5-5": 0.8865604,
            "fix-amend-rename-attribution": 0.389624,
        },
        abs=1e-6,
    )
    assert v.buckets == pytest.approx({DIRECT: 54.8159045, UNJOINED: 12.0914389}, abs=1e-6)
    assert (v.backlog_entries, v.backlog_usd) == (1, pytest.approx(0.389624))


def test_every_breakdown_sums_to_the_total():
    dataset, _ = build(MIXED)
    for v in dataset.views:
        for parts in (
            v.buckets.values(),
            [b.usd for b in v.branches],
            [w.usd for w in v.weeks],
            [m.usd for m in v.models],
            [a.usd for a in v.audit],
        ):
            assert math.fsum(parts) == pytest.approx(v.total, abs=1e-9)
        assert sum(b.entries for b in v.branches) == v.entries == len(v.audit)
        assert sum(w.entries for w in v.weeks) == v.entries


def test_currencies_are_never_summed():
    dataset, _ = build(MIXED)
    assert [(v.currency, v.total) for v in dataset.views] == [
        ("USD", pytest.approx(15.75)),
        ("EUR", pytest.approx(7.0)),
    ]


def test_identities_on_one_branch_are_one_branch():
    row = {b.branch: b for b in view(build(MIXED)[0], "USD").branches}["feature/x"]
    assert (row.entries, row.usd, row.bucket) == (2, 7.0, UNJOINED)


def test_the_default_branch_file_is_the_direct_bucket():
    usd = view(build(MIXED)[0], "USD")
    assert usd.buckets == pytest.approx({DIRECT: 3.75, UNJOINED: 12.0})


def test_the_default_branch_is_compared_after_sanitising():
    dataset, _ = build({".tkus/a/release-1.jsonl": ledger(entry(2.0))}, default="release:1")
    assert dataset.views[0].buckets[DIRECT] == 2.0


def test_backlog_is_kept_in_totals_and_flagged():
    usd = view(build(MIXED)[0], "USD")
    assert (usd.backlog_entries, usd.backlog_usd) == (1, 2.5)
    assert {b.branch: b.backlog_usd for b in usd.branches}["main"] == 2.5
    assert [a.backlog for a in usd.audit if a.branch == "main"] == [False, True]


def test_weeks_start_on_monday_utc_and_follow_until():
    assert week_of("2026-09-07T23:59:59Z") == "2026-09-07"  # a Monday
    assert week_of("2026-09-13T23:59:59Z") == "2026-09-07"  # the Sunday after
    assert week_of("2026-09-06T12:00:00Z") == "2026-08-31"
    assert week_of(None) == week_of("garbage") == "unknown"
    usd = view(build(MIXED)[0], "USD")
    assert [(w.week, w.usd) for w in usd.weeks] == [("2026-09-07", 8.75), ("2026-09-14", 7.0)]


def test_model_rows_include_what_providers_do_not_explain():
    rows = {(m.provider, m.model): m.usd for m in view(build(MIXED)[0], "USD").models}
    assert rows == pytest.approx(
        {
            ("claude-code", "claude-opus-5"): 10.75,
            ("claude-code", "a"): 3.0,
            ("copilot", "b"): 1.5,
            ("(none)", "(not broken down by model)"): 0.5,
        }
    )


def test_the_dataset_carries_no_identities():
    dataset, _ = build(MIXED)
    assert not any(name in repr(dataset) for name in ("alice", "bob", "carol"))


def test_no_ledger_means_no_views():
    dataset, problems = build({})
    assert dataset.views == () and dataset.ledger_files == 0 and problems == []
