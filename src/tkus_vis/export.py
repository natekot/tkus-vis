"""Slides → files: lay each slide out as HTML, then print it to PNG and PDF with Chrome."""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

from markupsafe import Markup
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright
from pypdf import PdfWriter

from . import theme
from .render import TEMPLATES
from .story import Slide


class ExportError(Exception):
    """Slides can't be exported. The message is shown to the user."""


@dataclass(frozen=True)
class Exported:
    written: list[Path]
    overflowing: list[str]  # slugs whose content runs past the slide's edges


# True when everything inside <main> fits the 1920×1080 slide.
_FITS = (
    "() => { const m = document.querySelector('main');"
    " return m.scrollHeight <= m.clientHeight && m.scrollWidth <= m.clientWidth; }"
)


def slide_html(slide: Slide, chart_svg: str | None) -> str:
    # vl-convert's SVG escapes the text it draws (tested), so it is embedded as markup.
    return TEMPLATES.get_template("slide.html.j2").render(
        slide=slide, t=theme, chart=Markup(chart_svg or "")
    )


def export(pages: list[tuple[str, str]], out_dir: Path, executable: str | None = None) -> Exported:
    """Print each (slug, html) page to <slug>.png (2x), and all of them to one vector slides.pdf."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    overflowing: list[str] = []
    pdfs: list[bytes] = []
    launch = {"executable_path": executable} if executable else {"channel": "chrome"}
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(**launch)
            try:
                context = browser.new_context(
                    viewport={"width": theme.SLIDE_WIDTH, "height": theme.SLIDE_HEIGHT},
                    device_scale_factor=2,
                )
                page = context.new_page()
                page.emulate_media(media="screen")
                for slug, html in pages:
                    page.set_content(html, wait_until="load")
                    if not page.evaluate(_FITS):
                        overflowing.append(slug)
                    png = out_dir / f"{slug}.png"
                    page.screenshot(path=str(png))
                    written.append(png)
                    pdfs.append(
                        page.pdf(
                            width=f"{theme.SLIDE_WIDTH}px",
                            height=f"{theme.SLIDE_HEIGHT}px",
                            print_background=True,
                            margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
                        )
                    )
            finally:
                browser.close()
    except PlaywrightError as exc:
        raise ExportError(f"can't export slides with Google Chrome: {exc}") from exc
    deck = PdfWriter()
    for pdf in pdfs:
        deck.append(io.BytesIO(pdf))
    deck.write(out_dir / "slides.pdf")
    written.append(out_dir / "slides.pdf")
    return Exported(written, overflowing)
