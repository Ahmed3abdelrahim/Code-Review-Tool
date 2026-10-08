"""Coverage models: every changed file is reviewed or has exactly one skip reason."""

from __future__ import annotations

import re
from typing import Any

import pytest
from pydantic import ValidationError

from aireviewer.contracts.coverage import CoverageGap, FileCoverage, RunCoverage, SkipReason

pytestmark = pytest.mark.p0


def file_data(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "path": "src/a.py",
        "change_type": "modified",
        "language": "python",
        "added": 3,
        "deleted": 1,
        "reviewed": True,
    }
    data.update(overrides)
    return data


def test_file_reviewed_xor_skip_reason() -> None:
    FileCoverage.model_validate(file_data())
    FileCoverage.model_validate(file_data(reviewed=False, skip_reason="generated"))
    with pytest.raises(ValidationError):
        FileCoverage.model_validate(file_data(reviewed=True, skip_reason="generated"))
    with pytest.raises(ValidationError):
        FileCoverage.model_validate(file_data(reviewed=False))


def test_skip_reasons_match_t1_7() -> None:
    assert {r.value for r in SkipReason} == {
        "unsupported_language",
        "generated",
        "excluded_by_policy",
        "binary",
        "too_large",
        "over_file_budget",
        "over_line_budget",
    }


def test_renamed_file_requires_old_path() -> None:
    with pytest.raises(ValidationError, match="old_path"):
        FileCoverage.model_validate(file_data(change_type="renamed"))
    FileCoverage.model_validate(file_data(change_type="renamed", old_path="src/old.py"))
    with pytest.raises(ValidationError, match="old_path"):
        FileCoverage.model_validate(file_data(old_path="src/old.py"))


def test_run_coverage_rejects_duplicate_paths() -> None:
    one = FileCoverage.model_validate(file_data())
    other = FileCoverage.model_validate(file_data(path="src/b.py"))
    with pytest.raises(ValidationError, match=re.escape("duplicated: ['src/a.py']")):
        RunCoverage(files=[one, other, one])

    coverage = RunCoverage(
        files=[
            one,
            FileCoverage.model_validate(
                file_data(path="gen.py", reviewed=False, skip_reason="generated")
            ),
        ],
        gaps=[CoverageGap(component="llm:security", reason="model_unavailable")],
    )
    assert coverage.reviewed_count == 1
    assert [f.path for f in coverage.skipped] == ["gen.py"]


def test_counts_cannot_be_negative() -> None:
    with pytest.raises(ValidationError):
        FileCoverage.model_validate(file_data(added=-1))
