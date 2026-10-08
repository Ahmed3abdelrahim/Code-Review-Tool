"""Coverage: what the run reviewed and what it did not (failure honesty).

Every changed file appears once, either reviewed or with exactly one skip reason (T1.7).
Gaps record partial coverage by a tool or pass (T2.1, T3.6, T4.1). Which skips make a run
`partial` is decided by T1.7.
"""

from __future__ import annotations

from collections import Counter
from enum import StrEnum
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt, model_validator

_CONTRACT = ConfigDict(extra="forbid", validate_assignment=True)
NonEmpty = Annotated[str, Field(min_length=1)]


class ChangeType(StrEnum):
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"
    COPIED = "copied"


class Language(StrEnum):
    PYTHON = "python"
    TYPESCRIPT = "typescript"


class SkipReason(StrEnum):
    UNSUPPORTED_LANGUAGE = "unsupported_language"
    GENERATED = "generated"
    EXCLUDED_BY_POLICY = "excluded_by_policy"
    BINARY = "binary"
    TOO_LARGE = "too_large"
    OVER_FILE_BUDGET = "over_file_budget"
    OVER_LINE_BUDGET = "over_line_budget"


_NEEDS_OLD_PATH = frozenset({ChangeType.RENAMED, ChangeType.COPIED})


class FileCoverage(BaseModel):
    model_config = _CONTRACT

    path: NonEmpty
    old_path: NonEmpty | None = None  # set for renamed and copied files only
    change_type: ChangeType
    language: Language | None  # None: unsupported
    added: NonNegativeInt
    deleted: NonNegativeInt
    reviewed: bool
    skip_reason: SkipReason | None = None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.reviewed == (self.skip_reason is not None):
            raise ValueError("exactly one of reviewed=true or a skip_reason is required")
        if (self.old_path is not None) != (self.change_type in _NEEDS_OLD_PATH):
            raise ValueError("old_path is required for renamed/copied files and only for them")
        return self


class CoverageGap(BaseModel):
    model_config = _CONTRACT

    component: NonEmpty  # e.g. "ruff", "llm:security", "depgraph"
    reason: NonEmpty
    path: NonEmpty | None = None  # None: the gap applies to the whole run


class RunCoverage(BaseModel):
    model_config = _CONTRACT

    files: list[FileCoverage] = []
    gaps: list[CoverageGap] = []

    @model_validator(mode="after")
    def _unique_paths(self) -> Self:
        duplicates = sorted(p for p, n in Counter(f.path for f in self.files).items() if n > 1)
        if duplicates:
            raise ValueError(f"each changed file must appear once; duplicated: {duplicates}")
        return self

    @property
    def reviewed_count(self) -> int:
        return sum(1 for f in self.files if f.reviewed)

    @property
    def skipped(self) -> list[FileCoverage]:
        return [f for f in self.files if not f.reviewed]
