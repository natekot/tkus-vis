import pytest

from tkus_vis.ledger import branch_key, split_ledger_path


@pytest.mark.parametrize(
    "name, key",
    [
        ("feature/x", "feature/x"),
        ('fix/a:b<c>"d|e?f*g', "fix/a-b-c--d-e-f-g"),  # Windows-forbidden characters
        ("release/.hidden.", "release/hidden"),  # leading/trailing dots stripped
        (" spaced ", "spaced"),
        ("a/../b", "a/-/b"),  # a segment left empty becomes "-"
        ("tab\there", "tab-here"),  # control characters
        ("fix/ünïcode", "fix/ünïcode"),  # non-ASCII is kept
        ("", "detached"),
    ],
)
def test_branch_key_matches_tkus(name, key):
    # Mirrors tkus's repoledger._branch_path / _sanitize, applied per "/" segment.
    assert branch_key(name) == key


def test_split_ledger_path():
    assert split_ledger_path(".tkus/alice/feature/x.jsonl") == ("alice", "feature/x")
    assert split_ledger_path(".tkus/bob/main.jsonl") == ("bob", "main")
    # A file directly under .tkus/ has no identity; tkus groups it under its whole path.
    assert split_ledger_path(".tkus/stray.jsonl") == ("unknown", ".tkus/stray.jsonl")
