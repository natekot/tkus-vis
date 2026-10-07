"""Dataset → report files. Formatting only: every figure comes from the model."""

from __future__ import annotations

import json
from dataclasses import asdict

from jinja2 import Environment, PackageLoader, StrictUndefined

from . import __version__
from .model import DIRECT, PR, UNJOINED, UNMATCHED, Dataset

BUCKET_LABELS = {
    DIRECT: "Direct to default branch",
    UNJOINED: "Other branches (not yet matched to PRs)",
    PR: "In pull requests",
    UNMATCHED: "No pull request found",
}

# autoescape: branch and model names come from analysed repositories, so they're untrusted.
TEMPLATES = Environment(
    loader=PackageLoader("tkus_vis", "templates"),
    autoescape=True,
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
)
TEMPLATES.filters["money"] = lambda value: f"{value:,.2f}"
# PR links come from the git host, so they're untrusted too: only web addresses become links.
TEMPLATES.tests["web_link"] = lambda url: url.startswith("https://")


def render_html(dataset: Dataset) -> str:
    template = TEMPLATES.get_template("report.html.j2")
    return template.render(d=dataset, labels=BUCKET_LABELS, version=__version__)


def render_json(dataset: Dataset) -> str:
    data = {"generator": f"tkus-vis {__version__}", **asdict(dataset)}
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
