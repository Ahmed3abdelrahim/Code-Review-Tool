"""Match predictions to labels (plan section 8.3, D20).

A prediction can match a label when the canonical paths (renames applied to both) and the
sides are equal, the line ranges overlap with LINE_TOLERANCE lines of slack, and the
categories are compatible. Inline predictions are matched first, then summary predictions
against the labels still free; annotations and unpublished findings never match.

Within a channel the assignment is one-to-one and maximum-cardinality: as many pairs as
possible, then the smallest total severity disagreement, then the smallest total line gap.
It is solved exactly (Hungarian algorithm on integer costs) over predictions and labels in
a canonical order, so the result does not depend on input order.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from aireviewer.contracts.findings import Category, Channel, Finding, Severity
from aireviewer.eval.cases import Case, Label
from aireviewer.eval.predictions import eval_key

__all__ = [
    "COMPATIBLE_CATEGORIES",
    "LINE_TOLERANCE",
    "SEVERITY_RANK",
    "categories_compatible",
    "line_gap",
    "match_case",
]

LINE_TOLERANCE: Final = 3
COMPATIBLE_CATEGORIES: Final = frozenset(
    {Category.CORRECTNESS, Category.RELIABILITY, Category.PERFORMANCE}
)
SEVERITY_RANK: Final = {severity: rank for rank, severity in enumerate(Severity)}
_MATCH_ORDER: Final = (Channel.INLINE, Channel.SUMMARY)


def categories_compatible(a: Category, b: Category) -> bool:
    return a == b or (a in COMPATIBLE_CATEGORIES and b in COMPATIBLE_CATEGORIES)


def line_gap(p_start: int, p_end: int, l_start: int, l_end: int) -> int:
    """Lines between two ranges; 0 when they overlap."""
    return max(0, p_start - l_end, l_start - p_end)


def match_case(case: Case, findings: Sequence[Finding]) -> dict[int, str]:
    """Return {index in `findings`: label id} for the matched predictions."""
    matched: dict[int, str] = {}
    free = sorted(case.labels, key=lambda label: label.id)
    for channel in _MATCH_ORDER:
        rows = sorted(
            (i for i, f in enumerate(findings) if f.channel is channel),
            key=lambda i: _canonical_order(case, findings[i]),
        )
        assigned = _assign(case, [findings[i] for i in rows], free)
        for row, label in assigned.items():
            matched[rows[row]] = label.id
        taken = {label.id for label in assigned.values()}
        free = [label for label in free if label.id not in taken]
    return matched


def _canonical_order(case: Case, finding: Finding) -> tuple[object, ...]:
    location = finding.location
    return (
        case.canonical_path(location.path),
        location.side.value,
        location.start_line,
        location.end_line,
        finding.category.value,
        SEVERITY_RANK[finding.severity],
        eval_key(case, finding),
        finding.title,
        finding.explanation,
    )


def _pair_cost(case: Case, finding: Finding, label: Label) -> tuple[int, int] | None:
    """(severity disagreement, line gap) when the pair can match, else None."""
    location = finding.location
    if case.canonical_path(location.path) != case.canonical_path(label.path):
        return None
    if location.side != label.side or not categories_compatible(finding.category, label.category):
        return None
    gap = line_gap(location.start_line, location.end_line, label.lines[0], label.lines[1])
    if gap > LINE_TOLERANCE:
        return None
    return abs(SEVERITY_RANK[finding.severity] - SEVERITY_RANK[label.severity]), gap


def _assign(case: Case, findings: Sequence[Finding], labels: Sequence[Label]) -> dict[int, Label]:
    if not findings or not labels:
        return {}
    n = len(findings)
    # Integer costs ordered lexicographically: unmatched predictions, then severity
    # disagreement, then line gap. Gaps sum to at most 3n < weight; one more match
    # (saving `unmatched`) outweighs any sum of pair costs.
    weight = LINE_TOLERANCE * n + 1
    unmatched = n * (len(SEVERITY_RANK) * weight + LINE_TOLERANCE) + 1
    forbidden = unmatched + 1
    matrix: list[list[int]] = []
    for finding in findings:
        row = []
        for label in labels:
            cost = _pair_cost(case, finding, label)
            row.append(forbidden if cost is None else cost[0] * weight + cost[1])
        row += [unmatched] * n  # one "stay unmatched" column per prediction
        matrix.append(row)
    columns = _min_cost_assignment(matrix)
    return {
        row: labels[col]
        for row, col in enumerate(columns)
        if col < len(labels) and matrix[row][col] < unmatched
    }


def _min_cost_assignment(cost: Sequence[Sequence[int]]) -> list[int]:
    """Hungarian algorithm (rows <= columns): the column assigned to each row."""
    rows, cols = len(cost), len(cost[0])
    infinity = sum(max(r) for r in cost) + 1
    u = [0] * (rows + 1)
    v = [0] * (cols + 1)
    owner = [0] * (cols + 1)  # row (1-based) assigned to each column; 0 = none
    way = [0] * (cols + 1)
    for row in range(1, rows + 1):
        owner[0] = row
        col0 = 0
        min_slack = [infinity] * (cols + 1)
        used = [False] * (cols + 1)
        while True:
            used[col0] = True
            row0, delta, col1 = owner[col0], infinity, 0
            for col in range(1, cols + 1):
                if used[col]:
                    continue
                slack = cost[row0 - 1][col - 1] - u[row0] - v[col]
                if slack < min_slack[col]:
                    min_slack[col], way[col] = slack, col0
                if min_slack[col] < delta:
                    delta, col1 = min_slack[col], col
            for col in range(cols + 1):
                if used[col]:
                    u[owner[col]] += delta
                    v[col] -= delta
                else:
                    min_slack[col] -= delta
            col0 = col1
            if owner[col0] == 0:
                break
        while col0:
            col1 = way[col0]
            owner[col0] = owner[col1]
            col0 = col1
    assignment = [-1] * rows
    for col in range(1, cols + 1):
        if owner[col]:
            assignment[owner[col] - 1] = col - 1
    return assignment
