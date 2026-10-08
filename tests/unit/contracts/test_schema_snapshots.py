"""Exported JSON Schemas match the committed snapshots (AC5).

A failing snapshot means a contract changed: that needs a DECISIONS.md entry, and the
snapshot update (`pytest --snapshot-update`) needs a reason in the task report.
"""

from __future__ import annotations

import pytest
from syrupy.assertion import SnapshotAssertion
from syrupy.extensions.json import JSONSnapshotExtension

from aireviewer.contracts.schemas import json_schemas

pytestmark = pytest.mark.p0


@pytest.fixture
def snapshot_json(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    return snapshot.use_extension(JSONSnapshotExtension)


def test_exported_schema_names() -> None:
    assert set(json_schemas()) == {"Finding", "LLMFindingOut"}


def test_finding_schema_snapshot(snapshot_json: SnapshotAssertion) -> None:
    assert json_schemas()["Finding"] == snapshot_json


def test_llm_finding_out_schema_snapshot(snapshot_json: SnapshotAssertion) -> None:
    assert json_schemas()["LLMFindingOut"] == snapshot_json
