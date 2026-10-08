"""Predictions files and the evaluation key (T0.5, D20)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from aireviewer.eval.errors import EvalInputError
from aireviewer.eval.predictions import (
    EVAL_KEY_VERSION,
    SCORED_CHANNELS,
    eval_key,
    load_predictions,
    parse_predictions,
)
from aireviewer.pipeline.fingerprint import digest, fingerprint_fields

pytestmark = pytest.mark.p0


def document(cases: dict[str, list[Any]], **extra: Any) -> str:
    return json.dumps(
        {
            "version": 1,
            "producer": {"engine": "test"},
            "cases": {
                case_id: [f.model_dump(mode="json") if hasattr(f, "model_dump") else f for f in fs]
                for case_id, fs in cases.items()
            },
            **extra,
        }
    )


def test_predictions_validated(make_case: Any, make_finding: Any) -> None:
    case = make_case()
    text = document({"case-one": [make_finding(), make_finding(start=20)]})
    predictions = parse_predictions(text, [case])
    assert predictions.producer == {"engine": "test"}
    assert [f.location.start_line for f in predictions.by_case["case-one"]] == [10, 20]

    broken = make_finding().model_dump(mode="json")
    broken["severity"] = "huge"
    broken["location"]["start_line"] = 0
    with pytest.raises(EvalInputError) as excinfo:
        parse_predictions(document({"case-one": [make_finding(), broken]}), [case])
    messages = excinfo.value.messages
    assert any("cases.case-one[1].severity:" in m for m in messages), messages
    assert any("cases.case-one[1].location.start_line:" in m for m in messages), messages

    for bad in ["not json", "[]", json.dumps({"version": 2, "cases": {}})]:
        with pytest.raises(EvalInputError):
            parse_predictions(bad, [case])
    with pytest.raises(EvalInputError, match="unknown key"):
        parse_predictions(document({"case-one": []}, extra_field=1), [case])


def test_unknown_and_missing_cases_rejected(make_case: Any, make_finding: Any) -> None:
    one, two = make_case(), make_case(id="case-two")
    with pytest.raises(EvalInputError) as excinfo:
        parse_predictions(document({"case-one": [], "case-zzz": []}), [one, two])
    text = " ".join(excinfo.value.messages)
    assert "case-zzz" in text
    assert "unknown case" in text
    assert "case-two" in text
    assert "missing" in text
    # An empty list means the case ran and found nothing.
    assert parse_predictions(document({"case-one": [], "case-two": []}), [one, two])


def test_unscored_channels_excluded(make_case: Any, make_finding: Any) -> None:
    assert {c.value for c in SCORED_CHANNELS} == {"inline", "summary"}
    findings = [make_finding(channel=c) for c in ("inline", "summary", "annotation", "none")]
    predictions = parse_predictions(document({"case-one": findings}), [make_case()])
    assert [f.channel.value for f in predictions.scored("case-one")] == ["inline", "summary"]
    assert predictions.unscored_counts() == {"annotation": 1, "none": 1}


def test_eval_key_ignores_producer_fingerprint(make_case: Any, make_finding: Any) -> None:
    assert EVAL_KEY_VERSION == 1
    case = make_case()
    plain = make_finding()
    from_engine = make_finding(fingerprint="f" * 24)
    other_engine = make_finding(fingerprint="0" * 24)
    assert eval_key(case, plain) == eval_key(case, from_engine) == eval_key(case, other_engine)
    # It is the section 5.5 fields with an empty enclosing symbol, plus the start line.
    fields = fingerprint_fields(
        category="correctness",
        rule_id=None,
        title="A bug",
        canonical_path="src/a.py",
        enclosing_symbol="",
        excerpt="x = 1",
    )
    assert eval_key(case, plain) == digest([*fields, 10])
    # The start line and the content matter; the end line does not.
    assert eval_key(case, make_finding(start=99)) != eval_key(case, plain)
    assert eval_key(case, make_finding(start=10, end=14)) == eval_key(case, plain)
    assert eval_key(case, make_finding(excerpt="y = 2")) != eval_key(case, plain)


def test_eval_key_is_rename_aware(make_case: Any, make_finding: Any) -> None:
    case = make_case(renames=[{"from": "src/old.py", "to": "src/new.py"}])
    old = make_finding(path="src/old.py")
    new = make_finding(path="src/new.py")
    assert eval_key(case, old) == eval_key(case, new)


def test_load_predictions_from_file(tmp_path: Path, make_case: Any, make_finding: Any) -> None:
    path = tmp_path / "predictions.json"
    path.write_text(document({"case-one": [make_finding()]}), encoding="utf-8")
    assert len(load_predictions(path, [make_case()]).by_case["case-one"]) == 1
    with pytest.raises(EvalInputError, match="not found"):
        load_predictions(tmp_path / "missing.json", [make_case()])
