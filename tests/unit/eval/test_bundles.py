"""Git bundle headers, parsed without git (D21)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest

from aireviewer.eval.bundles import (
    MAX_BUNDLE_BYTES,
    MAX_HEADER_BYTES,
    MAX_TOTAL_BUNDLE_BYTES,
    BundleError,
    bundle_problems,
    case_refs,
    parse_bundle_header,
    read_bundle_header,
)

pytestmark = pytest.mark.p0

A, B, C = "a" * 40, "b" * 40, "c" * 40


def bundle(*lines: str, version: int = 2) -> bytes:
    return (f"# v{version} git bundle\n" + "".join(f"{x}\n" for x in lines) + "\n").encode() + (
        b"PACK\x00\x00\x00\x02binary pack data"
    )


def test_limits() -> None:
    assert MAX_BUNDLE_BYTES == 5 * 1024 * 1024
    assert MAX_TOTAL_BUNDLE_BYTES == 100 * 1024 * 1024


def test_header_v2_and_v3() -> None:
    header = parse_bundle_header(bundle(f"{A} refs/aireview/x/base", f"{B} refs/aireview/x/head"))
    assert header.version == 2
    assert header.capabilities == {}
    assert header.prerequisites == ()
    assert header.refs == {"refs/aireview/x/base": A, "refs/aireview/x/head": B}
    assert header.self_contained

    v3 = parse_bundle_header(bundle("@object-format=sha1", f"{A} refs/heads/main", version=3))
    assert (v3.version, v3.capabilities, v3.refs) == (
        3,
        {"object-format": "sha1"},
        {"refs/heads/main": A},
    )

    sha256 = "d" * 64
    v3_256 = parse_bundle_header(
        bundle("@object-format=sha256", f"{sha256} refs/heads/main", version=3)
    )
    assert v3_256.refs == {"refs/heads/main": sha256}


def test_prerequisites_detected() -> None:
    header = parse_bundle_header(bundle(f"-{C} some commit subject", f"{A} refs/heads/main"))
    assert header.prerequisites == (C,)
    assert not header.self_contained
    # A filtered (partial) bundle is not self-contained either.
    filtered = parse_bundle_header(bundle("@filter=blob:none", f"{A} refs/heads/main", version=3))
    assert not filtered.self_contained


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"PACK....",
        b"# v4 git bundle\n\nPACK",
        b"# v2 git bundle\n" + f"{A} refs/heads/main\n".encode(),  # no blank line
        bundle("zzzz refs/heads/main"),
        bundle(f"{A[:39]} refs/heads/main"),
        bundle(f"{A}"),  # ref without a name
        bundle(f"{A} refs/heads/main", f"{B} refs/heads/main"),  # duplicate ref
        bundle(f"{A} refs/heads/a b"),  # space inside a ref name
        bundle("@object-format=sha1", f"{A} refs/heads/main"),  # capability in v2
        bundle("@object-format=sha256", f"{A} refs/heads/main", version=3),  # length mismatch
        b"# v2 git bundle\n" + b"\xff\xfe refs/heads/main\n\nPACK",
    ],
)
def test_malformed_header_rejected(data: bytes) -> None:
    with pytest.raises(BundleError):
        parse_bundle_header(data)


def test_header_read_is_bounded(tmp_path: Path) -> None:
    path = tmp_path / "huge.bundle"
    path.write_bytes(b"# v2 git bundle\n" + b"x" * (MAX_HEADER_BYTES * 4))
    started = time.monotonic()
    with pytest.raises(BundleError, match="header"):
        read_bundle_header(path)
    assert time.monotonic() - started < 2
    with pytest.raises(BundleError, match="not found"):
        read_bundle_header(tmp_path / "missing.bundle")


def test_case_refs_named_per_case(tmp_path: Path, make_case: Any) -> None:
    assert case_refs("py-shop-001") == (
        "refs/aireview/py-shop-001/base",
        "refs/aireview/py-shop-001/head",
    )
    case = make_case()
    base_ref, head_ref = case_refs(case.id)
    eval_dir = tmp_path / "eval"
    (eval_dir / "bundles").mkdir(parents=True)
    path = eval_dir / case.bundle

    path.write_bytes(
        bundle(f"{case.bundle_base_sha} {base_ref}", f"{case.bundle_head_sha} {head_ref}")
    )
    assert bundle_problems(eval_dir, case) == []

    path.write_bytes(bundle(f"{case.bundle_base_sha} {base_ref}", f"{A} {head_ref}"))
    assert any("head" in p and A[:12] in p for p in bundle_problems(eval_dir, case))

    path.write_bytes(bundle(f"{case.bundle_base_sha} {base_ref}"))
    assert any(head_ref in p for p in bundle_problems(eval_dir, case))

    path.write_bytes(
        bundle(
            f"-{C} parent",
            f"{case.bundle_base_sha} {base_ref}",
            f"{case.bundle_head_sha} {head_ref}",
        )
    )
    assert any("self-contained" in p for p in bundle_problems(eval_dir, case))

    path.write_bytes(b"garbage")
    assert bundle_problems(eval_dir, case)


def test_oversized_bundle_reported(tmp_path: Path, make_case: Any) -> None:
    case = make_case()
    base_ref, head_ref = case_refs(case.id)
    eval_dir = tmp_path / "eval"
    (eval_dir / "bundles").mkdir(parents=True)
    data = bundle(f"{case.bundle_base_sha} {base_ref}", f"{case.bundle_head_sha} {head_ref}")
    (eval_dir / case.bundle).write_bytes(data + b"\0" * MAX_BUNDLE_BYTES)
    assert any("MB" in p or "bytes" in p for p in bundle_problems(eval_dir, case))
