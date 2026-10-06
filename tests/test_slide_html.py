import pytest
from helpers import Outline, entry, ledger, tkus_ledger_files

from tkus_vis.charts import chart_svg
from tkus_vis.export import slide_html
from tkus_vis.ledger import Snapshot
from tkus_vis.model import build_dataset
from tkus_vis.story import slides_for


def slides(files):
    dataset, _ = build_dataset(Snapshot("tkus", "origin/main", "b" * 40, "main", files), "t")
    return {s.slug: s for s in slides_for(dataset, dataset.views[0])}


@pytest.fixture(scope="module")
def tkus():
    return slides(tkus_ledger_files())


def test_headline_layout(tkus):
    html = slide_html(tkus["01-headline"], None)
    assert Outline(html).landmarks == [
        "main#01-headline",
        "h1: tkus: $66.91 of AI agent spend over 9 weeks",
    ]
    for text in (
        "$66.91",
        "recorded AI agent spend",
        "19",
        "commits with AI usage",
        "Aug 13 – Oct 6, 2026",
        "Includes $0.39 of install backlog",
    ):
        assert text in html
    assert "<svg" not in html


def test_chart_layout_embeds_the_svg(tkus):
    slide = tkus["02-weekly-spend"]
    html = slide_html(slide, chart_svg(slide))
    assert Outline(html).landmarks == [
        "main#02-weekly-spend",
        "h1: Spend peaked in the week of Aug 17 at $37.87",
    ]
    assert html.count("<svg") >= 1 and "Source: tkus ledger in tkus" in html


def test_slides_are_fixed_size_and_load_nothing(tkus):
    for slide in tkus.values():
        html = slide_html(slide, chart_svg(slide))
        assert Outline(html).fetches == []
        assert "width: 1920px" in html and "height: 1080px" in html
        assert "size: 1920px 1080px" in html  # the PDF page


def test_untrusted_names_in_titles_are_escaped():
    evil = "<img src=x onerror=alert(1)>"
    s = slides(
        {
            ".tkus/a/main.jsonl": ledger(
                entry(1.0, providers=[{"provider": "claude-code", "model": evil, "usd": 1.0}])
            )
        }
    )["03-spend-by-model"]
    html = slide_html(s, chart_svg(s))
    assert evil not in html and Outline(html).fetches == []
