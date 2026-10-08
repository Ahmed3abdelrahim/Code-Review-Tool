"""Convention detectors: repository-supplied regexes, searched with a timeout (D19).

Patterns are validated when the policy loads (`contracts/policy.py`); searching them
against repository text could still backtrack catastrophically (ReDoS), so every search
runs under the `regex` package's timeout. What a TIMEOUT means for a finding is decided by
the convention pass (T4.7).
"""

from __future__ import annotations

import functools
from enum import StrEnum
from typing import Final

import regex

DETECTOR_TIMEOUT_SECONDS: Final = 0.1


class DetectorResult(StrEnum):
    MATCH = "match"
    NO_MATCH = "no_match"
    TIMEOUT = "timeout"


@functools.lru_cache(maxsize=256)
def _compiled(pattern: str) -> regex.Pattern[str]:
    return regex.compile(pattern)


def detector_search(
    pattern: str, text: str, *, timeout: float = DETECTOR_TIMEOUT_SECONDS
) -> DetectorResult:
    """Search `text` for a validated detector pattern, giving up after `timeout` seconds."""
    try:
        found = _compiled(pattern).search(text, timeout=timeout)
    except TimeoutError:
        return DetectorResult.TIMEOUT
    return DetectorResult.MATCH if found is not None else DetectorResult.NO_MATCH
