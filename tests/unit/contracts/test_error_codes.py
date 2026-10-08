"""Error codes (plan section 5.7, refined by D18)."""

from __future__ import annotations

import pytest

from aireviewer.contracts.run_state import TERMINAL_STATUSES
from aireviewer.errors import ErrorCode, ErrorOutcome

pytestmark = pytest.mark.p0

# Hardcoded from D18: code -> (outcome, retryable).
EXPECTED = {
    "POLICY_INVALID": ("none", False),
    "TOOL_TIMEOUT": ("partial", False),
    "TOOL_FAILED": ("partial", False),
    "MODEL_UNAVAILABLE": ("partial", False),
    "MODEL_OUTPUT_INVALID": ("partial", False),
    "BUDGET_EXCEEDED": ("partial", False),
    "DIFF_TOO_LARGE": ("partial", False),
    "SNAPSHOT_HEAD_MOVED": ("superseded", False),
    "CANCELLED": ("cancelled", False),
    "GITHUB_RATE_LIMITED": ("failed", True),
    "SNAPSHOT_FETCH_FAILED": ("failed", True),
    "PUBLISH_FAILED": ("failed", True),
    "GITHUB_PERMISSION_DENIED": ("failed", False),
    "INTERNAL": ("failed", False),
}


def test_error_codes_match_section_5_7() -> None:
    assert {code.value for code in ErrorCode} == set(EXPECTED)
    assert all(code.name == code.value for code in ErrorCode)


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_every_code_has_outcome_and_retry_policy(name: str) -> None:
    code = ErrorCode(name)

    assert (code.outcome.value, code.retryable) == EXPECTED[name]
    assert code.summary
    assert "\n" not in code.summary
    assert len(code.summary) <= 120


def test_outcomes_are_terminal_run_statuses() -> None:
    terminal = {status.value for status in TERMINAL_STATUSES}
    assert {outcome.value for outcome in ErrorOutcome} == {"none"} | {
        "partial",
        "failed",
        "superseded",
        "cancelled",
    }
    assert {o.value for o in ErrorOutcome if o is not ErrorOutcome.NONE} <= terminal
