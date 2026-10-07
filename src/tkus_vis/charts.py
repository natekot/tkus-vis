"""Slide → Vega-Lite spec → SVG. Vega-Lite does the charting; this only declares it."""

from __future__ import annotations

import json
import math

import vl_convert

from . import theme
from .story import Slide

# Room the y-axis labels take beside a column chart, and the most x labels that stay legible.
_PLOT_WIDTH = theme.CHART_WIDTH - 80
_MAX_X_LABELS = 12
_LEGEND_ROOM = 72  # height a top legend takes in a bar chart
_CONCAT_WIDTH = theme.CHART_WIDTH - 160  # room for both y-axes' labels and titles


def _thickness(space: float, count: int) -> int:
    """Bar thickness: capped, and at most 60% of its band, so every band keeps air."""
    return max(2, min(theme.BAR_MAX, int(0.6 * space / max(count, 1))))


def chart_spec(slide: Slide) -> dict | None:
    if slide.kind == "columns":
        return _columns(slide)
    if slide.kind == "bars":
        return _bars(slide)
    if slide.kind == "histogram":
        return _histogram(slide)
    if slide.kind == "throughput":
        return _throughput(slide)
    return None


def chart_svg(slide: Slide) -> str | None:
    spec = chart_spec(slide)
    return None if spec is None else vl_convert.vegalite_to_svg(spec)


def _base(values: list[dict], height: int) -> dict:
    return {
        "width": theme.CHART_WIDTH,
        "height": height,
        "autosize": {"type": "fit", "contains": "padding"},
        "config": theme.vega_config(),
        "data": {"values": values},
    }


def _money_format(top: float, currency: str) -> str:
    decimals = 0 if top >= 10 else 2
    return f"{'$' if currency == 'USD' else ''},.{decimals}f"


def _count_axis(tick_count: int | dict) -> dict:
    """An axis of whole counts, each labelled once.

    vl-convert ignores tickMinStep, so half steps ("0, 1, 1, 2, 2" under format "d") are
    avoided by asking for no more ticks than the largest count. Callers pass Vega-Lite's
    default density, one tick per 40px, capped at that count.
    """
    return {"format": "d", "tickCount": tick_count, "domain": False}


def _top(slide: Slide) -> float:
    return max((b.usd for b in slide.bars), default=0.0)


def _week_axis(keys: list[str], labels: dict[str, str]) -> tuple[list[str], str]:
    """The weeks to label (every stride-th, ending on the latest) and the label lookup."""
    stride = math.ceil(len(keys) / _MAX_X_LABELS)
    return keys[::-1][::stride][::-1], f"{json.dumps(labels)}[datum.value]"


def _columns(slide: Slide) -> dict:
    values = [
        {"week": b.key or b.label, "label": b.label, "usd": b.usd, "value": b.value}
        for b in slide.bars
    ]
    shown, label_expr = _week_axis(
        [v["week"] for v in values], {v["week"]: v["label"] for v in values}
    )
    return {
        **_base(values, theme.CHART_HEIGHT),
        "encoding": {
            "x": {
                "field": "week",
                "type": "ordinal",
                "sort": None,
                "title": None,
                "axis": {"labelAngle": 0, "values": shown, "labelExpr": label_expr},
            },
            "y": {
                "field": "usd",
                "type": "quantitative",
                "title": None,
                "axis": {
                    "format": _money_format(_top(slide), slide.currency),
                    "tickCount": 5,
                    "domain": False,
                },
            },
        },
        "layer": [
            {
                "mark": {
                    "type": "bar",
                    "color": theme.ACCENT,
                    "size": _thickness(_PLOT_WIDTH, len(values)),
                    "cornerRadiusEnd": theme.CORNER,
                }
            },
            {
                "mark": {"type": "text", "baseline": "bottom", "dy": -12, "fontWeight": "bold"},
                "encoding": {"text": {"field": "value"}},
            },
        ],
    }


def _bars(slide: Slide) -> dict:
    names = dict(slide.legend)
    values = [
        {"label": b.label, "usd": b.usd, "value": b.value, "series": names.get(b.group, b.group)}
        for b in slide.bars
    ]
    top = max((b.usd for b in slide.bars), default=0.0)
    low = min([0.0] + [b.usd for b in slide.bars])
    color = {
        "field": "series",
        "type": "nominal",
        "scale": {
            "domain": [names.get("accent", "accent"), names.get("rest", "rest")],
            "range": [theme.ACCENT, theme.DEEMPHASIS],
        },
        "legend": None,
    }
    if len(slide.legend) >= 2:
        color["legend"] = {"title": None, "orient": "top", "direction": "horizontal", "offset": 32}
    legend_room = _LEGEND_ROOM if len(slide.legend) >= 2 else 0
    height = min(theme.CHART_HEIGHT, theme.BAR_STEP * max(len(values), 1) + legend_room)
    return {
        **_base(values, height),
        "encoding": {
            "y": {
                "field": "label",
                "type": "nominal",
                "sort": None,
                "title": None,
                "axis": {
                    "labelFontSize": theme.LABEL_SIZE,
                    "labelColor": theme.INK,
                    "labelLimit": theme.LABEL_LIMIT,
                    "labelPadding": 20,
                    "domain": False,
                },
            },
            "x": {
                "field": "usd",
                "type": "quantitative",
                "axis": None,
                # Room past the longest bar for its "$58.03 · 87%" label.
                "scale": {"domain": [low, top * 1.35 if top > 0 else 1.0], "nice": False},
            },
        },
        "layer": [
            {
                "mark": {
                    "type": "bar",
                    "size": _thickness(height - legend_room, len(values)),
                    "cornerRadiusEnd": theme.CORNER,
                },
                "encoding": {"color": color},
            },
            {
                "mark": {"type": "text", "align": "left", "baseline": "middle", "dx": 14},
                "encoding": {"text": {"field": "value"}},
            },
        ],
    }


def _histogram(slide: Slide) -> dict:
    middle, label = slide.rule
    values = [{"usd": v} for v in slide.values]
    x_axis = {"format": _money_format(max(slide.values), slide.currency), "labelAngle": 0}
    return {
        **_base(values, theme.CHART_HEIGHT),
        "layer": [
            {
                "mark": {
                    "type": "bar",
                    "color": theme.ACCENT,
                    "cornerRadiusEnd": theme.CORNER,
                    "binSpacing": 4,
                },
                "encoding": {
                    "x": {
                        "field": "usd",
                        "type": "quantitative",
                        "bin": {"maxbins": 15},
                        "title": "AI cost per merged PR",
                        "axis": x_axis,
                    },
                    "y": {
                        "aggregate": "count",
                        "type": "quantitative",
                        "title": "Merged PRs",
                        # Only Vega knows the bin counts: read the largest off the y scale.
                        "axis": _count_axis({"expr": "min(ceil(height / 40), domain('y')[1])"}),
                    },
                },
            },
            {
                "mark": {"type": "rule", "color": theme.INK, "strokeWidth": 2},
                "encoding": {"x": {"datum": middle}},
            },
            {
                # Above the plot, so the label never sits on a bar.
                "mark": {
                    "type": "text",
                    "align": "center",
                    "baseline": "bottom",
                    "fontWeight": "bold",
                },
                "encoding": {
                    "x": {"datum": middle},
                    "y": {"value": -12},
                    "text": {"value": label},
                },
            },
        ],
    }


def _throughput(slide: Slide) -> dict:
    keys = [b.key for b in slide.bars]
    shown, label_expr = _week_axis(keys, {b.key: b.label for b in slide.bars})
    size = _thickness(_CONCAT_WIDTH, len(keys))
    x = {"field": "week", "type": "ordinal", "sort": keys, "title": None}
    spend = {
        "width": _CONCAT_WIDTH,
        "height": 250,
        "data": {"values": [{"week": b.key, "usd": b.usd, "value": b.value} for b in slide.bars]},
        "encoding": {
            "x": {**x, "axis": {"labels": False, "ticks": False}},
            "y": {
                "field": "usd",
                "type": "quantitative",
                "title": "AI spend",
                "axis": {
                    "format": _money_format(_top(slide), slide.currency),
                    "tickCount": 4,
                    "domain": False,
                },
            },
        },
        "layer": [
            {
                "mark": {
                    "type": "bar",
                    "color": theme.ACCENT,
                    "size": size,
                    "cornerRadiusEnd": theme.CORNER,
                }
            },
            {
                "mark": {"type": "text", "baseline": "bottom", "dy": -10, "fontWeight": "bold"},
                "encoding": {"text": {"field": "value"}},
            },
        ],
    }
    counts = [  # empty weeks draw nothing: a zero-height segment would nick the baseline
        {"week": k, "count": n, "series": series, "rank": rank}
        for k, _label, with_cost, without in slide.merges
        for rank, (n, series) in enumerate(
            ((with_cost, "With cost data"), (without, "No cost data"))
        )
        if n
    ]
    height = 190
    most = max((with_cost + without for *_, with_cost, without in slide.merges), default=0)
    merged = {
        "width": _CONCAT_WIDTH,
        "height": height,
        "data": {"values": counts},
        # Stacked segments are separated by a surface-colored gap, not rounded (dataviz).
        "mark": {"type": "bar", "size": size, "stroke": theme.SURFACE, "strokeWidth": 3},
        "encoding": {
            "x": {**x, "axis": {"labelAngle": 0, "values": shown, "labelExpr": label_expr}},
            "y": {
                "field": "count",
                "type": "quantitative",
                "title": "PRs merged",
                "axis": _count_axis(max(1, min(math.ceil(height / 40), most))),
            },
            "color": {
                "field": "series",
                "type": "nominal",
                "scale": {
                    "domain": ["With cost data", "No cost data"],
                    "range": [theme.ACCENT, theme.DEEMPHASIS],
                },
                # Beneath its own chart, not above the spend chart it doesn't describe.
                "legend": {"title": None, "orient": "bottom", "direction": "horizontal"},
            },
            "order": {"field": "rank", "sort": "ascending"},  # cost data at the base
        },
    }
    return {
        "config": theme.vega_config(),
        "spacing": 40,
        "vconcat": [spend, merged],
        "resolve": {"scale": {"x": "shared"}},
    }
