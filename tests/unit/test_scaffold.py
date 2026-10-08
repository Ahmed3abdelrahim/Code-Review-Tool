"""Scaffold guarantees: strict markers, directory-based layer markers, decisions log."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.p0

REPO_ROOT = Path(__file__).resolve().parents[2]
PLAN_MARKERS = {
    "unit",
    "integration",
    "security",
    "faults",
    "e2e",
    "eval",
    "p0",
    "p1",
    "p2",
    "p3",
    "p4",
    "p5",
}
ENV_ALLOWLIST = ("PATH", "HOME", "LANG", "TMPDIR")


def _run_pytest_with_repo_config(test_file: Path) -> subprocess.CompletedProcess[str]:
    """Run pytest on one file using this repository's pytest configuration."""
    env = {key: os.environ[key] for key in ENV_ALLOWLIST if key in os.environ}
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [
            sys.executable,
            "-m",
            "pytest",
            "-c",
            str(REPO_ROOT / "pyproject.toml"),
            "--rootdir",
            str(REPO_ROOT),
            "-p",
            "no:cacheprovider",
            str(test_file),
        ],
        cwd=test_file.parent,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_unregistered_marker_fails_run(tmp_path: Path) -> None:
    registered = tmp_path / "test_registered.py"
    registered.write_text(
        "import pytest\n\n@pytest.mark.unit\ndef test_ok():\n    pass\n", encoding="utf-8"
    )
    unregistered = tmp_path / "test_unregistered.py"
    unregistered.write_text(
        "import pytest\n\n@pytest.mark.definitely_not_registered\ndef test_ok():\n    pass\n",
        encoding="utf-8",
    )

    control = _run_pytest_with_repo_config(registered)
    assert control.returncode == 0, control.stdout + control.stderr

    result = _run_pytest_with_repo_config(unregistered)
    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "'definitely_not_registered' not found in `markers` configuration option" in output


def test_plan_markers_registered(request: pytest.FixtureRequest) -> None:
    lines: list[str] = request.config.getini("markers")
    registered = {line.split(":", 1)[0].strip() for line in lines}
    assert PLAN_MARKERS - registered == set()


def test_tests_auto_marked_by_directory(request: pytest.FixtureRequest) -> None:
    # This module only declares p0; `unit` must come from tests/conftest.py.
    assert request.node.get_closest_marker("unit") is not None
    assert request.node.get_closest_marker("integration") is None


def test_decisions_contains_d1_to_d10() -> None:
    decisions = (REPO_ROOT / "docs" / "DECISIONS.md").read_text(encoding="utf-8")
    missing = [n for n in range(1, 11) if not re.search(rf"^## D{n} — \S", decisions, re.M)]
    assert missing == []
