#!/usr/bin/env python3
"""Self-test for block_git.py. Run: python3 .claude/hooks/test_block_git.py"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import subprocess
import sys

HOOK = pathlib.Path(__file__).with_name("block_git.py")
spec = importlib.util.spec_from_file_location("block_git", HOOK)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

ALLOWED = [
    "git clone https://github.com/example/repo.git eval/repos/repo",
    "git -c core.symlinks=false clone https://github.com/example/repo.git /tmp/repo",
    "git --version",
    "ls -la",
    "cat .gitignore",
    "uv run pytest tests/integration/snapshot/test_git_source.py -k git_source",
    'uv run pytest -k "git"',
    "ruff check src/aireviewer/snapshot/git.py",
    "uv add gitpython",
    "pip install git+https://github.com/example/pkg.git",
    "docker compose -p aireviewer up -d postgres",
    "make check",
]
BLOCKED = [
    "git status",
    "git diff",
    "git log --oneline",
    "git add .",
    'git commit -m "x"',
    "git push origin main",
    "git -C . push",
    "/usr/bin/git log",
    'bash -c "git add ."',
    "sh -c 'git commit -m x'",
    "echo $(git rev-parse HEAD)",
    "echo `git rev-parse HEAD`",
    "ls && git diff",
    "GIT_DIR=. git status",
    "docker compose exec worker git pull",
    "python3 -c \"import subprocess; subprocess.run(['git','commit'])\"",
    "git clone https://github.com/example/repo.git && git checkout main",
    "git init",
    "git config user.name x",
]

failures = []
for cmd in ALLOWED:
    if module.find_violation(cmd) is not None:
        failures.append(f"should be ALLOWED: {cmd}")
for cmd in BLOCKED:
    if module.find_violation(cmd) is None:
        failures.append(f"should be BLOCKED: {cmd}")

# End-to-end: run the hook as Claude Code does (JSON on stdin, exit code).
def run_hook(payload: str) -> int:
    return subprocess.run([sys.executable, str(HOOK)], input=payload, text=True, capture_output=True).returncode

checks = [
    (json.dumps({"tool_name": "Bash", "tool_input": {"command": "git status"}}), 2),
    (json.dumps({"tool_name": "Bash", "tool_input": {"command": "make check"}}), 0),
    (json.dumps({"tool_name": "Bash", "tool_input": {"command": "git clone https://x/y.git"}}), 0),
    ("not json", 2),
]
for payload, expected in checks:
    got = run_hook(payload)
    if got != expected:
        failures.append(f"exit code {got} != {expected} for payload {payload!r}")

total = len(ALLOWED) + len(BLOCKED) + len(checks)
if failures:
    print("FAILED:")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print(f"OK: {total} checks passed ({len(ALLOWED)} allowed, {len(BLOCKED)} blocked, {len(checks)} end-to-end)")
