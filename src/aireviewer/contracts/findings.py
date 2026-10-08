"""Finding contracts (plan section 5.1, tightened by D17).

`Finding` is the one schema every layer produces. `LLMFindingOut` is the restricted subset
the model may return: it cites anchor IDs and never supplies paths, line numbers, SHAs,
fingerprints, scores or channels (extra fields are forbidden, also in the JSON Schema).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Final, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from aireviewer.contracts.anchors import ANCHOR_PATTERN, DIFF_ANCHOR_PATTERN, Side

__all__ = [
    "RULE_CATEGORIES",
    "Category",
    "Channel",
    "Evidence",
    "EvidenceStrength",
    "Finding",
    "FindingStatus",
    "LLMEvidenceOut",
    "LLMFindingOut",
    "Location",
    "Severity",
    "Side",
    "Source",
]


class Source(StrEnum):
    RUFF = "ruff"
    ESLINT = "eslint"
    LIZARD = "lizard"
    JSCPD = "jscpd"
    SECRETS = "secrets"
    DEPGRAPH = "depgraph"
    LLM = "llm"


class Category(StrEnum):
    LINT = "lint"
    MAINTAINABILITY = "maintainability"
    DESIGN = "design"
    CORRECTNESS = "correctness"
    SECURITY = "security"
    RELIABILITY = "reliability"
    PERFORMANCE = "performance"
    TESTING = "testing"


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EvidenceStrength(StrEnum):
    DETERMINISTIC = "deterministic"  # produced or confirmed by a tool
    VALIDATED = "validated"  # LLM finding whose evidence passed all gates
    MODEL_ONLY = "model_only"  # LLM claim without tool confirmation (never inline by default)


class Channel(StrEnum):
    INLINE = "inline"
    SUMMARY = "summary"
    ANNOTATION = "annotation"
    NONE = "none"


class FindingStatus(StrEnum):
    CANDIDATE = "candidate"
    REJECTED = "rejected"
    VALIDATED = "validated"
    PUBLISHED = "published"
    SUMMARIZED = "summarized"
    SUPPRESSED = "suppressed"
    CARRIED_OVER = "carried_over"
    RESOLVED = "resolved"


RULE_CATEGORIES: Final = frozenset({Category.LINT, Category.MAINTAINABILITY, Category.DESIGN})

AnchorIdStr = Annotated[str, Field(pattern=ANCHOR_PATTERN)]
DiffAnchorIdStr = Annotated[str, Field(pattern=DIFF_ANCHOR_PATTERN)]
RuleId = Annotated[str, Field(min_length=1)]
Title = Annotated[str, Field(min_length=1, max_length=120)]
Explanation = Annotated[str, Field(min_length=1, max_length=2000)]
Suggestion = Annotated[str, Field(max_length=1500)]
ShortText = Annotated[str, Field(max_length=500)]
Excerpt = Annotated[str, Field(max_length=500)]  # must match the snapshot (normalized whitespace)

_CONTRACT = ConfigDict(extra="forbid", validate_assignment=True)


def _require_rule_id(category: Category, rule_id: str | None) -> None:
    if category in RULE_CATEGORIES and rule_id is None:
        raise ValueError(f"rule_id is required for category {category.value!r}")


class Location(BaseModel):
    model_config = _CONTRACT

    path: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    side: Side = Side.RIGHT
    anchor_ids: list[AnchorIdStr] = []  # anchors this location was derived from

    @model_validator(mode="after")
    def _end_not_before_start(self) -> Self:
        if self.end_line < self.start_line:
            raise ValueError("end_line must not be before start_line")
        return self


class Evidence(BaseModel):
    model_config = _CONTRACT

    path: str
    line: int = Field(ge=1)
    side: Side = Side.RIGHT
    excerpt: Excerpt


class Finding(BaseModel):
    model_config = _CONTRACT

    # set by producers
    source: Source
    category: Category
    rule_id: RuleId | None = None  # required for lint, maintainability, design
    severity: Severity
    title: Title
    location: Location
    evidence: list[Evidence] = Field(min_length=1)
    explanation: Explanation
    suggestion: Suggestion | None = None
    trigger: ShortText | None = None  # LLM defect findings: input/condition that causes it
    impact: ShortText | None = None  # LLM defect findings: what goes wrong
    tool_payload: dict[str, JsonValue] = {}  # raw tool fields (code, message, metric values)
    # set by the pipeline, never by the model
    evidence_strength: EvidenceStrength = EvidenceStrength.MODEL_ONLY
    introduced_by_pr: bool = False
    fingerprint: str = ""
    score: float = 0.0
    channel: Channel = Channel.NONE
    status: FindingStatus = FindingStatus.CANDIDATE
    rejection_reason: str | None = None

    @model_validator(mode="after")
    def _rule_id_for_rule_categories(self) -> Self:
        _require_rule_id(self.category, self.rule_id)
        return self


class LLMEvidenceOut(BaseModel):
    """Evidence as the model reports it: an anchor (diff line or context snippet) and the
    excerpt copied from that line."""

    model_config = _CONTRACT

    anchor_id: AnchorIdStr
    excerpt: Excerpt


class LLMFindingOut(BaseModel):
    """What the model may return. The pipeline fills in everything else."""

    model_config = _CONTRACT

    category: Category
    severity: Severity
    title: Title
    anchor_ids: list[DiffAnchorIdStr] = Field(min_length=1, max_length=10)
    evidence: list[LLMEvidenceOut] = Field(min_length=1, max_length=10)
    explanation: Explanation
    suggestion: Suggestion | None = None
    trigger: ShortText | None = None
    impact: ShortText | None = None
    rule_id: RuleId | None = None  # required for lint, maintainability, design

    @model_validator(mode="after")
    def _rule_id_for_rule_categories(self) -> Self:
        _require_rule_id(self.category, self.rule_id)
        return self
