"""Injectable clock."""

from __future__ import annotations

from datetime import timedelta

import pytest

from aireviewer.clock import Clock, SystemClock

pytestmark = pytest.mark.p0


def test_system_clock_now_is_utc_aware() -> None:
    clock: Clock = SystemClock()

    now = clock.now()
    first, second = clock.monotonic(), clock.monotonic()

    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(0)
    assert second >= first
