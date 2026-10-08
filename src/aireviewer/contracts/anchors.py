"""Anchor IDs (plan section 5.2): what the model cites instead of paths and line numbers.

Grammar (canonical: no leading zeros, ASCII digits, 1..999,999,999):
  F{file}:H{hunk}:+{new_line}   added line, RIGHT, commentable
  F{file}:H{hunk}:-{old_line}   deleted line, LEFT, commentable
  F{file}:H{hunk}:={new_line}   context line, RIGHT, evidence only
  C{snippet}:{new_line}         context snippet outside the diff, evidence only

Resolving IDs against a diff is the AnchorMap's job (snapshot/anchors.py, T1.6).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from aireviewer.errors import MalformedAnchorId

MAX_NUMBER: Final = 999_999_999
_N: Final = r"[1-9][0-9]{0,8}"  # [0-9], not \d: other Unicode digits are not digits here
_DIFF_RE: Final = re.compile(rf"F({_N}):H({_N}):([-+=])({_N})")
_CONTEXT_RE: Final = re.compile(rf"C({_N}):({_N})")

# Anchored patterns for pydantic fields; they also show the grammar in the JSON Schema.
DIFF_ANCHOR_PATTERN: Final = rf"^F{_N}:H{_N}:[-+=]{_N}$"
ANCHOR_PATTERN: Final = rf"^(?:F{_N}:H{_N}:[-+=]{_N}|C{_N}:{_N})$"
_PREVIEW_CHARS: Final = 64


class Side(StrEnum):
    LEFT = "LEFT"
    RIGHT = "RIGHT"


class LineKind(StrEnum):
    ADDED = "+"
    DELETED = "-"
    CONTEXT = "="


def _check_number(name: str, value: int) -> None:
    if not 1 <= value <= MAX_NUMBER:
        raise MalformedAnchorId(f"anchor {name} must be between 1 and {MAX_NUMBER}")


@dataclass(frozen=True, slots=True)
class DiffAnchor:
    file: int
    hunk: int
    kind: LineKind
    line: int

    def __post_init__(self) -> None:
        for name in ("file", "hunk", "line"):
            _check_number(name, getattr(self, name))

    @property
    def side(self) -> Side:
        return Side.LEFT if self.kind is LineKind.DELETED else Side.RIGHT

    @property
    def is_commentable(self) -> bool:
        """Only added and deleted lines take inline comments (D6)."""
        return self.kind is not LineKind.CONTEXT


@dataclass(frozen=True, slots=True)
class ContextAnchor:
    snippet: int
    line: int

    def __post_init__(self) -> None:
        _check_number("snippet", self.snippet)
        _check_number("line", self.line)


type Anchor = DiffAnchor | ContextAnchor


def format_anchor(anchor: Anchor) -> str:
    match anchor:
        case DiffAnchor(file=file, hunk=hunk, kind=kind, line=line):
            return f"F{file}:H{hunk}:{kind.value}{line}"
        case ContextAnchor(snippet=snippet, line=line):
            return f"C{snippet}:{line}"


def parse_anchor(text: str) -> Anchor:
    if match := _DIFF_RE.fullmatch(text):
        file, hunk, kind, line = match.groups()
        return DiffAnchor(int(file), int(hunk), LineKind(kind), int(line))
    if match := _CONTEXT_RE.fullmatch(text):
        snippet, line = match.groups()
        return ContextAnchor(int(snippet), int(line))
    raise MalformedAnchorId(f"malformed anchor ID {_preview(text)}")


def _preview(text: str) -> str:
    """Bounded repr: anchor IDs come from model output."""
    if len(text) <= _PREVIEW_CHARS:
        return repr(text)
    return repr(text[:_PREVIEW_CHARS]) + f"... ({len(text)} chars)"
