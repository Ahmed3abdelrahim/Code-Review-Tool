"""Finding and LLMFindingOut (plan section 5.1, tightened by D17)."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from aireviewer.contracts.findings import (
    Category,
    Evidence,
    Finding,
    FindingStatus,
    LLMEvidenceOut,
    LLMFindingOut,
)

pytestmark = pytest.mark.p0

RULE_CATEGORIES = {"lint", "maintainability", "design"}


def finding_data(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "source": "ruff",
        "category": "lint",
        "rule_id": "F401",
        "severity": "low",
        "title": "Unused import",
        "location": {
            "path": "src/a.py",
            "start_line": 3,
            "end_line": 3,
            "anchor_ids": ["F1:H1:+3"],
        },
        "evidence": [{"path": "src/a.py", "line": 3, "excerpt": "import os"}],
        "explanation": "`os` is imported but never used.",
    }
    data.update(overrides)
    return data


def llm_data(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "category": "correctness",
        "severity": "high",
        "title": "Division by zero on empty list",
        "anchor_ids": ["F2:H3:+42"],
        "evidence": [{"anchor_id": "F2:H3:+42", "excerpt": "average = total / len(orders)"}],
        "explanation": "len(orders) can be 0.",
    }
    data.update(overrides)
    return data


def _error_types(excinfo: pytest.ExceptionInfo[ValidationError]) -> set[str]:
    return {error["type"] for error in excinfo.value.errors()}


@pytest.mark.parametrize("category", [c.value for c in Category])
def test_rule_id_required_for_rule_categories(category: str) -> None:
    requires_rule = category in RULE_CATEGORIES
    for model, data in ((Finding, finding_data), (LLMFindingOut, llm_data)):
        for missing in ({"rule_id": None}, {"rule_id": ""}):
            if requires_rule:
                with pytest.raises(ValidationError, match="rule_id"):
                    model.model_validate(data(category=category, **missing))
            elif missing["rule_id"] is None:
                model.model_validate(data(category=category, **missing))
        model.model_validate(data(category=category, rule_id="R1"))

    finding = Finding.model_validate(finding_data(category=category, rule_id="R1"))
    if requires_rule:
        # validate_assignment: the pipeline cannot drop a required rule_id later.
        with pytest.raises(ValidationError, match="rule_id"):
            finding.rule_id = None
    else:
        finding.rule_id = None


PIPELINE_FIELDS = {
    "path": "src/a.py",
    "line": 42,
    "start_line": 42,
    "end_line": 42,
    "side": "RIGHT",
    "sha": "a" * 40,
    "head_sha": "a" * 40,
    "commit_sha": "a" * 40,
    "fingerprint": "abc123",
    "score": 0.9,
    "channel": "inline",
    "status": "published",
    "evidence_strength": "deterministic",
    "source": "llm",
    "location": {"path": "src/a.py", "start_line": 1, "end_line": 1},
    "introduced_by_pr": True,
}


@pytest.mark.parametrize("field", sorted(PIPELINE_FIELDS))
def test_llm_output_forbids_pipeline_fields(field: str) -> None:
    value = PIPELINE_FIELDS[field]
    with pytest.raises(ValidationError) as top:
        LLMFindingOut.model_validate(llm_data(**{field: value}))
    assert _error_types(top) == {"extra_forbidden"}

    evidence = {"anchor_id": "F2:H3:+42", "excerpt": "x", field: value}
    with pytest.raises(ValidationError) as nested:
        LLMFindingOut.model_validate(llm_data(evidence=[evidence]))
    assert _error_types(nested) == {"extra_forbidden"}


def test_llm_schemas_forbid_additional_properties() -> None:
    assert LLMFindingOut.model_json_schema()["additionalProperties"] is False
    assert LLMEvidenceOut.model_json_schema()["additionalProperties"] is False


def test_excerpt_length_limit() -> None:
    ok, too_long = "x" * 500, "x" * 501
    Evidence(path="a.py", line=1, excerpt=ok)
    LLMEvidenceOut(anchor_id="F1:H1:+1", excerpt=ok)
    with pytest.raises(ValidationError):
        Evidence(path="a.py", line=1, excerpt=too_long)
    with pytest.raises(ValidationError):
        LLMEvidenceOut(anchor_id="F1:H1:+1", excerpt=too_long)


@pytest.mark.parametrize(
    "overrides",
    [
        {"anchor_ids": ["C1:5"]},  # location must be a diff anchor
        {"anchor_ids": ["src/orders.py:42"]},
        {"anchor_ids": ["F2:H3:+042"]},
        {"anchor_ids": []},
        {"anchor_ids": [f"F1:H1:+{n}" for n in range(1, 12)]},  # more than 10
        {"evidence": [{"anchor_id": "line 42", "excerpt": "x"}]},
        {"evidence": []},
    ],
)
def test_llm_anchor_ids_validated(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        LLMFindingOut.model_validate(llm_data(**overrides))


def test_llm_evidence_may_cite_context_snippets() -> None:
    evidence = [{"anchor_id": "C1:17", "excerpt": "def helper():"}]
    LLMFindingOut.model_validate(llm_data(evidence=evidence))


def test_location_end_not_before_start() -> None:
    location = {"path": "a.py", "start_line": 5, "end_line": 4}
    with pytest.raises(ValidationError, match="end_line"):
        Finding.model_validate(finding_data(location=location))


def test_location_anchor_ids_validated() -> None:
    location = {"path": "a.py", "start_line": 1, "end_line": 1, "anchor_ids": ["nope"]}
    with pytest.raises(ValidationError):
        Finding.model_validate(finding_data(location=location))
    Finding.model_validate(finding_data(location={**location, "anchor_ids": []}))


def test_finding_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError) as excinfo:
        Finding.model_validate(finding_data(severty="high"))
    assert _error_types(excinfo) == {"extra_forbidden"}


def test_status_is_enumerated() -> None:
    finding = Finding.model_validate(finding_data())
    assert finding.status is FindingStatus.CANDIDATE
    assert {s.value for s in FindingStatus} == {
        "candidate",
        "rejected",
        "validated",
        "published",
        "summarized",
        "suppressed",
        "carried_over",
        "resolved",
    }
    with pytest.raises(ValidationError):
        finding.status = "shipped"  # type: ignore[assignment]


def test_tool_payload_must_be_json() -> None:
    Finding.model_validate(finding_data(tool_payload={"code": "F401", "fix": {"n": [1, 2.5]}}))
    with pytest.raises(ValidationError):
        Finding.model_validate(finding_data(tool_payload={"obj": object()}))


@pytest.mark.parametrize("field", ["title", "explanation"])
def test_text_fields_not_empty(field: str) -> None:
    with pytest.raises(ValidationError):
        Finding.model_validate(finding_data(**{field: ""}))
    with pytest.raises(ValidationError):
        LLMFindingOut.model_validate(llm_data(**{field: ""}))


@pytest.mark.parametrize("field", ["trigger", "impact"])
def test_trigger_and_impact_bounded(field: str) -> None:
    LLMFindingOut.model_validate(llm_data(**{field: "x" * 500}))
    with pytest.raises(ValidationError):
        LLMFindingOut.model_validate(llm_data(**{field: "x" * 501}))
    with pytest.raises(ValidationError):
        Finding.model_validate(finding_data(**{field: "x" * 501}))
