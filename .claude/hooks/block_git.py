#!/usr/bin/env python3
"""Claude Code PreToolUse hook for Bash commands.

1. Block every git command except `git clone` (D11).
2. Block every command whose text mentions the holdout directory `eval/holdout` (D21):
   holdout data is off-limits to Claude; only the harness, run by the user, reads it.

Reads the hook event JSON from stdin.
Exit 0 = no objection (the normal permission flow continues).
Exit 2 = block the command; stderr is shown to Claude.
Deliberately conservative: a false positive only blocks one command.
"""
from __future__ import annotations

import json
import re
import sys

# "git" used as a program name: not preceded by a word character, dot or dash
# (so test_git.py, .gitignore and gitpython don't match), optionally with a
# path (/usr/bin/git), followed by whitespace, a quote, a separator or the end.
GIT_RE = re.compile(r"(?<![\w.\-])(?:[\w.\-]*/)*git(?=[\s\"'`;|&)]|$)")
OPTIONS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env"}
SEPARATORS = set(";|&)`\n")
ALLOWED_SUBCOMMANDS = {"clone"}
HOLDOUT_DIR = "eval/holdout"
# Path spellings that name the same directory: eval//holdout, eval/./holdout.
_PATH_NOISE = re.compile(r"/(?:\./)+|/{2,}")


def mentions_holdout(command: str) -> bool:
    """True when the command text names eval/holdout (after collapsing // and /./)."""
    normalized = _PATH_NOISE.sub("/", command)
    return HOLDOUT_DIR in normalized


def find_violation(command: str) -> str | None:
    """Return a short description of the first forbidden git use, or None."""
    for match in GIT_RE.finditer(command):
        rest = command[match.end():]
        cut = next((i for i, ch in enumerate(rest) if ch in SEPARATORS), len(rest))
        tokens = [t.strip("\"'()$") for t in rest[:cut].split()]
        tokens = [t for t in tokens if t]
        subcommand = None
        skip_next = False
        for tok in tokens:
            if skip_next:
                skip_next = False
                continue
            if tok in OPTIONS_WITH_VALUE:
                skip_next = True
                continue
            if tok.startswith("-"):
                continue
            subcommand = tok
            break
        if subcommand is None:
            continue  # bare `git` or `git --version`: harmless
        if subcommand not in ALLOWED_SUBCOMMANDS:
            return f"git {subcommand}"[:60]
    return None


def main() -> int:
    try:
        event = json.load(sys.stdin)
        command = event.get("tool_input", {}).get("command", "")
    except Exception as exc:  # fail closed: a broken hook must be visible
        print(f"block_git hook could not parse its input ({exc}); command blocked.", file=sys.stderr)
        return 2
    if not isinstance(command, str):
        return 0
    if mentions_holdout(command):
        print(
            f"Blocked by project policy: holdout data ({HOLDOUT_DIR}/) is off-limits to Claude "
            "(D21). Do not read, list, search or copy anything under it, by any means. The "
            "user runs every holdout step (seed-build, adjudication, scoring, reports) and "
            "shares only aggregate metrics.",
            file=sys.stderr,
        )
        return 2
    violation = find_violation(command)
    if violation:
        print(
            f"Blocked by project policy: Claude must not run git commands (detected '{violation}'). "
            "Only `git clone` is allowed; the user handles every other git operation. "
            "Do not work around this (no sh -c, subprocess, docker exec or full paths). "
            "Tell the user what you need instead.",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
