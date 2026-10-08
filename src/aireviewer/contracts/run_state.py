"""Run state machine (plan section 2.3, with the requeue transition from D18)."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from aireviewer.errors import IllegalTransition


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    SUPERSEDED = "superseded"
    CANCELLED = "cancelled"


class RunEvent(StrEnum):
    CLAIM = "claim"  # worker claims the job and acquires the PR lock
    REQUEUE = "requeue"  # retryable error or lease-expiry reclaim (D18)
    SUPERSEDE = "supersede"  # newer head SHA, cancel flag, or failed freshness check
    CANCEL = "cancel"  # PR closed or converted to draft
    COMPLETE = "complete"  # all stages succeeded with full coverage
    COMPLETE_PARTIAL = "complete_partial"  # published, but something was skipped
    FAIL = "fail"  # fatal error; nothing meaningful could be published


INITIAL_STATUS: Final = RunStatus.QUEUED  # "— -> queued": a webhook or rerun creates the run

TRANSITIONS: Final[Mapping[tuple[RunStatus, RunEvent], RunStatus]] = MappingProxyType(
    {
        (RunStatus.QUEUED, RunEvent.CLAIM): RunStatus.RUNNING,
        (RunStatus.QUEUED, RunEvent.SUPERSEDE): RunStatus.SUPERSEDED,
        (RunStatus.QUEUED, RunEvent.CANCEL): RunStatus.CANCELLED,
        (RunStatus.RUNNING, RunEvent.REQUEUE): RunStatus.QUEUED,
        (RunStatus.RUNNING, RunEvent.COMPLETE): RunStatus.COMPLETED,
        (RunStatus.RUNNING, RunEvent.COMPLETE_PARTIAL): RunStatus.PARTIAL,
        (RunStatus.RUNNING, RunEvent.FAIL): RunStatus.FAILED,
        (RunStatus.RUNNING, RunEvent.SUPERSEDE): RunStatus.SUPERSEDED,
        (RunStatus.RUNNING, RunEvent.CANCEL): RunStatus.CANCELLED,
    }
)

TERMINAL_STATUSES: Final = frozenset(
    {
        RunStatus.COMPLETED,
        RunStatus.PARTIAL,
        RunStatus.FAILED,
        RunStatus.SUPERSEDED,
        RunStatus.CANCELLED,
    }
)


def transition(current: RunStatus, event: RunEvent) -> RunStatus:
    """Return the next status, or raise IllegalTransition for any pair not in the table."""
    try:
        return TRANSITIONS[current, event]
    except KeyError:
        raise IllegalTransition(current, event) from None


def is_terminal(status: RunStatus) -> bool:
    return status in TERMINAL_STATUSES
