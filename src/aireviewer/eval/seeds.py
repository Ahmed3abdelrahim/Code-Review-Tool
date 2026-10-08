"""Seed trees for planted-bug cases (D21).

Layout: `eval/seeds/<repo>/<case id>/base/` and `.../head/` hold the two snapshots of a
case; an optional `.../pr.md` gives the pull request title (first line) and description.
Seed trees are repository content: they are copied into snapshot commits, never executed.
A seed must contain exactly what this repository's git records, so symlinks, `.git` entries
and paths ignored by this repository's `.gitignore` are refused rather than silently lost.
"""

from __future__ import annotations

import os
import re
import stat
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from pathspec import GitIgnoreSpec

from aireviewer.eval.cases import CASE_ID_PATTERN
from aireviewer.eval.errors import EvalInputError

__all__ = [
    "DEFAULT_PR_TITLE",
    "MAX_PR_TITLE",
    "SEEDS_DIR",
    "SeedCase",
    "SeedError",
    "collect_tree",
    "discover_seeds",
    "pr_description",
    "repository_ignore_spec",
]

SEEDS_DIR: Final = "seeds"
DEFAULT_PR_TITLE: Final = "Change under review"
MAX_PR_TITLE: Final = 120
MAX_PR_BODY: Final = 4000
_CASE_ID: Final = re.compile(CASE_ID_PATTERN)


class SeedError(EvalInputError):
    """A seed tree cannot be turned into a snapshot exactly."""


@dataclass(frozen=True, slots=True)
class SeedCase:
    repo: str
    case_id: str
    root: Path

    @property
    def base_dir(self) -> Path:
        return self.root / "base"

    @property
    def head_dir(self) -> Path:
        return self.root / "head"


def discover_seeds(eval_dir: Path) -> tuple[list[SeedCase], list[str]]:
    """All seed cases, sorted by repo and case id, plus problems with the layout."""
    seeds_dir = eval_dir / SEEDS_DIR
    if not seeds_dir.is_dir():
        return [], []
    seeds: list[SeedCase] = []
    errors: list[str] = []
    seen: dict[str, str] = {}
    for repo_dir in sorted(p for p in seeds_dir.iterdir() if p.is_dir()):
        for case_dir in sorted(p for p in repo_dir.iterdir() if p.is_dir()):
            where = f"{SEEDS_DIR}/{repo_dir.name}/{case_dir.name}"
            if not _CASE_ID.fullmatch(case_dir.name):
                errors.append(f"{where}: directory name is not a valid case id")
                continue
            missing = [part for part in ("base", "head") if not (case_dir / part).is_dir()]
            if missing:
                errors.append(f"{where}: missing {' and '.join(f'{m}/' for m in missing)}")
                continue
            if case_dir.name in seen:
                errors.append(f"{where}: case id also used in {SEEDS_DIR}/{seen[case_dir.name]}")
                continue
            seen[case_dir.name] = repo_dir.name
            seeds.append(SeedCase(repo_dir.name, case_dir.name, case_dir))
    return seeds, errors


def repository_ignore_spec(repo_root: Path) -> GitIgnoreSpec | None:
    """This repository's top-level .gitignore, to refuse seed files git would not record."""
    path = repo_root / ".gitignore"
    if not path.is_file():
        return None
    return GitIgnoreSpec.from_lines(path.read_text(encoding="utf-8").splitlines())


def collect_tree(root: Path, ignore: GitIgnoreSpec | None) -> list[str]:
    """Sorted repository-relative paths of the regular files under `root`."""
    files: list[str] = []
    problems: list[str] = []
    for current, dirs, names in os.walk(root, followlinks=False):
        here = Path(current)
        for name in list(dirs):
            path = here / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                problems.append(f"{relative}: symlinks are not allowed in seed trees")
                dirs.remove(name)
            elif name == ".git":
                problems.append(f"{relative}: .git directories are not allowed in seed trees")
                dirs.remove(name)
        for name in names:
            path = here / name
            relative = path.relative_to(root).as_posix()
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                problems.append(f"{relative}: symlinks are not allowed in seed trees")
            elif name == ".git":
                problems.append(f"{relative}: .git files are not allowed in seed trees")
            elif not stat.S_ISREG(mode):
                problems.append(f"{relative}: only regular files are allowed in seed trees")
            elif ignore is not None and ignore.match_file(relative):
                problems.append(
                    f"{relative}: ignored by this repository's .gitignore, so git would not "
                    "record it; rename or remove it"
                )
            else:
                files.append(relative)
    if problems:
        raise SeedError(*(f"{root}: {p}" for p in sorted(problems)))
    return sorted(files)


def pr_description(case_root: Path) -> tuple[str, str]:
    """(title, body) from `pr.md`: first non-empty line, then the rest."""
    path = case_root / "pr.md"
    if not path.is_file():
        return DEFAULT_PR_TITLE, ""
    lines = path.read_text(encoding="utf-8").splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    if not lines:
        return DEFAULT_PR_TITLE, ""
    title = lines[0].strip().lstrip("#").strip()
    body = "\n".join(lines[1:]).strip()
    for text in (title, body):
        if any(unicodedata.category(c) in ("Cc", "Cf", "Cs") for c in text if c not in "\n\t"):
            raise SeedError(f"{path}: control characters are not allowed")
    if not title or len(title) > MAX_PR_TITLE:
        raise SeedError(f"{path}: the title must be 1 to {MAX_PR_TITLE} characters")
    if len(body) > MAX_PR_BODY:
        raise SeedError(f"{path}: the description must be at most {MAX_PR_BODY} characters")
    return title, body
