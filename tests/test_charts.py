import re

import pytest
from helpers import entry, ledger, tkus_ledger_files

from tkus_vis import theme
from tkus_vis.charts import chart_spec, chart_svg
from tkus_vis.ledger import Snapshot
from tkus_vis.model import build_dataset
from tkus_vis.story import slides_for


def slides(files):
    dataset, _ = build_dataset(Snapshot("tkus", "origin/main", "b" * 40, "main", files), "t")
    return {s.slug.split("-", 1)[1]: s for s in slides_for(dataset, dataset.views[0])}


def drawn_text(svg: str) -> list[str]:
    """The strings Vega actually draws (aria-label attributes repeat the data in full)."""
    return re.findall(r"<text[^>]*>([^<]*)</text>", svg)


@pytest.fixture(scope="module")
def tkus():
    return slides(tkus_ledger_files())


def test_the_headline_has_no_chart(tkus):
    assert chart_spec(tkus["headline"]) is None and chart_svg(tkus["headline"]) is None


def test_weekly_columns_follow_the_mark_specs(tkus):
    spec = chart_spec(tkus["weekly-spend"])
    bar = spec["layer"][0]["mark"]
    assert (bar["type"], bar["color"]) == ("bar", theme.ACCENT)
    assert (bar["size"], bar["cornerRadiusEnd"]) == (theme.BAR_MAX, theme.CORNER)
    assert spec["encoding"]["y"]["axis"]["format"] == "$,.0f"
    assert [v["label"] for v in spec["data"]["values"]][:3] == ["Aug 10", "Aug 17", "Aug 24"]
    assert spec["config"]["font"] == theme.FONT


def test_single_series_bars_have_no_legend(tkus):
    color = chart_spec(tkus["spend-by-model"])["layer"][0]["encoding"]["color"]
    assert color["legend"] is None


def test_emphasis_bars_have_a_legend_in_accent_and_gray(tkus):
    color = chart_spec(tkus["where-spend-sits"])["layer"][0]["encoding"]["color"]
    assert color["scale"] == {
        "domain": ["Committed to main", "Other branches"],
        "range": [theme.ACCENT, theme.DEEMPHASIS],
    }
    assert color["legend"] is not None


def test_long_names_are_truncated_not_overflowing(tkus):
    axis = chart_spec(tkus["where-spend-sits"])["encoding"]["y"]["axis"]
    assert axis["labelLimit"] == theme.LABEL_LIMIT


@pytest.mark.parametrize("name", ["weekly-spend", "spend-by-model", "where-spend-sits"])
def test_charts_render_to_svg_at_chart_width(tkus, name):
    svg = chart_svg(tkus[name])
    assert "<svg" in svg[:200]
    assert re.search(rf'width="{theme.CHART_WIDTH}(\.0)?"', svg)


def test_rendered_charts_carry_the_story_labels(tkus):
    weekly = drawn_text(chart_svg(tkus["weekly-spend"]))
    assert "$37.87" in weekly and "Aug 17" in weekly and "†" in weekly
    assert "$58.03 · 87%" in drawn_text(chart_svg(tkus["spend-by-model"]))


def test_untrusted_names_are_escaped_in_svg():
    evil = "<img src=x onerror=alert(1)>"
    s = slides(
        {
            ".tkus/a/main.jsonl": ledger(
                entry(1.0, providers=[{"provider": "claude-code", "model": evil, "usd": 1.0}])
            )
        }
    )
    svg = chart_svg(s["spend-by-model"])
    assert "<img" not in svg and "&lt;img" in svg


def test_legend_labels_are_not_truncated(tkus):
    drawn = drawn_text(chart_svg(tkus["where-spend-sits"]))
    assert "Committed to main" in drawn and "Other branches" in drawn
