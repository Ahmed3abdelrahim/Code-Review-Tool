"""Snapshot bundles with real git, in temporary directories only (D21).

Needs the git CLI. These tests never touch this repository: every repository they create
lives under tmp_path.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
import yaml

from aireviewer.eval.bundles import (
    SNAPSHOT_AUTHOR,
    BundleCodeLookup,
    BundleError,
    build_seed_bundle,
    build_upstream_bundle,
    case_refs,
    read_bundle_header,
)
from aireviewer.eval.cases import Case
from aireviewer.eval.cli import main
from aireviewer.eval.git import GitError, run_git

pytestmark = pytest.mark.p0


def write(root: Path, files: dict[str, str | bytes]) -> Path:
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
    return root


def git_text(*args: str, cwd: Path | None = None) -> str:
    return run_git(list(args), cwd=cwd).decode().strip()


def fresh_repo_with(bundle: Path, tmp_path: Path, name: str = "verify") -> Path:
    repo = tmp_path / name
    run_git(["init", "-q", "--bare", str(repo)])
    run_git(["--git-dir", str(repo), "bundle", "verify", "-q", str(bundle)])
    run_git(["--git-dir", str(repo), "fetch", "-q", str(bundle), "refs/aireview/*:refs/aireview/*"])
    return repo


def case_for(bundle_base: str, bundle_head: str, **overrides: Any) -> Case:
    data: dict[str, Any] = {
        "id": "case-one",
        "split": "dev",
        "kind": "defect",
        "language": "python",
        "provenance": "planted",
        "source": {"repo": "https://github.com/example/py-shop", "license": "own"},
        "bundle": "bundles/case-one.bundle",
        "bundle_base_sha": bundle_base,
        "bundle_head_sha": bundle_head,
        "policy": "policies/default.yml",
        "labels": [
            {
                "id": "L1",
                "category": "correctness",
                "severity": "high",
                "path": "src/a.py",
                "lines": [2, 2],
                "description": "d",
            }
        ],
    }
    data.update(overrides)
    return Case.model_validate(data)


def test_seed_bundle_self_contained_and_deterministic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = write(tmp_path / "base", {"src/a.py": "x = 1\n", "README.md": "shop\n"})
    head = write(tmp_path / "head", {"src/a.py": "x = 2\n", "README.md": "shop\n"})
    out = tmp_path / "out" / "case-one.bundle"
    info = build_seed_bundle("case-one", base, head, out, title="Add totals", body="Adds x.")
    assert info.written
    assert info.size_bytes == out.stat().st_size

    header = read_bundle_header(out)
    base_ref, head_ref = case_refs("case-one")
    assert header.refs == {base_ref: info.base_sha, head_ref: info.head_sha}
    assert header.self_contained

    repo = fresh_repo_with(out, tmp_path)
    assert git_text("--git-dir", str(repo), "rev-list", "--count", head_ref) == "2"
    assert git_text("--git-dir", str(repo), "rev-list", "--count", base_ref) == "1"
    author = git_text("--git-dir", str(repo), "log", "-1", "--format=%an <%ae> %at", head_ref)
    assert author.startswith(SNAPSHOT_AUTHOR)
    message = git_text("--git-dir", str(repo), "log", "-1", "--format=%B", head_ref)
    assert message == "Add totals\n\nAdds x."

    # Same trees, another clock and identity in the environment: same commits.
    monkeypatch.setenv("TZ", "Asia/Tokyo")
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Mallory")
    monkeypatch.setenv("GIT_COMMITTER_DATE", "2031-05-05T05:05:05Z")
    again = build_seed_bundle(
        "case-one", base, head, tmp_path / "again.bundle", title="Add totals", body="Adds x."
    )
    assert (again.base_sha, again.head_sha) == (info.base_sha, info.head_sha)

    # Rebuilding an up-to-date bundle leaves the file untouched.
    before = out.stat().st_mtime_ns
    unchanged = build_seed_bundle("case-one", base, head, out, title="Add totals", body="Adds x.")
    assert not unchanged.written
    assert out.stat().st_mtime_ns == before


def test_bundle_lookup_reads_base_and_head(tmp_path: Path) -> None:
    eval_dir = tmp_path / "eval"
    base = write(tmp_path / "base", {"src/a.py": "a1\na2\n", "src/gone.py": "x\n"})
    head = write(tmp_path / "head", {"src/a.py": "a1\nb2\nb3\n"})
    info = build_seed_bundle("case-one", base, head, eval_dir / "bundles" / "case-one.bundle")
    case = case_for(info.base_sha, info.head_sha)
    with BundleCodeLookup(eval_dir) as lookup:
        assert lookup.lines(case, "src/a.py", "RIGHT", 1, 3) == [(1, "a1"), (2, "b2"), (3, "b3")]
        assert lookup.lines(case, "src/a.py", "LEFT", 2, 9) == [(2, "a2")]
        assert lookup.lines(case, "src/gone.py", "RIGHT", 1, 1) is None
        assert lookup.lines(case, "src/gone.py", "LEFT", 1, 1) == [(1, "x")]


@pytest.mark.parametrize(
    "path", ["../x", "/etc/passwd", "-p", "src/../src/a.py", "src", "", "src/a.py\n", "src\\a.py"]
)
def test_bundle_lookup_rejects_bad_paths(tmp_path: Path, path: str) -> None:
    eval_dir = tmp_path / "eval"
    base = write(tmp_path / "base", {"src/a.py": "a\n"})
    head = write(tmp_path / "head", {"src/a.py": "b\n"})
    info = build_seed_bundle("case-one", base, head, eval_dir / "bundles" / "case-one.bundle")
    with BundleCodeLookup(eval_dir) as lookup:
        assert lookup.lines(case_for(info.base_sha, info.head_sha), path, "RIGHT", 1, 1) is None


def test_bundle_lookup_survives_broken_bundles(tmp_path: Path) -> None:
    eval_dir = tmp_path / "eval"
    write(
        eval_dir,
        {"bundles/case-one.bundle": b"# v2 git bundle\n" + b"a" * 40 + b" refs/x\n\nPACKjunk"},
    )
    with BundleCodeLookup(eval_dir) as lookup:
        assert lookup.lines(case_for("a" * 40, "b" * 40), "src/a.py", "RIGHT", 1, 1) is None


def test_upstream_snapshot_preserves_trees(tmp_path: Path) -> None:
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    run_git(["init", "-q"], cwd=upstream)
    identity = ["-c", "user.name=Upstream", "-c", "user.email=up@example.invalid"]
    commits = []
    for n, files in enumerate(
        [{"a.py": "1\n"}, {"a.py": "2\n", "b.py": "b\n"}, {"a.py": "3\n", "link": "unused"}], 1
    ):
        write(upstream, files)
        run_git(["add", "-A"], cwd=upstream)
        run_git([*identity, "commit", "-q", "-m", f"c{n}"], cwd=upstream)
        commits.append(git_text("rev-parse", "HEAD", cwd=upstream))
    refs_before = git_text("for-each-ref", cwd=upstream)

    out = tmp_path / "case-one.bundle"
    info = build_upstream_bundle(
        "case-one", upstream, commits[0], commits[2], out, title="Upgrade a"
    )
    assert {info.base_sha, info.head_sha}.isdisjoint(commits)  # new snapshot commits
    repo = fresh_repo_with(out, tmp_path)
    base_ref, head_ref = case_refs("case-one")
    for ref, original in ((base_ref, commits[0]), (head_ref, commits[2])):
        snapshot_tree = git_text("--git-dir", str(repo), "rev-parse", f"{ref}^{{tree}}")
        assert snapshot_tree == git_text("rev-parse", f"{original}^{{tree}}", cwd=upstream)
    assert git_text("--git-dir", str(repo), "rev-list", "--count", head_ref) == "2"
    assert git_text("for-each-ref", cwd=upstream) == refs_before  # the clone is not modified
    with pytest.raises(BundleError, match="not a commit"):
        build_upstream_bundle("case-one", upstream, "0" * 40, commits[2], tmp_path / "x.bundle")


def test_bundle_size_limit_enforced(tmp_path: Path) -> None:
    base = write(tmp_path / "base", {"a.txt": "a\n"})
    head = write(tmp_path / "head", {"a.txt": "a\n", "noise.bin": os.urandom(50_000)})
    out = tmp_path / "big.bundle"
    with pytest.raises(BundleError, match="limit"):
        build_seed_bundle("case-one", base, head, out, max_bytes=10_000)
    assert not out.exists()


def hook_script(marker: Path) -> str:
    return f"#!/bin/sh\ntouch {marker}\n"


def test_git_ignores_user_configuration_and_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo.git"
    run_git(["init", "-q", "--bare", str(repo)])
    config = tmp_path / "evil.gitconfig"
    config.write_text("[user]\n\tname = Mallory\n", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("HOME", str(write(tmp_path / "home", {".gitconfig": config.read_text()})))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "home"))
    # The user's global configuration is invisible: user.name is not set at all.
    with pytest.raises(GitError):
        run_git(["--git-dir", str(repo), "config", "--get", "user.name"])
    # GIT_DIR from the environment is dropped: outside a repository, git finds none.
    monkeypatch.setenv("GIT_DIR", str(repo))
    outside = tmp_path / "not-a-repo"
    outside.mkdir()
    with pytest.raises(GitError):
        run_git(["rev-parse", "--git-dir"], cwd=outside)


def test_repository_hooks_never_run(tmp_path: Path) -> None:
    repo = tmp_path / "repo.git"
    run_git(["init", "-q", "--bare", str(repo)])
    marker = tmp_path / "hook-ran"
    hook = repo / "hooks" / "reference-transaction"
    hook.write_text(hook_script(marker), encoding="utf-8")
    hook.chmod(0o755)
    empty_tree = run_git(["--git-dir", str(repo), "mktree"], input_bytes=b"").decode().strip()
    commit = (
        run_git(
            ["--git-dir", str(repo), "commit-tree", empty_tree, "-m", "x"],
            env={
                "GIT_AUTHOR_NAME": "t",
                "GIT_AUTHOR_EMAIL": "t@e",
                "GIT_COMMITTER_NAME": "t",
                "GIT_COMMITTER_EMAIL": "t@e",
            },
        )
        .decode()
        .strip()
    )
    run_git(["--git-dir", str(repo), "update-ref", "refs/heads/x", commit])
    assert not marker.exists()


def test_seed_build_unaffected_by_hostile_user_setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = tmp_path / "hook-ran"
    template_hooks = write(
        tmp_path / "template" / "hooks", {"reference-transaction": hook_script(marker)}
    )
    (template_hooks / "reference-transaction").chmod(0o755)
    config = tmp_path / "evil.gitconfig"
    config.write_text(
        f"[init]\n\ttemplateDir = {tmp_path / 'template'}\n[user]\n\tname = Mallory\n"
        "[commit]\n\tgpgSign = true\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "elsewhere"))
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Mallory")
    base = write(tmp_path / "base", {"a.py": "1\n"})
    head = write(tmp_path / "head", {"a.py": "2\n"})
    out = tmp_path / "case-one.bundle"
    build_seed_bundle("case-one", base, head, out)
    assert not marker.exists()
    assert not (tmp_path / "elsewhere").exists()
    monkeypatch.delenv("GIT_DIR")
    repo = fresh_repo_with(out, tmp_path)
    author = git_text("--git-dir", str(repo), "log", "-1", "--format=%an", case_refs("case-one")[1])
    assert "Mallory" not in author


def test_seed_build_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    eval_dir = tmp_path / "eval"
    write(eval_dir, {"policies/default.yml": "version: 1\n"})
    write(
        eval_dir / "seeds" / "py-shop" / "case-one",
        {"base/src/a.py": "a\n", "head/src/a.py": "b\n"},
    )
    write(eval_dir / "seeds" / "py-shop" / "case-two", {"base/x.py": "1\n", "head/x.py": "2\n"})
    case = case_for("1" * 40, "2" * 40).model_dump(mode="json", by_alias=True)
    (eval_dir / "cases").mkdir()
    case_file = eval_dir / "cases" / "case-one.yaml"
    case_file.write_text(yaml.safe_dump(case), encoding="utf-8")

    assert main(["seed-build", "--eval-dir", str(eval_dir)]) == 1
    out = capsys.readouterr().out
    header = read_bundle_header(eval_dir / "bundles" / "case-one.bundle")
    head_sha = header.refs[case_refs("case-one")[1]]
    assert "case-one" in out
    assert "bundle_head_sha" in out
    assert head_sha in out  # tells the value to record
    assert "case-two: no case file" in out
    assert (eval_dir / "bundles" / "case-two.bundle").is_file()

    case["bundle_base_sha"] = header.refs[case_refs("case-one")[0]]
    case["bundle_head_sha"] = head_sha
    case_file.write_text(yaml.safe_dump(case), encoding="utf-8")
    assert main(["seed-build", "--eval-dir", str(eval_dir), "--case", "case-one"]) == 0
    out = capsys.readouterr().out
    assert "case-one" in out
    assert "unchanged" in out
    assert "case-two" not in out
