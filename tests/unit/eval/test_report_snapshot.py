"""Evaluation report (plan section 8.6): Markdown and metrics.json snapshots.

A failing snapshot means the report format changed; update it with
`pytest --snapshot-update` and give the reason in the task report.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from syrupy.assertion import SnapshotAssertion
from syrupy.extensions.json import JSONSnapshotExtension
from syrupy.extensions.single_file import SingleFileSnapshotExtension, WriteMode

from aireviewer.eval.matcher import MatchingMode
from aireviewer.eval.metrics import score
from aireviewer.eval.report import (
    metrics_document,
    render_markdown,
    summary_document,
    write_report,
)

pytestmark = pytest.mark.p0

GENERATED_AT = datetime(2026, 10, 8, 12, 0, 5, tzinfo=UTC)


class MarkdownSnapshotExtension(SingleFileSnapshotExtension):
    file_extension = "md"
    _write_mode = WriteMode.TEXT


class FixedClock:
    def now(self) -> datetime:
        return GENERATED_AT

    def monotonic(self) -> float:
        return 0.0


def scorecard(known_values: Any) -> Any:
    return score(known_values.cases, known_values.predictions, known_values.index, split="dev")


def test_report_markdown_snapshot(known_values: Any, snapshot: SnapshotAssertion) -> None:
    markdown = render_markdown(scorecard(known_values), generated_at=GENERATED_AT)
    # Ranges while adjudications are pending, single values when complete; n is always shown.
    assert "[42.9%, 57.1%]" in markdown
    assert "n=7" in markdown
    assert "66.7% (n=3)" in markdown
    assert "- Matching: strict (categories must be compatible)" in markdown
    assert markdown == snapshot.use_extension(MarkdownSnapshotExtension)


def test_metrics_json_snapshot(known_values: Any, snapshot: SnapshotAssertion) -> None:
    document = metrics_document(scorecard(known_values), generated_at=GENERATED_AT)
    json.dumps(document, allow_nan=False)  # plain JSON
    all_inline = document["inline_precision"]["all"]
    assert all_inline["n"] == 7
    assert (all_inline["lower"], all_inline["upper"], all_inline["value"]) == (
        0.4286,
        0.5714,
        None,
    )
    assert document["producer"] == {"engine": "fixture-1", "model": "none"}
    assert document["split"] == "dev"
    assert document["matching"] == "strict"
    assert document == snapshot.use_extension(JSONSnapshotExtension)


def test_report_directory_name(known_values: Any, tmp_path: Path) -> None:
    card = scorecard(known_values)
    first = write_report(card, out_dir=tmp_path / "reports", clock=FixedClock())
    assert first.name == "20261008T120005Z-dev-score"
    assert (first / "report.md").read_text(encoding="utf-8") == render_markdown(
        card, generated_at=GENERATED_AT
    )
    written = json.loads((first / "metrics.json").read_text(encoding="utf-8"))
    assert written == metrics_document(card, generated_at=GENERATED_AT)
    # A second report in the same second never overwrites the first.
    second = write_report(card, out_dir=tmp_path / "reports", clock=FixedClock())
    assert second.name == "20261008T120005Z-dev-score-2"
    assert first.exists()


def test_report_escapes_untrusted_text(make_case: Any, make_finding: Any) -> None:
    from aireviewer.eval.adjudicate import AdjudicationIndex
    from aireviewer.eval.predictions import Predictions

    case = make_case(kind="clean", labels=[])
    hostile = make_finding(title="a | b\x1b[31m <script>", excerpt="e")
    predictions = Predictions(producer={"engine": "x | y"}, by_case={"case-one": (hostile,)})
    card = score([case], predictions, AdjudicationIndex([]), split="dev")
    markdown = render_markdown(card, generated_at=GENERATED_AT)
    assert "\x1b" not in markdown
    assert "a \\| b" in markdown
    assert "x \\| y" in markdown
    assert "<script>" not in markdown


def test_report_states_location_matching(known_values: Any) -> None:
    card = score(
        known_values.cases,
        known_values.predictions,
        known_values.index,
        split="all",
        matching=MatchingMode.LOCATION,
    )
    assert card.matching is MatchingMode.LOCATION
    markdown = render_markdown(card, generated_at=GENERATED_AT)
    assert "- Matching: location only (categories ignored)" in markdown
    assert metrics_document(card, generated_at=GENERATED_AT)["matching"] == "location"


def test_summary_document(known_values: Any) -> None:
    summary = summary_document(scorecard(known_values), generated_at=GENERATED_AT)
    json.dumps(summary, allow_nan=False)
    assert summary["producer"] == {"engine": "fixture-1", "model": "none"}
    assert summary["matching"] == "strict"
    assert summary["cases"] == {"total": 3, "by_kind": {"clean": 1, "defect": 1, "design": 1}}
    all_inline = summary["inline_precision"]["all"]
    assert (all_inline["n"], all_inline["lower"], all_inline["upper"]) == (7, 0.4286, 0.5714)
    assert summary["high_severity_recall"]["value"] == 0.6667
    assert summary["high_severity_recall"]["inline_value"] == 0.3333
    assert summary["comments_per_pr"] == {"mean": 2.3333, "max": 3}
    assert summary["false_positives_per_pr"]["upper"] == 1.0
    assert summary["pending_adjudications"] == 1
    assert summary["eval_key_version"] == 1
