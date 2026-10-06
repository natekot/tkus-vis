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


def _thickness(space: float, count: int) -> int:
    """Bar thickness: capped, and at most 60% of its band, so every band keeps air."""
    return max(2, min(theme.BAR_MAX, int(0.6 * space / max(count, 1))))


def chart_spec(slide: Slide) -> dict | None:
    if slide.kind == "columns":
        return _columns(slide)
    if slide.kind == "bars":
        return _bars(slide)
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


def _money_format(slide: Slide) -> str:
    top = max((b.usd for b in slide.bars), default=0.0)
    decimals = 0 if top >= 10 else 2
    return f"{'$' if slide.currency == 'USD' else ''},.{decimals}f"


def _columns(slide: Slide) -> dict:
    values = [
        {"week": b.key or b.label, "label": b.label, "usd": b.usd, "value": b.value}
        for b in slide.bars
    ]
    # Label every stride-th week, counting back from the latest so it is always labelled.
    stride = math.ceil(len(values) / _MAX_X_LABELS)
    shown = [v["week"] for v in values][::-1][::stride][::-1]
    names = json.dumps({v["week"]: v["label"] for v in values})
    return {
        **_base(values, theme.CHART_HEIGHT),
        "encoding": {
            "x": {
                "field": "week",
                "type": "ordinal",
                "sort": None,
                "title": None,
                "axis": {"labelAngle": 0, "values": shown, "labelExpr": f"{names}[datum.value]"},
            },
            "y": {
                "field": "usd",
                "type": "quantitative",
                "title": None,
                "axis": {"format": _money_format(slide), "tickCount": 5, "domain": False},
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
