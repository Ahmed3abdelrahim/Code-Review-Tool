"""Converting CodeRabbit review comments into a predictions file (D21)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from aireviewer.contracts.findings import Category, Channel, Severity, Side
from aireviewer.eval.coderabbit import (
    BOT_LOGIN,
    ConversionError,
    build_predictions,
    convert_comments,
    load_comment_file,
    load_overrides,
)
from aireviewer.eval.errors import EvalInputError
from aireviewer.eval.predictions import parse_predictions

pytestmark = pytest.mark.p0

HEAD = "e" * 40  # the fixture case's bundle_head_sha

BODY = """_⚠️ Potential issue_ | _🟠 Major_

**Division by zero when the order list is empty**

`len(orders)` can be 0 here.

<details>
<summary>🤖 Prompt for AI Agents</summary>
ignored
</details>
"""


def comment(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": 1001,
        "user": {"login": BOT_LOGIN, "type": "Bot"},
        "path": "src/a.py",
        "line": 12,
        "start_line": None,
        "side": "RIGHT",
        "start_side": None,
        "original_line": 12,
        "commit_id": HEAD,
        "original_commit_id": HEAD,
        "subject_type": "line",
        "diff_hunk": "@@ -10,2 +10,3 @@\n a = 1\n+b = 2\n+average = total / len(orders)",
        "body": BODY,
    }
    data.update(overrides)
    return data


def test_only_top_level_bot_comments(make_case: Any) -> None:
    comments = [
        comment(id=1),
        comment(id=2, user={"login": "alice", "type": "User"}),
        comment(id=3, in_reply_to_id=1),
        comment(id=4, user={"login": "other-bot[bot]", "type": "Bot"}),
    ]
    result = convert_comments(make_case(), comments, {})
    assert len(result.findings) == 1
    assert result.skipped == {"not_coderabbit": 2, "reply": 1}


def test_line_side_and_range(make_case: Any) -> None:
    result = convert_comments(
        make_case(),
        [comment(start_line=10, line=12), comment(id=2, line=7, side="LEFT")],
        {},
    )
    two, one = result.findings  # sorted by location: line 7 before line 10
    assert (one.location.start_line, one.location.end_line, one.location.side) == (
        10,
        12,
        Side.RIGHT,
    )
    assert (two.location.start_line, two.location.end_line, two.location.side) == (7, 7, Side.LEFT)
    assert one.channel is Channel.INLINE
    assert one.location.path == one.evidence[0].path == "src/a.py"
    assert one.evidence[0].line == 12


def test_file_level_comments_skipped(make_case: Any) -> None:
    comments = [comment(id=1, subject_type="file", line=None, original_line=None)]
    result = convert_comments(make_case(), comments, {})
    assert result.findings == ()
    assert result.skipped == {"file_level": 1}


@pytest.mark.parametrize(
    ("markers", "category", "severity", "rule_id"),
    [
        ("_⚠️ Potential issue_ | _🟠 Major_", Category.CORRECTNESS, Severity.HIGH, None),
        ("_⚠️ Potential issue_ | _🔴 Critical_", Category.CORRECTNESS, Severity.CRITICAL, None),
        ("_⚠️ Potential issue_", Category.CORRECTNESS, Severity.MEDIUM, None),
        (
            "_🛠️ Refactor suggestion_ | _🟡 Minor_",
            Category.MAINTAINABILITY,
            Severity.MEDIUM,
            "coderabbit.refactor",
        ),
        ("_🧹 Nitpick_ | _🔵 Trivial_", Category.LINT, Severity.LOW, "coderabbit.nitpick"),
        ("_🧹 Nitpick (assertive)_", Category.LINT, Severity.LOW, "coderabbit.nitpick"),
        ("_💡 Verification agent_", Category.CORRECTNESS, Severity.MEDIUM, None),
        ("Something new", Category.CORRECTNESS, Severity.MEDIUM, None),
    ],
)
def test_title_category_severity_mapping(
    markers: str, category: Category, severity: Severity, rule_id: str | None, make_case: Any
) -> None:
    body = f"{markers}\n\n**Division by zero when the order list is empty**\n\nDetails."
    (finding,) = convert_comments(make_case(), [comment(body=body)], {}).findings
    assert (finding.category, finding.severity, finding.rule_id) == (category, severity, rule_id)
    assert finding.title == "Division by zero when the order list is empty"
    assert "Details." in finding.explanation


def test_title_fallbacks(make_case: Any) -> None:
    plain = convert_comments(make_case(), [comment(body="Consider caching `x` here.\nMore.")], {})
    assert plain.findings[0].title == "Consider caching x here."
    long = convert_comments(make_case(), [comment(body="**" + "word " * 60 + "**")], {})
    assert len(long.findings[0].title) <= 120
    empty = convert_comments(make_case(), [comment(id=77, body="")], {})
    assert empty.findings[0].title == "CodeRabbit comment 77"
    assert empty.findings[0].explanation


def test_overrides_applied(make_case: Any, tmp_path: Path) -> None:
    path = tmp_path / "overrides.yaml"
    path.write_text(
        "- id: 1001\n  category: security\n  severity: critical\n- id: 1002\n  category: design\n",
        encoding="utf-8",
    )
    overrides = load_overrides(path)
    result = convert_comments(make_case(), [comment(), comment(id=1002)], overrides)
    first, second = result.findings
    assert (first.category, first.severity, first.rule_id) == (
        Category.SECURITY,
        Severity.CRITICAL,
        None,
    )
    assert (second.category, second.severity, second.rule_id) == (
        Category.DESIGN,
        Severity.HIGH,  # from the "Major" marker
        "coderabbit.design",
    )
    path.write_text("- id: 1001\n  category: style\n- id: x\n", encoding="utf-8")
    with pytest.raises(EvalInputError) as excinfo:
        load_overrides(path)
    assert any("[0].category" in m for m in excinfo.value.messages), excinfo.value.messages
    assert any("[1].id" in m for m in excinfo.value.messages), excinfo.value.messages
    path.write_text("- id: 5\n- id: 5\n", encoding="utf-8")
    with pytest.raises(EvalInputError, match="duplicate"):
        load_overrides(path)


def test_evidence_from_diff_hunk(make_case: Any) -> None:
    (finding,) = convert_comments(make_case(), [comment()], {}).findings
    assert finding.evidence[0].excerpt == "average = total / len(orders)"
    hunk = "@@ -5,2 +5,1 @@\n-removed = old()\n kept = 1"
    (left,) = convert_comments(
        make_case(), [comment(diff_hunk=hunk, side="LEFT", line=5)], {}
    ).findings
    assert left.evidence[0].excerpt == "kept = 1"
    (no_hunk,) = convert_comments(make_case(), [comment(diff_hunk="")], {}).findings
    assert no_hunk.evidence[0].excerpt == ""


def test_comment_on_other_commit_rejected(make_case: Any) -> None:
    other = "f" * 40
    with pytest.raises(ConversionError, match="1001") as excinfo:
        convert_comments(make_case(), [comment(commit_id=other, original_commit_id=other)], {})
    assert "bundle_head_sha" in str(excinfo.value)


def test_paginated_concatenated_arrays(tmp_path: Path) -> None:
    path = tmp_path / "case-one.json"
    path.write_text(
        json.dumps([comment(id=1)]) + "\n" + json.dumps([comment(id=2), comment(id=3)]),
        encoding="utf-8",
    )
    assert [c["id"] for c in load_comment_file(path)] == [1, 2, 3]
    path.write_text("[]", encoding="utf-8")
    assert load_comment_file(path) == []
    for bad in ("{not json", '{"id": 1}', "[1, 2]"):
        path.write_text(bad, encoding="utf-8")
        with pytest.raises(EvalInputError, match=re.escape("case-one.json")):
            load_comment_file(path)


def test_hostile_body_sanitized(make_case: Any) -> None:
    body = "**Bug\x1b[31m here‮**\n\n" + "evil\x07 " * 1000
    (finding,) = convert_comments(make_case(), [comment(body=body)], {}).findings
    for text in (finding.title, finding.explanation):
        assert "\x1b" not in text
        assert "‮" not in text
        assert "\x07" not in text
    assert len(finding.explanation) <= 2000


def test_deterministic_output(make_case: Any, tmp_path: Path) -> None:
    case = make_case()
    comments = [
        comment(id=i, path=p, line=n)
        for i, (p, n) in enumerate([("src/b.py", 3), ("src/a.py", 9), ("src/a.py", 2)], start=1)
    ]
    shuffled = [comments[2], comments[0], comments[1]]
    first = convert_comments(case, comments, {}).findings
    second = convert_comments(case, shuffled, {}).findings
    assert first == second
    assert [(f.location.path, f.location.start_line) for f in first] == [
        ("src/a.py", 2),
        ("src/a.py", 9),
        ("src/b.py", 3),
    ]


def test_build_predictions_requires_every_case(make_case: Any, tmp_path: Path) -> None:
    one, two = make_case(), make_case(id="case-two")
    comments_dir = tmp_path / "coderabbit"
    comments_dir.mkdir()
    (comments_dir / "case-one.json").write_text(json.dumps([comment()]), encoding="utf-8")
    with pytest.raises(EvalInputError, match=re.escape("case-two.json")):
        build_predictions([one, two], comments_dir, {})

    (comments_dir / "case-two.json").write_text("[]", encoding="utf-8")
    (comments_dir / "case-zzz.json").write_text("[]", encoding="utf-8")
    with pytest.raises(EvalInputError, match="case-zzz"):
        build_predictions([one, two], comments_dir, {})

    (comments_dir / "case-zzz.json").unlink()
    document, stats = build_predictions([one, two], comments_dir, {})
    assert document["producer"]["engine"] == "coderabbit"
    assert "converted_at" not in document["producer"]  # deterministic: no timestamps
    assert stats == {"case-one": {"findings": 1}, "case-two": {"findings": 0}}
    predictions = parse_predictions(json.dumps(document), [one, two])
    assert len(predictions.by_case["case-one"]) == 1
    assert predictions.by_case["case-two"] == ()
