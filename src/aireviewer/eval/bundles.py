"""Snapshot bundles for benchmark cases (D21).

Every case has its own bundle `eval/bundles/<case>.bundle` holding exactly two commits: a
root commit with the base snapshot and its child with the head snapshot, under the refs
`refs/aireview/<case>/base` and `refs/aireview/<case>/head`. Commits use a fixed identity,
date and message, so the same trees always give the same SHAs (`bundle_base_sha`,
`bundle_head_sha` in the case file). Bundles are self-contained (no prerequisites) and at
most MAX_BUNDLE_BYTES.

Headers are parsed in Python (no git), so integrity checks run anywhere. Building and
reading run git through `eval.git.run_git`, in temporary repositories only; an upstream
clone is only read (through alternates), never written.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import Final, Self

from pathspec import GitIgnoreSpec

from aireviewer.contracts.anchors import Side
from aireviewer.errors import AIReviewerError
from aireviewer.eval.cases import Case
from aireviewer.eval.git import GitError, run_git
from aireviewer.eval.seeds import DEFAULT_PR_TITLE, collect_tree

__all__ = [
    "BASE_MESSAGE",
    "MAX_BUNDLE_BYTES",
    "MAX_HEADER_BYTES",
    "MAX_TOTAL_BUNDLE_BYTES",
    "SNAPSHOT_AUTHOR",
    "BundleCodeLookup",
    "BundleError",
    "BundleHeader",
    "BundleInfo",
    "build_seed_bundle",
    "build_upstream_bundle",
    "bundle_problems",
    "case_refs",
    "parse_bundle_header",
    "read_bundle_header",
]

MAX_BUNDLE_BYTES: Final = 5 * 1024 * 1024
MAX_TOTAL_BUNDLE_BYTES: Final = 100 * 1024 * 1024
MAX_HEADER_BYTES: Final = 1024 * 1024
MAX_SOURCE_BYTES: Final = 2 * 1024 * 1024
REF_PREFIX: Final = "refs/aireview/"
SNAPSHOT_AUTHOR: Final = "aireview benchmark"
SNAPSHOT_EMAIL: Final = "benchmark@aireview.invalid"
SNAPSHOT_DATE: Final = "2026-01-01T00:00:00+0000"
BASE_MESSAGE: Final = "Base snapshot"
_SNAPSHOT_ENV: Final = {
    "GIT_AUTHOR_NAME": SNAPSHOT_AUTHOR,
    "GIT_AUTHOR_EMAIL": SNAPSHOT_EMAIL,
    "GIT_AUTHOR_DATE": SNAPSHOT_DATE,
    "GIT_COMMITTER_NAME": SNAPSHOT_AUTHOR,
    "GIT_COMMITTER_EMAIL": SNAPSHOT_EMAIL,
    "GIT_COMMITTER_DATE": SNAPSHOT_DATE,
    "TZ": "UTC",
}
_SIGNATURES: Final = {b"# v2 git bundle": 2, b"# v3 git bundle": 3}
_HEX_LENGTH: Final = {"sha1": 40, "sha256": 64}
_REF_NAME: Final = re.compile(r"[\x21-\x7e]+")
_SHA: Final = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?")


class BundleError(AIReviewerError):
    pass


# --- headers ----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BundleHeader:
    version: int
    capabilities: Mapping[str, str]
    prerequisites: tuple[str, ...]
    refs: Mapping[str, str]  # ref name -> object id

    @property
    def self_contained(self) -> bool:
        """Unpackable into an empty repository: no prerequisites and no object filter."""
        return not self.prerequisites and "filter" not in self.capabilities


def case_refs(case_id: str) -> tuple[str, str]:
    return f"{REF_PREFIX}{case_id}/base", f"{REF_PREFIX}{case_id}/head"


def read_bundle_header(path: Path) -> BundleHeader:
    if not path.is_file():
        raise BundleError(f"bundle not found: {path}")
    with path.open("rb") as handle:
        return parse_bundle_header(handle.read(MAX_HEADER_BYTES))


def parse_bundle_header(data: bytes) -> BundleHeader:
    end = data.find(b"\n\n")
    if end < 0:
        if len(data) >= MAX_HEADER_BYTES:
            raise BundleError(f"bundle header is longer than {MAX_HEADER_BYTES} bytes")
        raise BundleError("bundle header is not terminated by an empty line")
    signature, *lines = data[:end].split(b"\n")
    version = _SIGNATURES.get(signature)
    if version is None:
        raise BundleError("not a v2 or v3 git bundle")
    capabilities: dict[str, str] = {}
    prerequisites: list[str] = []
    refs: dict[str, str] = {}
    for raw in lines:
        if raw.startswith(b"@"):
            if version < 3 or prerequisites or refs:
                raise BundleError("bundle capability in the wrong place")
            key, _, value = _ascii(raw[1:]).partition("=")
            capabilities[key] = value
            continue
        expected = _HEX_LENGTH.get(capabilities.get("object-format", "sha1"))
        if expected is None:
            raise BundleError("unknown bundle object format")
        if raw.startswith(b"-"):
            sha = _ascii(raw[1 : 1 + expected])
            if not _is_sha(sha, expected) or raw[1 + expected : 2 + expected] not in (b"", b" "):
                raise BundleError("malformed prerequisite line in bundle header")
            prerequisites.append(sha)
            continue
        text = _ascii(raw)
        sha, _, name = text.partition(" ")
        if not _is_sha(sha, expected) or not _REF_NAME.fullmatch(name):
            raise BundleError("malformed reference line in bundle header")
        if name in refs:
            raise BundleError(f"duplicate reference {name} in bundle header")
        refs[name] = sha
    return BundleHeader(version, capabilities, tuple(prerequisites), refs)


def _ascii(raw: bytes) -> str:
    try:
        return raw.decode("ascii")
    except UnicodeDecodeError:
        raise BundleError("bundle header line is not ASCII") from None


def _is_sha(text: str, length: int) -> bool:
    return len(text) == length and _SHA.fullmatch(text) is not None


def bundle_problems(eval_dir: Path, case: Case) -> list[str]:
    """Why a case's bundle is unusable (empty when it is fine)."""
    path = eval_dir / case.bundle
    if not path.is_file():
        return [f"bundle: {case.bundle} not found"]
    size = path.stat().st_size
    problems = []
    if size > MAX_BUNDLE_BYTES:
        problems.append(
            f"bundle: {case.bundle} is {size} bytes ({size / 2**20:.1f} MB); "
            f"the limit is {MAX_BUNDLE_BYTES // 2**20} MB"
        )
    try:
        header = read_bundle_header(path)
    except BundleError as exc:
        return [*problems, f"bundle: {case.bundle}: {exc}"]
    if not header.self_contained:
        problems.append(f"bundle: {case.bundle} is not self-contained (prerequisites or a filter)")
    for side, ref, expected in zip(
        ("base", "head"),
        case_refs(case.id),
        (case.bundle_base_sha, case.bundle_head_sha),
        strict=True,
    ):
        actual = header.refs.get(ref)
        if actual is None:
            problems.append(f"bundle: {case.bundle} has no {ref}")
        elif actual != expected:
            problems.append(
                f"bundle: {ref} is {actual[:12]}, but the case says "
                f"bundle_{side}_sha {expected[:12]}"
            )
    return problems


# --- building ---------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BundleInfo:
    base_sha: str
    head_sha: str
    size_bytes: int
    written: bool  # False when an identical bundle was already in place


def build_seed_bundle(
    case_id: str,
    base_dir: Path,
    head_dir: Path,
    out_path: Path,
    *,
    title: str = DEFAULT_PR_TITLE,
    body: str = "",
    ignore: GitIgnoreSpec | None = None,
    max_bytes: int = MAX_BUNDLE_BYTES,
) -> BundleInfo:
    """Snapshot two seed trees as base and head commits and bundle them."""
    base_files = collect_tree(base_dir, ignore)
    head_files = collect_tree(head_dir, ignore)
    with tempfile.TemporaryDirectory(prefix="aireview-seed-") as tmp:
        repo = Path(tmp) / "repo.git"
        run_git(["init", "-q", "--bare", str(repo)])
        base_tree = _write_tree(repo, base_dir, base_files)
        head_tree = _write_tree(repo, head_dir, head_files)
        if base_tree == head_tree:
            raise BundleError(f"{case_id}: base and head trees are identical")
        base, head = _snapshot_commits(repo, base_tree, head_tree, _message(title, body))
        return _write_bundle(repo, case_id, base, head, out_path, max_bytes, Path(tmp))


def build_upstream_bundle(
    case_id: str,
    repo_dir: Path,
    base_sha: str,
    head_sha: str,
    out_path: Path,
    *,
    title: str = DEFAULT_PR_TITLE,
    body: str = "",
    max_bytes: int = MAX_BUNDLE_BYTES,
) -> BundleInfo:
    """Snapshot two upstream commits' trees (not their history) into a two-commit bundle.

    The upstream clone is only read: a temporary repository borrows its objects through
    `objects/info/alternates`.
    """
    common = (
        run_git(["rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=repo_dir)
        .decode()
        .strip()
    )
    trees = []
    for sha in (base_sha, head_sha):
        if not _SHA.fullmatch(sha):
            raise BundleError(f"{sha!r} is not a commit SHA")
        try:
            kind = run_git(["cat-file", "-t", sha], cwd=repo_dir).decode().strip()
        except GitError:
            kind = "missing"
        if kind != "commit":
            raise BundleError(f"{sha} is not a commit in {repo_dir}")
        trees.append(run_git(["rev-parse", f"{sha}^{{tree}}"], cwd=repo_dir).decode().strip())
    with tempfile.TemporaryDirectory(prefix="aireview-upstream-") as tmp:
        repo = Path(tmp) / "repo.git"
        run_git(["init", "-q", "--bare", str(repo)])
        (repo / "objects" / "info" / "alternates").write_text(
            str(Path(common) / "objects") + "\n", encoding="utf-8"
        )
        base, head = _snapshot_commits(repo, trees[0], trees[1], _message(title, body))
        return _write_bundle(repo, case_id, base, head, out_path, max_bytes, Path(tmp))


def _message(title: str, body: str) -> str:
    return f"{title}\n\n{body}\n" if body else f"{title}\n"


def _write_tree(repo: Path, root: Path, files: Sequence[str]) -> str:
    """Write the files' exact bytes (no filters, no attributes) and return the tree id."""
    git_dir = ["--git-dir", str(repo)]
    paths = "\n".join(str(root / f) for f in files).encode() + b"\n"
    shas = (
        run_git([*git_dir, "hash-object", "-w", "--no-filters", "--stdin-paths"], input_bytes=paths)
        .decode()
        .split()
    )
    entries = b"".join(
        f"{_mode(root / f)} {sha}\t{f}".encode() + b"\0" for f, sha in zip(files, shas, strict=True)
    )
    index = {"GIT_INDEX_FILE": str(repo / "snapshot.index")}
    if (repo / "snapshot.index").exists():
        (repo / "snapshot.index").unlink()
    run_git(
        [*git_dir, "update-index", "-z", "--add", "--index-info"], input_bytes=entries, env=index
    )
    return run_git([*git_dir, "write-tree"], env=index).decode().strip()


def _mode(path: Path) -> str:
    return "100755" if path.stat().st_mode & stat.S_IXUSR else "100644"


def _snapshot_commits(repo: Path, base_tree: str, head_tree: str, message: str) -> tuple[str, str]:
    git_dir = ["--git-dir", str(repo)]
    base = run_git(
        [*git_dir, "commit-tree", base_tree, "-F", "-"],
        input_bytes=f"{BASE_MESSAGE}\n".encode(),
        env=_SNAPSHOT_ENV,
    )
    head = run_git(
        [*git_dir, "commit-tree", head_tree, "-p", base.decode().strip(), "-F", "-"],
        input_bytes=message.encode(),
        env=_SNAPSHOT_ENV,
    )
    return base.decode().strip(), head.decode().strip()


def _write_bundle(
    repo: Path, case_id: str, base: str, head: str, out_path: Path, max_bytes: int, tmp: Path
) -> BundleInfo:
    base_ref, head_ref = case_refs(case_id)
    if out_path.is_file():
        try:
            existing = read_bundle_header(out_path)
        except BundleError:
            existing = None
        if (
            existing is not None
            and existing.self_contained
            and existing.refs
            == {
                base_ref: base,
                head_ref: head,
            }
        ):
            return BundleInfo(base, head, out_path.stat().st_size, written=False)
    git_dir = ["--git-dir", str(repo)]
    run_git([*git_dir, "update-ref", base_ref, base])
    run_git([*git_dir, "update-ref", head_ref, head])
    staged = tmp / "out.bundle"
    run_git([*git_dir, "bundle", "create", "--quiet", str(staged), base_ref, head_ref])
    size = staged.stat().st_size
    if size > max_bytes:
        raise BundleError(f"{case_id}: the bundle is {size} bytes; the limit is {max_bytes} bytes")
    header = read_bundle_header(staged)
    if not header.self_contained or header.refs != {base_ref: base, head_ref: head}:
        raise BundleError(f"{case_id}: git wrote an unexpected bundle header")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    partial = out_path.with_name(out_path.name + ".partial")
    shutil.copyfile(staged, partial)
    os.replace(partial, out_path)
    return BundleInfo(base, head, size, written=True)


# --- reading code from bundles ------------------------------------------------------------------


@dataclass
class BundleCodeLookup:
    """CodeLookup over case bundles: head side from bundle_head_sha, base from bundle_base_sha.

    Each bundle is fetched once into a temporary bare repository; files are read with
    `git cat-file blob`, which applies no filters or attributes. Any problem (missing or
    broken bundle, unknown path, oversized file) gives None, never an exception.
    """

    eval_dir: Path
    max_source_bytes: int = MAX_SOURCE_BYTES
    _tmp: tempfile.TemporaryDirectory[str] | None = field(default=None, init=False, repr=False)
    _repos: dict[Path, Path | None] = field(default_factory=dict, init=False, repr=False)

    def lines(
        self, case: Case, path: str, side: Side | str, start: int, end: int
    ) -> list[tuple[int, str]] | None:
        if not _plain_repo_path(path):
            return None
        repo = self._repo_for(case)
        if repo is None:
            return None
        sha = case.bundle_head_sha if Side(side) is Side.RIGHT else case.bundle_base_sha
        spec = f"{sha}:{path}"
        git_dir = ["--git-dir", str(repo)]
        try:
            if run_git([*git_dir, "cat-file", "-t", spec]).decode().strip() != "blob":
                return None
            if int(run_git([*git_dir, "cat-file", "-s", spec])) > self.max_source_bytes:
                return None
            data = run_git([*git_dir, "cat-file", "blob", spec])
        except (GitError, ValueError):
            return None
        text = data.decode("utf-8", errors="replace").splitlines()
        first, last = max(start, 1), min(end, len(text))
        return [(n, text[n - 1]) for n in range(first, last + 1)]

    def _repo_for(self, case: Case) -> Path | None:
        bundle = (self.eval_dir / case.bundle).resolve()
        if bundle in self._repos:
            return self._repos[bundle]
        repo: Path | None = None
        if bundle.is_relative_to(self.eval_dir.resolve()):
            try:
                if read_bundle_header(bundle).self_contained:
                    if self._tmp is None:
                        self._tmp = tempfile.TemporaryDirectory(prefix="aireview-lookup-")
                    repo = Path(self._tmp.name) / f"{len(self._repos)}.git"
                    run_git(["init", "-q", "--bare", str(repo)])
                    run_git(
                        [
                            "--git-dir",
                            str(repo),
                            "fetch",
                            "-q",
                            str(bundle),
                            f"{REF_PREFIX}*:{REF_PREFIX}*",
                        ]
                    )
            except (BundleError, GitError):
                repo = None
        self._repos[bundle] = repo
        return repo

    def close(self) -> None:
        if self._tmp is not None:
            self._tmp.cleanup()
            self._tmp = None
        self._repos.clear()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


def _plain_repo_path(path: str) -> bool:
    if not path or path.startswith(("/", "-")) or "\\" in path:
        return False
    if any(_is_control(c) for c in path):
        return False
    return all(part not in ("", ".", "..") for part in path.split("/"))


def _is_control(char: str) -> bool:
    return ord(char) < 0x20 or ord(char) == 0x7F
