"""Convert CodeRabbit's pull request review comments into a predictions file (D21).

Input: one file per case, `<case id>.json`, as exported with
`gh api --paginate repos/<org>/<repo>/pulls/<n>/comments` (pages may be concatenated JSON
arrays). Only CodeRabbit's top-level line comments are scored, as inline findings; replies,
other users and file-level comments are counted and skipped. CodeRabbit's walkthrough and
the nitpicks folded into its review body are not inline comments and are not converted.

Category and severity come from CodeRabbit's markers ("Potential issue", "Refactor
suggestion", "Nitpick"; "Critical", "Major", "Minor", "Trivial"), correctable per comment
with an overrides file. Comment bodies are untrusted text: control and formatting
characters are removed and lengths are bounded.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Final

from pydantic import BaseModel, ConfigDict, Field, Strict, TypeAdapter, ValidationError

from aireviewer.config_files import ConfigFileError, load_yaml_document, validation_messages
from aireviewer.contracts.findings import RULE_CATEGORIES, Category, Finding, Severity
from aireviewer.eval.adjudicate import sanitize_for_terminal
from aireviewer.eval.cases import Case
from aireviewer.eval.errors import EvalInputError

__all__ = [
    "BOT_LOGIN",
    "ConversionError",
    "ConversionResult",
    "Override",
    "build_predictions",
    "convert_comments",
    "load_comment_file",
    "load_overrides",
]

BOT_LOGIN: Final = "coderabbitai[bot]"
MAX_COMMENT_FILE_BYTES: Final = 32 * 1024 * 1024
MAX_OVERRIDES_BYTES: Final = 1024 * 1024
TITLE_CHARS: Final = 120
EXPLANATION_CHARS: Final = 2000
EXCERPT_CHARS: Final = 500
PRODUCER: Final = {
    "engine": "coderabbit",
    "source": "github pull request review comments",
    "scope": "top-level inline comments by coderabbitai[bot]",
}

_MARKER_LINE: Final = re.compile(r"^_[^_\n]+_(?:\s*\|\s*_[^_\n]+_)*$")
_BOLD_LINE: Final = re.compile(r"^\*\*(.+?)\*\*[.:]?$")
_DETAILS: Final = re.compile(r"<details>.*?</details>", re.DOTALL | re.IGNORECASE)
_HTML_COMMENT: Final = re.compile(r"<!--.*?-->", re.DOTALL)
_SEVERITY_WORDS: Final = (
    ("critical", Severity.CRITICAL),
    ("major", Severity.HIGH),
    ("minor", Severity.MEDIUM),
    ("trivial", Severity.LOW),
    ("info", Severity.INFO),
)


class ConversionError(EvalInputError):
    pass


@dataclass(frozen=True, slots=True)
class Override:
    category: Category | None = None
    severity: Severity | None = None
    rule_id: str | None = None


class _OverrideEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: Annotated[int, Strict(), Field(ge=1)]
    category: Category | None = None
    severity: Severity | None = None
    rule_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,99}$")] | None = None


_OVERRIDES: Final = TypeAdapter(list[_OverrideEntry])


@dataclass(frozen=True, slots=True)
class ConversionResult:
    findings: tuple[Finding, ...]
    skipped: Mapping[str, int]  # reason -> count


def load_overrides(path: Path) -> dict[int, Override]:
    """Overrides file: a YAML list of {id, category?, severity?, rule_id?}."""
    try:
        document = load_yaml_document(
            path.read_text(encoding="utf-8"), max_bytes=MAX_OVERRIDES_BYTES, what="overrides file"
        )
        entries = _OVERRIDES.validate_python(document if document is not None else [])
    except ConfigFileError as exc:
        raise EvalInputError(*(f"{path.name}: {m}" for m in exc.messages)) from None
    except ValidationError as exc:
        messages = validation_messages(exc, top_level="overrides")
        raise EvalInputError(*(f"{path.name}: {m}" for m in messages)) from None
    duplicates = sorted(n for n, c in Counter(e.id for e in entries).items() if c > 1)
    if duplicates:
        raise EvalInputError(f"{path.name}: duplicate comment ids {duplicates}")
    return {e.id: Override(e.category, e.severity, e.rule_id) for e in entries}


def load_comment_file(path: Path) -> list[dict[str, Any]]:
    """Comments from one exported file; concatenated JSON arrays (pages) are merged."""
    if path.stat().st_size > MAX_COMMENT_FILE_BYTES:
        raise EvalInputError(f"{path.name}: larger than {MAX_COMMENT_FILE_BYTES} bytes")
    text = path.read_text(encoding="utf-8")
    decoder = json.JSONDecoder()
    comments: list[dict[str, Any]] = []
    position = 0
    while True:
        while position < len(text) and text[position].isspace():
            position += 1
        if position == len(text):
            return comments
        try:
            page, position = decoder.raw_decode(text, position)
        except json.JSONDecodeError as exc:
            raise EvalInputError(f"{path.name}: invalid JSON at character {exc.pos}") from None
        if not isinstance(page, list) or not all(isinstance(c, dict) for c in page):
            raise EvalInputError(f"{path.name}: expected JSON arrays of comment objects")
        comments += page


def convert_comments(
    case: Case, comments: Sequence[Mapping[str, Any]], overrides: Mapping[int, Override]
) -> ConversionResult:
    skipped: Counter[str] = Counter()
    keyed: list[tuple[tuple[object, ...], Finding]] = []
    for comment in comments:
        user = comment.get("user") or {}
        if user.get("login") != BOT_LOGIN:
            skipped["not_coderabbit"] += 1
        elif comment.get("in_reply_to_id") is not None:
            skipped["reply"] += 1
        elif comment.get("subject_type") == "file" or (
            comment.get("line") is None and comment.get("original_line") is None
        ):
            skipped["file_level"] += 1
        else:
            finding = _finding(case, comment, overrides)
            location = finding.location
            order = (location.path, location.start_line, location.end_line, comment.get("id"))
            keyed.append((order, finding))
    keyed.sort(key=lambda item: item[0])
    return ConversionResult(tuple(f for _, f in keyed), dict(sorted(skipped.items())))


def build_predictions(
    cases: Sequence[Case], comments_dir: Path, overrides: Mapping[int, Override]
) -> tuple[dict[str, Any], dict[str, dict[str, int]]]:
    """The predictions document for `cases` and per-case conversion counts."""
    files = {p.stem: p for p in comments_dir.glob("*.json")} if comments_dir.is_dir() else {}
    ids = {c.id for c in cases}
    problems = [
        f"{comments_dir / f'{c.id}.json'}: missing (export CodeRabbit's comments for this case)"
        for c in cases
        if c.id not in files
    ]
    problems += [
        f"{files[name].name}: no such case among the selected cases ({name})"
        for name in sorted(set(files) - ids)
    ]
    if problems:
        raise EvalInputError(*problems)
    document_cases: dict[str, list[Any]] = {}
    stats: dict[str, dict[str, int]] = {}
    seen_ids: set[int] = set()
    for case in cases:
        comments = load_comment_file(files[case.id])
        seen_ids |= {c["id"] for c in comments if isinstance(c.get("id"), int)}
        result = convert_comments(case, comments, overrides)
        document_cases[case.id] = [f.model_dump(mode="json") for f in result.findings]
        stats[case.id] = {"findings": len(result.findings), **result.skipped}
    unused = sorted(set(overrides) - seen_ids)
    if unused:
        raise EvalInputError(f"overrides: comment ids not found in any export: {unused}")
    return {"version": 1, "producer": dict(PRODUCER), "cases": document_cases}, stats


# --- one comment --------------------------------------------------------------------------------


def _finding(case: Case, comment: Mapping[str, Any], overrides: Mapping[int, Override]) -> Finding:
    comment_id = comment.get("id")
    commit = comment.get("original_commit_id") or comment.get("commit_id")
    if commit != case.bundle_head_sha:
        raise ConversionError(
            f"case {case.id}: comment {comment_id} was made on commit {str(commit)[:12]}, not "
            f"on the case's bundle_head_sha {case.bundle_head_sha[:12]}; the sandbox PR does "
            "not match the bundle"
        )
    end = _line_number(comment.get("line") or comment.get("original_line"), comment_id)
    start = _line_number(
        comment.get("start_line") or comment.get("original_start_line") or end, comment_id
    )
    start, end = min(start, end), max(start, end)
    side = comment.get("side") or "RIGHT"
    path = str(comment.get("path", ""))
    markers, title, explanation = _parse_body(str(comment.get("body") or ""))
    category, severity, rule_id = _classify(markers)
    override = overrides.get(comment_id) if isinstance(comment_id, int) else None
    if override is not None:
        category, severity, rule_id = _apply(override, category, severity, rule_id)
    data = {
        "source": "llm",
        "category": category,
        "rule_id": rule_id,
        "severity": severity,
        "title": title or f"CodeRabbit comment {comment_id}",
        "location": {"path": path, "start_line": start, "end_line": end, "side": side},
        "evidence": [
            {"path": path, "line": end, "side": side, "excerpt": _excerpt(comment.get("diff_hunk"))}
        ],
        "explanation": explanation or title or "(no explanation provided)",
        "channel": "inline",
        "tool_payload": {"coderabbit_comment_id": comment_id, "markers": list(markers)},
    }
    try:
        return Finding.model_validate(data)
    except ValidationError as exc:
        messages = validation_messages(exc, top_level="comment")
        raise ConversionError(
            *(f"case {case.id}: comment {comment_id}: {m}" for m in messages)
        ) from None


def _line_number(value: object, comment_id: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ConversionError(f"comment {comment_id}: line numbers must be positive integers")
    return value


def _parse_body(body: str) -> tuple[tuple[str, ...], str, str]:
    """(markers, title, explanation) of a comment body."""
    text = _HTML_COMMENT.sub("", _DETAILS.sub("", sanitize_for_terminal(body)))
    lines = [line.strip() for line in text.splitlines()]
    markers: tuple[str, ...] = ()
    content = [line for line in lines if line]
    if content and _MARKER_LINE.match(content[0]):
        markers = tuple(part.strip().strip("_").strip() for part in content[0].split("|"))
        content = content[1:]
    title_index = next((i for i, line in enumerate(content) if _BOLD_LINE.match(line)), None)
    if title_index is None:
        title_index = 0 if content else None
    title = _plain(content[title_index]) if title_index is not None else ""
    rest = [line for i, line in enumerate(content) if i != title_index]
    explanation = "\n".join(rest)[:EXPLANATION_CHARS].strip()
    return markers, _shorten(title, TITLE_CHARS), explanation


def _plain(line: str) -> str:
    text = line.lstrip("#").strip()
    for token in ("**", "__", "`"):
        text = text.replace(token, "")
    return " ".join(text.split())


def _shorten(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0] or text[: limit - 1]
    return cut.rstrip() + "…"


def _classify(markers: Sequence[str]) -> tuple[Category, Severity, str | None]:
    joined = " ".join(markers).lower()
    if "nitpick" in joined:
        category, severity, rule_id = Category.LINT, Severity.LOW, "coderabbit.nitpick"
    elif "refactor" in joined:
        category, severity, rule_id = (
            Category.MAINTAINABILITY,
            Severity.MEDIUM,
            "coderabbit.refactor",
        )
    else:
        category, severity, rule_id = Category.CORRECTNESS, Severity.MEDIUM, None
    for word, marked in _SEVERITY_WORDS:
        if re.search(rf"\b{word}\b", joined):
            severity = marked
            break
    return category, severity, rule_id


def _apply(
    override: Override, category: Category, severity: Severity, rule_id: str | None
) -> tuple[Category, Severity, str | None]:
    new_category = override.category or category
    new_severity = override.severity or severity
    if override.rule_id is not None:
        new_rule = override.rule_id
    elif new_category not in RULE_CATEGORIES:
        new_rule = None
    elif new_category == category and rule_id is not None:
        new_rule = rule_id
    else:
        new_rule = f"coderabbit.{new_category.value}"
    return new_category, new_severity, new_rule


def _excerpt(diff_hunk: object) -> str:
    """The commented line: the last line of the diff hunk, without its +/-/space prefix."""
    if not isinstance(diff_hunk, str):
        return ""
    lines = [line for line in diff_hunk.splitlines() if line and not line.startswith(("@@", "\\"))]
    if not lines:
        return ""
    last = lines[-1]
    if last[0] in "+- ":
        last = last[1:]
    return sanitize_for_terminal(last).strip()[:EXCERPT_CHARS]
