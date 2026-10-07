import re

import pytest
import synthetic

from tkus_vis import theme
from tkus_vis.charts import chart_spec, chart_svg
from tkus_vis.ledger import Snapshot
from tkus_vis.model import build_dataset
from tkus_vis.story import Bar, Slide, slides_for


def drawn(svg):
    return re.findall(r"<text[^>]*>([^<]*)</text>", svg)


def width(svg):
    return float(re.search(r'width="([\d.]+)"', svg).group(1))


@pytest.fixture(scope="module")
def deck():
    snapshot = Snapshot(synthetic.REPO, "main", "c" * 40, "main", synthetic.FILES)
    dataset, _ = build_dataset(snapshot, "t", synthetic.PRS)
    return {s.slug.split("-", 1)[1]: s for s in slides_for(dataset, dataset.views[0])}


def test_histogram_bins_costs_and_marks_the_median(deck):
    spec = chart_spec(deck["cost-per-pr"])
    bars, rule, label = spec["layer"]
    assert bars["encoding"]["x"]["bin"] and bars["encoding"]["y"]["aggregate"] == "count"
    assert rule["encoding"]["x"]["datum"] == 5.5
    assert label["encoding"]["text"]["value"] == "median $5.50"
    svg = chart_svg(deck["cost-per-pr"])
    assert "median $5.50" in drawn(svg) and width(svg) <= theme.CHART_WIDTH


def test_throughput_is_two_charts_on_one_time_axis_never_two_y_axes(deck):
    spec = chart_spec(deck["spend-and-prs"])
    assert len(spec["vconcat"]) == 2
    assert spec["resolve"]["scale"]["x"] == "shared"
    color = spec["vconcat"][1]["encoding"]["color"]
    assert color["scale"]["domain"] == ["With cost data", "No cost data"]
    svg = chart_svg(deck["spend-and-prs"])
    texts = drawn(svg)
    assert "Sep 7" in texts and "With cost data" in texts and "$20.00 †" in texts
    assert width(svg) <= theme.CHART_WIDTH


def test_axis_titles_are_slide_sized():
    axis = theme.vega_config()["axis"]
    assert (axis["titleFontSize"], axis["titleColor"]) == (theme.AXIS_SIZE, theme.INK_SECONDARY)


def test_the_median_label_sits_above_the_bars_not_on_them(deck):
    label = chart_spec(deck["cost-per-pr"])["layer"][2]
    assert label["mark"]["baseline"] == "bottom" and label["encoding"]["y"]["value"] < 0


def test_merged_pr_counts_stack_cost_data_first_and_skip_empty_weeks(deck):
    merged = chart_spec(deck["spend-and-prs"])["vconcat"][1]
    assert all(row["count"] > 0 for row in merged["data"]["values"])
    assert merged["encoding"]["order"]["field"] == "rank"
    assert merged["encoding"]["color"]["legend"]["orient"] == "bottom"  # beside its own chart


def axis_labels(svg, title):
    """The tick labels of the axis with this title, in drawing order."""
    axis = re.search(rf"aria-label=\"[XY]-axis titled '{re.escape(title)}'.*?role-axis-label", svg)
    block = svg[axis.end() :].split("</g>", 1)[0]
    return re.findall(r"<text[^>]*>([^<]*)</text>", block)


def test_a_histogram_of_few_prs_counts_in_whole_numbers_once_each():
    slide = Slide(
        "cost-per-pr", "histogram", "t", "s", "USD", values=(9.0, 5.0, 5.0), rule=(5.0, "m")
    )
    assert axis_labels(chart_svg(slide), "Merged PRs") == ["0", "1", "2"]


def test_weeks_of_few_merges_count_in_whole_numbers_once_each():
    slide = Slide(
        "spend-and-prs",
        "throughput",
        "t",
        "s",
        "USD",
        bars=(Bar("Sep 7", 10.0, key="2026-09-07"), Bar("Sep 14", 5.0, key="2026-09-14")),
        merges=(("2026-09-07", "Sep 7", 1, 0), ("2026-09-14", "Sep 14", 1, 1)),
    )
    assert axis_labels(chart_svg(slide), "PRs merged") == ["0", "1", "2"]
