"""Seed trees for planted-bug cases: eval/seeds/<repo>/<case>/{base,head}/ (D21)."""

from __future__ import annotations

from pathlib import Path

import pytest

from aireviewer.eval.seeds import (
    DEFAULT_PR_TITLE,
    SeedError,
    collect_tree,
    discover_seeds,
    pr_description,
    repository_ignore_spec,
)

pytestmark = pytest.mark.p0


def write(root: Path, files: dict[str, str]) -> None:
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def seed(
    eval_dir: Path, repo: str, case_id: str, base: dict[str, str], head: dict[str, str]
) -> Path:
    root = eval_dir / "seeds" / repo / case_id
    write(root / "base", base)
    write(root / "head", head)
    return root


def test_discover_seeds(tmp_path: Path) -> None:
    eval_dir = tmp_path / "eval"
    seed(eval_dir, "py-shop", "py-shop-001", {"a.py": "x = 1\n"}, {"a.py": "x = 2\n"})
    seed(eval_dir, "ts-tasks", "ts-tasks-001", {"a.ts": "1\n"}, {"a.ts": "2\n"})
    (eval_dir / "seeds" / "py-shop" / "py-shop-002" / "base").mkdir(parents=True)  # no head/
    (eval_dir / "seeds" / "py-shop" / "Bad_Name" / "base").mkdir(parents=True)
    (eval_dir / "seeds" / "README.md").write_text("notes\n", encoding="utf-8")

    seeds, errors = discover_seeds(eval_dir)
    assert [(s.repo, s.case_id) for s in seeds] == [
        ("py-shop", "py-shop-001"),
        ("ts-tasks", "ts-tasks-001"),
    ]
    assert seeds[0].base_dir == eval_dir / "seeds" / "py-shop" / "py-shop-001" / "base"
    assert any("py-shop-002" in e and "head" in e for e in errors), errors
    assert any("Bad_Name" in e and "case id" in e for e in errors), errors
    assert discover_seeds(tmp_path / "nothing") == ([], [])


def test_collect_tree_lists_files_sorted(tmp_path: Path) -> None:
    write(tmp_path, {"src/b.py": "b", "src/a.py": "a", "README.md": "r", "pkg/sub/c.ts": "c"})
    (tmp_path / "empty-dir").mkdir()  # git cannot record empty directories: ignored
    assert collect_tree(tmp_path, None) == ["README.md", "pkg/sub/c.ts", "src/a.py", "src/b.py"]


@pytest.mark.parametrize("kind", ["file-link", "dir-link"])
def test_collect_tree_rejects_symlinks(tmp_path: Path, kind: str) -> None:
    root = tmp_path / "tree"
    write(root, {"a.py": "a"})
    target = tmp_path / "outside"
    target.mkdir()
    (target / "secret.txt").write_text("s", encoding="utf-8")
    if kind == "file-link":
        (root / "link.txt").symlink_to(target / "secret.txt")
    else:
        (root / "linked").symlink_to(target)
    with pytest.raises(SeedError, match="symlink"):
        collect_tree(root, None)


def test_collect_tree_rejects_git_metadata(tmp_path: Path) -> None:
    write(tmp_path, {"a.py": "a", "sub/.git/config": "[core]\n"})
    with pytest.raises(SeedError, match=r"\.git"):
        collect_tree(tmp_path, None)
    (tmp_path / "sub" / ".git" / "config").unlink()
    (tmp_path / "sub" / ".git").rmdir()
    (tmp_path / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")
    with pytest.raises(SeedError, match=r"\.git"):
        collect_tree(tmp_path, None)


def test_collect_tree_rejects_paths_this_repository_ignores(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".gitignore").write_text(
        ".env\n.env.*\n!.env.example\nbuild/\n*.pem\n__pycache__/\n", encoding="utf-8"
    )
    spec = repository_ignore_spec(repo)
    assert spec is not None
    tree = tmp_path / "tree"
    write(tree, {"src/a.py": "a", ".env.example": "X=1"})
    assert collect_tree(tree, spec) == [".env.example", "src/a.py"]
    for ignored in (
        ".env",
        "web/.env.local",
        "build/out.js",
        "certs/k.pem",
        "src/__pycache__/a.pyc",
    ):
        write(tree, {ignored: "x"})
        with pytest.raises(SeedError, match="ignored"):
            collect_tree(tree, spec)
        (tree / ignored).unlink()
    assert repository_ignore_spec(tmp_path / "no-repo") is None


def test_collect_tree_reports_every_problem(tmp_path: Path) -> None:
    write(tmp_path, {"a.py": "a", ".git/HEAD": "ref"})
    (tmp_path / "l").symlink_to(tmp_path / "a.py")
    with pytest.raises(SeedError) as excinfo:
        collect_tree(tmp_path, None)
    assert len(excinfo.value.messages) == 2


def test_pr_description(tmp_path: Path) -> None:
    assert pr_description(tmp_path) == (DEFAULT_PR_TITLE, "")
    (tmp_path / "pr.md").write_text(
        "Add bulk discounts\n\nApplies tiered rates.\n", encoding="utf-8"
    )
    assert pr_description(tmp_path) == ("Add bulk discounts", "Applies tiered rates.")
    (tmp_path / "pr.md").write_text("\n\n", encoding="utf-8")
    assert pr_description(tmp_path) == (DEFAULT_PR_TITLE, "")
    (tmp_path / "pr.md").write_text("t" * 300 + "\n", encoding="utf-8")
    with pytest.raises(SeedError, match="title"):
        pr_description(tmp_path)
    (tmp_path / "pr.md").write_text("Title\x1b[2J\n", encoding="utf-8")
    with pytest.raises(SeedError, match="control"):
        pr_description(tmp_path)
