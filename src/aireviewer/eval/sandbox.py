"""Shell commands for pushing benchmark cases to the sandbox organization (D11, D21).

This module only formats text: the user runs the commands. Every value placed in a command
is validated or shell-quoted. The pull request title and description come from the seed's
pr.md (or a neutral default) and never mention the labels, so a reviewer under evaluation
gets no hints.
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Sequence
from pathlib import Path
from typing import Final
from urllib.parse import urlsplit

from aireviewer.eval.bundles import case_refs
from aireviewer.eval.cases import Case
from aireviewer.eval.seeds import DEFAULT_PR_TITLE, SEEDS_DIR, pr_description

__all__ = ["ORG_PATTERN", "sandbox_commands", "sandbox_repo_name"]

ORG_PATTERN: Final = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})")
_REPO_NAME: Final = re.compile(r"[A-Za-z0-9._-]{1,100}")


def sandbox_repo_name(case: Case) -> str:
    """The sandbox repository for a case: the last segment of its source repository URL."""
    name = urlsplit(case.source.repo).path.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
    if not _REPO_NAME.fullmatch(name) or name in (".", ".."):
        raise ValueError(f"{case.id}: cannot derive a repository name from {case.source.repo}")
    return name


def sandbox_commands(cases: Sequence[Case], *, eval_dir: Path, org: str) -> str:
    if not ORG_PATTERN.fullmatch(org):
        raise ValueError(f"invalid GitHub organization name: {org!r}")
    q = shlex.quote
    eval_abs = eval_dir.resolve()
    out = [
        "# Run these yourself, in order. Nothing here has been executed.",
        f"# Create each sandbox repository on GitHub first (empty), under {org}.",
        "",
    ]
    by_repo: dict[str, list[Case]] = {}
    for case in cases:
        by_repo.setdefault(sandbox_repo_name(case), []).append(case)
    for repo, repo_cases in sorted(by_repo.items()):
        clone = eval_abs / "repos" / "sandbox" / repo
        out += [
            f"# --- {org}/{repo} ---",
            f"git init -q {q(str(clone))}",
            f"cd {q(str(clone))}",
            f"git remote add sandbox https://github.com/{org}/{repo}.git",
            "",
        ]
        for case in sorted(repo_cases, key=lambda c: c.id):
            base_ref, head_ref = case_refs(case.id)
            base_branch = f"aireview/{case.id}/base"
            head_branch = f"aireview/{case.id}/head"
            title, body = _pr_text(eval_abs, case)
            export = eval_abs / "baselines" / "coderabbit" / f"{case.id}.json"
            number = f"$(gh pr view {head_branch} --repo {org}/{repo} --json number --jq .number)"
            out += [
                f"# {case.id}",
                f"git fetch -q {q(str(eval_abs / case.bundle))} "
                f"'{base_ref}:{base_ref}' '{head_ref}:{head_ref}'",
                "git push sandbox "
                f"{base_ref}:refs/heads/{base_branch} {head_ref}:refs/heads/{head_branch}",
                f"gh pr create --repo {org}/{repo} --base {base_branch} --head {head_branch} "
                f"--title {q(title)} --body {q(body)}",
                "# after CodeRabbit has reviewed the pull request:",
                f'gh api --paginate "repos/{org}/{repo}/pulls/{number}/comments" '
                f"> {q(str(export))}",
                "",
            ]
    return "\n".join(out) + "\n"


def _pr_text(eval_dir: Path, case: Case) -> tuple[str, str]:
    seeds = (
        sorted((eval_dir / SEEDS_DIR).glob(f"*/{case.id}"))
        if (eval_dir / SEEDS_DIR).is_dir()
        else []
    )
    if seeds:
        return pr_description(seeds[0])
    return DEFAULT_PR_TITLE, ""
