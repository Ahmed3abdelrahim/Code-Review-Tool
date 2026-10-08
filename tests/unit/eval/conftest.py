"""Shared factories for the evaluation tests (pure: safe to use from hypothesis tests)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from aireviewer.contracts.findings import Finding
from aireviewer.eval.adjudicate import Adjudication, AdjudicationIndex, Verdict
from aireviewer.eval.cases import Case
from aireviewer.eval.predictions import Predictions

SHA_BASE = "a" * 40
SHA_HEAD = "b" * 40
BUNDLE_BASE = "c" * 40
BUNDLE_HEAD = "e" * 40

type FindingFactory = Callable[..., Finding]
type LabelFactory = Callable[..., dict[str, Any]]
type CaseFactory = Callable[..., Case]


def _finding(
    *,
    path: str = "src/a.py",
    start: int = 10,
    end: int | None = None,
    category: str = "correctness",
    severity: str = "high",
    channel: str = "inline",
    side: str = "RIGHT",
    rule_id: str | None = None,
    title: str = "A bug",
    excerpt: str = "x = 1",
    fingerprint: str = "",
    source: str = "llm",
) -> Finding:
    return Finding.model_validate(
        {
            "source": source,
            "category": category,
            "rule_id": rule_id,
            "severity": severity,
            "title": title,
            "location": {
                "path": path,
                "start_line": start,
                "end_line": end if end is not None else start,
                "side": side,
            },
            "evidence": [{"path": path, "line": start, "side": side, "excerpt": excerpt}],
            "explanation": "Explanation.",
            "channel": channel,
            "fingerprint": fingerprint,
        }
    )


def _label(
    label_id: str = "L1",
    *,
    path: str = "src/a.py",
    lines: tuple[int, int] = (10, 10),
    category: str = "correctness",
    severity: str = "high",
    side: str | None = None,
    must_find: bool | None = None,
    description: str = "A labeled defect",
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": label_id,
        "category": category,
        "severity": severity,
        "path": path,
        "lines": list(lines),
        "description": description,
    }
    if side is not None:
        data["side"] = side
    if must_find is not None:
        data["must_find"] = must_find
    return data


def case_data(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": "case-one",
        "split": "dev",
        "kind": "defect",
        "language": "python",
        "source": {
            "repo": "https://github.com/example/shop",
            "license": "MIT",
            "pr": 123,
            "base_sha": SHA_BASE,
            "head_sha": SHA_HEAD,
        },
        "bundle": "bundles/case.bundle",
        "bundle_base_sha": BUNDLE_BASE,
        "bundle_head_sha": BUNDLE_HEAD,
        "policy": "policies/default.yml",
        "labels": [_label()],
        "provenance": "hand-labeled",
    }
    data.update(overrides)
    return data


def _case(**overrides: Any) -> Case:
    return Case.model_validate(case_data(**overrides))


@pytest.fixture
def make_finding() -> FindingFactory:
    return _finding


@pytest.fixture
def make_label() -> LabelFactory:
    return _label


@pytest.fixture
def make_case() -> CaseFactory:
    return _case


@pytest.fixture
def make_case_data() -> Callable[..., dict[str, Any]]:
    return case_data


@pytest.fixture
def eval_dir(tmp_path: Path) -> Path:
    """An eval/ directory with one bundle and one valid policy, and no cases yet."""
    root = tmp_path / "eval"
    (root / "cases").mkdir(parents=True)
    (root / "bundles").mkdir()
    (root / "policies").mkdir()
    (root / "bundles" / "case.bundle").write_bytes(b"")
    (root / "policies" / "default.yml").write_text("version: 1\n", encoding="utf-8")
    return root


@pytest.fixture
def write_case(eval_dir: Path) -> Callable[..., Path]:
    def write(data: dict[str, Any] | str, name: str | None = None) -> Path:
        if isinstance(data, str):
            text, stem = data, name or "case-one"
        else:
            text, stem = yaml.safe_dump(data, sort_keys=False), name or str(data["id"])
        path = eval_dir / "cases" / f"{stem}.yaml"
        path.write_text(text, encoding="utf-8")
        return path

    return write


# --- hand-built fixture set with hand-computed metrics (T0.5 AC4) -----------------------
#
# case-defect (defect): L1 correctness high a.py 10-12 must_find; L2 security medium a.py 30;
#                       L3 correctness critical a.py 80-82 must_find; expect.max_inline 2
#   P1  inline  correctness high   a.py 11  -> matches L1 (a stale "invalid" verdict is ignored)
#   P2  inline  reliability medium a.py 33  -> unmatched (security label), adjudicated invalid
#   P3  summary security low       a.py 28  -> matches L2 (gap 2)
#   P4  inline  lint F401          a.py 1   -> unmatched, no verdict: pending
# case-clean (clean): no labels
#   P5  inline  correctness medium c.py 5   -> valid
#   P6  inline  performance high   c.py 9   -> invalid
#   P7  annotation lint E501       c.py 1   -> not scored
#   P11 inline  correctness high   c.py 5   -> duplicate
# case-design (design): L1 design high b.py 5
#   P8  summary design layering.api-db b.py 5   -> matches L1
#   P9  summary design layering.api-db b.py 40  -> invalid
#   P10 inline  maintainability C901   b.py 50  -> valid
#
# Inline: n=7 (P1 P2 P4 P5 P6 P10 P11), correct 3, pending 1, invalid 2, duplicate 1
#   -> [3/7, 4/7]; correctness 2/3; reliability 0/1; lint [0, 1]; performance 0/1;
#      maintainability 1/1
# Summary: n=3 (P3 P8 P9), correct 2 -> 2/3; security 1/1; design 1/2
# High-severity recall: labels c-defect L1, L3, c-design L1 = 3; matched (any) 2 -> 2/3;
#   inline only 1 (P1) -> 1/3
# False positives per PR: invalid inline 2, pending inline 1, cases 3 -> [2/3, 3/3]
# Inline per case: 3, 3, 1 -> mean 7/3, max 3
# Per rule: layering.api-db 1/2 (P8 matched, P9 invalid); C901 1/1 (P10 valid)
# Missed must_find: case-defect/L3. Over max_inline: case-defect (3 > 2). Unscored: 1 annotation.


@dataclass(frozen=True)
class KnownValues:
    cases: tuple[Case, ...]
    predictions: Predictions
    index: AdjudicationIndex
    findings: dict[str, Finding]


VERDICT_TIME = datetime(2026, 10, 1, 9, 30, tzinfo=UTC)


def _known_values() -> KnownValues:
    defect = _case(
        id="case-defect",
        labels=[
            _label("L1", lines=(10, 12), must_find=True),
            _label("L2", lines=(30, 30), category="security", severity="medium"),
            _label("L3", lines=(80, 82), severity="critical", must_find=True),
        ],
        expect={"max_inline": 2},
    )
    clean = _case(id="case-clean", kind="clean", labels=[])
    design = _case(
        id="case-design",
        kind="design",
        labels=[_label("L1", path="src/b.py", lines=(5, 5), category="design")],
    )

    def f(name: str, **kw: Any) -> Finding:
        return _finding(title=f"Finding {name}", excerpt=f"code of {name}", **kw)

    findings = {
        "P1": f("P1", start=11),
        "P2": f("P2", start=33, category="reliability", severity="medium"),
        "P3": f("P3", start=28, category="security", severity="low", channel="summary"),
        "P4": f("P4", start=1, category="lint", severity="low", rule_id="F401", source="ruff"),
        "P5": f("P5", path="src/c.py", start=5, severity="medium"),
        "P6": f("P6", path="src/c.py", start=9, category="performance"),
        "P7": f(
            "P7",
            path="src/c.py",
            start=1,
            category="lint",
            severity="low",
            rule_id="E501",
            channel="annotation",
            source="ruff",
        ),
        "P11": f("P11", path="src/c.py", start=5),
        "P8": f(
            "P8",
            path="src/b.py",
            start=5,
            category="design",
            severity="medium",
            rule_id="layering.api-db",
            channel="summary",
            source="depgraph",
        ),
        "P9": f(
            "P9",
            path="src/b.py",
            start=40,
            category="design",
            severity="medium",
            rule_id="layering.api-db",
            channel="summary",
            source="depgraph",
        ),
        "P10": f(
            "P10",
            path="src/b.py",
            start=50,
            category="maintainability",
            severity="medium",
            rule_id="C901",
            source="lizard",
        ),
    }
    by_case = {
        "case-defect": tuple(findings[n] for n in ("P1", "P2", "P3", "P4")),
        "case-clean": tuple(findings[n] for n in ("P5", "P6", "P7", "P11")),
        "case-design": tuple(findings[n] for n in ("P8", "P9", "P10")),
    }
    cases = {c.id: c for c in (defect, clean, design)}
    verdicts = [
        ("case-defect", "P1", Verdict.INVALID),  # stale: P1 is matched, so it counts as correct
        ("case-defect", "P2", Verdict.INVALID),
        ("case-clean", "P5", Verdict.VALID),
        ("case-clean", "P6", Verdict.INVALID),
        ("case-clean", "P11", Verdict.DUPLICATE),
        ("case-design", "P9", Verdict.INVALID),
        ("case-design", "P10", Verdict.VALID),
    ]
    records = [
        Adjudication.for_finding(
            cases[case_id],
            findings[name],
            verdict=verdict,
            note=f"{name} checked",
            adjudicated_at=VERDICT_TIME,
        )
        for case_id, name, verdict in verdicts
    ]
    return KnownValues(
        cases=(defect, clean, design),
        predictions=Predictions(producer={"engine": "fixture-1", "model": "none"}, by_case=by_case),
        index=AdjudicationIndex(records),
        findings=findings,
    )


@pytest.fixture
def known_values() -> KnownValues:
    return _known_values()
