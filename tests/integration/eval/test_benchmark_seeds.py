"""The committed seed trees still produce the committed case bundles (T0.6, D21).

Rebuilds every seed of both splits into a temporary directory (git runs only there) and
compares the snapshot SHAs with the case files, so a seed edited without re-running
`aireview-eval seed-build` is caught. Needs the git CLI. Holdout problems are reported as
case ids only (D21 point 9).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aireviewer.eval.bundles import build_seed_bundle
from aireviewer.eval.cases import Split, load_cases, split_root
from aireviewer.eval.seeds import discover_seeds, pr_description, repository_ignore_spec

pytestmark = pytest.mark.p0

REPO_ROOT = Path(__file__).resolve().parents[3]
EVAL_DIR = REPO_ROOT / "eval"


def test_seed_bundles_match_seed_trees(tmp_path: Path) -> None:
    try:
        loaded = load_cases(EVAL_DIR)
    except Exception as exc:  # any message could quote holdout content
        pytest.fail(f"loading the cases raised {type(exc).__name__}", pytrace=False)
    cases = {c.id: c for c in loaded.cases}
    ignore = repository_ignore_spec(REPO_ROOT)
    dev: list[str] = []
    hidden: set[str] = set()
    built = 0
    for split in Split:
        root = split_root(EVAL_DIR, split)
        seeds, layout_errors = discover_seeds(root)
        if split is Split.HOLDOUT:
            hidden |= {f"<layout problem {n + 1}>" for n in range(len(layout_errors))}
        else:
            dev += layout_errors
        for seed in seeds:
            problem = None
            try:
                title, body = pr_description(seed.root)
                info = build_seed_bundle(
                    seed.case_id,
                    seed.base_dir,
                    seed.head_dir,
                    tmp_path / split.value / f"{seed.case_id}.bundle",
                    title=title,
                    body=body,
                    ignore=ignore,
                )
            except Exception as exc:
                problem = f"cannot be built ({type(exc).__name__}: {exc})"
            else:
                built += 1
                case = cases.get(seed.case_id)
                if case is None or case.split is not split:
                    problem = "no valid case file in this split"
                elif (case.bundle_base_sha, case.bundle_head_sha) != (info.base_sha, info.head_sha):
                    problem = (
                        f"the seed gives base {info.base_sha[:12]} head {info.head_sha[:12]}, "
                        f"the case file says base {case.bundle_base_sha[:12]} "
                        f"head {case.bundle_head_sha[:12]}; re-run seed-build"
                    )
            if problem is None:
                continue
            if split is Split.HOLDOUT:
                hidden.add(seed.case_id)
            else:
                dev.append(f"{seed.case_id}: {problem}")
    if built == 0 and not dev and not hidden:
        pytest.fail("no seed cases found", pytrace=False)
    if dev or hidden:
        lines = ["seed trees and case bundles disagree:", *dev]
        if hidden:
            lines.append(f"holdout: problems in {len(hidden)} seed(s): {', '.join(sorted(hidden))}")
        pytest.fail("\n".join(lines), pytrace=False)
