"""Matching predictions to labels (plan section 8.3, D20)."""

from __future__ import annotations

from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from aireviewer.contracts.findings import Category
from aireviewer.eval.matcher import (
    COMPATIBLE_CATEGORIES,
    LINE_TOLERANCE,
    MatchingMode,
    categories_compatible,
    line_gap,
    match_case,
)

pytestmark = pytest.mark.p0


def pairs(case: Any, findings: list[Any]) -> dict[str, str]:
    """Matched pairs as {prediction title: label id}."""
    matched = match_case(case, findings)
    return {findings[i].title: label_id for i, label_id in matched.items()}


def test_line_tolerance(make_case: Any, make_label: Any, make_finding: Any) -> None:
    assert LINE_TOLERANCE == 3
    assert line_gap(10, 12, 10, 12) == 0
    assert line_gap(5, 20, 10, 12) == 0  # containment
    assert line_gap(13, 13, 10, 12) == 1
    assert line_gap(1, 6, 10, 12) == 4
    case = make_case(labels=[make_label(lines=(40, 44))])
    for start, end, matches in [
        (36, 36, False),  # 4 before the label
        (37, 37, True),  # 3 before
        (40, 44, True),
        (30, 50, True),
        (47, 47, True),  # 3 after
        (48, 52, False),  # 4 after
    ]:
        finding = make_finding(start=start, end=end, title="p")
        assert (pairs(case, [finding]) == {"p": "L1"}) is matches, (start, end)


def test_category_compatibility(make_case: Any, make_label: Any, make_finding: Any) -> None:
    group = {Category.CORRECTNESS, Category.RELIABILITY, Category.PERFORMANCE}
    assert group == COMPATIBLE_CATEGORIES
    for a in Category:
        for b in Category:
            expected = a == b or (a in group and b in group)
            assert categories_compatible(a, b) is expected, (a, b)

    case = make_case(labels=[make_label(category="correctness")])
    assert pairs(case, [make_finding(category="performance", title="p")]) == {"p": "L1"}
    assert pairs(case, [make_finding(category="security", title="p")]) == {}
    design = make_case(kind="design", labels=[make_label(category="design")])
    assert pairs(design, [make_finding(category="maintainability", title="p", rule_id="R")]) == {}
    assert pairs(design, [make_finding(category="design", title="p", rule_id="R")]) == {"p": "L1"}


def test_one_to_one_assignment(make_case: Any, make_label: Any, make_finding: Any) -> None:
    case = make_case(labels=[make_label("L1", lines=(10, 10))])
    findings = [make_finding(start=10, title="first"), make_finding(start=11, title="second")]
    assert pairs(case, findings) == {"first": "L1"}  # one label, one prediction

    two = make_case(labels=[make_label("L1", lines=(10, 10)), make_label("L2", lines=(12, 12))])
    findings = [make_finding(start=11, title="a"), make_finding(start=11, title="b")]
    result = pairs(two, findings)
    assert sorted(result.values()) == ["L1", "L2"]  # each label used once


def test_maximum_cardinality_beats_greedy(
    make_case: Any, make_label: Any, make_finding: Any
) -> None:
    # Greedy by distance would pair P1-L1 (gap 1) and leave P2 and L2 unmatched.
    case = make_case(labels=[make_label("L1", lines=(10, 10)), make_label("L2", lines=(14, 14))])
    p1 = make_finding(start=11, title="P1")  # gap 1 to L1, gap 3 to L2
    p2 = make_finding(start=7, title="P2")  # gap 3 to L1, out of reach of L2
    assert pairs(case, [p1, p2]) == {"P1": "L2", "P2": "L1"}
    assert pairs(case, [p2, p1]) == {"P1": "L2", "P2": "L1"}


def test_priority_severity_then_distance(
    make_case: Any, make_label: Any, make_finding: Any
) -> None:
    case = make_case(labels=[make_label(lines=(10, 10), severity="high")])
    agreeing = make_finding(start=12, severity="high", title="agreeing")
    closer = make_finding(start=10, severity="low", title="closer")
    assert pairs(case, [closer, agreeing]) == {"agreeing": "L1"}

    near = make_finding(start=10, severity="high", title="near")
    far = make_finding(start=13, severity="high", title="far")
    assert pairs(case, [far, near]) == {"near": "L1"}

    # Among equal costs, the result is still fixed (canonical order, not input order).
    twin_a = make_finding(start=11, severity="high", title="twin-a")
    twin_b = make_finding(start=9, severity="high", title="twin-b")
    assert pairs(case, [twin_a, twin_b]) == pairs(case, [twin_b, twin_a])


def test_rename_aware_path(make_case: Any, make_label: Any, make_finding: Any) -> None:
    renames = [{"from": "src/old.py", "to": "src/new.py"}]
    on_new = make_case(renames=renames, labels=[make_label(path="src/new.py")])
    on_old = make_case(renames=renames, labels=[make_label(path="src/old.py")])
    for case in (on_new, on_old):
        for path in ("src/old.py", "src/new.py"):
            assert pairs(case, [make_finding(path=path, title="p")]) == {"p": "L1"}, path
    plain = make_case(labels=[make_label(path="src/new.py")])
    assert pairs(plain, [make_finding(path="src/old.py", title="p")]) == {}
    assert pairs(plain, [make_finding(path="src/other.py", title="p")]) == {}


def test_side_must_match(make_case: Any, make_label: Any, make_finding: Any) -> None:
    case = make_case(labels=[make_label(side="LEFT")])
    assert pairs(case, [make_finding(side="RIGHT", title="right")]) == {}
    assert pairs(case, [make_finding(side="LEFT", title="left")]) == {"left": "L1"}


def test_inline_matched_before_summary(make_case: Any, make_label: Any, make_finding: Any) -> None:
    case = make_case(labels=[make_label(lines=(10, 10), severity="high")])
    summary = make_finding(start=10, severity="high", channel="summary", title="summary")
    inline = make_finding(start=13, severity="low", channel="inline", title="inline")
    assert pairs(case, [summary, inline]) == {"inline": "L1"}

    # A summary finding takes a label that no inline finding matched.
    assert pairs(case, [summary]) == {"summary": "L1"}
    # Annotations and unpublished findings are never matched.
    for channel in ("annotation", "none"):
        assert pairs(case, [make_finding(start=10, channel=channel, title="x")]) == {}


_lines = st.integers(min_value=1, max_value=30)


@settings(max_examples=150, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    labels=st.lists(
        st.tuples(_lines, st.integers(0, 3), st.sampled_from(["correctness", "security"])),
        min_size=1,
        max_size=6,
    ),
    findings=st.lists(
        st.tuples(
            _lines,
            st.integers(0, 3),
            st.sampled_from(["correctness", "performance", "security"]),
            st.sampled_from(["low", "high"]),
            st.sampled_from(["inline", "summary"]),
        ),
        max_size=8,
    ),
    data=st.data(),
)
def test_deterministic_under_input_order(
    labels: list[tuple[int, int, str]],
    findings: list[tuple[int, int, str, str, str]],
    data: st.DataObject,
    make_case: Any,
    make_label: Any,
    make_finding: Any,
) -> None:
    label_dicts = [
        make_label(f"L{i}", lines=(start, start + length), category=category)
        for i, (start, length, category) in enumerate(labels)
    ]
    predictions = [
        make_finding(
            start=start,
            end=start + length,
            category=category,
            severity=severity,
            channel=channel,
            title=f"p{i}",
        )
        for i, (start, length, category, severity, channel) in enumerate(findings)
    ]
    reference = pairs(make_case(labels=label_dicts), predictions)
    shuffled_labels = data.draw(st.permutations(label_dicts))
    shuffled_predictions = data.draw(st.permutations(predictions))
    assert pairs(make_case(labels=shuffled_labels), shuffled_predictions) == reference
    # One-to-one in both directions.
    assert len(set(reference.values())) == len(reference)


def test_location_mode_ignores_category(make_case: Any, make_label: Any, make_finding: Any) -> None:
    case = make_case(labels=[make_label(category="correctness", lines=(10, 10))])
    security = make_finding(category="security", start=11, title="p")
    assert match_case(case, [security]) == {}  # strict is the default
    assert match_case(case, [security], mode=MatchingMode.STRICT) == {}
    assert match_case(case, [security], mode=MatchingMode.LOCATION) == {0: "L1"}
    # Location still means path, side and lines.
    for other in (
        make_finding(category="security", start=20, title="far"),
        make_finding(category="security", start=11, side="LEFT", title="left"),
        make_finding(category="security", path="src/b.py", start=11, title="path"),
    ):
        assert match_case(case, [other], mode=MatchingMode.LOCATION) == {}
