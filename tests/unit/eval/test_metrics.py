"""Evaluation metrics (plan section 8.5, D20) against hand-computed values."""

from __future__ import annotations

from datetime import UTC, datetime
from fractions import Fraction
from typing import Any

import pytest

from aireviewer.eval.adjudicate import Adjudication, AdjudicationIndex, Verdict
from aireviewer.eval.metrics import Outcome, Precision, score
from aireviewer.eval.predictions import Predictions, eval_key

pytestmark = pytest.mark.p0


def run(cases: list[Any], by_case: dict[str, list[Any]], records: list[Any] | None = None) -> Any:
    predictions = Predictions(producer={}, by_case={k: tuple(v) for k, v in by_case.items()})
    return score(cases, predictions, AdjudicationIndex(records or []), split="dev")


def verdict(case: Any, finding: Any, value: Verdict) -> Adjudication:
    when = datetime(2026, 10, 1, tzinfo=UTC)
    return Adjudication.for_finding(case, finding, verdict=value, note="", adjudicated_at=when)


def as_tuple(p: Precision) -> tuple[int, int, int, int, int]:
    return (p.n, p.correct, p.pending, p.invalid, p.duplicate)


def test_known_values_fixture(known_values: Any) -> None:
    card = score(known_values.cases, known_values.predictions, known_values.index, split="dev")
    inline = card.inline_precision
    assert as_tuple(inline["all"]) == (7, 3, 1, 2, 1)
    assert (inline["all"].lower, inline["all"].upper) == (Fraction(3, 7), Fraction(4, 7))
    assert inline["all"].value is None
    assert {k: (p.lower, p.upper) for k, p in inline.items() if k != "all"} == {
        "correctness": (Fraction(2, 3), Fraction(2, 3)),
        "reliability": (0, 0),
        "lint": (0, 1),
        "performance": (0, 0),
        "maintainability": (1, 1),
    }
    summary = card.summary_precision
    assert as_tuple(summary["all"]) == (3, 2, 0, 1, 0)
    assert summary["all"].value == Fraction(2, 3)
    assert {k: p.value for k, p in summary.items() if k != "all"} == {
        "security": 1,
        "design": Fraction(1, 2),
    }
    recall = card.high_severity_recall
    assert (recall.labels, recall.matched, recall.matched_inline) == (3, 2, 1)
    assert (recall.value, recall.inline_value) == (Fraction(2, 3), Fraction(1, 3))
    fp = card.false_positives_per_pr
    assert (fp.cases, fp.invalid, fp.pending) == (3, 2, 1)
    assert (fp.lower, fp.upper, fp.value) == (Fraction(2, 3), 1, None)
    assert (card.inline_per_case.mean, card.inline_per_case.max) == (Fraction(7, 3), 3)
    assert {k: (p.n, p.value) for k, p in card.per_rule_precision.items()} == {
        "C901": (1, 1),
        "layering.api-db": (2, Fraction(1, 2)),
    }
    assert card.missed_must_find == (("case-defect", "L3"),)
    assert card.max_inline_exceeded == (("case-defect", 3, 2),)
    assert card.unscored == {"annotation": 1}
    assert [(p.case_id, p.finding.title) for p in card.pending] == [("case-defect", "Finding P4")]
    outcomes = {s.finding.title.removeprefix("Finding "): s.outcome for s in card.scored}
    assert outcomes == {
        "P1": Outcome.MATCHED,
        "P2": Outcome.INVALID,
        "P3": Outcome.MATCHED,
        "P4": Outcome.PENDING,
        "P5": Outcome.VALID,
        "P6": Outcome.INVALID,
        "P11": Outcome.DUPLICATE,
        "P8": Outcome.MATCHED,
        "P9": Outcome.INVALID,
        "P10": Outcome.VALID,
    }


def test_precision_range_with_pending(make_case: Any, make_finding: Any) -> None:
    case = make_case(kind="clean", labels=[])
    findings = [make_finding(title=f"f{i}", excerpt=f"e{i}") for i in range(4)]
    records = [
        verdict(case, findings[0], Verdict.VALID),
        verdict(case, findings[1], Verdict.INVALID),
    ]
    card = run([case], {"case-one": findings}, records)
    p = card.inline_precision["all"]
    assert as_tuple(p) == (4, 1, 2, 1, 0)
    assert (p.lower, p.upper, p.value, p.complete) == (Fraction(1, 4), Fraction(3, 4), None, False)


def test_precision_single_value_when_complete(make_case: Any, make_finding: Any) -> None:
    case = make_case(kind="clean", labels=[])
    findings = [make_finding(title=f"f{i}", excerpt=f"e{i}") for i in range(3)]
    records = [
        verdict(case, findings[0], Verdict.VALID),
        verdict(case, findings[1], Verdict.INVALID),
        verdict(case, findings[2], Verdict.VALID),
    ]
    p = run([case], {"case-one": findings}, records).inline_precision["all"]
    assert p.complete
    assert p.lower == p.upper == p.value == Fraction(2, 3)
    assert p.n == 3


def test_precision_undefined_without_findings(make_case: Any) -> None:
    card = run([make_case(kind="clean", labels=[])], {"case-one": []})
    p = card.inline_precision["all"]
    assert (p.n, p.lower, p.upper, p.value) == (0, None, None, None)
    assert card.false_positives_per_pr.value == 0
    assert card.high_severity_recall.value is None  # no high-severity labels


def test_recall_high_severity_only(make_case: Any, make_label: Any, make_finding: Any) -> None:
    case = make_case(
        labels=[
            make_label("L1", lines=(10, 10), severity="critical"),
            make_label("L2", lines=(20, 20), severity="high"),
            make_label("L3", lines=(30, 30), severity="medium"),
            make_label("L4", lines=(40, 40), severity="low"),
        ]
    )
    findings = [
        make_finding(start=20, severity="high", channel="summary", title="f2"),
        make_finding(start=30, severity="medium", title="f3"),
        make_finding(start=40, severity="low", title="f4"),
    ]
    recall = run([case], {"case-one": findings}).high_severity_recall
    # Only L1 and L2 count; L3 and L4 being found does not raise recall.
    assert (recall.labels, recall.matched, recall.matched_inline) == (2, 1, 0)
    assert (recall.value, recall.inline_value) == (Fraction(1, 2), 0)


def test_fp_per_pr(make_case: Any, make_finding: Any) -> None:
    one = make_case(id="case-one", kind="clean", labels=[])
    two = make_case(id="case-two", kind="clean", labels=[])
    f1 = make_finding(title="a", excerpt="a")
    f2 = make_finding(title="b", excerpt="b")
    s1 = make_finding(title="c", excerpt="c", channel="summary")
    records = [
        verdict(one, f1, Verdict.INVALID),
        verdict(one, f2, Verdict.INVALID),
        verdict(one, s1, Verdict.INVALID),  # summary findings are not inline FPs
    ]
    fp = run([one, two], {"case-one": [f1, f2, s1], "case-two": []}, records).false_positives_per_pr
    assert (fp.cases, fp.invalid, fp.pending, fp.value) == (2, 2, 0, 1)


def test_duplicates_lower_precision_but_are_not_fps(make_case: Any, make_finding: Any) -> None:
    case = make_case(kind="clean", labels=[])
    a, b = make_finding(title="a", excerpt="a"), make_finding(title="b", excerpt="b")
    records = [verdict(case, a, Verdict.VALID), verdict(case, b, Verdict.DUPLICATE)]
    card = run([case], {"case-one": [a, b]}, records)
    assert card.inline_precision["all"].value == Fraction(1, 2)
    assert card.false_positives_per_pr.value == 0


def test_per_rule_precision(make_case: Any, make_finding: Any) -> None:
    case = make_case(kind="clean", labels=[])
    # The two layer.a findings have the same rule, path and excerpt on different lines:
    # they are two findings, not one.
    findings = [
        make_finding(category="design", rule_id="layer.a", channel="summary", start=10),
        make_finding(category="design", rule_id="layer.a", channel="inline", start=20),
        make_finding(category="maintainability", rule_id="C901", channel="summary", title="3"),
        make_finding(category="lint", rule_id="F401", channel="summary", title="4"),
        make_finding(category="correctness", channel="inline", title="5"),
    ]
    records = [
        verdict(case, findings[0], Verdict.VALID),
        verdict(case, findings[1], Verdict.INVALID),
    ]
    per_rule = run([case], {"case-one": findings}, records).per_rule_precision
    assert set(per_rule) == {"layer.a", "C901"}  # only design and maintainability rules
    assert as_tuple(per_rule["layer.a"]) == (2, 1, 0, 1, 0)
    assert as_tuple(per_rule["C901"]) == (1, 0, 1, 0, 0)


def test_identical_excerpts_on_different_lines_are_distinct(
    make_case: Any, make_finding: Any
) -> None:
    # The same line of code in two functions: same rule, path and excerpt, other lines.
    case = make_case(kind="clean", labels=[])
    first = make_finding(category="lint", rule_id="F841", start=12, excerpt="result = None")
    second = make_finding(category="lint", rule_id="F841", start=48, excerpt="result = None")
    assert eval_key(case, first) != eval_key(case, second)

    records = [verdict(case, first, Verdict.VALID), verdict(case, second, Verdict.INVALID)]
    card = run([case], {"case-one": [first, second]}, records)
    assert [s.outcome for s in card.scored] == [Outcome.VALID, Outcome.INVALID]
    assert as_tuple(card.inline_precision["all"]) == (2, 1, 0, 1, 0)
    assert card.false_positives_per_pr.value == 1


def test_inline_per_run(make_case: Any, make_finding: Any) -> None:
    cases = [make_case(id=f"case-{n}", kind="clean", labels=[]) for n in ("a", "b", "c")]
    by_case = {
        "case-a": [make_finding(title=str(i)) for i in range(4)],
        "case-b": [make_finding(channel="summary")],
        "case-c": [make_finding()],
    }
    stats = run(cases, by_case).inline_per_case
    assert (stats.mean, stats.max) == (Fraction(5, 3), 4)
    empty = run([cases[0]], {"case-a": []}).inline_per_case
    assert (empty.mean, empty.max) == (0, 0)


def test_missed_must_find_listed(make_case: Any, make_label: Any, make_finding: Any) -> None:
    case = make_case(
        labels=[
            make_label("L1", lines=(10, 10), must_find=True),
            make_label("L2", lines=(20, 20), must_find=True),
            make_label("L3", lines=(30, 30)),
        ]
    )
    card = run([case], {"case-one": [make_finding(start=20, channel="summary")]})
    assert card.missed_must_find == (("case-one", "L1"),)


def test_max_inline_expectation(make_case: Any, make_finding: Any) -> None:
    capped = make_case(id="capped", kind="clean", labels=[], expect={"max_inline": 1})
    free = make_case(id="free", kind="clean", labels=[])
    two = [make_finding(title="a"), make_finding(title="b")]
    card = run([capped, free], {"capped": two, "free": two})
    assert card.max_inline_exceeded == (("capped", 2, 1),)


def test_matched_beats_stale_verdict(make_case: Any, make_label: Any, make_finding: Any) -> None:
    case = make_case(labels=[make_label(lines=(10, 10))])
    found = make_finding(start=10)
    card = run([case], {"case-one": [found]}, [verdict(case, found, Verdict.INVALID)])
    assert card.inline_precision["all"].value == 1
