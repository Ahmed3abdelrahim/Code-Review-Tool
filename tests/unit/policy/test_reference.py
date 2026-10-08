"""docs/POLICY_REFERENCE.md is generated from the policy models and must be up to date."""

from __future__ import annotations

from pathlib import Path

import pytest

from aireviewer.contracts.policy import Policy
from aireviewer.policy.reference import render_policy_reference

pytestmark = pytest.mark.p0

REFERENCE = Path(__file__).resolve().parents[3] / "docs" / "POLICY_REFERENCE.md"


def test_policy_reference_up_to_date() -> None:
    rendered = render_policy_reference()
    for name, field in Policy.model_fields.items():
        assert f"`{field.alias or name}`" in rendered
    assert "`architecture.layers[].may_import`" in rendered
    assert "`architecture.forbidden[].from`" in rendered
    assert REFERENCE.is_file(), "docs/POLICY_REFERENCE.md is missing: run `make policy-docs`"
    assert REFERENCE.read_text(encoding="utf-8") == rendered, (
        "docs/POLICY_REFERENCE.md is out of date: run `make policy-docs`"
    )
