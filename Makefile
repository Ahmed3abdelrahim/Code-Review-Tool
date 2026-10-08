# Targets from docs/Code_Review_IMPLEMENTATION_PLAN.md section 4.2.
SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

RUN := uv run --locked
PYTEST := $(RUN) pytest

# D14: suites that may still collect zero tests (pytest exit code 5).
# The task that adds a suite's first test removes it from this list:
# faults -> T1.2, security -> T1.3. (integration left in T0.6, with its first tests.)
ALLOW_EMPTY := security faults

# $(call run_suite,<marker>): pytest -m <marker>; exit code 5 is tolerated only for ALLOW_EMPTY.
define run_suite
	@status=0; $(PYTEST) -m "$(1)" || status=$$?; \
	if [ $$status -eq 5 ] && [[ " $(ALLOW_EMPTY) " == *" $(1) "* ]]; then \
		echo "WARNING: no '$(1)' tests collected; tolerated because '$(1)' is in ALLOW_EMPTY (D14)."; \
	else \
		exit $$status; \
	fi
endef

.PHONY: help setup fmt lint type test test-int test-sec test-faults test-hooks check check-all \
	e2e eval eval-live eval-compare up down migrate policy-docs

help: ## List targets
	@grep -E '^[a-zA-Z0-9_%-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-14s %s\n", $$1, $$2}'

setup: ## uv sync, npm ci in tools/node, install pre-commit hooks (SKIP_HOOKS=1 to skip)
	@command -v uv >/dev/null || { echo "uv is not installed: see README.md"; exit 1; }
	uv sync --locked
	@if [ -f tools/node/package-lock.json ]; then \
		npm ci --ignore-scripts --prefix tools/node; \
	else \
		echo "tools/node/package-lock.json not present yet; skipping npm ci"; \
	fi
	@if [ -n "$(SKIP_HOOKS)" ]; then \
		echo "SKIP_HOOKS is set; not installing pre-commit hooks"; \
	elif [ -d .git ]; then \
		$(RUN) pre-commit install; \
	else \
		echo "No .git directory; skipping pre-commit install"; \
	fi

fmt: ## Format and autofix
	$(RUN) ruff format
	$(RUN) ruff check --fix

lint: ## ruff check + ruff format --check
	$(RUN) ruff check
	$(RUN) ruff format --check

type: ## mypy --strict on src/
	$(RUN) mypy

test: ## Unit tests (no Docker, no network)
	$(PYTEST) -m unit

test-int: ## Integration tests (Docker)
	$(call run_suite,integration)

test-sec: ## Security tests
	$(call run_suite,security)

test-faults: ## Fault-injection tests
	$(call run_suite,faults)

test-hooks: ## Self-test of the Claude Code git hook
	python3 .claude/hooks/test_block_git.py

check: lint type test ## lint + type + unit tests (before every commit)

check-all: check test-int test-sec test-faults test-hooks ## Everything CI runs

policy-docs: ## Regenerate docs/POLICY_REFERENCE.md from the policy models
	$(RUN) python -m aireviewer.policy.reference docs/POLICY_REFERENCE.md

verify-p%: ## Phase verification: make verify-p<N>
	$(PYTEST) -m "p$* and not e2e and not eval"

e2e: ## End-to-end against the sandbox repo (manual)
	@echo "make e2e is not available until T1.10"; exit 1

eval: ## Benchmark with recorded model responses
	@echo "make eval is not available until T3.13"; exit 1

eval-live: ## Benchmark with the live model (costs money)
	@echo "make eval-live is not available until T3.13"; exit 1

eval-compare: ## Compare the latest report with eval/baseline.json
	@echo "make eval-compare is not available until T3.13"; exit 1

up: ## Start the compose stack (project: aireviewer)
	docker compose up -d --wait

down: ## Stop the compose stack (keeps volumes)
	docker compose down

migrate: ## alembic upgrade head
	@echo "make migrate is not available until T1.1"; exit 1
