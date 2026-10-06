"""The look of every slide: one place for color, type and mark sizes.

Colors are the dataviz reference palette, light mode, since slides are light only.
Sizes are CSS px on a 1920×1080 slide, roughly twice the dataviz UI specs, because a
slide is read from across a room.
"""

SLIDE_WIDTH, SLIDE_HEIGHT = 1920, 1080
CHART_WIDTH, CHART_HEIGHT = 1728, 600  # the chart area inside the slide's margins

# Unquoted on purpose: valid CSS, and nothing for HTML escaping to mangle.
FONT = "Helvetica Neue, Helvetica, Arial, sans-serif"

SURFACE = "#ffffff"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
ACCENT = "#2a78d6"  # categorical slot 1: the subject
DEEMPHASIS = "#c3c2b7"  # the rest, in an emphasis chart

BAR_MAX = 64  # bar and column thickness cap; the rest of the band is air
BAR_STEP = 110  # row height per horizontal bar
CORNER = 8  # rounded data end; square at the baseline
LABEL_SIZE = 26
AXIS_SIZE = 22
LABEL_LIMIT = 560  # px before an axis label is truncated with an ellipsis


def vega_config() -> dict:
    return {
        "background": None,  # transparent: the slide's surface shows through
        "font": FONT,
        "padding": 0,
        "view": {"stroke": None},
        "axis": {
            "labelFont": FONT,
            "labelFontSize": AXIS_SIZE,
            "labelColor": INK_MUTED,
            "labelPadding": 12,
            "ticks": False,
            "gridColor": GRID,
            "gridWidth": 1,
            "domainColor": AXIS,
            "domainWidth": 1,
        },
        "legend": {
            "labelFont": FONT,
            "labelFontSize": LABEL_SIZE,
            "labelColor": INK_SECONDARY,
            "symbolType": "square",
            "symbolSize": 400,
            "symbolStrokeWidth": 0,
            "columnPadding": 40,
            "labelLimit": LABEL_LIMIT,
        },
        "text": {"font": FONT, "fontSize": LABEL_SIZE, "color": INK},
    }
