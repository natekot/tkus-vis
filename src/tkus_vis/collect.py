"""Read a ledger snapshot from a local clone. The only module that runs git.

Read-only: rev-parse, symbolic-ref, ls-tree and cat-file. Never fetch or check out.
"""

from __future__ import annotations

import os
import subprocess

from .ledger import LEDGER_DIR, Snapshot


class CollectError(Exception):
    """A clone or ref that can't be read. The message is shown to the user."""


def read_local(path: str, ref: str | None = None, default_branch: str | None = None) -> Snapshot:
    """Every ledger file at one commit: `ref`, else the default branch.

    The default branch comes from origin/HEAD unless given. Without either we
    stop rather than guess, because guessing wrong files a feature branch's
    spend as direct-to-default. Its tree is read from origin/<name> when that
    exists (what the server has merged), else from the local branch.
    """
    root = _git(path, "rev-parse", "--show-toplevel", error=f"{path} is not a git repository")
    root = root.strip()
    origin = _origin_head(root)
    default_branch = default_branch or origin
    if not default_branch:
        raise CollectError(
            "can't tell the default branch: origin/HEAD is not set. Pass --default-branch "
            "NAME, or run `git remote set-head origin --auto` in the clone."
        )
    # A name that isn't a branch (a typo, or "origin/main") would match no ledger
    # file and silently empty the direct bucket.
    on_origin = _ref_exists(root, f"refs/remotes/origin/{default_branch}")
    if not on_origin and not _ref_exists(root, f"refs/heads/{default_branch}"):
        raise CollectError(
            f"default branch {default_branch!r} is neither a local branch nor a branch on "
            f"origin in {root}.{_branch_hint(default_branch)}"
        )
    if ref is None:
        ref = f"origin/{default_branch}" if on_origin else default_branch
    commit = _git(
        root,
        "rev-parse",
        "--verify",
        "--quiet",
        f"{ref}^{{commit}}",
        error=f"ref {ref!r} not found in {root}",
    ).strip()
    return Snapshot(
        repo=os.path.basename(root),
        ref=ref,
        commit=commit,
        default_branch=default_branch,
        files=_ledger_files(root, commit),
    )


def _origin_head(root: str) -> str | None:
    out = _run(root, "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD")
    prefix = "refs/remotes/origin/"
    if out and out.strip().startswith(prefix):
        return out.strip()[len(prefix) :]
    return None


def _ref_exists(root: str, refname: str) -> bool:
    return _run(root, "show-ref", "--verify", "--quiet", refname) is not None


def _branch_hint(name: str) -> str:
    for prefix in ("refs/heads/", "refs/remotes/origin/", "origin/"):
        if name.startswith(prefix):
            return f" Did you mean --default-branch {name[len(prefix) :]}?"
    return ""


def _ledger_files(root: str, commit: str) -> dict[str, str]:
    # -z: without it git quotes non-ASCII paths, and the names stop matching branches.
    listing = _git(
        root,
        "ls-tree",
        "-r",
        "-z",
        commit,
        "--",
        LEDGER_DIR,
        error=f"can't list {LEDGER_DIR}/ at {commit}",
    )
    blobs = []
    for record in listing.split("\0"):
        if not record:
            continue
        meta, rel = record.split("\t", 1)
        _mode, kind, sha = meta.split(" ")
        if kind == "blob" and rel.endswith(".jsonl"):
            blobs.append((rel, sha))
    if not blobs:
        return {}
    batch = subprocess.run(
        ["git", "-C", root, "cat-file", "--batch"],
        input="".join(f"{sha}\n" for _, sha in blobs).encode(),
        capture_output=True,
        check=True,
    ).stdout
    files, pos = {}, 0
    for rel, _sha in blobs:
        header_end = batch.index(b"\n", pos)  # "<sha> blob <size>"
        size = int(batch[pos:header_end].split(b" ")[2])
        start = header_end + 1
        files[rel] = batch[start : start + size].decode("utf-8", "replace")
        pos = start + size + 1  # each blob's content is followed by a newline
    return files


def _run(cwd: str, *args: str) -> str | None:
    try:
        proc = subprocess.run(["git", "-C", cwd, *args], capture_output=True)
    except OSError as exc:
        raise CollectError(f"can't run git: {exc}") from exc
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8", "replace")


def _git(cwd: str, *args: str, error: str) -> str:
    out = _run(cwd, *args)
    if out is None:
        raise CollectError(error)
    return out
