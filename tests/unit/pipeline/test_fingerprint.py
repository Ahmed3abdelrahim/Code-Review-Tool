"""Finding fingerprint (plan section 5.5, D20)."""

from __future__ import annotations

from typing import Any

import pytest

from aireviewer.contracts.findings import Finding
from aireviewer.pipeline.fingerprint import (
    FINGERPRINT_LENGTH,
    finding_fingerprint,
    fingerprint,
    normalize_excerpt,
    normalize_title,
)

pytestmark = pytest.mark.p0

BASE: dict[str, Any] = {
    "category": "correctness",
    "rule_id": None,
    "title": "Division by zero on empty list",
    "canonical_path": "src/orders.py",
    "enclosing_symbol": "Orders.average",
    "excerpt": "average = total / len(orders)",
}


def make_finding(**overrides: Any) -> Finding:
    data: dict[str, Any] = {
        "source": "llm",
        "category": "correctness",
        "severity": "high",
        "title": "Division by zero on empty list",
        "location": {"path": "src/orders.py", "start_line": 42, "end_line": 42},
        "evidence": [
            {"path": "src/orders.py", "line": 42, "excerpt": "average = total / len(orders)"},
            {"path": "src/orders.py", "line": 40, "excerpt": "orders = load()"},
        ],
        "explanation": "len(orders) can be 0.",
    }
    data.update(overrides)
    return Finding.model_validate(data)


def test_fingerprint_is_24_hex() -> None:
    value = fingerprint(**BASE)
    assert FINGERPRINT_LENGTH == 24
    assert len(value) == 24
    assert int(value, 16) >= 0
    assert fingerprint(**BASE) == value  # pure


def test_line_numbers_excluded() -> None:
    moved = make_finding(location={"path": "src/orders.py", "start_line": 90, "end_line": 93})
    evidence_moved = make_finding(
        evidence=[{"path": "src/orders.py", "line": 90, "excerpt": "average = total / len(orders)"}]
    )
    assert finding_fingerprint(make_finding()) == finding_fingerprint(moved)
    assert finding_fingerprint(make_finding()) == finding_fingerprint(evidence_moved)


def test_title_normalization() -> None:
    assert (
        normalize_title("Division-by-zero in 2 places: avg()!") == "division by zero in places avg"
    )
    assert normalize_title("  UNUSED   import\tOS ") == "unused import os"
    assert normalize_title("one two three four five six seven eight nine ten") == (
        "one two three four five six seven eight"
    )
    assert normalize_title("Größe über 10 % überschritten") == "größe über überschritten"
    assert normalize_title("123 !!!") == ""


def test_rule_id_used_instead_of_title() -> None:
    with_rule = {**BASE, "rule_id": "F401"}
    assert fingerprint(**with_rule) == fingerprint(**{**with_rule, "title": "Another title"})
    assert fingerprint(**BASE) != fingerprint(**{**BASE, "title": "Another title"})
    # Titles that normalize the same give the same fingerprint.
    assert fingerprint(**BASE) == fingerprint(
        **{**BASE, "title": "division by ZERO on empty list!"}
    )


def test_excerpt_whitespace_collapsed() -> None:
    assert normalize_excerpt("  a =\t total \n /  n ") == "a = total / n"
    assert fingerprint(**BASE) == fingerprint(
        **{**BASE, "excerpt": "average  =  total /\tlen(orders) "}
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("category", "reliability"),
        ("rule_id", "R1"),
        ("canonical_path", "src/other.py"),
        ("enclosing_symbol", ""),
        ("excerpt", "average = total / count"),
    ],
)
def test_every_component_changes_fingerprint(field: str, value: Any) -> None:
    assert fingerprint(**BASE) != fingerprint(**{**BASE, field: value})


def test_fields_cannot_collide() -> None:
    # Joining the fields with "|" would make these two identical.
    one = fingerprint(**{**BASE, "canonical_path": "a|b", "enclosing_symbol": "c"})
    two = fingerprint(**{**BASE, "canonical_path": "a", "enclosing_symbol": "b|c"})
    assert one != two


def test_finding_fingerprint_uses_first_evidence_and_canonical_path() -> None:
    finding = make_finding(rule_id=None)
    expected = fingerprint(
        category="correctness",
        rule_id=None,
        title=finding.title,
        canonical_path="src/orders.py",
        enclosing_symbol="",
        excerpt="average = total / len(orders)",
    )
    assert finding_fingerprint(finding) == expected
    renamed = fingerprint(**{**BASE, "canonical_path": "src/new.py", "enclosing_symbol": ""})
    assert finding_fingerprint(finding, canonical_path="src/new.py") == renamed
    assert finding_fingerprint(finding, enclosing_symbol="Orders.average") == fingerprint(**BASE)
