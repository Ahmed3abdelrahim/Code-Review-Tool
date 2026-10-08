# Decisions

Append-only log: never edit or delete an entry; record a change of mind as a new entry that supersedes the old one.

---

## D1 — Internal dependency-graph builder for architecture rules
- **Date:** 2026-10-08
- **Decision:** Architecture rules use an internal dependency-graph builder (Python `ast` + Tree-sitter for TypeScript) instead of running import-linter and dependency-cruiser. import-linter is kept as a dev-only test oracle.
- **Reason:** Findings need the exact import line as evidence and anchor; base-vs-head deltas are uniform across languages; nothing from the reviewed repo is imported or evaluated; dependency-cruiser configs are executable JavaScript.
- **Alternatives considered:** Running import-linter (Python) and dependency-cruiser (TypeScript) on the reviewed repository.

## D2 — Lizard for complexity and size metrics
- **Date:** 2026-10-08
- **Decision:** Lizard computes complexity and size metrics for both languages (radon dropped).
- **Reason:** One tool, one parser path, library API usable in-process, consistent metrics across languages.
- **Alternatives considered:** radon for Python alongside a separate tool for TypeScript.

## D3 — Sync-first Python
- **Date:** 2026-10-08
- **Decision:** The worker is synchronous; only the webhook route is `async` (to read raw bytes). Concurrency comes from worker processes plus bounded thread pools for model and HTTP I/O.
- **Reason:** Git and subprocess heavy workload; simpler code, simpler tests.
- **Alternatives considered:** An async codebase throughout (async worker, async DB and HTTP clients).

## D4 — Feedback through GitHub reactions
- **Date:** 2026-10-08
- **Decision:** Feedback is collected through GitHub reactions (👍 useful, 👎 false positive, 😕 unclear) on the bot's inline comments, synced on each run and by a periodic job.
- **Reason:** Gives a feedback loop without building a dashboard in the MVP.
- **Alternatives considered:** A dashboard for feedback in the MVP.

## D5 — Rerun through the check run's "Re-run" button
- **Date:** 2026-10-08
- **Decision:** Manual reruns use the check run's "Re-run" button (`check_run.rerequested` webhook).
- **Reason:** Manual rerun without a dashboard or comment commands.
- **Alternatives considered:** A dashboard action or PR comment commands.

## D6 — Inline comments only on added or deleted lines
- **Date:** 2026-10-08
- **Decision:** Inline comments go only on added (`+`, RIGHT) or deleted (`-`, LEFT) lines, never on context lines.
- **Reason:** Removes the main source of GitHub 422 errors; context lines may not be commentable.
- **Alternatives considered:** Also commenting on context lines within diff hunks.

## D7 — Check run conclusion is never `failure` by default
- **Date:** 2026-10-08
- **Decision:** Completed with no findings → `success`; findings, partial or tool failure → `neutral` with a distinct title. Configurable.
- **Reason:** Advisory mode: a tool problem must not look like a code verdict or block merges.
- **Alternatives considered:** Concluding `failure` when findings exist or when a tool fails.

## D8 — Phase 5 dashboard uses server-rendered HTML
- **Date:** 2026-10-08
- **Decision:** The Phase 5 dashboard uses server-rendered HTML (Jinja2 + HTMX) instead of React. React remains an option.
- **Reason:** Far less work for a solo developer; the dashboard is read-mostly.
- **Alternatives considered:** A React single-page application.

## D9 — Secret detection is a Layer A tool
- **Date:** 2026-10-08
- **Decision:** Secret detection is a Layer A tool (`detect-secrets` library) that both produces findings and drives redaction before any model call.
- **Reason:** One detector, two uses; deterministic evidence for secret findings.
- **Alternatives considered:** Separate mechanisms for secret findings and for pre-model redaction.

## D10 — Checkouts use `core.symlinks=false`
- **Date:** 2026-10-08
- **Decision:** Checkouts use `core.symlinks=false` and file reads refuse symlinks.
- **Reason:** A malicious repo symlink (for example to `/etc/passwd` or a key file) must never be read into tool input or a prompt.
- **Alternatives considered:** Default checkouts that materialize symlinks.

## D11 — Git policy for Claude Code
- **Date:** 2026-10-08
- **Decision:** Claude never runs git commands except `git clone`, enforced by the PreToolUse hook `.claude/hooks/block_git.py` plus deny rules; the user performs all version-control operations. Product code and tests may run git through subprocess in temporary directories. Work that needs git on external repositories (T0.6 bundles, T3.13 mining) is implemented as scripts that only touch clones under `eval/repos/` or temp dirs and never push. Pushing benchmark PRs to the sandbox organization (T0.6), `pre-commit install` (T0.1) and anything touching this repository's history are done by the user.
- **Reason:** The user keeps full control of branches, commits, pushes and repository history; a hook makes the rule enforceable instead of relying on instructions alone.
- **Alternatives considered:** Letting Claude run read-only git commands (status, diff, log); letting Claude create branches and commits for the user to review; relying on deny rules alone without a hook.

## D12 — Plan location and Claude Code configuration
- **Date:** 2026-10-08
- **Decision:** The plan lives at `docs/Code_Review_IMPLEMENTATION_PLAN.md` (not `docs/IMPLEMENTATION_PLAN.md` as written inside the plan) and is read-only for Claude (deny rule). Sessions start in plan mode with effort high. `CLAUDE.md`, the two commands, `PROGRESS.md` and `DECISIONS.md` were created during setup, so that part of T0.1 is already done.
- **Reason:** Keeps the plan as an unmodified source of truth and forces a reviewed plan before every edit.
- **Alternatives considered:** Renaming the file to match the path in the plan; letting Claude edit the plan directly.

## D13 — Docker on a shared dev server
- **Date:** 2026-10-08
- **Decision:** The compose project is named `aireviewer`; Claude operates only on this project's containers, volumes, networks and images; destructive docker commands require approval; host ports are configurable through environment variables.
- **Reason:** The server is shared with other users and services; this project must not disturb their resources or clash with their ports.
- **Alternatives considered:** Unrestricted docker use; requiring approval for every docker command.

## D14 — Empty test suites tolerated only through an expiring allowlist
- **Date:** 2026-10-08
- **Decision:** pytest exits with code 5 when it collects no tests. The Makefile tolerates exit code 5 only for suites listed in its `ALLOW_EMPTY` variable (initially `integration security faults`), and prints a visible warning when it does. `make test` and `make verify-p<N>` stay strict. The task that adds a suite's first test removes that suite from `ALLOW_EMPTY`: `integration` in T1.1, `faults` in T1.2, `security` in T1.3.
- **Reason:** `make check-all` (CI) must be green from T0.1, before any integration, security or fault test exists, without placeholder tests and without letting a suite silently stay empty forever.
- **Alternatives considered:** Placeholder tests per marker; tolerating exit code 5 for every pytest target.

## D15 — Settings loading and log redaction design
- **Date:** 2026-10-08
- **Decision:** Settings are split by process role (`CommonSettings`, `ApiSettings`, `WorkerSettings`) and loaded through `load_settings()`, which raises `ConfigError` naming each bad `AIREVIEW_*` variable, never its value or length, and is not chained to pydantic's `ValidationError`. No `.env` loading in the application. Webhook secret must be at least 32 characters. Logging: structlog and stdlib records share one `ProcessorFormatter` on the root handler; the redaction processor runs last before JSON rendering, after plain-text exception formatting (`format_exc_info`; never `dict_tracebacks` or frame locals). It masks values of sensitive keys (normalized: lowercase, `-` → `_`; exact names plus suffixes `_token`, `_secret`, `_password`, `_api_key`, `_private_key`), text patterns (GitHub tokens, Bearer, Authorization values, sensitive key=value pairs, JWTs, PEM blocks including truncated ones, URL credentials) and known secret setting values of at least 12 characters. Non-JSON values are `repr()`'d, capped at 10,000 characters, before redaction. Uncaught exceptions (`sys.excepthook`, `threading.excepthook`) go through the same logger. `print` is banned in `src/` (ruff T20).
- **Reason:** Secrets must never reach logs from any path: messages, bound fields, object reprs, tracebacks, third-party loggers or crashes. Short known values (for example a dev database password like `postgres`) would mask ordinary words, so they rely on the URL pattern instead.
- **Alternatives considered:** One settings class with every role's variables required; redaction in the structlog chain only (misses stdlib loggers); `dict_tracebacks` (can include frame locals); literal replacement of every known secret regardless of length.

## D16 — Unknown AIREVIEW_* variables fail fast
- **Date:** 2026-10-08
- **Decision:** `load_settings()` rejects any `AIREVIEW_*` environment variable that is neither a setting of any role (`CommonSettings`, `ApiSettings`, `WorkerSettings`) nor listed in `NON_SETTING_VARIABLES` (`AIREVIEW_PG_PORT`, `AIREVIEW_RECORD`). The `ConfigError` names the variable, never its value. Known means known to any role, so the API and the worker can share one env file. Every secret setting has a minimum length of at least 12 characters (model API key 12, webhook secret 32), so known-value log redaction (D15) always covers it.
- **Reason:** A typo such as `AIREVIEW_LOG_LEVL` or `AIREVIEW_DAILY_COST_LIMT_USD` would otherwise be ignored silently and the default would apply, which for a cost cap or a secret is a real failure.
- **Alternatives considered:** Ignoring unknown prefixed variables (pydantic-settings default); rejecting variables unknown to the loading role only (breaks a shared env file).

## D17 — Contract tightenings beyond the literal §5.1 code
- **Date:** 2026-10-08
- **Decision:** All contract models use `extra="forbid"` (not only `LLMFindingOut`) and `validate_assignment=True`. `Finding.status` is a `FindingStatus` enum with the eight values from the §5.1 comment instead of a free `str`. `tool_payload` is `dict[str, JsonValue]`. `Location.end_line >= start_line`; `title` and `explanation` are non-empty; `rule_id`, when set, is non-empty; `trigger` and `impact` are at most 500 characters. `Location.anchor_ids` and all LLM anchor IDs must match the §5.2 grammar (`LLMFindingOut.anchor_ids`: diff anchors only, 1–10; evidence: diff or context-snippet anchors, 1–10). The `rule_id` rule applies to `LLMFindingOut` too. `Side` is defined in `contracts/anchors.py` and re-exported from `contracts/findings.py` (avoids an import cycle; the public import path is unchanged).
- **Reason:** Catch typos, invalid states and non-serializable payloads at the boundary; let the anchor grammar and the forbidden extras show in the JSON Schema the model receives; reject a missing rule ID before a repair call is wasted.
- **Alternatives considered:** Implementing §5.1 literally and enforcing these rules in the T3.7 validation gates only.

## D18 — §2.3 and §5.7 refined
- **Date:** 2026-10-08
- **Decision:** (1) The run state machine gains a `requeue` event, `running → queued`, used for retryable errors and lease-expiry reclaim (9 transitions in total). (2) Each `ErrorCode` has an `outcome` (`partial`, `failed`, `superseded`, `cancelled` or `none`), a `retryable` flag and a one-line summary: `none` (warning, status unchanged): POLICY_INVALID; `partial`: TOOL_TIMEOUT, TOOL_FAILED, MODEL_UNAVAILABLE, MODEL_OUTPUT_INVALID, BUDGET_EXCEEDED, DIFF_TOO_LARGE; `superseded`: SNAPSHOT_HEAD_MOVED (T1.5 AC3); `cancelled`: CANCELLED; `failed` and retryable (requeue first, fail only after the maximum number of attempts): GITHUB_RATE_LIMITED, SNAPSHOT_FETCH_FAILED, PUBLISH_FAILED; `failed`, not retryable: GITHUB_PERMISSION_DENIED, INTERNAL.
- **Reason:** §5.7's "partial or failed" did not fit a moved head (superseded), a cancellation (cancelled), a non-fatal policy warning or transient GitHub failures; without `requeue`, a run that hit a retryable error or lost its lease would be stuck in `running`.
- **Alternatives considered:** Mapping every code to `partial` or `failed` as §5.7 states; modelling retries outside the state machine.

## D19 — Policy loading hardened, defaults shipped as package data (§3, §5.3 refined)
- **Date:** 2026-10-08
- **Decision:** (1) The defaults live in `src/aireviewer/policy/default_policy.yml` (package data, read with `importlib.resources`) instead of `config/default_policy.yml`; the policy models have no section defaults, so that file is the only source of default values, and an invalid defaults file raises `ConfigError`. (2) `PolicyResult.source` is `default` (no file), `repo` (valid file) or `fallback` (invalid file replaced by the defaults). An empty or comment-only file is `{}`: `repo`, no errors, the defaults' version. `version` is optional in a repository file (it comes from the defaults) and must be `1` if present. (3) Merge: mappings merge; lists, scalars and `null` replace; an invalid file falls back as a whole (no partial salvage). (4) YAML: at most 64 KiB (UTF-8 bytes) and 20 levels of nesting (checked while composing); aliases, duplicate keys, non-string keys, non-finite numbers, multiple documents and every tag outside the JSON-compatible core schema (python/*, timestamps, binary, sets, omap, pairs, local tags) are rejected. (5) Integers, floats and booleans are strict (no `"60"` → 60, no `true` → 1; `1` → 1.0 is allowed); enums take their string values. (6) Models are frozen with `extra="forbid"`; lists are tuples; `forbidden[].from` accepts only that spelling. Identifiers: layer names `^[a-z][a-z0-9_-]{0,63}$`, forbidden-rule and convention IDs `^[a-z0-9][a-z0-9._-]{0,99}$` (each unique), ruff codes `^[A-Z]{1,8}[0-9]{0,6}$`, ESLint rule names checked for syntax with values `off`/`warn`/`error` (the allowlist is T2.2's), `preset` only `recommended`; `languages` and `review.categories` without duplicates; `forbidden[].to` is a glob or `ext:<package>`; convention descriptions 1–500 characters without control characters. (7) Globs are pathspec `gitignore` patterns, at most 256 characters, no leading `/`, backslash, `..` segment, control character or `!` negation; `compile_globs` exposes the same engine for T1.7. `source_roots` (at least one when set) and `tsconfig` are plain relative paths. (8) Detectors (at most 500 characters) must compile with `regex`; `policy/detectors.py` searches with a 0.1 s timeout and returns `match`, `no_match` or `timeout`. (9) `policy_version = sha256(canonical_json(effective.model_dump(mode="json", by_alias=True)))[:16]` with sorted keys, compact separators and ASCII-only JSON; list order is part of the value. (10) Error messages are `location: message`, at most 20 plus "… and N more errors"; they never repeat values (key names are escaped and cut to 64 characters) and give only position and problem for YAML errors. A last-resort `except Exception` logs and falls back with "internal error while reading the policy", so a policy can never fail a run. (11) Budgets are only checked to be at least 1 here; the server clamps them to operator limits (T1.7, T3.1). No default conventions, layers or forbidden rules. (12) `docs/POLICY_REFERENCE.md` is generated from the models (`make policy-docs`) and a unit test fails while it is stale.
- **Reason:** The policy file is repository content and reaches the summary, the tool configs and the model's prompts; it must not be able to execute code, exhaust CPU or memory (alias bombs, deep nesting, ReDoS), hide typos or leak values. Package data keeps the defaults with the code that validates them in every install (editable, wheel, Docker image).
- **Alternatives considered:** `config/default_policy.yml` at the repository root (breaks a wheel install and needs a copy step in every image); lax pydantic coercion; salvaging the valid parts of an invalid file; hard budget ceilings in the schema.
