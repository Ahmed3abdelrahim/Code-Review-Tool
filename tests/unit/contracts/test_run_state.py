"""Run state machine (plan section 2.3, refined by D18)."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from aireviewer.contracts.run_state import (
    INITIAL_STATUS,
    TERMINAL_STATUSES,
    TRANSITIONS,
    RunEvent,
    RunStatus,
    transition,
)
from aireviewer.errors import IllegalTransition

pytestmark = pytest.mark.p0

# Hardcoded from section 2.3 plus the requeue row (D18); not imported from the implementation.
EXPECTED = {
    ("queued", "claim"): "running",
    ("queued", "supersede"): "superseded",
    ("queued", "cancel"): "cancelled",
    ("running", "requeue"): "queued",
    ("running", "complete"): "completed",
    ("running", "complete_partial"): "partial",
    ("running", "fail"): "failed",
    ("running", "supersede"): "superseded",
    ("running", "cancel"): "cancelled",
}
STATUSES = {"queued", "running", "completed", "partial", "failed", "superseded", "cancelled"}
TERMINAL = {"completed", "partial", "failed", "superseded", "cancelled"}


def test_allowed_transitions_table() -> None:
    assert {status.value for status in RunStatus} == STATUSES
    assert {status.value for status in TERMINAL_STATUSES} == TERMINAL
    assert INITIAL_STATUS is RunStatus.QUEUED
    table = {(s.value, e.value): t.value for (s, e), t in TRANSITIONS.items()}
    assert table == EXPECTED
    # Exhaustive over every pair, so no pair depends on what hypothesis happens to draw.
    for status in RunStatus:
        for event in RunEvent:
            expected = EXPECTED.get((status.value, event.value))
            if expected is None:
                with pytest.raises(IllegalTransition):
                    transition(status, event)
            else:
                assert transition(status, event).value == expected


@given(st.sampled_from(RunStatus), st.sampled_from(RunEvent))
def test_illegal_transitions_raise(status: RunStatus, event: RunEvent) -> None:
    expected = EXPECTED.get((status.value, event.value))
    if expected is not None:
        assert transition(status, event).value == expected
        return
    with pytest.raises(IllegalTransition) as excinfo:
        transition(status, event)
    assert excinfo.value.current is status
    assert excinfo.value.event is event


@pytest.mark.parametrize("status", sorted(TERMINAL))
def test_terminal_states_have_no_exits(status: str) -> None:
    for event in RunEvent:
        with pytest.raises(IllegalTransition):
            transition(RunStatus(status), event)
    assert not any(source.value == status for source, _ in TRANSITIONS)
