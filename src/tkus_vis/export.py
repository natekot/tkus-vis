"""Slides → files: lay each slide out as HTML, then print it to PNG and PDF with Chrome."""

from __future__ import annotations

from markupsafe import Markup

from . import theme
from .render import TEMPLATES
from .story import Slide


def slide_html(slide: Slide, chart_svg: str | None) -> str:
    # vl-convert's SVG escapes the text it draws (tested), so it is embedded as markup.
    return TEMPLATES.get_template("slide.html.j2").render(
        slide=slide, t=theme, chart=Markup(chart_svg or "")
    )
