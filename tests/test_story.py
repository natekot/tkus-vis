from datetime import date

import pytest
from helpers import entry, ledger

from tkus_vis.ledger import Snapshot
from tkus_vis.model import build_dataset
from tkus_vis.story import day, money, percent, period, week_series


def view_of(files):
    dataset, _ = build_dataset(Snapshot("demo", "main", "c" * 40, "main", files), "t")
    return dataset.views[0]


@pytest.mark.parametrize(
    "value, currency, text",
    [
        (66.9073434, "USD", "$66.91"),
        (1234.6, "USD", "$1,235"),
        (2_500_000, "USD", "$2.5M"),
        (-0.5, "USD", "-$0.50"),
        (-0.001, "USD", "$0.00"),
        (3, "EUR", "3.00 EUR"),
    ],
)
def test_money(value, currency, text):
    assert money(value, currency) == text


@pytest.mark.parametrize(
    "part, whole, text",
    [(54.8159045, 66.9073434, "82%"), (1, 3, "33%"), (0.001, 10, "<1%"), (1, 0, "–")],
)
def test_percent(part, whole, text):
    assert percent(part, whole) == text


def test_day_and_period():
    assert day(date(2026, 9, 7)) == "Sep 7"
    assert period(date(2026, 8, 13), date(2026, 10, 6)) == "Aug 13 – Oct 6, 2026"
    assert period(date(2026, 8, 13), date(2026, 8, 13)) == "Aug 13, 2026"


def test_period_names_both_years_across_a_year_boundary():
    assert period(date(2025, 12, 30), date(2026, 1, 4)) == "Dec 30, 2025 – Jan 4, 2026"


def test_week_series_includes_quiet_weeks_as_zero():
    view = view_of(
        {
            ".tkus/a/main.jsonl": ledger(
                entry(1.0, until="2026-09-08T10:00:00Z"),  # week of Sep 7
                entry(2.0, until="2026-09-22T10:00:00Z"),  # week of Sep 21
            ),
        }
    )
    assert [(w.week, w.entries, w.usd) for w in week_series(view)] == [
        ("2026-09-07", 1, 1.0),
        ("2026-09-14", 0, 0.0),
        ("2026-09-21", 1, 2.0),
    ]


def test_week_series_leaves_out_undated_entries():
    view = view_of({".tkus/a/main.jsonl": ledger(entry(1.0, until=None))})
    assert week_series(view) == []
