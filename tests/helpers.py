"""Shared test helpers: isolated git, ledger lines, and the pinned tkus ledger."""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest

from tkus_vis.model import PullRequest

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


API = "https://api.github.com"


def _pr_json(repo: str, p: PullRequest) -> dict:
    head_repo = {"full_name": f"someone/{repo.split('/')[1]}"} if p.fork else {"full_name": repo}
    return {
        "number": p.number,
        "title": p.title,
        "html_url": p.url,
        "state": p.state,
        "created_at": p.created_at,
        "merged_at": p.merged_at,
        "closed_at": p.closed_at,
        "head": {"ref": p.head, "repo": head_repo},
        "base": {"ref": "main", "repo": {"full_name": repo}},
    }


def fake_github(
    repo, files, prs, page_size=100, default_branch="main", truncated=False, status=None
):
    """Serve a repository's ledger and PRs the way the GitHub REST API shapes them."""
    blobs = {f"{i:040x}": text for i, text in enumerate(files.values(), start=1)}
    entries = [
        {"path": path.removeprefix(".tkus/"), "type": "blob", "sha": sha}
        for path, sha in zip(files, blobs, strict=True)
    ]
    pages = [prs[i : i + page_size] for i in range(0, len(prs), page_size)] or [[]]
    base = f"/repos/{repo}"
    routes = {
        base: {"default_branch": default_branch, "full_name": repo},
        f"{base}/commits/{default_branch}": {"sha": "c" * 40, "commit": {"tree": {"sha": "root"}}},
        f"{base}/git/trees/root": {
            "tree": [{"path": ".tkus", "type": "tree", "sha": "tkus"}] if files else [],
            "truncated": False,
        },
        f"{base}/git/trees/tkus?recursive=1": {"tree": entries, "truncated": truncated},
    }
    for sha, text in blobs.items():
        content = base64.encodebytes(text.encode()).decode()  # wrapped at 76, like GitHub
        routes[f"{base}/git/blobs/{sha}"] = {"content": content, "encoding": "base64"}
    for n, page in enumerate(pages, start=1):
        suffix = "" if n == 1 else f"&page={n}"
        routes[f"{base}/pulls?state=all&per_page=100{suffix}"] = [_pr_json(repo, p) for p in page]

    def fetch(url, headers):
        fetch.requests.append((url, dict(headers)))
        if status is not None:
            return status[0], status[1], b'{"message": "error"}'
        path = url.removeprefix(API)
        if path not in routes:
            return 404, {}, b'{"message": "Not Found"}'
        response_headers = {}
        if "/pulls?" in path:
            page = int(path.split("&page=")[1]) if "&page=" in path else 1
            if page < len(pages):
                response_headers["Link"] = (
                    f'<{API}{base}/pulls?state=all&per_page=100&page={page + 1}>; rel="next"'
                )
        return 200, response_headers, json.dumps(routes[path]).encode()

    fetch.requests = []
    return fetch


def fixture_name(url: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", url.removeprefix(API + "/")).strip("_") + ".json"


def replay(directory: Path):
    """Serve responses recorded by tests/record_github.py."""

    def fetch(url, headers):
        path = Path(directory) / fixture_name(url)
        if not path.is_file():
            return 404, {}, b'{"message": "Not Found"}'
        return 200, {}, path.read_bytes()

    return fetch
