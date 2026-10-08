"""Shared pytest configuration.

Layer markers come from the directory a test lives in (tests/unit -> `unit`, ...), so a
test can never drop out of `make test` or `make test-int` by forgetting its marker.
Tests outside those directories must carry a layer marker explicitly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
LAYER_DIRS = ("unit", "integration", "security", "faults", "e2e")
LAYER_MARKERS = (*LAYER_DIRS, "eval")


def _layer_for(path: Path) -> str | None:
    try:
        relative = path.resolve().relative_to(TESTS_DIR)
    except ValueError:
        return None
    top = relative.parts[0] if len(relative.parts) > 1 else None
    return top if top in LAYER_DIRS else None


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    unmarked: list[str] = []
    for item in items:
        layer = _layer_for(item.path)
        if layer is not None:
            item.add_marker(layer)
        elif not any(item.get_closest_marker(name) for name in LAYER_MARKERS):
            unmarked.append(item.nodeid)
    if unmarked:
        raise pytest.UsageError(
            f"Tests outside tests/{{{','.join(LAYER_DIRS)}}}/ need a layer marker: "
            + ", ".join(unmarked)
        )
