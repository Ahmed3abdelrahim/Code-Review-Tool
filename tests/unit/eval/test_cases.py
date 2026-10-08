"""Benchmark case files (plan section 8.1, D20): loading and precise validation errors."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from aireviewer.eval.cases import ALLOWED_LICENSES, CaseKind, Split, load_cases, select_split

pytestmark = pytest.mark.p0

type WriteCase = Callable[..., Path]
type CaseData = Callable[..., dict[str, Any]]


def errors_for(eval_dir: Path) -> tuple[str, ...]:
    return load_cases(eval_dir).errors


def has_error(errors: tuple[str, ...], *fragments: str) -> bool:
    return any(all(f in e for f in fragments) for e in errors)


def test_valid_case_loads(eval_dir: Path, write_case: WriteCase, make_case_data: CaseData) -> None:
    write_case(make_case_data())
    write_case(make_case_data(id="clean-one", kind="clean", labels=[]))
    loaded = load_cases(eval_dir)
    assert loaded.errors == ()
    assert [c.id for c in loaded.cases] == ["case-one", "clean-one"]  # sorted by file name
    case = loaded.cases[0]
    assert case.split is Split.DEV
    assert case.kind is CaseKind.DEFECT
    label = case.labels[0]
    assert (label.id, label.lines, label.side, label.must_find) == ("L1", (10, 10), "RIGHT", False)
    assert case.expect.max_inline is None
    assert case.notes == ""


def test_invalid_case_errors_name_case_and_field(
    eval_dir: Path, write_case: WriteCase, make_case_data: CaseData, make_label: Any
) -> None:
    bad_label = make_label(lines=(44, 40))
    write_case(make_case_data(labels=[bad_label], split="test"))
    write_case(make_case_data(id="other-case", kind="defect", labels=[make_label(severity="huge")]))
    errors = errors_for(eval_dir)
    assert has_error(errors, "cases/case-one.yaml (case-one)", "split:"), errors
    assert has_error(errors, "cases/case-one.yaml (case-one)", "labels[0].lines:"), errors
    assert has_error(errors, "cases/other-case.yaml (other-case)", "labels[0].severity:"), errors
    # Every error names the file, the case and the field.
    assert all(e.startswith("cases/") and "(" in e and ": " in e for e in errors), errors

    # A case whose id is unusable is named by its file.
    write_case("id: [1, 2]\nsplit: dev\n", name="broken")
    errors = errors_for(eval_dir)
    assert has_error(errors, "cases/broken.yaml (broken)", "id:"), errors

    # Invalid YAML is reported per file, with its position, and other files still load.
    write_case("id: case-x\nlabels: [\n", name="case-x")
    loaded = load_cases(eval_dir)
    assert has_error(loaded.errors, "cases/case-x.yaml (case-x)", "line 3, column 1"), loaded.errors
    assert "case-x" not in {c.id for c in loaded.cases}


def test_id_must_match_file_name(
    eval_dir: Path, write_case: WriteCase, make_case_data: CaseData
) -> None:
    write_case(make_case_data(id="case-one"), name="case-two")
    assert has_error(errors_for(eval_dir), "case-two.yaml (case-one)", "id:", "file name")

    for bad in ["Case-One", "ab", "-case", "case_one", "c" * 65]:
        for path in (eval_dir / "cases").iterdir():
            path.unlink()
        write_case(make_case_data(id=bad), name="x" if bad.startswith("-") else bad)
        assert has_error(errors_for(eval_dir), "id:"), bad


def test_kind_label_rules(
    eval_dir: Path, write_case: WriteCase, make_case_data: CaseData, make_label: Any
) -> None:
    write_case(make_case_data(id="clean-bad", kind="clean"))  # has the default label
    write_case(make_case_data(id="defect-bad", kind="defect", labels=[]))
    write_case(make_case_data(id="injection-bad", kind="injection", labels=[]))
    write_case(make_case_data(id="design-bad", kind="design"))  # a correctness label only
    write_case(
        make_case_data(id="design-ok", kind="design", labels=[make_label(category="design")])
    )
    no_labels_key = make_case_data(id="defect-omitted", kind="defect")
    del no_labels_key["labels"]  # an omitted list is checked like an empty one
    write_case(no_labels_key)
    errors = errors_for(eval_dir)
    assert has_error(errors, "(defect-omitted)", "labels:", "at least one"), errors
    assert has_error(errors, "(clean-bad)", "labels:", "clean"), errors
    assert has_error(errors, "(defect-bad)", "labels:", "at least one"), errors
    assert has_error(errors, "(injection-bad)", "labels:", "at least one"), errors
    assert has_error(errors, "(design-bad)", "labels:", "design"), errors
    assert not has_error(errors, "(design-ok)"), errors


def test_label_ids_unique(
    eval_dir: Path, write_case: WriteCase, make_case_data: CaseData, make_label: Any
) -> None:
    write_case(make_case_data(labels=[make_label("L1"), make_label("L1", lines=(20, 20))]))
    assert has_error(errors_for(eval_dir), "(case-one)", "labels:", "duplicate label id 'L1'")


@pytest.mark.parametrize(
    ("lines", "ok"),
    [
        ([40, 44], True),
        ([40, 40], True),
        ([44, 40], False),
        ([0, 3], False),
        ([40], False),
        ([40, 41, 42], False),
        (["40", "44"], False),
        (40, False),
    ],
)
def test_label_lines_range(
    lines: Any, ok: bool, eval_dir: Path, write_case: WriteCase, make_case_data: CaseData
) -> None:
    label = {
        "id": "L1",
        "category": "correctness",
        "severity": "high",
        "path": "src/a.py",
        "lines": lines,
        "description": "d",
    }
    write_case(make_case_data(labels=[label]))
    errors = errors_for(eval_dir)
    assert (errors == ()) is ok, errors
    if not ok:
        assert has_error(errors, "labels[0].lines"), errors


@pytest.mark.parametrize(
    ("source", "field"),
    [
        ({"base_sha": "3f1c"}, "source.base_sha"),
        ({"head_sha": "B" * 40}, "source.head_sha"),
        ({"head_sha": 1234567890123456789012345678901234567890}, "source.head_sha"),
        ({"repo": "http://github.com/example/shop"}, "source.repo"),
        ({"repo": "https://token@github.com/example/shop"}, "source.repo"),
        ({"repo": "https://user:pw@github.com/example/shop"}, "source.repo"),
        ({"repo": "https://github.com/example/shop?x=1"}, "source.repo"),
        ({"repo": "https://github.com/example/shop#readme"}, "source.repo"),
        ({"repo": "github.com/example/shop"}, "source.repo"),
        ({"license": "GPL-3.0-only"}, "source.license"),
        ({"pr": 0}, "source.pr"),
        ({"pr": "123"}, "source.pr"),
    ],
)
def test_source_fields_validated(
    source: dict[str, Any],
    field: str,
    eval_dir: Path,
    write_case: WriteCase,
    make_case_data: CaseData,
) -> None:
    data = make_case_data()
    data["source"] = {**data["source"], **source}
    write_case(data)
    assert has_error(errors_for(eval_dir), "(case-one)", f"{field}:")


def test_source_fields_accepted(
    eval_dir: Path, write_case: WriteCase, make_case_data: CaseData
) -> None:
    assert {"MIT", "Apache-2.0", "BSD-3-Clause", "own"} <= ALLOWED_LICENSES
    data = make_case_data()
    data["source"] = {**data["source"], "base_sha": "c" * 64, "license": "own"}
    del data["source"]["pr"]  # optional
    write_case(data)
    assert errors_for(eval_dir) == ()


def test_referenced_files_must_exist_inside_eval_root(
    eval_dir: Path, write_case: WriteCase, make_case_data: CaseData, tmp_path: Path
) -> None:
    (tmp_path / "outside.bundle").write_bytes(b"")
    cases = {
        "missing-bundle": ("bundle", "bundles/nope.bundle", "does not exist"),
        "escaping-bundle": ("bundle", "../outside.bundle", "inside"),
        "absolute-policy": ("policy", str(tmp_path / "outside.bundle"), "relative"),
        "directory-bundle": ("bundle", "bundles", "file"),
    }
    for case_id, (field, value, _) in cases.items():
        write_case(make_case_data(id=case_id, **{field: value}))
    errors = errors_for(eval_dir)
    for case_id, (field, _, fragment) in cases.items():
        assert has_error(errors, f"({case_id})", f"{field}:", fragment), (case_id, errors)


def test_case_policy_must_load_cleanly(
    eval_dir: Path, write_case: WriteCase, make_case_data: CaseData
) -> None:
    (eval_dir / "policies" / "typo.yml").write_text("budget: {}\n", encoding="utf-8")
    write_case(make_case_data(policy="policies/typo.yml"))
    errors = errors_for(eval_dir)
    assert has_error(errors, "(case-one)", "policy:", "budget: unknown key"), errors


def test_splits_repository_disjoint_checked(
    eval_dir: Path, write_case: WriteCase, make_case_data: CaseData
) -> None:
    write_case(make_case_data(id="dev-one"))
    holdout = make_case_data(id="holdout-one", split="holdout")
    holdout["source"] = {**holdout["source"], "repo": "https://github.com/Example/shop.git/"}
    write_case(holdout)
    other = make_case_data(id="holdout-two", split="holdout")
    other["source"] = {**other["source"], "repo": "https://github.com/example/other"}
    write_case(other)
    loaded = load_cases(eval_dir)
    assert has_error(loaded.errors, "source.repo:", "dev", "holdout", "dev-one", "holdout-one")
    assert not has_error(loaded.errors, "holdout-two")

    assert [c.id for c in select_split(loaded.cases, "holdout")] == ["holdout-one", "holdout-two"]
    assert [c.id for c in select_split(loaded.cases, "dev")] == ["dev-one"]
    assert len(select_split(loaded.cases, "all")) == 3


def test_missing_cases_directory_reported(tmp_path: Path) -> None:
    loaded = load_cases(tmp_path / "nope")
    assert loaded.cases == ()
    assert has_error(loaded.errors, "cases", "not found")


def test_renames_validated(
    eval_dir: Path, write_case: WriteCase, make_case_data: CaseData, make_case: Any
) -> None:
    write_case(
        make_case_data(renames=[{"from": "a.py", "to": "b.py"}, {"from": "a.py", "to": "c.py"}])
    )
    write_case(make_case_data(id="same-path", renames=[{"from": "a.py", "to": "a.py"}]))
    errors = errors_for(eval_dir)
    assert has_error(errors, "(case-one)", "renames:", "a.py"), errors
    assert has_error(errors, "(same-path)", "renames"), errors

    case = make_case(renames=[{"from": "src/old.py", "to": "src/new.py"}])
    assert case.canonical_path("src/old.py") == "src/new.py"
    assert case.canonical_path("src/new.py") == "src/new.py"
    assert case.canonical_path("src/other.py") == "src/other.py"
