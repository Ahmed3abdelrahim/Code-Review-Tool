"""A narrow git runner for the evaluation tooling (D11, D21).

Used only on repositories the tooling creates in temporary directories, and read-only on
user clones under eval/repos/. argv lists only, never a shell; the environment is an
allowlist, so the user's global and system git configuration, hooks, GIT_DIR and identity
variables never apply; every call has a timeout. Snapshot identity and dates are passed
explicitly by the caller.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

from aireviewer.errors import AIReviewerError

__all__ = ["GIT_TIMEOUT_SECONDS", "GitError", "run_git"]

GIT_TIMEOUT_SECONDS: Final = 120
_STDERR_CHARS: Final = 500

# Settings forced on every call, overriding any repository configuration.
_FORCED_CONFIG: Final = (
    "core.hooksPath=/dev/null",
    "core.fsmonitor=false",
    "core.autocrlf=false",
    "core.symlinks=true",
    "commit.gpgSign=false",
    "tag.gpgSign=false",
    "protocol.allow=never",
    "protocol.file.allow=always",  # local bundles and clones only
    "advice.detachedHead=false",
    "init.defaultBranch=main",
    "gc.auto=0",
)
_ALLOWED_ENV: Final = ("PATH", "SYSTEMROOT", "TMPDIR")


class GitError(AIReviewerError):
    def __init__(self, command: str, returncode: int | None, stderr: str) -> None:
        detail = "timed out" if returncode is None else f"exit code {returncode}"
        super().__init__(f"git {command} failed ({detail}): {stderr}")
        self.command = command
        self.returncode = returncode
        self.stderr = stderr


def run_git(
    args: Sequence[str],
    *,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
    input_bytes: bytes | None = None,
    timeout: float = GIT_TIMEOUT_SECONDS,
) -> bytes:
    """Run `git <args>` and return stdout; raise GitError on failure or timeout."""
    command_env = {key: os.environ[key] for key in _ALLOWED_ENV if key in os.environ}
    command_env.update(
        {
            "HOME": os.devnull,
            "XDG_CONFIG_HOME": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_OPTIONAL_LOCKS": "0",
            "LC_ALL": "C",
            "LANG": "C",
        }
    )
    command_env.update(env or {})
    argv = ["git"]
    for setting in _FORCED_CONFIG:
        argv += ["-c", setting]
    argv += list(args)
    name = _subcommand(args)
    try:
        completed = subprocess.run(  # noqa: S603 - argv list, no shell
            argv,
            cwd=cwd,
            env=command_env,
            input=input_bytes,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise GitError(name, None, "") from None
    except FileNotFoundError:
        raise GitError(name, None, "the git executable was not found") from None
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()
        raise GitError(name, completed.returncode, stderr[-_STDERR_CHARS:])
    return completed.stdout


def _subcommand(args: Sequence[str]) -> str:
    """The git subcommand in `args`, skipping global options and their values."""
    skip_next = False
    for arg in args:
        if skip_next:
            skip_next = False
        elif arg in ("-C", "-c", "--git-dir", "--work-tree"):
            skip_next = True
        elif not arg.startswith("-"):
            return arg
    return "?"
