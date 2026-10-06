import pytest
from helpers import git


class Repo:
    """A throwaway repository on `main`, committed through isolated git."""

    def __init__(self, path):
        self.path = path

    def write(self, files: dict[str, str]) -> None:
        for rel, text in files.items():
            target = self.path / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8", newline="")  # keep CRLF as given

    def commit(self, message: str = "change") -> str:
        git(self.path, "add", "-A")
        git(self.path, "commit", "-q", "--allow-empty", "-m", message)
        return git(self.path, "rev-parse", "HEAD").strip()


@pytest.fixture
def make_repo(tmp_path):
    def make(files: dict[str, str], name: str = "repo") -> Repo:
        repo = Repo(tmp_path / name)
        repo.path.mkdir()
        git(repo.path, "init", "-q", "-b", "main")
        repo.write(files)
        repo.commit("initial")
        return repo

    return make


@pytest.fixture
def clone(tmp_path):
    def make(source: Repo, name: str = "clone"):
        target = tmp_path / name
        git(tmp_path, "clone", "-q", str(source.path), str(target))
        return target

    return make
