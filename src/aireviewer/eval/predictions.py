"""Predictions files and the evaluation key (T0.5, D20).

A predictions file holds, per case, the list of `Finding` JSON a reviewer produced:

    {"version": 1, "producer": {"engine": "...", "model": "..."},
     "cases": {"<case_id>": [<Finding>, ...], ...}}

Every scored case must appear (an empty list means "ran, found nothing"); unknown case IDs
are errors. The harness never uses a producer's fingerprint: it keys adjudications by its
own evaluation key, the section 5.5 fields with an empty enclosing symbol plus the start
line. Benchmark commits are frozen, so both the symbol-less fields and the lines are stable;
the line keeps identical findings at different places apart.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from aireviewer.config_files import validation_messages
from aireviewer.contracts.findings import Channel, Finding
from aireviewer.eval.cases import CASE_ID_PATTERN, Case
from aireviewer.eval.errors import EvalInputError
from aireviewer.pipeline.fingerprint import digest, fingerprint_fields

__all__ = [
    "EVAL_KEY_VERSION",
    "MAX_PREDICTIONS_BYTES",
    "SCORED_CHANNELS",
    "Predictions",
    "eval_key",
    "load_predictions",
    "parse_predictions",
]

EVAL_KEY_VERSION: Final = 1
MAX_PREDICTIONS_BYTES: Final = 64 * 1024 * 1024
SCORED_CHANNELS: Final = frozenset({Channel.INLINE, Channel.SUMMARY})

ProducerKey = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")]
ProducerValue = Annotated[str, Field(max_length=200)]
CaseId = Annotated[str, Field(pattern=CASE_ID_PATTERN)]


class _PredictionsFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1]
    producer: dict[ProducerKey, ProducerValue] = {}
    cases: dict[CaseId, list[Finding]]


@dataclass(frozen=True, slots=True)
class Predictions:
    producer: Mapping[str, str]
    by_case: Mapping[str, tuple[Finding, ...]]

    def scored(self, case_id: str) -> tuple[Finding, ...]:
        """Inline and summary findings of a case, in file order."""
        return tuple(f for f in self.by_case.get(case_id, ()) if f.channel in SCORED_CHANNELS)

    def unscored_counts(self) -> dict[str, int]:
        counts = Counter(
            f.channel.value
            for findings in self.by_case.values()
            for f in findings
            if f.channel not in SCORED_CHANNELS
        )
        return dict(sorted(counts.items()))


def eval_key(case: Case, finding: Finding) -> str:
    """The adjudication key: the section 5.5 fields (rename-tracked path, no symbol) plus
    the start line, so identical findings at different places stay distinct (D20)."""
    fields = fingerprint_fields(
        category=finding.category,
        rule_id=finding.rule_id,
        title=finding.title,
        canonical_path=case.canonical_path(finding.location.path),
        enclosing_symbol="",
        excerpt=finding.evidence[0].excerpt,
    )
    return digest([*fields, finding.location.start_line])


def load_predictions(path: Path, cases: Sequence[Case]) -> Predictions:
    if not path.is_file():
        raise EvalInputError(f"{path}: predictions file not found")
    size = path.stat().st_size
    if size > MAX_PREDICTIONS_BYTES:
        raise EvalInputError(
            f"{path}: the file is {size} bytes; the limit is {MAX_PREDICTIONS_BYTES} bytes"
        )
    try:
        return parse_predictions(path.read_text(encoding="utf-8"), cases)
    except EvalInputError as exc:
        raise EvalInputError(*(f"{path.name}: {m}" for m in exc.messages)) from None
    except UnicodeDecodeError:
        raise EvalInputError(f"{path.name}: the file is not UTF-8") from None


def parse_predictions(text: str, cases: Sequence[Case]) -> Predictions:
    try:
        document = _PredictionsFile.model_validate_json(text)
    except ValidationError as exc:
        raise EvalInputError(*validation_messages(exc, top_level="predictions")) from None
    expected = {c.id for c in cases}
    given = set(document.cases)
    problems = [
        f"cases.{case_id}: unknown case (not among the selected cases)"
        for case_id in sorted(given - expected)
    ]
    problems += [
        f"cases.{case_id}: missing; list every scored case, [] if it has no findings"
        for case_id in sorted(expected - given)
    ]
    if problems:
        raise EvalInputError(*problems)
    return Predictions(
        producer=dict(document.producer),
        by_case={case_id: tuple(findings) for case_id, findings in document.cases.items()},
    )
