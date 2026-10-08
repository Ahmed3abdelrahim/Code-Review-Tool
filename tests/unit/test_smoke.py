"""Smoke tests: the package is importable and exposes its version."""

from __future__ import annotations

import tomllib
from importlib.metadata import version
from pathlib import Path

import pytest

pytestmark = pytest.mark.p0

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_package_imports() -> None:
    import aireviewer

    assert aireviewer.__name__ == "aireviewer"


def test_version_exposed() -> None:
    import aireviewer

    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert isinstance(aireviewer.__version__, str)
    assert aireviewer.__version__
    assert aireviewer.__version__ == version("aireviewer") == pyproject["project"]["version"]
