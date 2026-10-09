"""Integrity of the committed benchmark under eval/ (T0.6, D21).

These tests read the real benchmark, both splits. Their output reaches Claude, so holdout
problems are reported only as counts and case ids (D21 point 9): every failure message is
built from sanitized text and raised with `pytest.fail(..., pytrace=False)`, never through
assertion introspection on holdout data. Unexpected exceptions are reported by type only.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import NoReturn

import pytest

from aireviewer.eval.bundles import MAX_BUNDLE_BYTES, MAX_TOTAL_BUNDLE_BYTES, bundle_problems
from aireviewer.eval.cases import Case, CaseKind, CaseSet, Provenance, Split, load_cases, split_root
from aireviewer.eval.seeds import SEEDS_DIR

pytestmark = pytest.mark.p0

EVAL_DIR = Path(__file__).resolve().parents[3] / "eval"
POLICY_FILE = ".ai-review.yml"
MIN_CASES = 20


def _hidden_failure(exc: BaseException, what: str) -> NoReturn:
    pytest.fail(
        f"{what} raised {type(exc).__name__} (details hidden: holdout material may be involved)",
        pytrace=False,
    )


def _load() -> CaseSet:
    try:
        return load_cases(EVAL_DIR)
    except Exception as exc:  # any message could quote holdout content
        _hidden_failure(exc, "loading the cases")


def _cases() -> tuple[Case, ...]:
    loaded = _load()
    if loaded.errors:
        pytest.fail("the cases are invalid:\n" + "\n".join(loaded.redacted_errors()), pytrace=False)
    if not loaded.cases:
        pytest.fail("the benchmark has no cases", pytrace=False)
    return loaded.cases


def _report(title: str, dev: Iterable[str], holdout_ids: Iterable[str]) -> None:
    """Fail with dev problems verbatim and holdout problems as a count of case ids."""
    dev, hidden = list(dev), sorted(set(holdout_ids))
    if not dev and not hidden:
        return
    lines = [f"{title}:", *dev]
    if hidden:
        lines.append(
            f"holdout: problems in {len(hidden)} case(s): {', '.join(hidden)} (details hidden)"
        )
    pytest.fail("\n".join(lines), pytrace=False)


def test_all_cases_valid() -> None:
    _cases()


def test_splits_repository_disjoint() -> None:
    loaded = _load()
    if not loaded.cases:
        pytest.fail("the benchmark has no valid cases", pytrace=False)
    shared = [
        ids
        for error, ids in zip(loaded.errors, loaded.error_holdout_ids, strict=True)
        if error.startswith("source.repo:")
    ]
    _report(
        f"{len(shared)} repository(ies) used by both splits",
        [],
        [case_id for ids in shared for case_id in ids],
    )


def test_bundles_contain_base_and_head() -> None:
    dev: list[str] = []
    hidden: list[str] = []
    for case in _cases():
        try:
            problems = bundle_problems(split_root(EVAL_DIR, case.split), case)
        except Exception as exc:
            if case.split is Split.HOLDOUT:
                _hidden_failure(exc, "checking a holdout bundle")
            raise
        if case.split is Split.HOLDOUT:
            hidden += [case.id] if problems else []
        else:
            dev += [f"{case.id}: {p}" for p in problems]
    _report("bundle problems", dev, hidden)


def test_benchmark_size_and_mix() -> None:
    cases = _cases()
    problems: list[str] = []
    if len(cases) < MIN_CASES:
        problems.append(f"{len(cases)} cases; at least {MIN_CASES} are needed")
    missing = sorted(k.value for k in set(CaseKind) - {c.kind for c in cases})
    if missing:
        problems.append(f"kinds missing from the benchmark: {', '.join(missing)}")
    for split in Split:
        if not any(c.split is split for c in cases):
            problems.append(f"the {split.value} split has no cases")
    total = 0
    hidden: list[str] = []
    for case in cases:
        path = split_root(EVAL_DIR, case.split) / case.bundle
        size = path.stat().st_size if path.is_file() else 0
        total += size
        if size > MAX_BUNDLE_BYTES:
            if case.split is Split.HOLDOUT:
                hidden.append(case.id)
            else:
                problems.append(f"{case.id}: bundle is {size} bytes (limit {MAX_BUNDLE_BYTES})")
    if total > MAX_TOTAL_BUNDLE_BYTES:
        problems.append(f"bundles total {total} bytes (limit {MAX_TOTAL_BUNDLE_BYTES})")
    _report("benchmark size and mix", problems, hidden)


def test_seed_policy_matches_case_policy() -> None:
    """A planted case's seed trees carry the case policy as .ai-review.yml, byte for byte."""
    dev: list[str] = []
    hidden: list[str] = []
    for case in _cases():
        if case.provenance is not Provenance.PLANTED:
            continue
        try:
            problems = _seed_policy_problems(split_root(EVAL_DIR, case.split), case)
        except Exception as exc:
            if case.split is Split.HOLDOUT:
                _hidden_failure(exc, "reading a holdout seed")
            raise
        if case.split is Split.HOLDOUT:
            hidden += [case.id] if problems else []
        else:
            dev += [f"{case.id}: {p}" for p in problems]
    _report("seed policies", dev, hidden)


def _seed_policy_problems(root: Path, case: Case) -> list[str]:
    seeds = sorted((root / SEEDS_DIR).glob(f"*/{case.id}")) if (root / SEEDS_DIR).is_dir() else []
    if len(seeds) != 1:
        return [f"expected one seed directory {SEEDS_DIR}/<repo>/{case.id}, found {len(seeds)}"]
    expected = (root / case.policy).read_bytes()
    problems = []
    for side in ("base", "head"):
        tree_policy = seeds[0] / side / POLICY_FILE
        if not tree_policy.is_file():
            problems.append(f"{side}/{POLICY_FILE} is missing")
        elif tree_policy.read_bytes() != expected:
            problems.append(f"{side}/{POLICY_FILE} differs from {case.policy}")
    return problems
