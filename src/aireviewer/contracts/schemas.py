"""JSON Schemas of the finding contracts, snapshot-tested so contract changes are visible."""

from __future__ import annotations

from typing import Any

from aireviewer.contracts.findings import Finding, LLMFindingOut


def json_schemas() -> dict[str, dict[str, Any]]:
    return {
        "Finding": Finding.model_json_schema(),
        "LLMFindingOut": LLMFindingOut.model_json_schema(),
    }
