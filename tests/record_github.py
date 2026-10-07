"""Record the GitHub responses tkus-vis reads for one repository, for replay in tests.

    uv run python tests/record_github.py natekot/tkus tests/fixtures/github/natekot-tkus

Only response bodies are saved: never request headers, so never the token. Every
"email" field is redacted first: tkus-vis never reads them, and never publishes them.
"""

import json
import sys
from pathlib import Path

from helpers import fixture_name

from tkus_vis.github import GitHub, _urlopen, pull_requests, read_repo, token


def redact(value):
    if isinstance(value, dict):
        return {
            k: "redacted@example.invalid" if k == "email" and v else redact(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


def main(repo: str, out: str) -> None:
    directory = Path(out)
    directory.mkdir(parents=True, exist_ok=True)

    def recording(url, headers):
        status, response_headers, body = _urlopen(url, headers)
        if status == 200:
            clean = json.dumps(redact(json.loads(body)), indent=1, ensure_ascii=False)
            (directory / fixture_name(url)).write_text(clean + "\n", encoding="utf-8")
        return status, response_headers, body

    gh = GitHub(token(), fetch=recording)
    snapshot = read_repo(gh, repo)
    prs = pull_requests(gh, repo)
    print(f"recorded {repo} at {snapshot.commit[:7]}: {len(snapshot.files)} files, {len(prs)} PRs")


if __name__ == "__main__":
    main(*sys.argv[1:])
