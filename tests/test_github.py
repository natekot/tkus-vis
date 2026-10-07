import re
import subprocess

import pytest
import synthetic
from helpers import FIXTURES, fake_github, replay

from tkus_vis import github
from tkus_vis.github import GitHub, GitHubError, pull_requests, read_repo

RECORDED = FIXTURES / "github" / "natekot-tkus"


def client(**kwargs):
    fetch = fake_github(synthetic.REPO, synthetic.FILES, synthetic.PRS, **kwargs)
    return GitHub("secret-token", fetch=fetch), fetch


def test_read_repo_returns_the_ledger_at_the_default_branch():
    gh, _ = client()
    snap = read_repo(gh, synthetic.REPO)
    assert (snap.repo, snap.ref, snap.default_branch, snap.commit) == (
        "acme/widgets",
        "main",
        "main",
        "c" * 40,
    )
    assert snap.files == synthetic.FILES


def test_a_repo_without_a_ledger_has_no_files():
    gh = GitHub(None, fetch=fake_github("a/b", {}, []))
    assert read_repo(gh, "a/b").files == {}


def test_pull_requests_follow_pagination_and_flag_forks():
    gh, fetch = client(page_size=3)
    prs = pull_requests(gh, synthetic.REPO)
    assert prs == synthetic.PRS  # all three pages, fields intact
    assert sum("/pulls?" in url for url, _ in fetch.requests) == 3


def test_a_truncated_ledger_tree_is_an_error_not_an_undercount():
    gh, _ = client(truncated=True)
    with pytest.raises(GitHubError, match="too large"):
        read_repo(gh, synthetic.REPO)


@pytest.mark.parametrize(
    "status, headers, message",
    [
        (404, {}, "not found"),
        (401, {}, "rejected the token"),
        (403, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1790000000"}, "rate limit"),
        (500, {}, "GitHub returned 500"),
    ],
)
def test_errors_are_explained(status, headers, message):
    gh, _ = client(status=(status, headers))
    with pytest.raises(GitHubError, match=message):
        read_repo(gh, synthetic.REPO)


def test_the_token_is_sent_and_never_leaks():
    gh, fetch = client(status=(401, {}))
    with pytest.raises(GitHubError) as exc:
        read_repo(gh, synthetic.REPO)
    assert fetch.requests[0][1]["Authorization"] == "Bearer secret-token"
    assert "secret-token" not in str(exc.value)
    assert "Authorization" not in GitHub(None, fetch=fetch)._headers


def test_token_prefers_github_token_then_the_gh_login(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", " from-env ")
    assert github.token() == "from-env"
    monkeypatch.delenv("GITHUB_TOKEN")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout="from-gh\n", stderr=""),
    )
    assert github.token() == "from-gh"

    def missing(*a, **k):
        raise FileNotFoundError("gh")

    monkeypatch.setattr(subprocess, "run", missing)
    assert github.token() is None


def test_recorded_natekot_tkus_replays():
    gh = GitHub(None, fetch=replay(RECORDED))
    snap = read_repo(gh, "natekot/tkus")
    assert snap.default_branch == "main" and len(snap.files) == 5
    assert all(path.startswith(".tkus/") and path.endswith(".jsonl") for path in snap.files)
    [only] = pull_requests(gh, "natekot/tkus")
    assert (only.number, only.status, only.head, only.fork) == (
        1,
        "closed",
        "tkus-protection-selftest",
        False,
    )


def test_recorded_fixtures_hold_no_token():
    for path in RECORDED.glob("*.json"):
        assert "gho_" not in path.read_text() and "ghp_" not in path.read_text()


def test_recorded_fixtures_hold_no_email_address():
    # tkus never publishes email addresses, and neither does tkus-vis (spec §3, §6).
    for path in RECORDED.glob("*.json"):
        assert not re.search(r'"email":\s*"[^"]*@(?!example\.invalid)', path.read_text()), path.name
