# Progress

## Phase 0 — Foundation
- [x] T0.1 Project scaffold
- [x] T0.2 Settings, logging, redaction
- [x] T0.3 Core contracts
- [x] T0.4 Policy schema and loader
- [x] T0.5 Evaluation format, matcher, metrics
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
2026-10-08 — T0.4 — Policy models in contracts/policy.py; loader, packaged defaults (src/aireviewer/policy/default_policy.yml, read with importlib.resources), detectors and the reference generator in src/aireviewer/policy/ (D19). Added pyyaml, regex, pathspec (runtime) and types-PyYAML, types-regex (dev). New target `make policy-docs` regenerates docs/POLICY_REFERENCE.md; test_policy_reference_up_to_date fails while it is stale. The tests use the §5.3 example with the layers domain (may_import: []), schemas and db (may_import: [domain]) added; paths chosen: src/app/domain/**, src/app/schemas/**, src/app/db/**.
2026-10-08 — T0.4 — For T1.7/T3.1: policy budgets are only checked to be ≥ 1; the server clamps them to operator limits, and every clamp must be reported in the summary ("max_llm_calls lowered from X to Y by server limit"). T1.7 matches policy globs with `compile_globs` (pathspec `gitignore`), the engine validation uses.
2026-10-08 — T0.4 — For T1.8/T1.9: the summary lists `PolicyResult.errors` at the top when `source` is `fallback` (ErrorCode POLICY_INVALID, outcome none); a policy file changed by the PR is ignored for the run and noted (§5.3 rule 1). Open question for T1.8: should an invalid policy skip Layer C (deterministic layers only, run partial), so that a typo cannot send excluded paths to the model? Nothing implemented for it yet.
2026-10-08 — T0.4 — For T2.2: ESLint rule names and levels are only checked for syntax; the allowlist check belongs to config generation. For T4.7: `detector_search` returns `timeout` after 0.1 s; the convention pass decides what a timeout means for a finding.
2026-10-09 — T0.5 — Evaluation harness in src/aireviewer/eval/ (cases, predictions, matcher, adjudicate, metrics, report, cli) and the §5.5 fingerprint in src/aireviewer/pipeline/fingerprint.py (D20). The hardened YAML loader moved from policy/loader.py to src/aireviewer/config_files.py (shared with case files; policy behaviour unchanged). Console script `aireview-eval` (validate, score, adjudicate). Adjudications are keyed by `eval_key` = the §5.5 fields without enclosing symbol plus the start line (key_version 1). Snapshots created: tests/unit/eval/__snapshots__/test_report_snapshot/ (initial report.md and metrics.json of the hand-computed fixture set).
2026-10-09 — T0.5 — For T0.6: implement a bundle-backed `CodeLookup` (temp dir, argv lists, timeout) with integration tests, and remove `integration` from ALLOW_EMPTY when the first integration test lands (D14). CodeRabbit predictions must use the D20 predictions format with `channel: inline`; fingerprints may be left empty (the harness computes its own key). `test_splits_repository_disjoint` can rely on the check in `load_cases`. The §8.1 example's `base_sha: 3f1c...` is a placeholder: real cases need full quoted SHAs.
2026-10-09 — T0.5 — For T2.8: compute fingerprints with `pipeline.fingerprint.fingerprint` plus the resolved enclosing symbol. Never change `eval_key` or EVAL_KEY_VERSION without a migration of eval/adjudications.jsonl.
2026-10-09 — T0.5 — For T3.13: the runner writes predictions in the D20 format and the report adds latency p50/p95, cost and partial rate. `make eval-compare` must fail if either high-severity recall figure (inline + summary, or inline only) or any category's inline precision drops by more than 5 points versus eval/baseline.json.
2026-10-09 — T0.6 — Tooling (first of two T0.6 commits; T0.6 stays unticked until the data commit): seed trees and snapshot bundles (eval/seeds.py, eval/bundles.py, eval/git.py), CodeRabbit import (eval/coderabbit.py), sandbox command printer (eval/sandbox.py), location matching mode, `score --summary-out`, bundle-backed code in `adjudicate`; new subcommands seed-build, snapshot-upstream, sandbox-commands, import-coderabbit (D21). Holdout isolation: one root per split (`--split dev` → eval/, `--split holdout` → eval/holdout/; no `all`), cases of both roots loaded for cross-split checks, split/root rule; `.claude/settings.json` denies `Read(eval/holdout/**)` and `.claude/hooks/block_git.py` blocks Bash commands mentioning eval/holdout (self-test pinned at 48 checks). For the data commit: `test_benchmark_integrity.py` must report holdout problems without holdout details (counts and ids only), since its output reaches Claude. Case schema: `bundle_base_sha`/`bundle_head_sha` required, provenance `planted`. `integration` removed from ALLOW_EMPTY (first integration tests: tests/integration/eval/test_bundle_git.py; they need the git CLI). Snapshots updated: tests/unit/eval/__snapshots__/test_report_snapshot/ (the report now states the matching mode). Workflow guide: eval/README.md.
2026-10-09 — T0.6 — Data commit still to do: seeds for py-shop (~7) and ts-tasks (~6) drafted by Claude from the user's idea list, py-ledger (~4) and ts-notes (~3) holdout bugs written by the user under eval/holdout/ (off-limits to Claude: deny rule plus hook, D21 point 9; holdout seed-build, adjudication and scoring run by the user, who shares only aggregate metrics), 1–2 small MIT/BSD repositories (2–4 real-bug cases chosen by the user); every label reviewed by the user; then tests/unit/eval/test_benchmark_integrity.py (test_all_cases_valid, test_splits_repository_disjoint, test_bundles_contain_base_and_head, test_benchmark_size_and_mix: ≥ 20 cases, all four kinds, both splits non-empty; bundles ≤ 5 MB each and ≤ 100 MB in total), sandbox push, CodeRabbit export, import, adjudication and eval/baselines/coderabbit.json.
2026-10-09 — T0.6 — For T3.13: score our engine with strict matching for its metrics and gates, and once with `--matching location` for the comparison table with CodeRabbit.
2026-10-09 — T0.6 — Data commit, dev part (labels drafted by Claude, pending the user's review): 15 planted cases, py-shop-001…008 (Python: 4 defect, 2 clean, 1 design, 1 injection) and ts-tasks-001…007 (TypeScript: 3 defect, 2 clean, 1 design, 1 injection); one shared base app per repository; policies eval/policies/py-shop.yml and ts-tasks.yml, copied as .ai-review.yml into every seed tree; repo URLs under https://github.com/ahmed-aireview-sandbox/ (license own). New: tests/unit/eval/test_benchmark_integrity.py (the four named tests plus test_seed_policy_matches_case_policy), tests/integration/eval/test_benchmark_seeds.py, `CaseSet.error_holdout_ids`/`redacted_errors()`, `validate --redact-holdout`, redacted holdout errors in `--split dev` commands, `eval` excluded from ruff (D22). The TypeScript seeds were not type-checked (no tsc on the host; nothing is installed for seeds).
2026-10-09 — T0.6 — Still open: test_benchmark_size_and_mix fails until ≥ 20 cases exist and the holdout split is non-empty (user's py-ledger and ts-notes cases; their seed trees need `.ai-review.yml` equal to the case policy); OSS cases; sandbox push, CodeRabbit export/import/adjudication and eval/baselines/coderabbit.json. `make check` is red only on that test until then.
