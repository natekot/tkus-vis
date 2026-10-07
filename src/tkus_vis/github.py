"""Read a repository's ledger and pull requests through the GitHub REST API. Read-only.

The host sits behind read_repo and pull_requests, which return the same plain data a
local clone gives (a Snapshot) plus model.PullRequest, so another host can slot in.
"""

from __future__ import annotations

import base64
import http.client
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from . import __version__
from .ledger import LEDGER_DIR, Snapshot
from .model import PullRequest

API = "https://api.github.com"
REPO_NAME = re.compile(r"^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$")
_NEXT = re.compile(r'<([^>]+)>;\s*rel="next"')

# (url, request headers) -> (status, response headers, body)
Fetch = Callable[[str, dict[str, str]], tuple[int, dict[str, str], bytes]]


class GitHubError(Exception):
    """GitHub can't be read. The message is shown to the user and never holds the token."""


def token() -> str | None:
    """GITHUB_TOKEN, else the GitHub CLI's login, else None."""
    value = os.environ.get("GITHUB_TOKEN", "").strip()
    if value:
        return value
    try:
        out = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return (out.stdout.strip() or None) if out.returncode == 0 else None


def _urlopen(url: str, headers: dict[str, str]) -> tuple[int, dict[str, str], bytes]:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers or {}), exc.read()
    except (urllib.error.URLError, OSError, http.client.HTTPException) as exc:
        raise GitHubError(f"can't reach GitHub: {exc}") from exc


class GitHub:
    def __init__(self, token: str | None, fetch: Fetch | None = None):
        self._fetch = fetch or _urlopen
        self._headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": f"tkus-vis/{__version__}",
        }
        if token:
            self._headers["Authorization"] = f"Bearer {token}"

    def get(self, path: str) -> Any:
        return self._request(path)[0]

    def pages(self, path: str) -> Iterator[Any]:
        url: str | None = path
        while url:
            body, headers = self._request(url)
            yield body
            match = _NEXT.search(headers.get("link", ""))
            url = match.group(1) if match else None

    def _request(self, path_or_url: str) -> tuple[Any, dict[str, str]]:
        url = path_or_url if path_or_url.startswith(API) else API + path_or_url
        status, headers, body = self._fetch(url, dict(self._headers))
        headers = {k.lower(): v for k, v in headers.items()}
        path = url.removeprefix(API)
        if status != 200:
            raise GitHubError(_explain(status, headers, path))
        try:
            return json.loads(body), headers
        except ValueError as exc:
            raise GitHubError(
                f"GitHub's reply for {path} was not JSON (is a proxy or login page in the way?)"
            ) from exc


@contextmanager
def _expected_shape(repo: str) -> Iterator[None]:
    """A reply shaped other than the REST API documents is an error, not a traceback."""
    try:
        yield
    except (KeyError, IndexError, TypeError, AttributeError, ValueError) as exc:
        raise GitHubError(f"GitHub sent an unexpected reply for {repo}") from exc


def _explain(status: int, headers: dict[str, str], path: str) -> str:
    if status == 401:
        return "GitHub rejected the token; set GITHUB_TOKEN or run `gh auth login`"
    if status in (403, 429) and headers.get("x-ratelimit-remaining") == "0":
        reset = headers.get("x-ratelimit-reset", "")
        when = (
            datetime.fromtimestamp(int(reset), tz=timezone.utc).strftime("%H:%M UTC")
            if reset.isdigit()
            else "later"
        )
        return f"GitHub's rate limit is used up; it resets at {when}"
    if status == 404:
        return f"not found on GitHub: {path} (check the name, and that the token can read it)"
    return f"GitHub returned {status} for {path}"


def read_repo(
    github: GitHub, repo: str, ref: str | None = None, default_branch: str | None = None
) -> Snapshot:
    """Every ledger file at one commit of a GitHub repository: ref, else the default branch."""
    with _expected_shape(repo):
        return _read_repo(github, repo, ref, default_branch)


def _read_repo(github: GitHub, repo: str, ref: str | None, default_branch: str | None) -> Snapshot:
    default_branch = default_branch or github.get(f"/repos/{repo}")["default_branch"]
    ref = ref or default_branch
    commit = github.get(f"/repos/{repo}/commits/{quote(ref, safe='/')}")
    root = github.get(f"/repos/{repo}/git/trees/{commit['commit']['tree']['sha']}")
    ledger = next(
        (t for t in root["tree"] if t["path"] == LEDGER_DIR and t["type"] == "tree"), None
    )
    files: dict[str, str] = {}
    if ledger is not None:
        # Only the ledger's subtree, recursively: a whole-repository listing truncates.
        listing = github.get(f"/repos/{repo}/git/trees/{ledger['sha']}?recursive=1")
        if listing.get("truncated"):
            raise GitHubError(f"{repo}'s {LEDGER_DIR}/ is too large for one GitHub tree listing")
        for item in listing["tree"]:
            if item["type"] == "blob" and item["path"].endswith(".jsonl"):
                blob = github.get(f"/repos/{repo}/git/blobs/{item['sha']}")
                text = base64.b64decode(blob["content"]).decode("utf-8", "replace")
                files[f"{LEDGER_DIR}/{item['path']}"] = text
    return Snapshot(
        repo=repo, ref=ref, commit=commit["sha"], default_branch=default_branch, files=files
    )


def pull_requests(github: GitHub, repo: str) -> list[PullRequest]:
    with _expected_shape(repo):
        return _pull_requests(github, repo)


def _pull_requests(github: GitHub, repo: str) -> list[PullRequest]:
    prs = []
    for page in github.pages(f"/repos/{repo}/pulls?state=all&per_page=100"):
        for item in page:
            head = item.get("head") or {}
            head_repo = (head.get("repo") or {}).get("full_name")
            base_repo = ((item.get("base") or {}).get("repo") or {}).get("full_name")
            prs.append(
                PullRequest(
                    number=item["number"],
                    title=item.get("title") or "",
                    url=item.get("html_url") or "",
                    state=item.get("state") or "",
                    head=head.get("ref") or "",
                    created_at=item.get("created_at") or "",
                    merged_at=item.get("merged_at"),
                    closed_at=item.get("closed_at"),
                    fork=head_repo is None or head_repo != base_repo,  # a deleted fork has no repo
                )
            )
    return prs
