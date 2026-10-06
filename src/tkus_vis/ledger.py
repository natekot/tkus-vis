"""The tkus ledger file format ("Ledger format" in the tkus README).

Pure: no git, no I/O. tkus-vis depends on the documented format only, never on
tkus itself, so the path rules are reimplemented here to match tkus's
repoledger._sanitize / _branch_path and __main__._ledger_scope.
"""

from __future__ import annotations

import re

LEDGER_DIR = ".tkus"

# Characters Windows forbids in filenames. tkus replaces each with "-".
_UNSAFE = re.compile(r'[<>:"\\|?*\x00-\x1f]')


def sanitize_segment(name: str, fallback: str) -> str:
    name = _UNSAFE.sub("-", (name or "").strip())
    name = name.strip(". ")  # Windows rejects leading/trailing dots and spaces
    return name or fallback


def branch_key(name: str) -> str:
    """A branch name as tkus files it: each "/" segment sanitised separately.

    PR head refs and the default branch must pass through this before they are
    compared with ledger paths, or names with forbidden characters never match.
    A blank name files under "detached", as tkus's branch_name does.
    """
    if not name.strip():
        return "detached"
    return "/".join(sanitize_segment(part, "-") for part in name.strip().split("/"))


def split_ledger_path(rel: str) -> tuple[str, str]:
    """(identity, branch) for a path under .tkus/, grouped as `tkus rollup` does."""
    parts = rel.split("/")
    if len(parts) <= 2:
        return "unknown", rel
    return parts[1], "/".join(parts[2:]).rsplit(".jsonl", 1)[0]
