import json

import pytest
from helpers import Outline, entry, ledger, tkus_ledger_files

from tkus_vis.ledger import Snapshot
from tkus_vis.model import build_dataset
from tkus_vis.render import render_html, render_json


def dataset(files):
    built, _ = build_dataset(
        Snapshot("demo", "origin/main", "c" * 40, "main", files), "2026-10-06T12:00:00Z"
    )
    return built


def test_page_outline():
    assert Outline(render_html(dataset(tkus_ledger_files()))).landmarks == [
        "header#summary",
        "h1: AI agent spend: demo",
        "section#spend-usd",
        "h2: Spend by branch",
        "h2: Spend by week",
        "h2: Spend by model",
        "section#methodology",
        "h2: Coverage and methodology",
    ]


def test_headline_figures():
    html = render_html(dataset(tkus_ledger_files()))
    assert "66.91 USD" in html and "54.82" in html and "0.39" in html  # total, main, backlog


@pytest.mark.parametrize("files", [tkus_ledger_files(), {}])
def test_page_needs_no_network(files):
    assert Outline(render_html(dataset(files))).fetches == []


def test_untrusted_names_are_escaped():
    evil = "<img src=x onerror=alert(1)>"
    html = render_html(
        dataset(
            {
                f".tkus/a/{evil}.jsonl": ledger(
                    entry(1.0, providers=[{"provider": "claude-code", "model": evil, "usd": 1.0}])
                ),
            }
        )
    )
    assert evil not in html and "&lt;img src=x onerror=alert(1)&gt;" in html
    assert Outline(html).fetches == []


def test_no_ledger_says_unknown_not_zero():
    html = render_html(dataset({}))
    assert "section#no-ledger" in Outline(html).landmarks
    assert "unknown, not zero" in html and "0.00" not in html


def test_mixed_currencies_render_separately_with_a_warning():
    html = render_html(
        dataset(
            {
                ".tkus/a/main.jsonl": ledger(entry(1.0)),
                ".tkus/a/eu.jsonl": ledger(entry(2.0, currency="EUR")),
            }
        )
    )
    landmarks = Outline(html).landmarks
    assert "section#spend-usd" in landmarks and "section#spend-eur" in landmarks
    assert "never summed" in html


def test_dataset_json_has_the_figures_and_no_identities():
    files = {
        ".tkus/alice/main.jsonl": ledger(entry(1.0)),
        ".tkus/bob/feature/x.jsonl": ledger(entry(2.0)),
    }
    text = render_json(dataset(files))
    data = json.loads(text)
    assert data["generator"].startswith("tkus-vis ")
    assert data["views"][0]["total"] == pytest.approx(3.0)
    assert {row["branch"] for row in data["views"][0]["audit"]} == {"main", "feature/x"}
    assert "alice" not in text and "bob" not in text
