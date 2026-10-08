"""Typed application errors and the run-level error codes (plan section 5.7, D18)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from aireviewer.contracts.run_state import RunEvent, RunStatus


class AIReviewerError(Exception):
    """Base class for all application errors."""


class ConfigError(AIReviewerError):
    """Missing or invalid configuration at startup.

    Not a run outcome, so it has no section 5.7 error code. Messages name environment
    variables, never their values.
    """


class ErrorOutcome(StrEnum):
    """What an error does to the run (D18). NONE: a warning; the status is unchanged."""

    NONE = "none"
    PARTIAL = "partial"
    FAILED = "failed"
    SUPERSEDED = "superseded"
    CANCELLED = "cancelled"


class ErrorCode(StrEnum):
    """Run-level error codes (plan section 5.7, refined by D18)."""

    SNAPSHOT_FETCH_FAILED = "SNAPSHOT_FETCH_FAILED"
    SNAPSHOT_HEAD_MOVED = "SNAPSHOT_HEAD_MOVED"
    DIFF_TOO_LARGE = "DIFF_TOO_LARGE"
    POLICY_INVALID = "POLICY_INVALID"
    TOOL_TIMEOUT = "TOOL_TIMEOUT"
    TOOL_FAILED = "TOOL_FAILED"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    MODEL_OUTPUT_INVALID = "MODEL_OUTPUT_INVALID"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    GITHUB_RATE_LIMITED = "GITHUB_RATE_LIMITED"
    GITHUB_PERMISSION_DENIED = "GITHUB_PERMISSION_DENIED"
    PUBLISH_FAILED = "PUBLISH_FAILED"
    CANCELLED = "CANCELLED"
    INTERNAL = "INTERNAL"

    @property
    def outcome(self) -> ErrorOutcome:
        return _ERROR_POLICIES[self].outcome

    @property
    def retryable(self) -> bool:
        """Requeue the run first; it fails only after the maximum number of attempts."""
        return _ERROR_POLICIES[self].retryable

    @property
    def summary(self) -> str:
        """One human-readable line for the summary comment and the check run."""
        return _ERROR_POLICIES[self].summary


@dataclass(frozen=True, slots=True)
class _ErrorPolicy:
    outcome: ErrorOutcome
    retryable: bool
    summary: str


_partial = ErrorOutcome.PARTIAL
_failed = ErrorOutcome.FAILED
_ERROR_POLICIES: Final[Mapping[ErrorCode, _ErrorPolicy]] = MappingProxyType(
    {
        ErrorCode.POLICY_INVALID: _ErrorPolicy(
            ErrorOutcome.NONE, False, "The .ai-review.yml policy is invalid; defaults were used."
        ),
        ErrorCode.TOOL_TIMEOUT: _ErrorPolicy(
            _partial, False, "A review tool timed out; its checks are missing from this review."
        ),
        ErrorCode.TOOL_FAILED: _ErrorPolicy(
            _partial, False, "A review tool failed; its checks are missing from this review."
        ),
        ErrorCode.MODEL_UNAVAILABLE: _ErrorPolicy(
            _partial, False, "The language model was unavailable; AI review passes were skipped."
        ),
        ErrorCode.MODEL_OUTPUT_INVALID: _ErrorPolicy(
            _partial, False, "The language model returned invalid output; some passes are missing."
        ),
        ErrorCode.BUDGET_EXCEEDED: _ErrorPolicy(
            _partial, False, "The review budget was reached; some files or passes were skipped."
        ),
        ErrorCode.DIFF_TOO_LARGE: _ErrorPolicy(
            _partial,
            False,
            "The diff is too large to review completely; some changes were skipped.",
        ),
        ErrorCode.SNAPSHOT_HEAD_MOVED: _ErrorPolicy(
            ErrorOutcome.SUPERSEDED,
            False,
            "The pull request changed during the review; a newer run replaces this one.",
        ),
        ErrorCode.CANCELLED: _ErrorPolicy(
            ErrorOutcome.CANCELLED,
            False,
            "The review was cancelled because the pull request was closed or made a draft.",
        ),
        ErrorCode.GITHUB_RATE_LIMITED: _ErrorPolicy(
            _failed, True, "GitHub rate limits prevented the review from completing."
        ),
        ErrorCode.SNAPSHOT_FETCH_FAILED: _ErrorPolicy(
            _failed, True, "The pull request's commits could not be fetched."
        ),
        ErrorCode.PUBLISH_FAILED: _ErrorPolicy(
            _failed, True, "The review could not be published to GitHub."
        ),
        ErrorCode.GITHUB_PERMISSION_DENIED: _ErrorPolicy(
            _failed, False, "The GitHub App lacks a permission this review needs."
        ),
        ErrorCode.INTERNAL: _ErrorPolicy(_failed, False, "An internal error stopped the review."),
    }
)


class IllegalTransition(AIReviewerError):
    """A run state change that the state machine (plan section 2.3, D18) does not allow."""

    def __init__(self, current: RunStatus, event: RunEvent) -> None:
        super().__init__(f"illegal run transition: {current} --{event}-->")
        self.current = current
        self.event = event


class MalformedAnchorId(AIReviewerError, ValueError):
    """An anchor ID that does not follow the section 5.2 grammar.

    Subclasses ValueError so pydantic validators report it as a validation error.
    """
