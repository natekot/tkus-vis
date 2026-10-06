"""Slide → Vega-Lite spec → SVG. Vega-Lite does the charting; this only declares it."""

from __future__ import annotations

import vl_convert

from . import theme
from .story import Slide


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
    values = [{"label": b.label, "usd": b.usd, "value": b.value} for b in slide.bars]
    return {
        **_base(values, theme.CHART_HEIGHT),
        "encoding": {
            "x": {
                "field": "label",
                "type": "ordinal",
                "sort": None,
                "title": None,
                "axis": {"labelAngle": 0},
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
                    "size": theme.BAR_MAX,
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
    height = min(theme.CHART_HEIGHT, theme.BAR_STEP * max(len(values), 1))
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
                "mark": {"type": "bar", "size": theme.BAR_MAX, "cornerRadiusEnd": theme.CORNER},
                "encoding": {"color": color},
            },
            {
                "mark": {"type": "text", "align": "left", "baseline": "middle", "dx": 14},
                "encoding": {"text": {"field": "value"}},
            },
        ],
    }
