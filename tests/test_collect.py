import pytest
from helpers import entry, git, ledger

from tkus_vis.collect import CollectError, read_local


def test_reads_every_ledger_file_at_the_ref(make_repo):
    repo = make_repo(
        {
            ".tkus/alice/main.jsonl": ledger(entry(1.0)),
            ".tkus/alice/feature/x.jsonl": ledger(entry(2.0)),
            ".tkus/bob/feature/x.jsonl": ledger(entry(3.0)),
            ".tkus/README.md": "not a ledger",
            "src/app.py": "print()\n",
        }
    )
    snap = read_local(str(repo.path), default_branch="main")
    assert (snap.repo, snap.ref, snap.default_branch) == ("repo", "main", "main")
    assert snap.commit == git(repo.path, "rev-parse", "HEAD").strip()
    assert sorted(snap.files) == [
        ".tkus/alice/feature/x.jsonl",
        ".tkus/alice/main.jsonl",
        ".tkus/bob/feature/x.jsonl",
    ]
    assert snap.files[".tkus/alice/main.jsonl"] == ledger(entry(1.0))


def test_reads_the_commit_not_the_worktree(make_repo):
    repo = make_repo({".tkus/alice/main.jsonl": ledger(entry(1.0))})
    repo.write(
        {
            ".tkus/alice/main.jsonl": ledger(entry(1.0), entry(9.0)),
            ".tkus/alice/new.jsonl": ledger(entry(5.0)),
        }
    )
    snap = read_local(str(repo.path), default_branch="main")
    assert snap.files == {".tkus/alice/main.jsonl": ledger(entry(1.0))}


def test_reads_non_ascii_paths_exactly(make_repo):
    path = ".tkus/zoë/fix/ünïcode café.jsonl"
    repo = make_repo({path: ledger(entry(1.0))})
    assert list(read_local(str(repo.path), default_branch="main").files) == [path]


def test_an_explicit_ref_is_read(make_repo):
    repo = make_repo({".tkus/a/main.jsonl": ledger(entry(1.0))})
    first = git(repo.path, "rev-parse", "HEAD").strip()
    repo.write({".tkus/a/main.jsonl": ledger(entry(1.0), entry(2.0))})
    repo.commit()
    snap = read_local(str(repo.path), ref=first, default_branch="main")
    assert snap.commit == first
    assert snap.files[".tkus/a/main.jsonl"] == ledger(entry(1.0))


def test_default_branch_and_ref_come_from_origin_head(make_repo, clone):
    path = clone(make_repo({".tkus/a/main.jsonl": ledger(entry(1.0))}))
    git(path, "checkout", "-q", "-b", "feature/y")
    snap = read_local(str(path))
    assert (snap.default_branch, snap.ref) == ("main", "origin/main")


def test_without_origin_head_the_default_branch_must_be_given(make_repo):
    repo = make_repo({".tkus/a/main.jsonl": ledger(entry(1.0))})
    git(repo.path, "checkout", "-q", "-b", "feature/y")
    with pytest.raises(CollectError, match="--default-branch"):
        read_local(str(repo.path))


def test_a_repo_without_a_ledger_has_no_files(make_repo):
    repo = make_repo({"README.md": "hi\n"})
    assert read_local(str(repo.path), default_branch="main").files == {}


def test_unknown_ref_is_an_error(make_repo):
    repo = make_repo({"README.md": "hi\n"})
    with pytest.raises(CollectError, match="nope"):
        read_local(str(repo.path), ref="nope", default_branch="main")


def test_not_a_repository_is_an_error(tmp_path):
    with pytest.raises(CollectError, match="not a git repository"):
        read_local(str(tmp_path), default_branch="main")


def test_default_branch_must_name_a_real_branch(make_repo, clone):
    # "origin/main" resolves as a ref but is not a branch name, so nothing would land
    # in the direct bucket. That must be an error, not a silent 0.00.
    path = clone(make_repo({".tkus/a/main.jsonl": ledger(entry(1.0))}))
    git(path, "remote", "set-head", "origin", "-d")
    with pytest.raises(CollectError, match="--default-branch main"):
        read_local(str(path), default_branch="origin/main")


def test_without_a_local_default_branch_the_remote_one_is_read(make_repo, clone):
    path = clone(make_repo({".tkus/a/main.jsonl": ledger(entry(1.0))}))
    git(path, "checkout", "-q", "-b", "feature/y")
    git(path, "branch", "-q", "-D", "main")
    git(path, "remote", "set-head", "origin", "-d")
    snap = read_local(str(path), default_branch="main")
    assert (snap.ref, snap.default_branch) == ("origin/main", "main")
    assert snap.files == {".tkus/a/main.jsonl": ledger(entry(1.0))}
