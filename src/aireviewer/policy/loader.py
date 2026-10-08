"""Load the effective policy of a run (plan section 5.3, T0.4, D19).

The repository's `.ai-review.yml` text (from the base commit) is parsed with a hardened
safe loader, deep-merged over the packaged defaults (maps merge; lists, scalars and null
replace) and validated once. A bad file never fails the run: the defaults apply and the
result carries readable errors for the summary.
"""

from __future__ import annotations

import copy
import functools
import hashlib
import json
import math
import re
from collections.abc import Hashable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from importlib import resources
from typing import Any, Final, NoReturn

import yaml
from pydantic import ValidationError

from aireviewer.contracts.policy import Policy
from aireviewer.errors import ConfigError
from aireviewer.logging import get_logger

__all__ = [
    "MAX_ERRORS",
    "MAX_POLICY_BYTES",
    "MAX_POLICY_DEPTH",
    "PolicyResult",
    "PolicySource",
    "canonical_json",
    "default_policy",
    "load_policy",
    "merge_policy",
    "policy_version",
]

MAX_POLICY_BYTES: Final = 64 * 1024
MAX_POLICY_DEPTH: Final = 20
MAX_ERRORS: Final = 20
_MAX_KEY_CHARS: Final = 64
_PLAIN_KEY: Final = re.compile(r"[A-Za-z0-9_-]+")
_DEFAULTS_RESOURCE: Final = "default_policy.yml"

_log = get_logger(__name__)


class PolicySource(StrEnum):
    DEFAULT = "default"  # no policy file
    REPO = "repo"  # the repository's file, merged over the defaults
    FALLBACK = "fallback"  # the repository's file was invalid; defaults apply


@dataclass(frozen=True, slots=True)
class PolicyResult:
    effective: Policy
    version: str  # sha256 of the canonical JSON of `effective`, first 16 hex digits
    errors: tuple[str, ...]  # human-readable; empty unless source is FALLBACK
    source: PolicySource


def load_policy(base_file_text: str | None) -> PolicyResult:
    """Return the effective policy. Never raises for any input text."""
    if base_file_text is None:
        return _defaults(PolicySource.DEFAULT, ())
    try:
        effective = _validated(merge_policy(_default_data(), _parse_document(base_file_text)))
    except _PolicyFileError as exc:
        return _defaults(PolicySource.FALLBACK, _bounded(exc.messages))
    except Exception:
        # Safety net for bugs: a policy problem must never fail the run (section 5.3).
        _log.exception("policy_load_internal_error")
        return _defaults(
            PolicySource.FALLBACK,
            ("internal error while reading the policy; defaults were used",),
        )
    return PolicyResult(effective, policy_version(effective), (), PolicySource.REPO)


@functools.cache
def default_policy() -> Policy:
    """The packaged defaults. An invalid defaults file is a bug and fails at startup."""
    text = resources.files(__package__).joinpath(_DEFAULTS_RESOURCE).read_text("utf-8")
    try:
        return _validated(_parse_document(text))
    except _PolicyFileError as exc:
        raise ConfigError(
            f"the built-in {_DEFAULTS_RESOURCE} is invalid: " + "; ".join(exc.messages)
        ) from None


def merge_policy(base: Mapping[str, Any], overlay: Mapping[str, Any]) -> dict[str, Any]:
    """Deep merge: mappings merge key by key; lists, scalars and null replace.

    Returns a new structure that shares no mutable state with the inputs.
    """
    merged: dict[str, Any] = copy.deepcopy(dict(base))
    for key, value in overlay.items():
        current = merged.get(key)
        if isinstance(current, Mapping) and isinstance(value, Mapping):
            merged[key] = merge_policy(current, value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def canonical_json(value: object) -> bytes:
    """Key-order-independent JSON (ASCII-only, so any string can be encoded)."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


def policy_version(policy: Policy) -> str:
    dumped = policy.model_dump(mode="json", by_alias=True)
    return hashlib.sha256(canonical_json(dumped)).hexdigest()[:16]


# --- internals ---------------------------------------------------------------------------


class _PolicyFileError(Exception):
    """The text cannot become a policy; `messages` are safe to show in the summary."""

    def __init__(self, *messages: str) -> None:
        super().__init__(*messages)
        self.messages = messages


def _defaults(source: PolicySource, errors: tuple[str, ...]) -> PolicyResult:
    policy = default_policy()
    return PolicyResult(policy, policy_version(policy), errors, source)


def _default_data() -> dict[str, Any]:
    return default_policy().model_dump(mode="json", by_alias=True)


def _validated(data: dict[str, Any]) -> Policy:
    try:
        return Policy.model_validate(data)
    except ValidationError as exc:
        raise _PolicyFileError(*_validation_messages(exc)) from None


def _parse_document(text: str) -> dict[str, Any]:
    size = len(text.encode("utf-8", errors="surrogatepass"))
    if size > MAX_POLICY_BYTES:
        raise _PolicyFileError(
            f"the policy file is {size} bytes; the limit is {MAX_POLICY_BYTES} bytes"
        )
    try:
        loader = _PolicyLoader(text)  # the reader rejects unprintable characters here
        try:
            document = loader.get_single_data()
        finally:
            loader.dispose()
    except yaml.YAMLError as exc:
        raise _PolicyFileError(_yaml_message(exc)) from None
    if document is None:  # empty or comment-only file
        return {}
    if not isinstance(document, dict):
        raise _PolicyFileError("the top level of the policy file must be a mapping of keys")
    return document


class _YAMLProblem(yaml.MarkedYAMLError):
    def __init__(self, problem: str, mark: yaml.Mark | None) -> None:
        super().__init__(problem=problem, problem_mark=mark)


class _PolicyLoader(yaml.SafeLoader):
    """SafeLoader that only builds JSON-compatible data.

    Rejects aliases (an alias bomb under 64 KiB still makes merging and validation
    exponential), nesting deeper than MAX_POLICY_DEPTH (checked while composing, before a
    RecursionError can happen), duplicate and non-string keys, non-finite floats, and
    every tag outside the JSON-compatible core (python/*, timestamps, binary, sets, local
    tags).
    """

    def __init__(self, stream: str) -> None:
        super().__init__(stream)
        self._depth = 0

    def compose_node(self, parent: yaml.Node | None, index: int) -> yaml.Node | None:
        if self.check_event(yaml.AliasEvent):
            raise _YAMLProblem("YAML aliases (*name) are not supported", self._mark())
        self._depth += 1
        try:
            if self._depth > MAX_POLICY_DEPTH:
                raise _YAMLProblem(
                    f"nesting deeper than {MAX_POLICY_DEPTH} levels is not supported",
                    self._mark(),
                )
            return super().compose_node(parent, index)
        finally:
            self._depth -= 1

    def _mark(self) -> yaml.Mark | None:
        event = self.peek_event()  # type: ignore[no-untyped-call]
        return event.start_mark if event is not None else None

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Hashable, Any]:
        self.flatten_mapping(node)
        seen: set[str] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=True)
            if not isinstance(key, str):
                raise _YAMLProblem(
                    "keys must be strings (quote keys such as on, yes, no, null or numbers)",
                    key_node.start_mark,
                )
            if key in seen:
                raise _YAMLProblem(f"duplicate key {_quote(key)}", key_node.start_mark)
            seen.add(key)
        return super().construct_mapping(node, deep=deep)

    def construct_yaml_float(self, node: yaml.ScalarNode) -> float:
        value = super().construct_yaml_float(node)
        if not math.isfinite(value):
            raise _YAMLProblem("numbers must be finite", node.start_mark)
        return value

    def construct_undefined(self, node: yaml.Node) -> NoReturn:
        raise _YAMLProblem(f"unsupported YAML tag {_tag_name(node.tag)}", node.start_mark)

    def construct_unsupported(self, node: yaml.Node) -> NoReturn:
        kind = _UNSUPPORTED_TYPES[node.tag]
        raise _YAMLProblem(
            f"{kind} values are not supported; quote the value to use it as a string",
            node.start_mark,
        )


_CORE_TAG_PREFIX: Final = "tag:yaml.org,2002:"
_UNSUPPORTED_TYPES: Final = {
    f"{_CORE_TAG_PREFIX}timestamp": "date and time",
    f"{_CORE_TAG_PREFIX}binary": "binary",
    f"{_CORE_TAG_PREFIX}set": "set",
    f"{_CORE_TAG_PREFIX}omap": "ordered map",
    f"{_CORE_TAG_PREFIX}pairs": "pairs",
}


def _tag_name(tag: str) -> str:
    """`!!name` for core-schema tags (how they are written), the full tag otherwise."""
    if tag.startswith(_CORE_TAG_PREFIX):
        tag = "!!" + tag.removeprefix(_CORE_TAG_PREFIX)
    return _quote(tag)


# The base classes registered their own functions; point the tags at the overrides.
_PolicyLoader.add_constructor(f"{_CORE_TAG_PREFIX}float", _PolicyLoader.construct_yaml_float)
for _tag in _UNSUPPORTED_TYPES:
    _PolicyLoader.add_constructor(_tag, _PolicyLoader.construct_unsupported)
_PolicyLoader.add_constructor(None, _PolicyLoader.construct_undefined)  # type: ignore[arg-type]


def _yaml_message(exc: yaml.YAMLError) -> str:
    """Position and problem only; never PyYAML's excerpt of the file."""
    if isinstance(exc, yaml.MarkedYAMLError):
        mark = exc.problem_mark or exc.context_mark
        problem = exc.problem or exc.context or "invalid YAML"
        if exc.context and problem.startswith("but "):  # e.g. "expected X", "but found Y"
            problem = f"{exc.context}, {problem}"
        if mark is None:
            return f"invalid YAML: {problem}"
        return f"invalid YAML at line {mark.line + 1}, column {mark.column + 1}: {problem}"
    if isinstance(exc, yaml.reader.ReaderError):
        return (
            f"invalid YAML at character {exc.position + 1}: "
            "the file contains a character that YAML does not allow"
        )
    return "invalid YAML"


def _quote(key: object) -> str:
    """A key or tag as it appears in an error message: escaped and bounded."""
    text = str(key)
    if _PLAIN_KEY.fullmatch(text) and len(text) <= _MAX_KEY_CHARS:
        return text
    quoted = json.dumps(text[:_MAX_KEY_CHARS], ensure_ascii=True)
    return quoted + ("…" if len(text) > _MAX_KEY_CHARS else "")


def _location(loc: Sequence[int | str]) -> str:
    parts: list[str] = []
    for item in loc:
        if isinstance(item, int):
            parts.append(f"[{item}]")
        elif item == "[key]":
            parts.append(" (key)")
        else:
            parts.append(("." if parts else "") + _quote(item))
    return "".join(parts) or "policy"


_TYPE_MESSAGES: Final = {
    "extra_forbidden": "unknown key",
    "missing": "required",
    "model_type": "must be a mapping",
    "model_attributes_type": "must be a mapping",
    "dict_type": "must be a mapping",
    "tuple_type": "must be a list",
    "list_type": "must be a list",
}


def _validation_messages(exc: ValidationError) -> list[str]:
    errors = exc.errors(include_url=False, include_context=False, include_input=False)
    failed_items = {e["loc"][:-1] for e in errors if e["loc"] and isinstance(e["loc"][-1], int)}
    messages = []
    for error in errors:
        loc = error["loc"]
        if error["type"] == "too_short" and loc in failed_items:
            continue  # pydantic counts only the valid items; the item errors say more
        text = _TYPE_MESSAGES.get(error["type"]) or error["msg"]
        text = text.removeprefix("Value error, ").replace("Tuple should", "List should")
        messages.append(f"{_location(loc)}: {text}")
    return messages


def _bounded(messages: Sequence[str]) -> tuple[str, ...]:
    if len(messages) <= MAX_ERRORS:
        return tuple(messages)
    hidden = len(messages) - MAX_ERRORS
    return (*messages[:MAX_ERRORS], f"… and {hidden} more errors")
