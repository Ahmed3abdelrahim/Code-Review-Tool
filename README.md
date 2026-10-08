# AI Code Reviewer

GitHub App that reviews pull requests with three layers in one pipeline: deterministic tools,
dependency-graph design rules and an LLM review. The plan is in
`docs/Code_Review_IMPLEMENTATION_PLAN.md`; progress in `docs/PROGRESS.md`; decisions in
`docs/DECISIONS.md`.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) 0.12.23 (pinned in `pyproject.toml`):
  `curl -LsSf https://astral.sh/uv/install.sh | sh`
- GNU Make, Docker with Compose v2, Python 3.12 (uv can provide it)

## Setup

```bash
make setup         # uv sync, npm ci (once tools/node exists), pre-commit install
make check         # lint + types + unit tests
cp .env.example .env   # then edit; needed for `make up`
make up            # Postgres on 127.0.0.1:${AIREVIEW_PG_PORT:-55432}
```

uv installs into `.venv` by default. To use an existing virtualenv instead (for example the
virtualenvwrapper env `code_review`), export
`UV_PROJECT_ENVIRONMENT=$HOME/.virtualenvs/code_review` before running `make`.

`make help` lists all targets.
