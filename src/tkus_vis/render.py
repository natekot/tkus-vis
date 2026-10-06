"""Dataset → report files. Formatting only: every figure comes from the model."""

from __future__ import annotations

import json
from dataclasses import asdict

from jinja2 import Environment, PackageLoader, StrictUndefined

from . import __version__
from .model import DIRECT, UNJOINED, Dataset

BUCKET_LABELS = {
    DIRECT: "Direct to default branch",
    UNJOINED: "Other branches (not yet matched to PRs)",
}

# autoescape: branch and model names come from analysed repositories, so they're untrusted.
_env = Environment(
    loader=PackageLoader("tkus_vis", "templates"),
    autoescape=True,
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
)
_env.filters["money"] = lambda value: f"{value:,.2f}"


def render_html(dataset: Dataset) -> str:
    template = _env.get_template("report.html.j2")
    return template.render(d=dataset, labels=BUCKET_LABELS, version=__version__)


def render_json(dataset: Dataset) -> str:
    data = {"generator": f"tkus-vis {__version__}", **asdict(dataset)}
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
