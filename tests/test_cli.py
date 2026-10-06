import json

import pytest
from helpers import entry, ledger, tkus_ledger_files

from tkus_vis.cli import main


def build(repo_path, out, *extra):
    return main(
        ["build", "--path", str(repo_path), "--default-branch", "main", "-o", str(out), *extra]
    )


def test_build_writes_report_and_dataset(make_repo, tmp_path, capsys):
    repo = make_repo(tkus_ledger_files())
    out = tmp_path / "out" / "report.html"
    assert build(repo.path, out) == 0
    assert "AI agent spend: repo" in out.read_text(encoding="utf-8")
    data = json.loads((tmp_path / "out" / "report.json").read_text(encoding="utf-8"))
    assert data["views"][0]["total"] == pytest.approx(66.9073434, abs=1e-6)
    assert "66.91 USD" in capsys.readouterr().out


def test_ledger_problems_go_to_stderr(make_repo, tmp_path, capsys):
    repo = make_repo({".tkus/a/main.jsonl": ledger(entry(1.0), "{corrupt")})
    assert build(repo.path, tmp_path / "r.html") == 0
    assert ".tkus/a/main.jsonl:2: skipped: not valid JSON" in capsys.readouterr().err


def test_repo_without_ledger_still_reports(make_repo, tmp_path, capsys):
    repo = make_repo({"README.md": "hi\n"})
    assert build(repo.path, tmp_path / "r.html") == 0
    assert "unknown, not zero" in (tmp_path / "r.html").read_text(encoding="utf-8")
    assert "cost unknown" in capsys.readouterr().out


def test_collect_errors_exit_2(tmp_path, capsys):
    assert build(tmp_path, tmp_path / "r.html") == 2
    assert "not a git repository" in capsys.readouterr().err


def test_dataset_may_not_overwrite_the_report(make_repo, tmp_path, capsys):
    repo = make_repo({".tkus/a/main.jsonl": ledger(entry(1.0))})
    assert build(repo.path, tmp_path / "r.json") == 2
    assert "would overwrite" in capsys.readouterr().err


def test_explicit_data_path(make_repo, tmp_path):
    repo = make_repo({".tkus/a/main.jsonl": ledger(entry(1.0))})
    assert build(repo.path, tmp_path / "r.html", "--data", str(tmp_path / "d" / "x.json")) == 0
    assert (tmp_path / "d" / "x.json").is_file()
