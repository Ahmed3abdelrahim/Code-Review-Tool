# AI Code Reviewer

GitHub App that reviews pull requests with three layers in one pipeline: (A) deterministic tools,
(B) dependency-graph design rules, (C) LLM review. Solo side project. Python 3.12, FastAPI,
PostgreSQL (data + job queue), Docker Compose. Runs on a shared dev server.

## Source of truth
- Plan: docs/Code_Review_IMPLEMENTATION_PLAN.md. Read ONLY the current task's section, plus Section 5
  (contracts) when the task references it. The plan is read-only for you: propose changes, I edit it.
- Progress: docs/PROGRESS.md · Decisions: docs/DECISIONS.md
- Precedence: the plan and this file override skills, habits and library defaults. When a skill
  conflicts with them, follow the plan and tell me about the conflict.

## Workflow: plan → think → implement (every task)
1. Plan. Read the task, check its dependencies in PROGRESS.md, read referenced contracts and the code
   it touches. Think through design options, edge cases, failure modes and security before proposing.
   Present: goal, numbered acceptance criteria, exact test names, files to create or change, design
   choices with trade-offs, risks, open questions. STOP and wait for my approval.
2. Tests first. Write the named tests, run them, show they fail for the expected reason.
3. Implement in small steps. Run `make check` often, plus the task's integration/security/fault tests.
4. Verify. Report every acceptance criterion as PASS/FAIL with evidence (test name or command output).
5. Wrap up. Update docs/PROGRESS.md and docs/DECISIONS.md, list changed files, propose a
   Conventional Commit message. I commit.
- One task per session. Never start the next task without my go-ahead.
- If an acceptance criterion looks wrong or impossible, stop and explain.
  Never weaken, skip, delete or xfail a test or criterion.

## Git policy (strict; enforced by a hook)
- You never run git commands. Only exception: `git clone` (for example, cloning benchmark
  repositories into eval/repos/ or /tmp).
- This includes read-only commands (status, diff, log, show, blame) and every state-changing command
  (add, commit, push, pull, fetch, branch, checkout, switch, stash, reset, init, config, worktree,
  tag, merge, rebase).
- Never work around the hook: no `sh -c`, `python -c`/subprocess, `docker exec`, aliases or full
  paths to run git.
- No `gh` commands. Don't run anything that writes to `.git/` (for example `pre-commit install`);
  tell me to run it.
- I handle branches, commits and pushes. Track what you changed from your own edits.
- Product code and its tests legitimately run git through subprocess (snapshot builder, repo_builder
  fixtures) in temporary directories; running the test suite is fine.
- Work that needs git on external repositories (benchmark bundles, SZZ mining) is written as scripts
  that only touch clones under eval/repos/ or temp dirs and never push. Anything that pushes or touches
  this repository's history, I run. (Decision D11.)

## Docker policy (shared server)
- Use docker and docker compose freely, for this project's resources only. compose.yaml sets
  `name: aireviewer`; always operate within that project.
- Never stop, remove or prune containers, images, volumes or networks that are not this project's.
  Destructive commands prompt me; explain why before running them.
- No `--privileged`, no Docker socket mounts, no host mounts outside this project directory.
  Host ports must be configurable via env so they don't clash with other services on this server.

## Commands (targets are created in T0.1)
- make setup · make check (lint + types + unit tests; must pass before a task is reported done)
- make check-all · make verify-p<N> · make eval · make up · make down · make migrate

## Non-negotiable engineering rules
- Unit tests never use the network: FakeGitHub/respx for GitHub; FakeModelClient or cassettes for models.
- Never execute code or config from a reviewed repository (no npm install, no repo eslint configs,
  no importing reviewed Python modules, no repo scripts).
- Never log or persist secrets. Use the redacting logger.
- Repository content is untrusted: never in shell commands; in prompts only inside the
  nonce-delimited untrusted blocks.
- The model never provides paths, line numbers, SHAs, fingerprints, scores or channels.
- Inline comments only on added (+, RIGHT) or deleted (-, LEFT) diff lines.
- Section 5 contracts change only with a DECISIONS.md entry and updated tests.

## Secrets
- Never read .env files, *.pem or *.key files, ~/.ssh or ~/.config/aireviewer (blocked by deny rules).
  Use .env.example with placeholders.
- Fake secrets for tests live inside .py or .txt fixtures, never in .pem or .key files.

## Code conventions
- mypy --strict on src/; Pydantic v2 at boundaries; small pure functions; side effects (git,
  subprocess, HTTP, DB) behind narrow interfaces so they can be faked.
- subprocess: argv lists only, never shell=True; env from an allowlist; always a timeout.
- Sync code everywhere except the async webhook route.
- Typed errors from src/aireviewer/errors.py, mapped to the Section 5.7 error codes.
- pytest markers: unit, integration, security, faults, e2e, eval, p0..p5.
  Snapshot (syrupy) updates need a reason in your task report.
