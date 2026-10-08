"""Repository policy `.ai-review.yml`, schema v1 (plan section 5.3, tightened by D19).

The models have no defaults for the policy's sections: `policy/default_policy.yml` is the
only source of default values, and a repository's file is merged over it before
validation. Validation error messages never repeat the offending value (it comes from the
repository and ends up in the PR summary); they name the key and the rule instead.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable
from enum import StrEnum
from typing import Annotated, Final, Literal

import regex
from pathspec import PathSpec, Pattern
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, Strict, field_validator

from aireviewer.contracts.coverage import Language
from aireviewer.contracts.findings import Category, Severity

__all__ = [
    "MAX_DETECTOR_LENGTH",
    "MAX_GLOB_LENGTH",
    "POLICY_SCHEMA_VERSION",
    "ArchitecturePolicy",
    "Budgets",
    "CheckRunPolicy",
    "ComplexityPolicy",
    "Convention",
    "CyclesPolicy",
    "DuplicationPolicy",
    "ForbiddenRule",
    "Layer",
    "LintPolicy",
    "Policy",
    "PythonArchitecture",
    "PythonLint",
    "ReviewPolicy",
    "TypeScriptArchitecture",
    "TypeScriptLint",
    "compile_globs",
]

POLICY_SCHEMA_VERSION: Final = 1
MAX_GLOB_LENGTH: Final = 256
MAX_DETECTOR_LENGTH: Final = 500
EXTERNAL_PREFIX: Final = "ext:"

_GLOB_FLAVOR: Final = "gitignore"  # pathspec's gitignore-style wildmatch; T1.7 matches with it
_GLOB_CHARS: Final = frozenset("*?[")

# Only the YAML spelling of a key is accepted (`from`, not `from_`); dumps use it too.
_CONTRACT = ConfigDict(
    extra="forbid",
    frozen=True,
    validate_by_alias=True,
    validate_by_name=False,
    serialize_by_alias=True,
)


# --- value checks ---------------------------------------------------------------------------


def _has_control_chars(value: str) -> bool:
    return any(unicodedata.category(c) in ("Cc", "Cs") for c in value)


def _check_repo_path_syntax(value: str, what: str) -> None:
    if not value:
        raise ValueError(f"{what} must not be empty")
    if len(value) > MAX_GLOB_LENGTH:
        raise ValueError(f"{what} must be at most {MAX_GLOB_LENGTH} characters")
    if _has_control_chars(value):
        raise ValueError(f"{what} must not contain control characters")
    if value.startswith("/"):
        raise ValueError(f"{what} must be relative to the repository root (no leading '/')")
    if "\\" in value:
        raise ValueError(f"{what} must use '/' as separator and must not contain '\\'")
    if ".." in value.split("/"):
        raise ValueError(f"{what} must not contain '..'")


def _check_glob(value: str) -> str:
    _check_repo_path_syntax(value, "glob")
    if value.startswith("!"):
        raise ValueError("glob negation ('!') is not supported")
    try:
        PathSpec.from_lines(_GLOB_FLAVOR, [value])
    except Exception:  # pathspec raises several error types for invalid patterns
        raise ValueError("glob is not a valid pattern") from None
    return value


def _check_relative_path(value: str) -> str:
    _check_repo_path_syntax(value, "path")
    if _GLOB_CHARS & set(value):
        raise ValueError("path must be a plain path, not a glob")
    return value


_EXTERNAL_NAME = regex.compile(r"(?:@[a-z0-9][a-z0-9._-]*/)?[A-Za-z0-9_][A-Za-z0-9._-]*")


def _check_import_target(value: str) -> str:
    if value.startswith(EXTERNAL_PREFIX):
        if not _EXTERNAL_NAME.fullmatch(value.removeprefix(EXTERNAL_PREFIX)):
            raise ValueError(
                "external target must be 'ext:<package>' (for example ext:fastapi, "
                "ext:sqlalchemy.orm or ext:@scope/name)"
            )
        return value
    return _check_glob(value)


def _check_detector(value: str) -> str:
    if not value:
        raise ValueError("detector must not be empty")
    if len(value) > MAX_DETECTOR_LENGTH:
        raise ValueError(f"detector must be at most {MAX_DETECTOR_LENGTH} characters")
    try:
        regex.compile(value)
    except regex.error as exc:
        # str(exc) is the problem and its position ("missing ) at position 4"), never the
        # pattern itself.
        raise ValueError(f"detector is not a valid regular expression ({exc})") from None
    return value


def _check_text(value: str) -> str:
    if _has_control_chars(value):
        raise ValueError("text must not contain control characters")
    return value


def _check_unique[T](values: tuple[T, ...]) -> tuple[T, ...]:
    duplicates = sorted({str(v) for v in values if values.count(v) > 1})
    if duplicates:
        raise ValueError(f"duplicate entries: {', '.join(duplicates)}")
    return values


def _duplicates(names: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    repeated: list[str] = []
    for name in names:
        if name in seen and name not in repeated:
            repeated.append(name)
        seen.add(name)
    return repeated


# --- field types ------------------------------------------------------------------------------

PositiveInt = Annotated[int, Strict(), Field(ge=1)]
NonNegativeInt = Annotated[int, Strict(), Field(ge=0)]
Flag = Annotated[bool, Strict()]
Fraction = Annotated[float, Strict(), Field(ge=0, le=1, allow_inf_nan=False)]

Glob = Annotated[str, AfterValidator(_check_glob), Field(json_schema_extra={"format": "glob"})]
RelativePath = Annotated[
    str, AfterValidator(_check_relative_path), Field(json_schema_extra={"format": "path"})
]
ImportTarget = Annotated[
    str,
    AfterValidator(_check_import_target),
    Field(json_schema_extra={"format": "glob or ext:<package>"}),
]
Detector = Annotated[
    str, AfterValidator(_check_detector), Field(json_schema_extra={"format": "regex"})
]
LayerName = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")]
RuleId = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,99}$")]
PromotedRuleId = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,99}$")]
RuffCode = Annotated[str, Field(pattern=r"^[A-Z]{1,8}[0-9]{0,6}$")]
EslintRule = Annotated[
    str,
    Field(pattern=r"^(?:@[a-z0-9][a-z0-9._-]*/)?[a-z0-9][a-z0-9-]*(?:/[a-z0-9][a-z0-9-]*)?$"),
]
EslintLevel = Literal["off", "warn", "error"]
Description = Annotated[str, AfterValidator(_check_text), Field(min_length=1, max_length=500)]


class EslintPreset(StrEnum):
    RECOMMENDED = "recommended"  # maps to a fixed rule set in policy/generate_eslint.py (T2.2)


# --- models -----------------------------------------------------------------------------------


class Budgets(BaseModel):
    """Per-run limits. The server may lower them to operator limits (T1.7, T3.1)."""

    model_config = _CONTRACT

    max_files: PositiveInt = Field(description="Eligible changed files reviewed per run.")
    max_file_bytes: PositiveInt = Field(description="Larger files are skipped as too_large.")
    max_changed_lines: PositiveInt = Field(description="Changed lines reviewed per run.")
    max_llm_input_tokens: PositiveInt = Field(description="Model input tokens per run.")
    max_llm_calls: PositiveInt = Field(description="Model calls per run.")


class PythonLint(BaseModel):
    model_config = _CONTRACT

    select: tuple[RuffCode, ...] = Field(description="Ruff rule codes or prefixes to enable.")
    ignore: tuple[RuffCode, ...] = Field(description="Ruff rule codes or prefixes to disable.")


class TypeScriptLint(BaseModel):
    model_config = _CONTRACT

    preset: EslintPreset = Field(description="Fixed ESLint rule set.")
    rules: dict[EslintRule, EslintLevel] = Field(
        description="Rule overrides (off, warn or error); rules outside the allowlist are "
        "reported by config generation (T2.2)."
    )


class LintPolicy(BaseModel):
    model_config = _CONTRACT

    python: PythonLint
    typescript: TypeScriptLint


class ComplexityPolicy(BaseModel):
    model_config = _CONTRACT

    max_ccn: PositiveInt = Field(description="Maximum cyclomatic complexity of a function.")
    max_function_lines: PositiveInt = Field(description="Maximum lines of a function.")
    max_params: PositiveInt = Field(description="Maximum parameters of a function.")
    worsen_delta: PositiveInt = Field(
        description="A function already over a limit is flagged only if it worsens by at "
        "least this much."
    )


class DuplicationPolicy(BaseModel):
    model_config = _CONTRACT

    enabled: Flag = Field(description="Report duplicated code.")
    min_tokens: PositiveInt = Field(description="Smallest duplicate reported, in tokens.")


class PythonArchitecture(BaseModel):
    model_config = _CONTRACT

    source_roots: Annotated[tuple[RelativePath, ...], Field(min_length=1)] | None = Field(
        default=None, description="Import roots; null means auto-detect."
    )


class TypeScriptArchitecture(BaseModel):
    model_config = _CONTRACT

    tsconfig: RelativePath = Field(description="tsconfig file, read as JSONC, never executed.")


class Layer(BaseModel):
    model_config = _CONTRACT

    name: LayerName = Field(description="Unique layer name.")
    paths: Annotated[tuple[Glob, ...], Field(min_length=1)] = Field(
        description="Files that belong to the layer."
    )
    may_import: tuple[LayerName, ...] = Field(
        default=(), description="Layers this layer may import; each must be defined."
    )


class ForbiddenRule(BaseModel):
    model_config = _CONTRACT

    id: RuleId = Field(description="Unique rule ID, shown on findings.")
    from_: Annotated[tuple[Glob, ...], Field(min_length=1)] = Field(
        alias="from", description="Importing files."
    )
    to: Annotated[tuple[ImportTarget, ...], Field(min_length=1)] = Field(
        description="Forbidden targets: globs of repository files or ext:<package>."
    )
    severity: Severity = Field(default=Severity.MEDIUM, description="Severity of findings.")


class CyclesPolicy(BaseModel):
    model_config = _CONTRACT

    enabled: Flag = Field(description="Report new dependency cycles.")


class ArchitecturePolicy(BaseModel):
    model_config = _CONTRACT

    python: PythonArchitecture
    typescript: TypeScriptArchitecture
    layers: tuple[Layer, ...] = Field(description="Layer rules (repository-specific).")
    forbidden: tuple[ForbiddenRule, ...] = Field(description="Forbidden dependencies.")
    cycles: CyclesPolicy
    drift_threshold: Fraction = Field(
        description="A rule is enforced only if at least this share of existing edges follows it."
    )

    @field_validator("layers")
    @classmethod
    def _layers_consistent(cls, layers: tuple[Layer, ...]) -> tuple[Layer, ...]:
        problems = [f"duplicate layer name '{n}'" for n in _duplicates(x.name for x in layers)]
        defined = {x.name for x in layers}
        problems += [
            f"layer '{x.name}' may import unknown layer '{target}'"
            for x in layers
            for target in x.may_import
            if target not in defined
        ]
        if problems:
            raise ValueError("; ".join(problems))
        return layers

    @field_validator("forbidden")
    @classmethod
    def _forbidden_ids_unique(cls, rules: tuple[ForbiddenRule, ...]) -> tuple[ForbiddenRule, ...]:
        if duplicates := _duplicates(r.id for r in rules):
            raise ValueError("; ".join(f"duplicate forbidden rule id '{d}'" for d in duplicates))
        return rules


class Convention(BaseModel):
    model_config = _CONTRACT

    id: RuleId = Field(description="Unique convention ID, shown on findings.")
    description: Description = Field(description="The rule, as the reviewer should apply it.")
    paths: Annotated[tuple[Glob, ...], Field(min_length=1)] = Field(
        default=("**",), description="Files the convention applies to."
    )
    severity: Severity = Field(default=Severity.MEDIUM, description="Severity of findings.")
    detector: Detector | None = Field(
        default=None,
        description="Optional regex pre-filter; findings must match it. Searched with a timeout.",
    )


class CheckRunPolicy(BaseModel):
    model_config = _CONTRACT

    fail_on_tool_error: Flag = Field(description="Fail the check run when a tool fails.")


class ReviewPolicy(BaseModel):
    model_config = _CONTRACT

    categories: Annotated[
        tuple[Category, ...], Field(min_length=1), AfterValidator(_check_unique)
    ] = Field(description="Finding categories to report, without duplicates.")
    inline_cap: NonNegativeInt = Field(description="Maximum inline comments per run.")
    min_inline_severity: Severity = Field(description="Lowest severity posted inline.")
    promote_inline: tuple[PromotedRuleId, ...] = Field(
        description="Rule IDs proven precise enough for inline comments (design and "
        "maintainability)."
    )
    skip_drafts: Flag = Field(description="Do not review draft pull requests.")
    check_run: CheckRunPolicy


class Policy(BaseModel):
    """The effective policy of a run: defaults merged with the repository's file."""

    model_config = _CONTRACT

    version: Literal[1] = Field(description="Policy schema version.")
    languages: Annotated[
        tuple[Language, ...], Field(min_length=1), AfterValidator(_check_unique)
    ] = Field(description="Languages to review, without duplicates.")
    exclude_paths: tuple[Glob, ...] = Field(description="Files never reviewed.")
    budgets: Budgets
    lint: LintPolicy
    complexity: ComplexityPolicy
    duplication: DuplicationPolicy
    architecture: ArchitecturePolicy
    conventions: tuple[Convention, ...] = Field(
        description="Repository conventions checked by the convention pass."
    )
    review: ReviewPolicy

    @field_validator("conventions")
    @classmethod
    def _convention_ids_unique(cls, conventions: tuple[Convention, ...]) -> tuple[Convention, ...]:
        if duplicates := _duplicates(c.id for c in conventions):
            raise ValueError("; ".join(f"duplicate convention id '{d}'" for d in duplicates))
        return conventions


def compile_globs(patterns: Iterable[str]) -> PathSpec[Pattern]:
    """Compile policy globs with the engine validation uses (gitignore-style wildmatch)."""
    return PathSpec.from_lines(_GLOB_FLAVOR, patterns)
