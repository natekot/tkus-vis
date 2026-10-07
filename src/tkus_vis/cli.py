"""Command line: collect → model → render (a report) or export (slides)."""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .charts import chart_svg
from .collect import CollectError, read_local
from .export import ExportError, export, slide_html
from .github import REPO_NAME, GitHub, GitHubError, pull_requests, read_repo, token
from .model import Dataset, build_dataset
from .render import render_html, render_json
from .story import slides_for


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tkus-vis", description="Report AI agent spend recorded by tkus."
    )
    parser.add_argument("--version", action="version", version=f"tkus-vis {__version__}")
    source = argparse.ArgumentParser(add_help=False)
    source.add_argument("--path", help="local clone to read the ledger from")
    source.add_argument(
        "--repo",
        type=_repo_name,
        help="GitHub OWNER/NAME: match spend to its pull requests "
        "(and read the ledger through GitHub unless --path is given)",
    )
    source.add_argument("--ref", help="ref to read the ledger at (default: the default branch)")
    source.add_argument("--default-branch", help="the default branch (default: from origin/HEAD)")
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser(
        "build", parents=[source], help="write an HTML report and its dataset"
    )
    build.add_argument("-o", "--output", required=True, type=Path, help="HTML report to write")
    build.add_argument(
        "--data", type=Path, help="dataset JSON to write (default: the report's path with .json)"
    )
    slides = commands.add_parser(
        "slides", parents=[source], help="write slide-ready infographics as PNGs and one PDF"
    )
    slides.add_argument("-o", "--output", required=True, type=Path, help="directory for the slides")
    args = parser.parse_args(argv)
    if not args.path and not args.repo:
        parser.error("give --path, --repo, or both")
    return _build(args) if args.command == "build" else _slides(args)


def _repo_name(text: str) -> str:
    if not REPO_NAME.match(text):
        raise argparse.ArgumentTypeError(f"expected OWNER/NAME, got {text!r}")
    return text


def _dataset(args: argparse.Namespace) -> Dataset | None:
    prs = None
    try:
        gh = None
        if args.repo:
            key = token()
            if key is None:
                print(
                    "tkus-vis: no GitHub token (set GITHUB_TOKEN or run `gh auth login`); "
                    "trying without one, limited to 60 requests an hour",
                    file=sys.stderr,
                )
            gh = GitHub(key)
        if args.path:
            snapshot = read_local(args.path, ref=args.ref, default_branch=args.default_branch)
        else:
            snapshot = read_repo(gh, args.repo, ref=args.ref, default_branch=args.default_branch)
        if gh is not None:
            prs = pull_requests(gh, args.repo)
    except (CollectError, GitHubError) as exc:
        print(f"tkus-vis: {exc}", file=sys.stderr)
        return None
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    dataset, problems = build_dataset(snapshot, generated, prs)
    for problem in problems:
        print(f"tkus-vis: {problem.path}:{problem.line}: {problem.message}", file=sys.stderr)
    if len(dataset.views) > 1:
        print(
            "tkus-vis: the ledger records more than one currency; each is reported separately",
            file=sys.stderr,
        )
    return dataset


def _build(args: argparse.Namespace) -> int:
    report: Path = args.output
    data: Path = args.data or report.with_suffix(".json")
    if data.resolve() == report.resolve():
        print(
            f"tkus-vis: the dataset would overwrite the report at {report}; pass --data",
            file=sys.stderr,
        )
        return 2
    dataset = _dataset(args)
    if dataset is None:
        return 2
    for path in (report, data):
        path.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(render_html(dataset), encoding="utf-8")
    data.write_text(render_json(dataset), encoding="utf-8")
    totals = ", ".join(f"{v.total:,.2f} {v.currency}" for v in dataset.views)
    print(f"{report}: {totals or f'no tkus ledger at {dataset.ref}; cost unknown'}")
    return 0


def currency_prefixes(currencies: list[str]) -> list[str]:
    """File-name prefixes for each currency's slides: path-safe, and never shared."""
    taken: set[str] = set()
    prefixes = []
    for currency in currencies:
        base = re.sub(r"[^a-z0-9]+", "-", currency.lower()).strip("-") or "currency"
        name, n = base, 1
        while name in taken:
            n += 1
            name = f"{base}-{n}"
        taken.add(name)
        prefixes.append(name)
    return prefixes


def _slides(args: argparse.Namespace) -> int:
    dataset = _dataset(args)
    if dataset is None:
        return 2
    if not dataset.views:
        print(f"tkus-vis: no tkus ledger at {dataset.ref}; cost unknown, so no slides were written")
        return 0
    pages = []
    prefixes = currency_prefixes([v.currency for v in dataset.views])
    for view, name in zip(dataset.views, prefixes, strict=True):
        prefix = f"{name}-" if len(dataset.views) > 1 else ""
        for slide in slides_for(dataset, view):
            pages.append((prefix + slide.slug, slide_html(slide, chart_svg(slide))))
    try:
        result = export(pages, args.output)
    except ExportError as exc:
        print(f"tkus-vis: {exc}", file=sys.stderr)
        return 2
    for slug in result.overflowing:
        print(
            f"tkus-vis: {slug} doesn't fit on the slide; check it before using it",
            file=sys.stderr,
        )
    data = args.output / "dataset.json"
    data.write_text(render_json(dataset), encoding="utf-8")
    for path in [*result.written, data]:
        print(path)
    return 0
