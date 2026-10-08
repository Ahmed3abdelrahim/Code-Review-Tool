"""Adjudication of unmatched predictions (plan section 8.4, D20).

Verdicts (valid, invalid, duplicate) are appended to `eval/adjudications.jsonl`, keyed by
`(case_id, key)` where `key` is the harness's own evaluation key (`eval_key`, versioned by
`key_version`), never a producer's fingerprint. For the same key the last line wins; the
file keeps the history. An earlier verdict on a similar finding (same case, canonical path,
side and category, overlapping lines) is offered as a suggestion in the session, never
reused silently.

Predictions are untrusted text (model or CodeRabbit output): control and formatting
characters are removed before anything is printed to the terminal.
"""

from __future__ import annotations

import os
import unicodedata
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Final, Literal, Protocol, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError

from aireviewer.clock import Clock
from aireviewer.config_files import validation_messages
from aireviewer.contracts.anchors import Side
from aireviewer.contracts.findings import Category, Finding
from aireviewer.eval.cases import CASE_ID_PATTERN, Case
from aireviewer.eval.errors import EvalInputError
from aireviewer.eval.predictions import EVAL_KEY_VERSION, eval_key
from aireviewer.pipeline.fingerprint import FINGERPRINT_LENGTH

__all__ = [
    "Adjudication",
    "AdjudicationIndex",
    "AdjudicationStore",
    "CodeLookup",
    "DirectoryCodeLookup",
    "NoCodeLookup",
    "PendingItem",
    "SessionSummary",
    "Verdict",
    "run_session",
    "sanitize_for_terminal",
]

NEARBY_LABEL_LINES: Final = 10
CODE_CONTEXT_LINES: Final = 2
MAX_SOURCE_BYTES: Final = 2 * 1024 * 1024
_EXPLANATION_CHARS: Final = 1500


class Verdict(StrEnum):
    VALID = "valid"
    INVALID = "invalid"
    DUPLICATE = "duplicate"


class Adjudication(BaseModel):
    """One line of adjudications.jsonl."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: Annotated[str, Field(pattern=CASE_ID_PATTERN)]
    key: Annotated[str, Field(pattern=rf"^[0-9a-f]{{{FINGERPRINT_LENGTH}}}$")]
    key_version: Literal[1]
    verdict: Verdict
    note: Annotated[str, Field(max_length=2000)] = ""
    # What the verdict was about: shown to humans and used to suggest verdicts for
    # similar findings.
    title: Annotated[str, Field(max_length=200)]
    category: Category
    path: str
    side: Side
    start_line: Annotated[int, Field(ge=1)]
    end_line: Annotated[int, Field(ge=1)]
    adjudicated_at: AwareDatetime

    @classmethod
    def for_finding(
        cls,
        case: Case,
        finding: Finding,
        *,
        verdict: Verdict,
        note: str,
        adjudicated_at: AwareDatetime,
    ) -> Self:
        location = finding.location
        return cls(
            case_id=case.id,
            key=eval_key(case, finding),
            key_version=EVAL_KEY_VERSION,
            verdict=verdict,
            note=sanitize_for_terminal(note)[:2000],
            title=finding.title[:200],
            category=finding.category,
            path=case.canonical_path(location.path),
            side=location.side,
            start_line=location.start_line,
            end_line=location.end_line,
            adjudicated_at=adjudicated_at,
        )


class AdjudicationIndex:
    """The latest verdict per (case_id, key), in file order."""

    def __init__(self, records: Iterable[Adjudication]) -> None:
        self._latest: dict[tuple[str, str], Adjudication] = {}
        for record in records:
            self.add(record)

    def add(self, record: Adjudication) -> None:
        self._latest.pop((record.case_id, record.key), None)  # re-insert: newest last
        self._latest[record.case_id, record.key] = record

    def get(self, case_id: str, key: str) -> Adjudication | None:
        return self._latest.get((case_id, key))

    def similar(self, case: Case, finding: Finding) -> Adjudication | None:
        """The most recent verdict on another finding at the same place and category."""
        location = finding.location
        path, key = case.canonical_path(location.path), eval_key(case, finding)
        candidates = [
            r
            for r in self._latest.values()
            if r.case_id == case.id
            and r.key != key
            and r.path == path
            and r.side == location.side
            and r.category == finding.category
            and r.start_line <= location.end_line
            and location.start_line <= r.end_line
        ]
        return candidates[-1] if candidates else None

    def __len__(self) -> int:
        return len(self._latest)


class AdjudicationStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> AdjudicationIndex:
        if not self.path.exists():
            return AdjudicationIndex([])
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            raise EvalInputError(f"{self.path.name}: the file is not UTF-8") from None
        records: list[Adjudication] = []
        problems: list[str] = []
        for number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                records.append(Adjudication.model_validate_json(line))
            except ValidationError as exc:
                problems += [
                    f"{self.path.name}:{number}: {m}"
                    for m in validation_messages(exc, top_level="record")
                ]
        if problems:
            raise EvalInputError(*problems)
        return AdjudicationIndex(records)

    def append(self, record: Adjudication) -> None:
        """Append one verdict and make it durable before the session continues."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(record.model_dump_json() + "\n")
            handle.flush()
            os.fsync(handle.fileno())


# --- code shown in the session ----------------------------------------------------------------


class CodeLookup(Protocol):
    def lines(
        self, case: Case, path: str, side: Side | str, start: int, end: int
    ) -> list[tuple[int, str]] | None:
        """Numbered lines `start`..`end` of a file, or None when unavailable."""


class NoCodeLookup:
    def lines(
        self, case: Case, path: str, side: Side | str, start: int, end: int
    ) -> list[tuple[int, str]] | None:
        return None


class DirectoryCodeLookup:
    """Reads head-side files from `<root>/<case_id>/<path>` (one checkout per case).

    Paths that resolve outside the case's directory (`..`, symlinks) are refused. The
    reader for git bundles comes with T0.6.
    """

    def __init__(self, root: Path) -> None:
        self.root = root

    def lines(
        self, case: Case, path: str, side: Side | str, start: int, end: int
    ) -> list[tuple[int, str]] | None:
        if Side(side) is not Side.RIGHT:
            return None
        case_root = (self.root / case.id).resolve()
        try:
            target = (case_root / path).resolve()
        except OSError:
            return None
        if not target.is_relative_to(case_root) or not target.is_file():
            return None
        if target.stat().st_size > MAX_SOURCE_BYTES:
            return None
        text = target.read_text(encoding="utf-8", errors="replace").splitlines()
        first, last = max(start, 1), min(end, len(text))
        return [(n, text[n - 1]) for n in range(first, last + 1)]


# --- the interactive session ------------------------------------------------------------------


class PendingItem(Protocol):
    """A prediction without a verdict (metrics.ScoredFinding satisfies it)."""

    @property
    def case_id(self) -> str: ...

    @property
    def finding(self) -> Finding: ...

    @property
    def key(self) -> str: ...


@dataclass(slots=True)
class SessionSummary:
    recorded: int = 0
    skipped: int = 0
    stopped: bool = False


_CHOICES: Final = {"v": Verdict.VALID, "i": Verdict.INVALID, "d": Verdict.DUPLICATE}
_REMOVED_CATEGORIES: Final = frozenset({"Cc", "Cf", "Cs", "Co"})


def sanitize_for_terminal(text: str) -> str:
    """Drop control, format (bidi), surrogate and private-use characters; keep \\n and \\t."""
    return "".join(
        c for c in text if c in "\n\t" or unicodedata.category(c) not in _REMOVED_CATEGORIES
    )


def run_session(
    pending: Sequence[PendingItem],
    *,
    cases: Mapping[str, Case],
    store: AdjudicationStore,
    index: AdjudicationIndex,
    ask: Callable[[str], str],
    write: Callable[[str], None],
    clock: Clock,
    code: CodeLookup,
) -> SessionSummary:
    """Ask for a verdict on each pending prediction; every verdict is saved immediately.

    `ask` raises EOFError at the end of input, which ends the session like "quit".
    """
    summary = SessionSummary()
    for number, item in enumerate(pending, start=1):
        case = cases[item.case_id]
        if index.get(case.id, item.key) is not None:
            continue  # decided earlier in this session (same key twice)
        suggestion = index.similar(case, item.finding)
        write(_describe(number, len(pending), case, item, suggestion, code))
        try:
            choice = _choose(ask, write, suggestion is not None)
            if choice == "q":
                summary.stopped = True
                break
            if choice == "s":
                summary.skipped += 1
                continue
            if choice == "a" and suggestion is not None:
                verdict = suggestion.verdict
                note = f"accepted earlier verdict {suggestion.key[:8]}: {suggestion.note}"
            else:
                verdict = _CHOICES[choice]
                note = ask("Note (optional): ").strip()
        except EOFError:
            summary.stopped = True
            break
        record = Adjudication.for_finding(
            case, item.finding, verdict=verdict, note=note.strip(), adjudicated_at=clock.now()
        )
        store.append(record)
        index.add(record)
        summary.recorded += 1
        write(f"Recorded: {verdict.value}\n\n")
    return summary


def _choose(ask: Callable[[str], str], write: Callable[[str], None], can_accept: bool) -> str:
    options = "[v]alid, [i]nvalid, [d]uplicate, [s]kip, [q]uit"
    allowed = {"v", "i", "d", "s", "q"}
    if can_accept:
        options = "[a]ccept earlier verdict, " + options
        allowed.add("a")
    while True:
        answer = ask(f"{options}: ").strip().lower()
        if answer in allowed:
            return answer
        write(f"Please answer one of: {', '.join(sorted(allowed))}.\n")


def _describe(
    number: int,
    total: int,
    case: Case,
    item: PendingItem,
    suggestion: Adjudication | None,
    code: CodeLookup,
) -> str:
    finding, safe = item.finding, sanitize_for_terminal
    location = finding.location
    path = case.canonical_path(location.path)
    lines = [
        f"--- [{number}/{total}] {case.id} · {finding.channel.value} · "
        f"{finding.severity.value} {finding.category.value} · key {item.key[:8]}",
        f"Title: {safe(finding.title)}",
        f"Location: {safe(path)}:{location.start_line}-{location.end_line} ({location.side})",
    ]
    if finding.rule_id:
        lines.append(f"Rule: {safe(finding.rule_id)}")
    lines.append(f"Explanation: {safe(finding.explanation[:_EXPLANATION_CHARS])}")
    lines.append("Evidence:")
    lines += [f"  {safe(e.path)}:{e.line}  {safe(e.excerpt)}" for e in finding.evidence]
    shown = code.lines(
        case,
        path,
        location.side,
        location.start_line - CODE_CONTEXT_LINES,
        location.end_line + CODE_CONTEXT_LINES,
    )
    if shown:
        lines.append("Code:")
        for n, text in shown:
            marker = ">" if location.start_line <= n <= location.end_line else " "
            lines.append(f"  {marker}{n:>5} | {safe(text)}")
    nearby = [
        label
        for label in case.labels
        if case.canonical_path(label.path) == path
        and label.lines[0] - NEARBY_LABEL_LINES <= location.end_line
        and location.start_line <= label.lines[1] + NEARBY_LABEL_LINES
    ]
    if nearby:
        lines.append("Nearby labels:")
        lines += [
            f"  {label.id} {label.severity.value} {label.category.value} "
            f"{label.path}:{label.lines[0]}-{label.lines[1]} ({label.side}) - "
            f"{safe(label.description)}"
            for label in nearby
        ]
    if suggestion is not None:
        when = suggestion.adjudicated_at.strftime("%Y-%m-%d %H:%M %Z")
        lines.append(
            f"Earlier verdict for a similar finding ({when}, key {suggestion.key[:8]}): "
            f"{suggestion.verdict.value} - {safe(suggestion.note) or 'no note'} "
            f'("{safe(suggestion.title)}")'
        )
    return "\n".join(lines) + "\n"
