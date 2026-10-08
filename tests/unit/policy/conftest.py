"""Shared policy fixtures."""

from __future__ import annotations

import pytest

# The section 5.3 example, with the layers domain, schemas and db added so that every
# may_import reference resolves (the uncorrected example fails T0.4 AC4).
SECTION_5_3_EXAMPLE = """\
version: 1

languages: [python, typescript]
exclude_paths: ["**/migrations/**", "**/generated/**", "**/*.min.js", "**/vendor/**"]

budgets:
  max_files: 60               # eligible changed files reviewed per run
  max_file_bytes: 200000
  max_changed_lines: 1500
  max_llm_input_tokens: 120000
  max_llm_calls: 12

lint:
  python:
    select: ["E", "F", "B", "UP", "SIM", "BLE"]
    ignore: ["E501"]
  typescript:
    preset: recommended       # maps to a fixed rule set in generate_eslint.py
    rules: {}                 # overrides, validated against an allowlist

complexity:
  max_ccn: 12
  max_function_lines: 60
  max_params: 5
  worsen_delta: 3

duplication:
  enabled: true
  min_tokens: 60

architecture:
  python:
    source_roots: ["src"]     # auto-detected if omitted
  typescript:
    tsconfig: tsconfig.json   # read as JSONC, never executed
  layers:
    - name: api
      paths: ["src/app/api/**"]
      may_import: [services, schemas]
    - name: services
      paths: ["src/app/services/**"]
      may_import: [repositories, domain, schemas]
    - name: repositories
      paths: ["src/app/repositories/**"]
      may_import: [db, domain]
    - name: domain
      paths: ["src/app/domain/**"]
      may_import: []
    - name: schemas
      paths: ["src/app/schemas/**"]
      may_import: [domain]
    - name: db
      paths: ["src/app/db/**"]
      may_import: [domain]
  forbidden:
    - id: domain.no-framework
      from: ["src/app/domain/**"]
      to: ["ext:fastapi", "ext:sqlalchemy"]
      severity: medium
  cycles:
    enabled: true
  drift_threshold: 0.7

conventions:
  - id: money.decimal-only
    description: "Monetary amounts must use Decimal, never float."
    paths: ["src/app/billing/**"]
    severity: medium
    detector: "float\\\\("
  - id: errors.no-silent-except
    description: "Never swallow exceptions without logging and re-raising or returning an
      explicit error."
    severity: medium

review:
  categories: [correctness, security, reliability, performance, testing, design,
               maintainability, lint]
  inline_cap: 5
  min_inline_severity: medium
  promote_inline: []
  skip_drafts: true
  check_run:
    fail_on_tool_error: false
"""


@pytest.fixture
def section_5_3_example() -> str:
    return SECTION_5_3_EXAMPLE
