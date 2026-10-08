"""Evaluation reports (plan section 8.6): report.md and metrics.json.

Each run writes `<out_dir>/<UTC timestamp>-<split>-score/`. Precision is shown as a range
while adjudications are pending and as one value when complete; sample sizes are always
shown. Text from predictions is untrusted: control characters are removed and Markdown
table and HTML characters are escaped.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path
from typing import Any, Final

from aireviewer.clock import Clock
from aireviewer.eval.adjudicate import sanitize_for_terminal
from aireviewer.eval.matcher import MatchingMode
from aireviewer.eval.metrics import FalsePositives, Precision, Scorecard
from aireviewer.eval.predictions import EVAL_KEY_VERSION

__all__ = [
    "REPORT_FORMAT_VERSION",
    "metrics_document",
    "render_markdown",
    "summary_document",
    "write_report",
]

REPORT_FORMAT_VERSION: Final = 1
_MATCHING_TEXT: Final = {
    MatchingMode.STRICT: "strict (categories must be compatible)",
    MatchingMode.LOCATION: "location only (categories ignored)",
}
_PRECISION_COLUMNS: Final = "| {first} | Precision | Correct | Pending | Invalid | Duplicate |\n"


def write_report(card: Scorecard, *, out_dir: Path, clock: Clock) -> Path:
    """Write report.md and metrics.json into a new directory and return it."""
    generated_at = clock.now().astimezone(UTC)
    base = f"{generated_at:%Y%m%dT%H%M%SZ}-{card.split}-score"
    target, suffix = out_dir / base, 1
    while target.exists():
        suffix += 1
        target = out_dir / f"{base}-{suffix}"
    target.mkdir(parents=True)
    (target / "report.md").write_text(
        render_markdown(card, generated_at=generated_at), encoding="utf-8"
    )
    document = metrics_document(card, generated_at=generated_at)
    (target / "metrics.json").write_text(
        json.dumps(document, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return target


# --- metrics.json -----------------------------------------------------------------------------


def metrics_document(card: Scorecard, *, generated_at: datetime) -> dict[str, Any]:
    recall, fp = card.high_severity_recall, card.false_positives_per_pr
    return {
        "format_version": REPORT_FORMAT_VERSION,
        "generated_at": generated_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "split": card.split,
        "matching": card.matching.value,
        "producer": dict(card.producer),
        "eval_key_version": EVAL_KEY_VERSION,
        "cases": {
            "total": len(card.cases),
            "by_kind": dict(sorted(Counter(c.kind.value for c in card.cases).items())),
            "ids": [c.id for c in card.cases],
        },
        "inline_precision": {k: _precision_json(p) for k, p in card.inline_precision.items()},
        "summary_precision": {k: _precision_json(p) for k, p in card.summary_precision.items()},
        "high_severity_recall": {
            "labels": recall.labels,
            "matched": recall.matched,
            "matched_inline": recall.matched_inline,
            "value": _number(recall.value),
            "inline_value": _number(recall.inline_value),
        },
        "false_positives_per_pr": {
            "cases": fp.cases,
            "invalid": fp.invalid,
            "pending": fp.pending,
            "lower": _number(fp.lower),
            "upper": _number(fp.upper),
            "value": _number(fp.value),
        },
        "inline_per_case": {
            "mean": _number(card.inline_per_case.mean),
            "max": card.inline_per_case.max,
        },
        "per_rule_precision": {k: _precision_json(p) for k, p in card.per_rule_precision.items()},
        "missed_must_find": [
            {"case_id": c, "label_id": label} for c, label in card.missed_must_find
        ],
        "max_inline_exceeded": [
            {"case_id": c, "inline": n, "limit": limit} for c, n, limit in card.max_inline_exceeded
        ],
        "unscored": dict(card.unscored),
        "pending": [
            {
                "case_id": s.case_id,
                "key": s.key,
                "channel": s.finding.channel.value,
                "category": s.finding.category.value,
                "path": s.finding.location.path,
                "start_line": s.finding.location.start_line,
                "title": sanitize_for_terminal(s.finding.title),
            }
            for s in card.pending
        ],
    }


def summary_document(card: Scorecard, *, generated_at: datetime) -> dict[str, Any]:
    """The compact baseline summary (eval/baselines/<name>.json): precision (or its range),
    high-severity recall and comments per PR, with sample sizes."""
    full = metrics_document(card, generated_at=generated_at)
    return {
        "format_version": REPORT_FORMAT_VERSION,
        "generated_at": full["generated_at"],
        "producer": full["producer"],
        "split": card.split,
        "matching": card.matching.value,
        "eval_key_version": EVAL_KEY_VERSION,
        "cases": {"total": full["cases"]["total"], "by_kind": full["cases"]["by_kind"]},
        "inline_precision": full["inline_precision"],
        "high_severity_recall": full["high_severity_recall"],
        "false_positives_per_pr": full["false_positives_per_pr"],
        "comments_per_pr": full["inline_per_case"],
        "pending_adjudications": len(card.pending),
    }


def _number(value: Fraction | None) -> float | None:
    return None if value is None else round(float(value), 4)


def _precision_json(p: Precision) -> dict[str, Any]:
    return {
        "n": p.n,
        "correct": p.correct,
        "pending": p.pending,
        "invalid": p.invalid,
        "duplicate": p.duplicate,
        "lower": _number(p.lower),
        "upper": _number(p.upper),
        "value": _number(p.value),
    }


# --- report.md --------------------------------------------------------------------------------


def render_markdown(card: Scorecard, *, generated_at: datetime) -> str:
    kinds = Counter(c.kind.value for c in card.cases)
    kind_text = ", ".join(f"{kind} {n}" for kind, n in sorted(kinds.items())) or "none"
    producer = ", ".join(f"{_cell(k)} {_cell(v)}" for k, v in card.producer.items()) or "unknown"
    recall, stats = card.high_severity_recall, card.inline_per_case
    out = [
        "# Evaluation report\n\n",
        f"- Generated: {generated_at.astimezone(UTC):%Y-%m-%d %H:%M:%S} UTC\n",
        f"- Split: {card.split}\n",
        f"- Matching: {_MATCHING_TEXT[card.matching]}\n",
        f"- Cases: {len(card.cases)} ({kind_text})\n",
        f"- Producer: {producer}\n",
        f"- Evaluation key version: {EVAL_KEY_VERSION}\n",
        "\nPrecision is (matched + adjudicated valid) / n. While adjudications are pending it "
        "is shown as [pending counted wrong, pending counted right].\n",
        "\n## Inline precision\n\n",
        *_precision_table(card.inline_precision, first="Category"),
        "\n## Summary precision\n\n",
        *_precision_table(card.summary_precision, first="Category"),
        "\n## High-severity recall\n\n",
        "| Channels | Recall | Matched | Labels |\n|---|---|---|---|\n",
        f"| inline + summary | {_percent(recall.value)} | {recall.matched} | {recall.labels} |\n",
        f"| inline only | {_percent(recall.inline_value)} | {recall.matched_inline} | "
        f"{recall.labels} |\n",
        "\n## False positives per PR\n\n",
        f"{_fp_text(card.false_positives_per_pr)}\n",
        "\n## Inline comments per case\n\n",
        f"Mean {_decimal(stats.mean)}, max {stats.max}.\n",
        "\n## Per-rule precision (design, maintainability)\n\n",
    ]
    if card.per_rule_precision:
        out += _precision_table(card.per_rule_precision, first="Rule", escape_keys=True)
    else:
        out.append("No rule-based design or maintainability findings.\n")
    out.append("\n## Missed must-find labels\n\n")
    out += [f"- {c} / {label}\n" for c, label in card.missed_must_find] or ["None.\n"]
    out.append("\n## Cases over expect.max_inline\n\n")
    out += [
        f"- {c}: {n} inline comments (limit {limit})\n" for c, n, limit in card.max_inline_exceeded
    ] or ["None.\n"]
    out.append("\n## Not scored\n\n")
    out += [
        f"- {channel}: {n} finding{'s' if n != 1 else ''}\n" for channel, n in card.unscored.items()
    ] or ["None (only inline and summary findings are scored).\n"]
    out.append(f"\n## Pending adjudications ({len(card.pending)})\n\n")
    if card.pending:
        out.append("| Case | Channel | Category | Location | Title | Key |\n")
        out.append("|---|---|---|---|---|---|\n")
        for s in card.pending:
            location = s.finding.location
            out.append(
                f"| {s.case_id} | {s.finding.channel.value} | {s.finding.category.value} | "
                f"{_cell(location.path)}:{location.start_line} | {_cell(s.finding.title)} | "
                f"{s.key[:12]} |\n"
            )
        out.append("\nRun `aireview-eval adjudicate` to decide them.\n")
    else:
        out.append("None.\n")
    return "".join(out)


def _precision_table(
    rows: Mapping[str, Precision], *, first: str, escape_keys: bool = False
) -> list[str]:
    lines = [_PRECISION_COLUMNS.format(first=first), "|---|---|---|---|---|---|\n"]
    for key, p in rows.items():
        name = _cell(key) if escape_keys else key
        lines.append(
            f"| {name} | {_precision_text(p)} | {p.correct} | {p.pending} | {p.invalid} | "
            f"{p.duplicate} |\n"
        )
    return lines


def _precision_text(p: Precision) -> str:
    if p.n == 0:
        return "n/a (n=0)"
    if p.complete:
        return f"{_percent(p.value)} (n={p.n})"
    return f"[{_percent(p.lower)}, {_percent(p.upper)}] (n={p.n}, {p.pending} pending)"


def _fp_text(fp: FalsePositives) -> str:
    counts = f"{fp.invalid} invalid inline, {fp.pending} pending, {fp.cases} cases"
    if fp.cases == 0:
        return f"n/a ({counts})"
    if fp.pending == 0:
        return f"{_decimal(fp.value)} ({counts})"
    return f"[{_decimal(fp.lower)}, {_decimal(fp.upper)}] ({counts})"


def _percent(value: Fraction | None) -> str:
    return "n/a" if value is None else f"{float(value) * 100:.1f}%"


def _decimal(value: Fraction | None) -> str:
    return "n/a" if value is None else f"{float(value):.2f}"


def _cell(text: str) -> str:
    """Untrusted text in a Markdown table cell or list item."""
    clean = " ".join(sanitize_for_terminal(text).split())
    return clean.replace("|", "\\|").replace("<", "&lt;").replace(">", "&gt;")
