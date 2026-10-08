"""Evaluation metrics (plan section 8.5, D20), computed exactly with fractions.

Each scored prediction (inline or summary) is MATCHED to a label, or carries the verdict
of its adjudication (VALID, INVALID, DUPLICATE), or is PENDING. Precision is
(matched + valid) / n; while verdicts are pending it is the range
[correct / n, (correct + pending) / n]. Duplicates are not correct but are not false
positives either. Engine latency, cost and partial rate come with the engine (T3.13).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction
from typing import Final

from aireviewer.contracts.findings import Category, Channel, Finding, Severity
from aireviewer.eval.adjudicate import AdjudicationIndex, Verdict
from aireviewer.eval.cases import Case
from aireviewer.eval.matcher import SEVERITY_RANK, MatchingMode, match_case
from aireviewer.eval.predictions import Predictions, eval_key

__all__ = [
    "PER_RULE_CATEGORIES",
    "FalsePositives",
    "InlineStats",
    "Outcome",
    "Precision",
    "Recall",
    "Scorecard",
    "ScoredFinding",
    "score",
]

PER_RULE_CATEGORIES: Final = frozenset({Category.DESIGN, Category.MAINTAINABILITY})
_HIGH: Final = SEVERITY_RANK[Severity.HIGH]


class Outcome(StrEnum):
    MATCHED = "matched"
    VALID = "valid"
    INVALID = "invalid"
    DUPLICATE = "duplicate"
    PENDING = "pending"


_FROM_VERDICT: Final = {
    Verdict.VALID: Outcome.VALID,
    Verdict.INVALID: Outcome.INVALID,
    Verdict.DUPLICATE: Outcome.DUPLICATE,
}


@dataclass(frozen=True, slots=True)
class ScoredFinding:
    case_id: str
    finding: Finding
    key: str
    outcome: Outcome
    label_id: str | None  # set when MATCHED


@dataclass(frozen=True, slots=True)
class Precision:
    n: int
    correct: int  # matched + adjudicated valid
    pending: int
    invalid: int
    duplicate: int

    @classmethod
    def of(cls, outcomes: Iterable[Outcome]) -> Precision:
        counts = Counter(outcomes)
        return cls(
            n=counts.total(),
            correct=counts[Outcome.MATCHED] + counts[Outcome.VALID],
            pending=counts[Outcome.PENDING],
            invalid=counts[Outcome.INVALID],
            duplicate=counts[Outcome.DUPLICATE],
        )

    @property
    def complete(self) -> bool:
        return self.pending == 0

    @property
    def lower(self) -> Fraction | None:
        return Fraction(self.correct, self.n) if self.n else None

    @property
    def upper(self) -> Fraction | None:
        return Fraction(self.correct + self.pending, self.n) if self.n else None

    @property
    def value(self) -> Fraction | None:
        return self.lower if self.complete else None


@dataclass(frozen=True, slots=True)
class Recall:
    labels: int  # severity high or critical
    matched: int  # by an inline or summary prediction (headline)
    matched_inline: int

    @property
    def value(self) -> Fraction | None:
        return Fraction(self.matched, self.labels) if self.labels else None

    @property
    def inline_value(self) -> Fraction | None:
        return Fraction(self.matched_inline, self.labels) if self.labels else None


@dataclass(frozen=True, slots=True)
class FalsePositives:
    cases: int
    invalid: int  # invalid inline findings
    pending: int  # inline findings without a verdict

    @property
    def lower(self) -> Fraction | None:
        return Fraction(self.invalid, self.cases) if self.cases else None

    @property
    def upper(self) -> Fraction | None:
        return Fraction(self.invalid + self.pending, self.cases) if self.cases else None

    @property
    def value(self) -> Fraction | None:
        return self.lower if self.pending == 0 else None


@dataclass(frozen=True, slots=True)
class InlineStats:
    mean: Fraction
    max: int


@dataclass(frozen=True, slots=True)
class Scorecard:
    split: str
    matching: MatchingMode
    producer: Mapping[str, str]
    cases: tuple[Case, ...]
    scored: tuple[ScoredFinding, ...]
    inline_precision: Mapping[str, Precision]  # "all" plus each category with findings
    summary_precision: Mapping[str, Precision]
    high_severity_recall: Recall
    false_positives_per_pr: FalsePositives
    inline_per_case: InlineStats
    per_rule_precision: Mapping[str, Precision]  # design and maintainability rule IDs
    missed_must_find: tuple[tuple[str, str], ...]  # (case_id, label_id)
    max_inline_exceeded: tuple[tuple[str, int, int], ...]  # (case_id, inline, limit)
    unscored: Mapping[str, int]  # findings on other channels, by channel
    pending: tuple[ScoredFinding, ...]


def score(
    cases: Sequence[Case],
    predictions: Predictions,
    index: AdjudicationIndex,
    *,
    split: str,
    matching: MatchingMode = MatchingMode.STRICT,
) -> Scorecard:
    scored: list[ScoredFinding] = []
    matched_any: set[tuple[str, str]] = set()
    matched_inline: set[tuple[str, str]] = set()
    inline_counts: dict[str, int] = {}
    for case in cases:
        findings = predictions.scored(case.id)
        matches = match_case(case, findings, mode=matching)
        for i, finding in enumerate(findings):
            key = eval_key(case, finding)
            label_id = matches.get(i)
            if label_id is not None:
                outcome = Outcome.MATCHED
                matched_any.add((case.id, label_id))
                if finding.channel is Channel.INLINE:
                    matched_inline.add((case.id, label_id))
            else:
                record = index.get(case.id, key)
                outcome = _FROM_VERDICT[record.verdict] if record else Outcome.PENDING
            scored.append(ScoredFinding(case.id, finding, key, outcome, label_id))
        inline_counts[case.id] = sum(1 for f in findings if f.channel is Channel.INLINE)

    inline = [s for s in scored if s.finding.channel is Channel.INLINE]
    summary = [s for s in scored if s.finding.channel is Channel.SUMMARY]
    high_labels = [
        (case.id, label.id)
        for case in cases
        for label in case.labels
        if SEVERITY_RANK[label.severity] >= _HIGH
    ]
    return Scorecard(
        split=split,
        matching=matching,
        producer=dict(predictions.producer),
        cases=tuple(cases),
        scored=tuple(scored),
        inline_precision=_by_category(inline),
        summary_precision=_by_category(summary),
        high_severity_recall=Recall(
            labels=len(high_labels),
            matched=sum(1 for x in high_labels if x in matched_any),
            matched_inline=sum(1 for x in high_labels if x in matched_inline),
        ),
        false_positives_per_pr=FalsePositives(
            cases=len(cases),
            invalid=sum(1 for s in inline if s.outcome is Outcome.INVALID),
            pending=sum(1 for s in inline if s.outcome is Outcome.PENDING),
        ),
        inline_per_case=InlineStats(
            mean=Fraction(sum(inline_counts.values()), len(cases)) if cases else Fraction(0),
            max=max(inline_counts.values(), default=0),
        ),
        per_rule_precision=_per_rule(scored),
        missed_must_find=tuple(
            (case.id, label.id)
            for case in cases
            for label in case.labels
            if label.must_find and (case.id, label.id) not in matched_any
        ),
        max_inline_exceeded=tuple(
            (case.id, inline_counts[case.id], case.expect.max_inline)
            for case in cases
            if case.expect.max_inline is not None
            and inline_counts[case.id] > case.expect.max_inline
        ),
        unscored=predictions.unscored_counts(),
        pending=tuple(s for s in scored if s.outcome is Outcome.PENDING),
    )


def _by_category(scored: Sequence[ScoredFinding]) -> dict[str, Precision]:
    result = {"all": Precision.of(s.outcome for s in scored)}
    for category in Category:
        outcomes = [s.outcome for s in scored if s.finding.category is category]
        if outcomes:
            result[category.value] = Precision.of(outcomes)
    return result


def _per_rule(scored: Sequence[ScoredFinding]) -> dict[str, Precision]:
    by_rule: defaultdict[str, list[Outcome]] = defaultdict(list)
    for s in scored:
        if s.finding.category in PER_RULE_CATEGORIES and s.finding.rule_id:
            by_rule[s.finding.rule_id].append(s.outcome)
    return {rule: Precision.of(outcomes) for rule, outcomes in sorted(by_rule.items())}
