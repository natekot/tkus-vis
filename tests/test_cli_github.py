import json

import pytest
import synthetic
from helpers import FIXTURES, fake_github, replay

from tkus_vis import github
from tkus_vis.cli import main


@pytest.fixture
def synthetic_github(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setattr(
        github, "_urlopen", fake_github(synthetic.REPO, synthetic.FILES, synthetic.PRS)
    )


def dataset_of(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_build_with_repo_joins_prs(synthetic_github, tmp_path):
    out = tmp_path / "r.html"
    assert main(["build", "--repo", synthetic.REPO, "-o", str(out)]) == 0
    data = dataset_of(tmp_path / "r.json")
    assert (data["coverage"]["merged"], data["coverage"]["with_cost"]) == (6, 4)
    assert data["views"][0]["buckets"] == pytest.approx(
        {"direct": 2.0, "pr": 29.0, "unmatched": 18.5}
    )
    assert "In pull requests" in out.read_text(encoding="utf-8")


def test_path_and_repo_read_the_ledger_locally_and_prs_from_github(
    synthetic_github, make_repo, tmp_path
):
    repo = make_repo(synthetic.FILES)
    args = ["build", "--path", str(repo.path), "--default-branch", "main"]
    assert main([*args, "--repo", synthetic.REPO, "-o", str(tmp_path / "r.html")]) == 0
    assert dataset_of(tmp_path / "r.json")["views"][0]["buckets"]["pr"] == pytest.approx(29.0)


def test_recorded_natekot_tkus_has_no_merged_prs(monkeypatch, tmp_path):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setattr(github, "_urlopen", replay(FIXTURES / "github" / "natekot-tkus"))
    assert main(["build", "--repo", "natekot/tkus", "-o", str(tmp_path / "r.html")]) == 0
    data = dataset_of(tmp_path / "r.json")
    assert data["coverage"]["merged"] == 0
    assert data["views"][0]["buckets"]["pr"] == 0.0  # every branch: no PR found


def test_neither_path_nor_repo_is_a_usage_error(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["build", "-o", "r.html"])
    assert exc.value.code == 2 and "--path, --repo" in capsys.readouterr().err


def test_a_malformed_repo_name_is_a_usage_error():
    with pytest.raises(SystemExit) as exc:
        main(["build", "--repo", "not a repo", "-o", "r.html"])
    assert exc.value.code == 2


def test_github_errors_exit_2(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setattr(github, "_urlopen", fake_github("a/b", {}, [], status=(404, {})))
    assert main(["build", "--repo", "a/b", "-o", str(tmp_path / "r.html")]) == 2
    err = capsys.readouterr().err
    assert "not found on GitHub" in err and "test-token" not in err


def test_a_missing_token_warns_and_carries_on(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("tkus_vis.cli.token", lambda: None)
    monkeypatch.setattr(
        github, "_urlopen", fake_github(synthetic.REPO, synthetic.FILES, synthetic.PRS)
    )
    assert main(["build", "--repo", synthetic.REPO, "-o", str(tmp_path / "r.html")]) == 0
    assert "no GitHub token" in capsys.readouterr().err
