"""Shared test helpers: isolated git, ledger lines, and the pinned tkus ledger."""

from __future__ import annotations

import json
import os
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"

CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
needs_chrome = pytest.mark.skipif(
    not CHROME.exists(), reason="exporting slides needs Google Chrome"
)

# Tests build real repositories. Keep the user's git config out of them:
# signing, global hooks (including tkus's own), templates.
GIT_ENV = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
}


def git(cwd, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, env=GIT_ENV, check=True, capture_output=True, text=True
    ).stdout


def entry(
    usd,
    *,
    until="2026-09-08T19:04:26.645Z",
    since="2026-09-08T18:55:12.388Z",
    parent="0" * 40,
    currency="USD",
    providers=None,
    **extra,
) -> str:
    """One ledger line, shaped like the tkus README's example."""
    if providers is None:
        providers = [{"provider": "claude-code", "model": "claude-opus-5", "reqs": 1, "usd": usd}]
    return json.dumps(
        {
            "at": until,
            "since": since,
            "until": until,
            "parent": parent,
            "currency": currency,
            "usd": usd,
            "rates_version": "2026-08",
            "providers": providers,
            **extra,
        }
    )


def ledger(*lines: str) -> str:
    return "".join(line + "\n" for line in lines)


def tkus_ledger_files() -> dict[str, str]:
    """The real ledger from tkus@b6fce91, keyed by its .tkus/ path."""
    root = FIXTURES / "tkus-ledger"
    return {
        ".tkus/" + p.relative_to(root).as_posix(): p.read_text(encoding="utf-8")
        for p in sorted(root.rglob("*.jsonl"))
    }


class Outline(HTMLParser):
    """The page's landmarks, plus anything that would fetch over the network."""

    def __init__(self, html: str):
        super().__init__()
        self.landmarks: list[str] = []
        self.fetches: list[str] = []
        self._text: list[str] | None = None
        self._style = False
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("header", "section", "main") and attrs.get("id"):
            self.landmarks.append(f"{tag}#{attrs['id']}")
        if tag in ("h1", "h2"):
            self._text = []
        if "src" in attrs or tag in ("link", "script", "iframe", "object", "embed"):
            self.fetches.append(tag)
        self._style = tag == "style"

    def handle_endtag(self, tag):
        if tag in ("h1", "h2") and self._text is not None:
            self.landmarks.append(f"{tag}: {' '.join(''.join(self._text).split())}")
            self._text = None
        if tag == "style":
            self._style = False

    def handle_data(self, data):
        if self._text is not None:
            self._text.append(data)
        if self._style and ("url(" in data or "@import" in data):
            self.fetches.append("css")
