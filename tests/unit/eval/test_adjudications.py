"""Adjudication store and interactive session (plan section 8.4, D20)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from aireviewer.eval.adjudicate import (
    Adjudication,
    AdjudicationIndex,
    AdjudicationStore,
    DirectoryCodeLookup,
    NoCodeLookup,
    Verdict,
    run_session,
    sanitize_for_terminal,
)
from aireviewer.eval.errors import EvalInputError
from aireviewer.eval.metrics import score
from aireviewer.eval.predictions import EVAL_KEY_VERSION, Predictions, eval_key

pytestmark = pytest.mark.p0

T0 = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)


class FixedClock:
    def __init__(self) -> None:
        self._now = T0

    def now(self) -> datetime:
        self._now += timedelta(seconds=1)
        return self._now

    def monotonic(self) -> float:
        return 0.0


class Script:
    """Scripted answers for the session prompts; EOF when they run out."""

    def __init__(self, *answers: str) -> None:
        self._answers: Iterator[str] = iter(answers)
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        try:
            return next(self._answers)
        except StopIteration:
            raise EOFError from None


def pending_of(case: Any, findings: list[Any], index: AdjudicationIndex) -> list[Any]:
    predictions = Predictions(producer={}, by_case={case.id: tuple(findings)})
    return list(score([case], predictions, index, split="dev").pending)


def session(
    case: Any,
    findings: list[Any],
    store: AdjudicationStore,
    *answers: str,
    code: Any = None,
) -> tuple[Any, str, AdjudicationIndex]:
    index = store.load()
    output: list[str] = []
    summary = run_session(
        pending_of(case, findings, index),
        cases={case.id: case},
        store=store,
        index=index,
        ask=Script(*answers),
        write=output.append,
        clock=FixedClock(),
        code=code or NoCodeLookup(),
    )
    return summary, "".join(output), store.load()


def record(case: Any, finding: Any, value: Verdict, *, note: str = "", at: datetime = T0) -> Any:
    return Adjudication.for_finding(case, finding, verdict=value, note=note, adjudicated_at=at)


def test_store_appends_and_reloads(tmp_path: Path, make_case: Any, make_finding: Any) -> None:
    store = AdjudicationStore(tmp_path / "adjudications.jsonl")
    assert store.load().get("case-one", "0" * 24) is None  # a missing file is an empty store
    case = make_case(kind="clean", labels=[])
    a, b = make_finding(title="a"), make_finding(title="b")
    store.append(record(case, a, Verdict.VALID, note="ok"))
    store.append(record(case, b, Verdict.INVALID))

    lines = store.path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["key"] == eval_key(case, a)
    assert first["key_version"] == EVAL_KEY_VERSION
    assert (first["case_id"], first["verdict"], first["note"]) == ("case-one", "valid", "ok")
    assert (first["path"], first["side"], first["start_line"], first["category"]) == (
        "src/a.py",
        "RIGHT",
        10,
        "correctness",
    )
    index = store.load()
    assert index.get("case-one", eval_key(case, a)).verdict is Verdict.VALID  # type: ignore[union-attr]
    assert index.get("case-one", eval_key(case, b)).verdict is Verdict.INVALID  # type: ignore[union-attr]
    assert index.get("case-two", eval_key(case, a)) is None


def test_last_verdict_wins(tmp_path: Path, make_case: Any, make_finding: Any) -> None:
    store = AdjudicationStore(tmp_path / "adjudications.jsonl")
    case, finding = make_case(kind="clean", labels=[]), make_finding()
    store.append(record(case, finding, Verdict.INVALID, at=T0))
    store.append(record(case, finding, Verdict.VALID, at=T0 + timedelta(days=1)))
    assert store.load().get("case-one", eval_key(case, finding)).verdict is Verdict.VALID  # type: ignore[union-attr]
    assert len(store.path.read_text(encoding="utf-8").splitlines()) == 2  # history kept


def test_invalid_lines_reported_with_line_number(
    tmp_path: Path, make_case: Any, make_finding: Any
) -> None:
    path = tmp_path / "adjudications.jsonl"
    good = record(make_case(kind="clean", labels=[]), make_finding(), Verdict.VALID)
    good_line = good.model_dump_json()
    wrong_verdict = json.loads(good_line) | {"verdict": "maybe"}
    old_version = json.loads(good_line) | {"key_version": 2}
    extra = json.loads(good_line) | {"extra": 1}
    path.write_text(
        "\n".join(
            [
                good_line,
                "",
                "{not json",
                json.dumps(wrong_verdict),
                json.dumps(old_version),
                json.dumps(extra),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(EvalInputError) as excinfo:
        AdjudicationStore(path).load()
    messages = excinfo.value.messages
    assert any(m.startswith("adjudications.jsonl:3:") for m in messages), messages
    assert any(m.startswith("adjudications.jsonl:4: verdict:") for m in messages), messages
    assert any(m.startswith("adjudications.jsonl:5: key_version:") for m in messages), messages
    assert any(m.startswith("adjudications.jsonl:6: extra: unknown key") for m in messages)
    assert not any(":1:" in m or ":2:" in m for m in messages), messages


def test_session_records_verdicts(tmp_path: Path, make_case: Any, make_finding: Any) -> None:
    store = AdjudicationStore(tmp_path / "adjudications.jsonl")
    case = make_case(kind="clean", labels=[])
    findings = [make_finding(title="First bug"), make_finding(title="Second bug", start=20)]
    summary, output, index = session(case, findings, store, "v", "looks right", "i", "")
    assert (summary.recorded, summary.skipped, summary.stopped) == (2, 0, False)
    first = index.get("case-one", eval_key(case, findings[0]))
    second = index.get("case-one", eval_key(case, findings[1]))
    assert (first.verdict, first.note) == (Verdict.VALID, "looks right")  # type: ignore[union-attr]
    assert (second.verdict, second.note) == (Verdict.INVALID, "")  # type: ignore[union-attr]
    assert first.adjudicated_at.tzinfo is not None  # type: ignore[union-attr]
    assert "First bug" in output
    assert "Second bug" in output
    assert "src/a.py:10" in output
    assert "x = 1" in output  # evidence excerpt
    # The next session has nothing left to ask.
    summary, _, _ = session(case, findings, store)
    assert summary.recorded == summary.skipped == 0


def test_invalid_choice_asks_again(tmp_path: Path, make_case: Any, make_finding: Any) -> None:
    store = AdjudicationStore(tmp_path / "adjudications.jsonl")
    case = make_case(kind="clean", labels=[])
    summary, _output, index = session(case, [make_finding()], store, "x", "d", "dup of #1")
    assert summary.recorded == 1
    assert index.get("case-one", eval_key(case, make_finding())).verdict is Verdict.DUPLICATE  # type: ignore[union-attr]


def test_skip_and_quit(tmp_path: Path, make_case: Any, make_finding: Any) -> None:
    store = AdjudicationStore(tmp_path / "adjudications.jsonl")
    case = make_case(kind="clean", labels=[])
    findings = [make_finding(title=t, start=n) for n, t in ((10, "a"), (20, "b"), (30, "c"))]
    summary, _, _ = session(case, findings, store, "s", "q")
    assert (summary.recorded, summary.skipped, summary.stopped) == (0, 1, True)
    assert not store.path.exists() or store.path.read_text(encoding="utf-8") == ""
    # End of input stops the session too, keeping what was recorded.
    summary, _, index = session(case, findings, store, "v", "")
    assert (summary.recorded, summary.stopped) == (1, True)
    assert index.get("case-one", eval_key(case, findings[0])) is not None


def test_similar_verdict_suggested_not_reused(
    tmp_path: Path, make_case: Any, make_finding: Any
) -> None:
    store = AdjudicationStore(tmp_path / "adjudications.jsonl")
    case = make_case(kind="clean", labels=[])
    earlier = make_finding(start=10, end=12, title="Old wording", excerpt="old code")
    store.append(record(case, earlier, Verdict.INVALID, note="not reachable"))

    reworded = make_finding(start=12, end=14, title="New wording", excerpt="new code")
    assert eval_key(case, reworded) != eval_key(case, earlier)
    # Never reused silently: without a decision, the finding stays pending.
    assert len(pending_of(case, [reworded], store.load())) == 1

    summary, output, index = session(case, [reworded], store, "a")
    assert "Earlier verdict" in output
    assert "invalid" in output
    assert "not reachable" in output
    assert summary.recorded == 1
    accepted = index.get("case-one", eval_key(case, reworded))
    assert accepted is not None
    assert accepted.verdict is Verdict.INVALID
    assert eval_key(case, earlier)[:8] in accepted.note  # records where the verdict came from


@pytest.mark.parametrize(
    "changes",
    [
        {"start": 13, "end": 14},  # lines do not overlap (no tolerance for suggestions)
        {"side": "LEFT"},
        {"path": "src/other.py"},
        {"category": "security"},
    ],
)
def test_no_suggestion_for_different_findings(
    changes: dict[str, Any], tmp_path: Path, make_case: Any, make_finding: Any
) -> None:
    store = AdjudicationStore(tmp_path / "adjudications.jsonl")
    case = make_case(kind="clean", labels=[])
    store.append(record(case, make_finding(start=10, end=12, excerpt="old"), Verdict.INVALID))
    other = make_finding(**{"start": 10, "end": 12, "excerpt": "new", **changes})
    summary, output, _ = session(case, [other], store, "a", "s")
    assert "Earlier verdict" not in output
    assert summary.recorded == 0  # "a" is not a valid choice without a suggestion


def test_terminal_output_sanitized(tmp_path: Path, make_case: Any, make_finding: Any) -> None:
    assert sanitize_for_terminal("ok\x1b[31mred\x1b[0m‮evil\x07\r") == "ok[31mred[0mevil"
    assert sanitize_for_terminal("two\nlines\tok") == "two\nlines\tok"
    store = AdjudicationStore(tmp_path / "adjudications.jsonl")
    case = make_case(kind="clean", labels=[])
    hostile = make_finding(title="Bug \x1b]0;pwned\x07 here", excerpt="x\x1b[2J = 1")
    _, output, _ = session(case, [hostile], store, "s")
    assert "\x1b" not in output
    assert "\x07" not in output


def test_session_shows_code_and_nearby_labels(
    tmp_path: Path, make_case: Any, make_label: Any, make_finding: Any
) -> None:
    root = tmp_path / "checkouts"
    (root / "case-one" / "src").mkdir(parents=True)
    source = "".join(f"line {n}\n" for n in range(1, 31))
    (root / "case-one" / "src" / "a.py").write_text(source, encoding="utf-8")
    case = make_case(labels=[make_label("L1", lines=(20, 20), category="security")])
    store = AdjudicationStore(tmp_path / "adjudications.jsonl")
    finding = make_finding(start=14, category="correctness")  # near L1 but not matching it
    _, output, _ = session(case, [finding], store, "s", code=DirectoryCodeLookup(root))
    assert "line 14" in output
    assert "line 12" in output  # context around the finding
    assert "L1" in output  # nearby label, to judge duplicates


def test_directory_code_lookup_stays_inside_root(tmp_path: Path, make_case: Any) -> None:
    root = tmp_path / "checkouts"
    (root / "case-one" / "src").mkdir(parents=True)
    (root / "case-one" / "src" / "a.py").write_text("a\nb\nc\n", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("secret\n", encoding="utf-8")
    (root / "case-one" / "link.py").symlink_to(tmp_path / "secret.txt")
    lookup, case = DirectoryCodeLookup(root), make_case()
    assert lookup.lines(case, "src/a.py", "RIGHT", 2, 3) == [(2, "b"), (3, "c")]
    assert lookup.lines(case, "src/a.py", "RIGHT", 0, 99) == [(1, "a"), (2, "b"), (3, "c")]
    assert lookup.lines(case, "src/a.py", "LEFT", 1, 2) is None  # base side not checked out
    assert lookup.lines(case, "../../secret.txt", "RIGHT", 1, 1) is None
    assert lookup.lines(case, "link.py", "RIGHT", 1, 1) is None
    assert lookup.lines(case, "src/missing.py", "RIGHT", 1, 1) is None
    assert NoCodeLookup().lines(case, "src/a.py", "RIGHT", 1, 1) is None
