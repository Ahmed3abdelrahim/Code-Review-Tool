"""Convention detectors: repository-supplied regexes run with a timeout (ReDoS-safe)."""

from __future__ import annotations

import time

import pytest

from aireviewer.policy.detectors import DETECTOR_TIMEOUT_SECONDS, DetectorResult, detector_search

pytestmark = pytest.mark.p0


def test_detector_matches() -> None:
    assert detector_search("float\\(", "total = float(amount)") is DetectorResult.MATCH
    assert detector_search("float\\(", "total = Decimal(amount)") is DetectorResult.NO_MATCH
    assert detector_search(r"(?i)FLOAT\(", "float(x)") is DetectorResult.MATCH
    assert 0 < DETECTOR_TIMEOUT_SECONDS <= 1


def test_detector_times_out() -> None:
    evil, text = r"(a|aa)+$", "a" * 64 + "!"  # exponential backtracking without a timeout
    started = time.monotonic()
    assert detector_search(evil, text, timeout=0.05) is DetectorResult.TIMEOUT
    assert time.monotonic() - started < 2
    # The default timeout applies when none is given.
    started = time.monotonic()
    assert detector_search(evil, text) is DetectorResult.TIMEOUT
    assert time.monotonic() - started < DETECTOR_TIMEOUT_SECONDS + 2
