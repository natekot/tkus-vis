import struct
from dataclasses import replace

import pytest
from helpers import needs_chrome, tkus_ledger_files
from pypdf import PdfReader

from tkus_vis.charts import chart_svg
from tkus_vis.export import ExportError, export, slide_html
from tkus_vis.ledger import Snapshot
from tkus_vis.model import build_dataset
from tkus_vis.story import slides_for


@pytest.fixture(scope="module")
def tkus():
    dataset, _ = build_dataset(
        Snapshot("tkus", "origin/main", "b" * 40, "main", tkus_ledger_files()), "t"
    )
    return slides_for(dataset, dataset.views[0])


def png_size(path):
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", data[16:24])


@needs_chrome
def test_export_writes_2x_pngs_and_one_vector_pdf(tmp_path, tkus):
    pages = [(s.slug, slide_html(s, chart_svg(s))) for s in tkus[:2]]
    result = export(pages, tmp_path)
    assert result.written == [
        tmp_path / "01-headline.png",
        tmp_path / "02-weekly-spend.png",
        tmp_path / "slides.pdf",
    ]
    assert result.overflowing == []
    assert png_size(tmp_path / "01-headline.png") == (3840, 2160)
    pdf = PdfReader(tmp_path / "slides.pdf")
    assert len(pdf.pages) == 2  # a page per slide, in order
    for page in pdf.pages:
        box = page.mediabox
        assert (round(float(box.width)), round(float(box.height))) == (1440, 810)
    assert tkus[0].title in pdf.pages[0].extract_text()
    assert "Aug 17" in pdf.pages[1].extract_text()  # text stays text: vector, not a picture


@needs_chrome
def test_a_slide_that_overflows_is_reported(tmp_path, tkus):
    long = replace(tkus[0], slug="long", title="word " * 120)
    result = export([("long", slide_html(long, None))], tmp_path)
    assert result.overflowing == ["long"]
    assert (tmp_path / "long.png").is_file()  # still written, so it can be inspected


def test_export_without_chrome_is_a_clean_error(tmp_path):
    with pytest.raises(ExportError, match="Chrome"):
        export([("x", "<p>x</p>")], tmp_path, executable="/nonexistent/chrome")
