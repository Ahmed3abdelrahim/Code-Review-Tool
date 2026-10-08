# Progress

## Phase 0 — Foundation
- [x] T0.1 Project scaffold
- [x] T0.2 Settings, logging, redaction
- [x] T0.3 Core contracts
- [ ] T0.4 Policy schema and loader
- [ ] T0.5 Evaluation format, matcher, metrics
- [ ] T0.6 Benchmark seed and CodeRabbit baseline
- [ ] T0.7 GitHub App and sandbox setup
- [ ] Phase 0 gate

## Phase 1 — Backbone
- [ ] T1.1 Database schema and migrations
- [ ] T1.2 Postgres job queue
- [ ] T1.3 GitHub App auth and REST client
- [ ] T1.4 Webhook endpoint and events
- [ ] T1.5 Workspace and git snapshot
- [ ] T1.6 Diff parser and anchor map
- [ ] T1.7 Classification, coverage, budgets
- [ ] T1.8 Orchestrator skeleton
- [ ] T1.9 Publisher v0
- [ ] T1.10 E2E smoke
- [ ] Phase 1 gate

## Phase 2 — Deterministic layer
- [ ] T2.1 Tool runner
- [ ] T2.2 Config generation
- [ ] T2.3 Ruff adapter
- [ ] T2.4 ESLint adapter
- [ ] T2.5 Complexity and size ratchet
- [ ] T2.6 Duplication
- [ ] T2.7 Secret detection
- [ ] T2.8 Normalization, fingerprints, dedup
- [ ] T2.9 Routing v1, summary, annotations
- [ ] T2.10 Phase verification
- [ ] Phase 2 gate

## Phase 3 — LLM review
- [ ] T3.1 Model client, usage, budgets
- [ ] T3.2 Redaction
- [ ] T3.3 Context builder
- [ ] T3.4 Chunker
- [ ] T3.5 Prompt builder and versioning
- [ ] T3.6 Pass execution and parsing
- [ ] T3.7 Validation gates
- [ ] T3.8 Ranking and routing
- [ ] T3.9 Inline publication and sanitization
- [ ] T3.10 Explanation pass
- [ ] T3.11 Incremental review
- [ ] T3.12 Reactions feedback and suppression
- [ ] T3.13 Evaluation integration and mining
- [ ] T3.14 Phase verification
- [ ] Phase 3 gate

## Phase 4 — Design rules
- [ ] T4.1 Python import graph
- [ ] T4.2 TypeScript import graph
- [ ] T4.3 Repo map and base/head graphs
- [ ] T4.4 Layer and forbidden rules
- [ ] T4.5 Cycles
- [ ] T4.6 Policy drift
- [ ] T4.7 Convention pass
- [ ] T4.8 Design summary, promotion, per-rule precision
- [ ] T4.9 import-linter oracle
- [ ] T4.10 Phase verification
- [ ] Phase 4 gate

## Phase 5 — Extensions (optional)
- [ ] T5.1 Local model via vLLM
- [ ] T5.2 Minimal dashboard
- [ ] T5.3 Local CLI
- [ ] T5.4 Tool-runner isolation
- [ ] T5.5 GitLab adapter
- [ ] T5.6 Opt-in design suggestions

## Notes
<!-- date — task — note -->
2026-10-08 — T0.1 — Scaffold done: uv 0.12.23 pinned (`[tool.uv] required-version`, CI `setup-uv version`), ruff 0.16 / mypy 2.4 strict / pytest 9.1 with strict markers, Makefile §4.2 targets (migrate/e2e/eval* stubs exit 2 until T1.1/T1.10/T3.13), compose `postgres:16` on 127.0.0.1:${AIREVIEWER_PG_PORT:-55432}, CI with SHA-pinned actions. Layer markers are added from the test directory by tests/conftest.py. `docs/` is excluded from ruff (ruff 0.16 formats Markdown code blocks and would rewrite the plan).
2026-10-08 — T0.1 — D14: `ALLOW_EMPTY := integration security faults` in the Makefile; remove `integration` in T1.1, `faults` in T1.2, `security` in T1.3.
2026-10-08 — T0.1 — Local env: virtualenvwrapper env `code_review`; set `UV_PROJECT_ENVIRONMENT=$HOME/.virtualenvs/code_review` so `uv sync`/`make` install into it. CI and fresh clones use `.venv`.
2026-10-08 — T0.1 — Host Node is 18 (EOL). T2.1 must decide whether Layer A integration tests run inside the worker image (pinned Node LTS) rather than on host Node.
2026-10-08 — T0.1 — AC3 (CI green) is pending the user's first push; `make setup && make check-all` passes locally in a fresh copy.
2026-10-08 — T0.2 — Settings (`load_settings(ApiSettings|WorkerSettings)` → `ConfigError`), redacting JSON logging, `Clock`/`SystemClock`, `AIReviewerError`/`ConfigError` (D15). Added pydantic 2.14, pydantic-settings 2.15, structlog 26.1. Compose port variable renamed `AIREVIEWER_PG_PORT` → `AIREVIEW_PG_PORT`.
2026-10-08 — T0.2 — T0.3 adds the ErrorCode enum and the §5.7 mapping to errors.py.
2026-10-08 — T0.2 — T3.1 must make the model settings required (`AIREVIEW_MODEL_PROVIDER`, `_MODEL_ID`, `_DAILY_COST_LIMIT_USD`; API key/base URL by provider).
2026-10-08 — T0.2 — Entry points (worker T1.2, API T1.4) must call `load_settings(...)`, then `configure_logging(settings.log_level, secrets=settings.secret_values())`, and turn `ConfigError` into a stderr message plus a non-zero exit.
2026-10-08 — T0.2 — T1.4: run uvicorn with `log_config=None` so its loggers go through the redacting root handler.
2026-10-08 — T0.2 — Model API key minimum is 12 (= known-value redaction minimum). Any AIREVIEW_* variable that is not a setting of any role fails fast (D16); a new non-setting AIREVIEW_* variable must be added to `NON_SETTING_VARIABLES` in settings.py (today: AIREVIEW_PG_PORT, AIREVIEW_RECORD).
2026-10-08 — T0.1 — CI failure on GitHub: .gitignore excluded CLAUDE.md, docs/PROGRESS.md, docs/DECISIONS.md and .claude/; restored during T0.3 (only secrets, .venv, build output, caches, node_modules, eval/repos/ and .claude/settings.local.json are ignored).
2026-10-08 — T0.3 — Contracts in src/aireviewer/contracts/ (findings, anchors, run_state, coverage, schemas) plus ErrorCode/ErrorOutcome, IllegalTransition, MalformedAnchorId in errors.py (D17, D18). Added hypothesis 6.168 and syrupy 6.1 (dev).
2026-10-08 — T0.3 — Snapshots created: tests/unit/contracts/__snapshots__/test_schema_snapshots/ (initial JSON Schemas of Finding and LLMFindingOut). Syrupy checked against D14: deselected runs keep exit code 5; a full run fails on unused snapshots; no configuration needed.
2026-10-08 — T0.3 — For T1.2/T1.8: a retryable ErrorCode requeues the run (`RunEvent.REQUEUE`) and fails only after max attempts; lease-expiry reclaim also uses `requeue`. For T1.7: which skip reasons make a run `partial` is still to be decided there (§2.3 and T1.7 phrase it differently). For T3.7: `LLMFindingOut` only checks the anchor grammar; resolving anchors, `=`-anchor snapping and excerpt matching are the gates' job.
