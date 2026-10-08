"""Benchmark case files `eval/cases/<id>.yaml` (plan section 8.1, D20).

Errors name the file, the case and the field:
`cases/py-orders-001.yaml (py-orders-001): labels[0].lines: start must not be after end`.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Final, Literal
from urllib.parse import urlsplit

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    Strict,
    ValidationError,
    ValidationInfo,
    field_validator,
)

from aireviewer.config_files import ConfigFileError, load_yaml_mapping, validation_messages
from aireviewer.contracts.anchors import Side
from aireviewer.contracts.coverage import Language
from aireviewer.contracts.findings import Category, Severity
from aireviewer.policy.loader import PolicySource, load_policy

__all__ = [
    "ALLOWED_LICENSES",
    "CASE_ID_PATTERN",
    "MAX_CASE_BYTES",
    "Case",
    "CaseKind",
    "CaseSet",
    "Label",
    "Provenance",
    "Split",
    "load_cases",
    "select_split",
]

CASE_ID_PATTERN: Final = r"^[a-z0-9][a-z0-9-]{2,63}$"
MAX_CASE_BYTES: Final = 256 * 1024
CASES_DIR: Final = "cases"

# Section 8.2(4): permissively licensed repositories only, plus your own ("own").
ALLOWED_LICENSES: Final = frozenset(
    {
        "MIT",
        "Apache-2.0",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "ISC",
        "0BSD",
        "Zlib",
        "PSF-2.0",
        "Unlicense",
        "CC0-1.0",
        "own",
    }
)

_CONTRACT = ConfigDict(extra="forbid", frozen=True, validate_by_alias=True, validate_by_name=False)


class Split(StrEnum):
    DEV = "dev"
    HOLDOUT = "holdout"


class CaseKind(StrEnum):
    DEFECT = "defect"
    CLEAN = "clean"
    DESIGN = "design"
    INJECTION = "injection"


class Provenance(StrEnum):
    HAND_LABELED = "hand-labeled"
    PLANTED = "planted"  # D21: a bug planted in a seed tree under eval/seeds/
    REVIEW_COMMENT_MINING = "review-comment-mining"
    SZZ = "szz"


# --- value checks ---------------------------------------------------------------------------


def _check_plain_text(value: str) -> str:
    if any(unicodedata.category(c) in ("Cc", "Cs") for c in value if c not in "\n\t"):
        raise ValueError("must not contain control characters")
    return value


def _check_repo_path(value: str) -> str:
    """A repository-relative POSIX path (labels, renames)."""
    if not value:
        raise ValueError("path must not be empty")
    if value.startswith("/") or "\\" in value:
        raise ValueError("path must be repository-relative and use '/'")
    if ".." in value.split("/"):
        raise ValueError("path must not contain '..'")
    _check_plain_text(value)
    if "\n" in value or "\t" in value:
        raise ValueError("must not contain control characters")
    return value


def _check_eval_path(value: str) -> str:
    """A path relative to the eval directory (bundle, policy); existence is checked later."""
    if not value:
        raise ValueError("path must not be empty")
    if value.startswith("/") or Path(value).is_absolute():
        raise ValueError("path must be relative to the eval directory")
    if "\\" in value or ".." in value.split("/"):
        raise ValueError("path must stay inside the eval directory (no '..' or '\\')")
    return value


def _check_https_url(value: str) -> str:
    parts = urlsplit(value)
    if parts.scheme != "https" or not parts.hostname:
        raise ValueError("repo must be an https:// URL")
    if parts.username is not None or parts.password is not None:
        raise ValueError("repo URL must not contain credentials")
    if parts.query or parts.fragment:
        raise ValueError("repo URL must not have a query or fragment")
    return value


def _sha_must_be_text(value: object) -> object:
    if not isinstance(value, str):
        raise ValueError("must be a quoted string of 40 or 64 hex characters")
    return value


Sha = Annotated[
    str,
    BeforeValidator(_sha_must_be_text),
    Field(pattern=r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$"),
]
RepoPath = Annotated[str, AfterValidator(_check_repo_path)]
EvalPath = Annotated[str, AfterValidator(_check_eval_path)]
PositiveInt = Annotated[int, Strict(), Field(ge=1)]
Text = Annotated[str, AfterValidator(_check_plain_text)]


# --- models ---------------------------------------------------------------------------------


class CaseSource(BaseModel):
    model_config = _CONTRACT

    repo: Annotated[str, AfterValidator(_check_https_url)]
    license: str
    pr: PositiveInt | None = None
    # Upstream provenance; planted cases have no upstream commits (D21).
    base_sha: Sha | None = None
    head_sha: Sha | None = None

    @field_validator("license")
    @classmethod
    def _permissive(cls, value: str) -> str:
        if value not in ALLOWED_LICENSES:
            raise ValueError(
                "license must be one of " + ", ".join(sorted(ALLOWED_LICENSES, key=str.lower))
            )
        return value


class Label(BaseModel):
    model_config = _CONTRACT

    id: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$")]
    category: Category
    severity: Severity
    path: RepoPath
    side: Side = Side.RIGHT
    lines: tuple[PositiveInt, PositiveInt]
    description: Annotated[Text, Field(min_length=1, max_length=1000)]
    must_find: Annotated[bool, Strict()] = False

    @field_validator("lines")
    @classmethod
    def _ordered(cls, lines: tuple[int, int]) -> tuple[int, int]:
        if lines[0] > lines[1]:
            raise ValueError("start must not be after end")
        return lines


class Rename(BaseModel):
    model_config = _CONTRACT

    from_: RepoPath = Field(alias="from")
    to: RepoPath


class Expect(BaseModel):
    model_config = _CONTRACT

    max_inline: Annotated[int, Strict(), Field(ge=0)] | None = None


class Case(BaseModel):
    model_config = _CONTRACT

    id: Annotated[str, Field(pattern=CASE_ID_PATTERN)]
    split: Split
    kind: CaseKind
    language: Language
    provenance: Provenance  # before source: the source rules depend on it
    source: CaseSource
    bundle: EvalPath
    # The two snapshot commits in the bundle (D21); upstream SHAs stay in `source`.
    bundle_base_sha: Sha
    bundle_head_sha: Sha
    policy: EvalPath
    labels: tuple[Label, ...] = Field(default=(), validate_default=True)  # kind rules apply
    renames: tuple[Rename, ...] = ()  # D20: makes matching rename-aware offline
    expect: Expect = Expect()
    notes: Annotated[Text, Field(max_length=5000)] = ""

    @field_validator("source")
    @classmethod
    def _upstream_shas(cls, source: CaseSource, info: ValidationInfo) -> CaseSource:
        provenance = info.data.get("provenance")
        if provenance is None or provenance is Provenance.PLANTED:
            return source
        missing = [name for name in ("base_sha", "head_sha") if getattr(source, name) is None]
        if missing:
            raise ValueError(
                f"{' and '.join(missing)} required (upstream commits) unless provenance is planted"
            )
        return source

    @field_validator("bundle_head_sha")
    @classmethod
    def _snapshots_differ(cls, head: str, info: ValidationInfo) -> str:
        if head == info.data.get("bundle_base_sha"):
            raise ValueError("must differ from bundle_base_sha")
        return head

    @field_validator("labels")
    @classmethod
    def _labels_consistent(
        cls, labels: tuple[Label, ...], info: ValidationInfo
    ) -> tuple[Label, ...]:
        seen: set[str] = set()
        for label in labels:
            if label.id in seen:
                raise ValueError(f"duplicate label id '{label.id}'")
            seen.add(label.id)
        kind = info.data.get("kind")  # absent when kind itself is invalid
        if kind is CaseKind.CLEAN and labels:
            raise ValueError("a clean case must not have labels")
        if kind in (CaseKind.DEFECT, CaseKind.INJECTION) and not labels:
            raise ValueError(f"a {kind} case needs at least one label")
        if kind is CaseKind.DESIGN and not any(x.category is Category.DESIGN for x in labels):
            raise ValueError("a design case needs at least one design label")
        return labels

    @field_validator("renames")
    @classmethod
    def _renames_consistent(cls, renames: tuple[Rename, ...]) -> tuple[Rename, ...]:
        sources: set[str] = set()
        for rename in renames:
            if rename.from_ == rename.to:
                raise ValueError(f"rename of {rename.from_} must change the path")
            if rename.from_ in sources:
                raise ValueError(f"{rename.from_} is renamed more than once")
            sources.add(rename.from_)
        return renames

    def canonical_path(self, path: str) -> str:
        """The head path of a file, following the case's renames."""
        for rename in self.renames:
            if rename.from_ == path:
                return rename.to
        return path


# --- loading --------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CaseSet:
    cases: tuple[Case, ...]
    errors: tuple[str, ...]


def load_cases(eval_dir: Path) -> CaseSet:
    """Load and validate every `cases/*.yaml`; collect all errors instead of stopping."""
    cases_dir = eval_dir / CASES_DIR
    if not cases_dir.is_dir():
        return CaseSet((), (f"{CASES_DIR}/: directory not found in {eval_dir}",))
    cases: list[Case] = []
    errors: list[str] = []
    files = sorted(p for p in cases_dir.iterdir() if p.suffix in (".yaml", ".yml"))
    policy_errors: dict[Path, tuple[str, ...]] = {}
    for path in files:
        case, file_errors = _load_case(path, eval_dir, policy_errors)
        errors += file_errors
        if case is not None and not file_errors:
            cases.append(case)
    errors += _cross_case_errors(cases)
    return CaseSet(tuple(cases), tuple(errors))


def select_split(cases: Sequence[Case], split: Literal["dev", "holdout", "all"]) -> list[Case]:
    if split == "all":
        return list(cases)
    return [c for c in cases if c.split.value == split]


def _load_case(
    path: Path, eval_dir: Path, policy_errors: dict[Path, tuple[str, ...]]
) -> tuple[Case | None, list[str]]:
    relative = f"{CASES_DIR}/{path.name}"
    try:
        data = load_yaml_mapping(
            path.read_text(encoding="utf-8"), max_bytes=MAX_CASE_BYTES, what="case file"
        )
    except ConfigFileError as exc:
        return None, [f"{relative} ({path.stem}): {m}" for m in exc.messages]
    except (OSError, UnicodeDecodeError) as exc:
        return None, [f"{relative} ({path.stem}): cannot read the file ({type(exc).__name__})"]
    raw_id = data.get("id")
    case_id = raw_id if isinstance(raw_id, str) and raw_id else path.stem
    prefix = f"{relative} ({case_id})"
    try:
        case = Case.model_validate(data)
    except ValidationError as exc:
        return None, [f"{prefix}: {m}" for m in validation_messages(exc, top_level="case")]
    errors = []
    if case.id != path.stem:
        errors.append(f"{prefix}: id: must equal the file name ({path.stem})")
    errors += [f"{prefix}: bundle: {m}" for m in _file_problems(eval_dir, case.bundle)]
    policy_problems = _file_problems(eval_dir, case.policy)
    if not policy_problems:
        policy_problems = list(_policy_problems(eval_dir / case.policy, policy_errors))
    errors += [f"{prefix}: policy: {m}" for m in policy_problems]
    return case, errors


def _file_problems(eval_dir: Path, relative: str) -> list[str]:
    target = eval_dir / relative
    try:
        resolved = target.resolve()
    except OSError:
        return [f"{relative} cannot be resolved"]
    if not resolved.is_relative_to(eval_dir.resolve()):
        return [f"{relative} must stay inside the eval directory"]
    if not target.exists():
        return [f"{relative} does not exist"]
    if not target.is_file():
        return [f"{relative} must be a file"]
    return []


def _policy_problems(path: Path, cache: dict[Path, tuple[str, ...]]) -> tuple[str, ...]:
    if path not in cache:
        result = load_policy(path.read_text(encoding="utf-8"))
        problems = result.errors if result.source is PolicySource.FALLBACK else ()
        cache[path] = tuple(f"{path.name}: {e}" for e in problems)
    return cache[path]


def _normalized_repo(url: str) -> str:
    parts = urlsplit(url)
    path = parts.path.rstrip("/").removesuffix(".git").rstrip("/").lower()
    return f"{(parts.hostname or '').lower()}{path}"


def _cross_case_errors(cases: Sequence[Case]) -> list[str]:
    errors: list[str] = []
    by_repo: dict[str, dict[Split, list[str]]] = {}
    for case in cases:
        by_repo.setdefault(_normalized_repo(case.source.repo), {}).setdefault(
            case.split, []
        ).append(case.id)
    for repo, splits in sorted(by_repo.items()):
        if len(splits) > 1:
            listing = "; ".join(
                f"{split.value}: {', '.join(sorted(ids))}" for split, ids in sorted(splits.items())
            )
            errors.append(
                f"source.repo: {repo} appears in both dev and holdout cases ({listing}); "
                "splits must be repository-disjoint"
            )
    return errors
