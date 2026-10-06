"""Command line: collect → model → render."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .collect import CollectError, read_local
from .model import build_dataset
from .render import render_html, render_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tkus-vis", description="Report AI agent spend recorded by tkus."
    )
    parser.add_argument("--version", action="version", version=f"tkus-vis {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="write an HTML report and its dataset")
    build.add_argument("--path", required=True, help="local clone to read")
    build.add_argument("--ref", help="ref to read the ledger at (default: the default branch)")
    build.add_argument("--default-branch", help="the default branch (default: from origin/HEAD)")
    build.add_argument("-o", "--output", required=True, type=Path, help="HTML report to write")
    build.add_argument(
        "--data", type=Path, help="dataset JSON to write (default: the report's path with .json)"
    )
    args = parser.parse_args(argv)
    return _build(args)


def _build(args: argparse.Namespace) -> int:
    report: Path = args.output
    data: Path = args.data or report.with_suffix(".json")
    if data.resolve() == report.resolve():
        print(
            f"tkus-vis: the dataset would overwrite the report at {report}; pass --data",
            file=sys.stderr,
        )
        return 2
    try:
        snapshot = read_local(args.path, ref=args.ref, default_branch=args.default_branch)
    except CollectError as exc:
        print(f"tkus-vis: {exc}", file=sys.stderr)
        return 2
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    dataset, problems = build_dataset(snapshot, generated)
    for problem in problems:
        print(f"tkus-vis: {problem.path}:{problem.line}: {problem.message}", file=sys.stderr)
    if len(dataset.views) > 1:
        print(
            "tkus-vis: the ledger records more than one currency; each is reported separately",
            file=sys.stderr,
        )
    for path in (report, data):
        path.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(render_html(dataset), encoding="utf-8")
    data.write_text(render_json(dataset), encoding="utf-8")
    totals = ", ".join(f"{v.total:,.2f} {v.currency}" for v in dataset.views)
    print(f"{report}: {totals or f'no tkus ledger at {snapshot.ref}; cost unknown'}")
    return 0
