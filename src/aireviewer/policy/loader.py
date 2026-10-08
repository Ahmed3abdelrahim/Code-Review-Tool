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
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from importlib import resources
from typing import Any, Final

from pydantic import ValidationError

from aireviewer.config_files import (
    MAX_YAML_DEPTH,
    ConfigFileError,
    load_yaml_mapping,
    validation_messages,
)
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
MAX_POLICY_DEPTH: Final = MAX_YAML_DEPTH
MAX_ERRORS: Final = 20
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
        raise _PolicyFileError(*validation_messages(exc, top_level="policy")) from None


def _parse_document(text: str) -> dict[str, Any]:
    try:
        return load_yaml_mapping(text, max_bytes=MAX_POLICY_BYTES, what="policy file")
    except ConfigFileError as exc:
        raise _PolicyFileError(*exc.messages) from None


def _bounded(messages: Sequence[str]) -> tuple[str, ...]:
    if len(messages) <= MAX_ERRORS:
        return tuple(messages)
    hidden = len(messages) - MAX_ERRORS
    return (*messages[:MAX_ERRORS], f"… and {hidden} more errors")
