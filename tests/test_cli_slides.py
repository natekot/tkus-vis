import json

import pytest
from helpers import entry, ledger, needs_chrome, tkus_ledger_files

from tkus_vis.cli import currency_prefixes, main


def slides(repo_path, out):
    return main(["slides", "--path", str(repo_path), "--default-branch", "main", "-o", str(out)])


@needs_chrome
def test_slides_writes_images_and_the_dataset(make_repo, tmp_path, capsys):
    out = tmp_path / "slides"
    assert slides(make_repo(tkus_ledger_files()).path, out) == 0
    stems = ("01-headline", "02-weekly-spend", "03-spend-by-model", "04-where-spend-sits")
    assert sorted(p.name for p in out.iterdir()) == sorted(
        [f"{stem}.{ext}" for stem in stems for ext in ("png", "pdf")] + ["dataset.json"]
    )
    data = json.loads((out / "dataset.json").read_text(encoding="utf-8"))
    assert data["views"][0]["total"] == pytest.approx(66.9073434, abs=1e-6)
    assert "01-headline.png" in capsys.readouterr().out


@needs_chrome
def test_currency_names_cannot_escape_the_output_directory(make_repo, tmp_path):
    repo = make_repo({".tkus/a/main.jsonl": ledger(entry(1.0), entry(2.0, currency="../../x"))})
    out = tmp_path / "slides"
    assert slides(repo.path, out) == 0
    names = {p.name for p in out.iterdir()}
    assert "usd-01-headline.png" in names
    assert "x-01-headline.png" in names  # "../../x" slugged to "x"
    assert not (tmp_path / "x-01-headline.png").exists()


def test_no_ledger_writes_no_slides(make_repo, tmp_path, capsys):
    out = tmp_path / "slides"
    assert slides(make_repo({"README.md": "hi\n"}).path, out) == 0
    assert "no slides were written" in capsys.readouterr().out
    assert not out.exists()


def test_collect_errors_exit_2(tmp_path, capsys):
    assert slides(tmp_path, tmp_path / "out") == 2
    assert "not a git repository" in capsys.readouterr().err


def test_currency_prefixes_never_collide():
    # "€" and "£" both slug to "currency"; "USD" and "usd" both to "usd".
    assert currency_prefixes(["€", "£", "USD", "usd", "../../x"]) == [
        "currency",
        "currency-2",
        "usd",
        "usd-2",
        "x",
    ]
