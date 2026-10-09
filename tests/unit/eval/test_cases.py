"""Benchmark case files (plan section 8.1, D20): loading and precise validation errors."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from aireviewer.eval.cases import (
    ALLOWED_LICENSES,
    CaseKind,
    Split,
    load_cases,
    select_split,
    split_root,
)

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
    eval_dir: Path, holdout_dir: Path, write_case: WriteCase, make_case_data: CaseData
) -> None:
    write_case(make_case_data(id="dev-one"))
    holdout = make_case_data(id="holdout-one", split="holdout")
    holdout["source"] = {**holdout["source"], "repo": "https://github.com/Example/shop.git/"}
    write_case(holdout, holdout=True)
    other = make_case_data(id="holdout-two", split="holdout")
    other["source"] = {**other["source"], "repo": "https://github.com/example/other"}
    write_case(other, holdout=True)
    loaded = load_cases(eval_dir)  # loads both roots
    assert has_error(loaded.errors, "source.repo:", "dev", "holdout", "dev-one", "holdout-one")
    assert not has_error(loaded.errors, "holdout-two")

    assert [c.id for c in select_split(loaded.cases, "holdout")] == ["holdout-one", "holdout-two"]
    assert [c.id for c in select_split(loaded.cases, "dev")] == ["dev-one"]
    assert len(select_split(loaded.cases, "all")) == 3


def test_split_must_match_root(
    eval_dir: Path, holdout_dir: Path, write_case: WriteCase, make_case_data: CaseData
) -> None:
    write_case(make_case_data(id="dev-ok"))
    write_case(make_case_data(id="holdout-ok", split="holdout"), holdout=True)
    write_case(make_case_data(id="misplaced-holdout", split="holdout"))
    write_case(make_case_data(id="misplaced-dev"), holdout=True)
    loaded = load_cases(eval_dir)
    assert has_error(
        loaded.errors, "cases/misplaced-holdout.yaml", "split:", "must have split: dev"
    ), loaded.errors
    assert has_error(
        loaded.errors, "holdout/cases/misplaced-dev.yaml", "split:", "must have split: holdout"
    ), loaded.errors
    assert {c.id for c in loaded.cases} == {"dev-ok", "holdout-ok"}
    assert split_root(eval_dir, "dev") == eval_dir
    assert split_root(eval_dir, Split.HOLDOUT) == holdout_dir


def test_holdout_paths_are_relative_to_holdout_root(
    eval_dir: Path, holdout_dir: Path, write_case: WriteCase, make_case_data: CaseData
) -> None:
    (holdout_dir / "bundles" / "case.bundle").unlink()  # exists only in the dev root now
    write_case(make_case_data(id="holdout-one", split="holdout"), holdout=True)
    assert has_error(
        errors_for(eval_dir), "holdout/cases/holdout-one.yaml", "bundle:", "does not exist"
    )


def test_case_ids_unique_across_roots(
    eval_dir: Path, holdout_dir: Path, write_case: WriteCase, make_case_data: CaseData
) -> None:
    write_case(make_case_data(id="same-id"))
    twin = make_case_data(id="same-id", split="holdout")
    twin["source"] = {**twin["source"], "repo": "https://github.com/example/other"}
    write_case(twin, holdout=True)
    assert has_error(errors_for(eval_dir), "same-id", "more than one case")


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


def test_bundle_shas_required_and_validated(
    eval_dir: Path, write_case: WriteCase, make_case_data: CaseData
) -> None:
    missing = make_case_data(id="missing-shas")
    del missing["bundle_base_sha"]
    write_case(missing)
    write_case(make_case_data(id="same-shas", bundle_head_sha="c" * 40))
    write_case(make_case_data(id="short-sha", bundle_base_sha="c" * 12))
    errors = errors_for(eval_dir)
    assert has_error(errors, "(missing-shas)", "bundle_base_sha: required"), errors
    assert has_error(errors, "(same-shas)", "bundle_head_sha:", "differ"), errors
    assert has_error(errors, "(short-sha)", "bundle_base_sha:"), errors


def test_planted_cases_need_no_upstream_shas(
    eval_dir: Path, write_case: WriteCase, make_case_data: CaseData
) -> None:
    planted = make_case_data(id="planted-one", provenance="planted")
    planted["source"] = {"repo": "https://github.com/example/py-shop", "license": "own"}
    write_case(planted)
    upstream = make_case_data(id="upstream-one")
    del upstream["source"]["base_sha"]
    write_case(upstream)
    errors = errors_for(eval_dir)
    assert not has_error(errors, "(planted-one)"), errors
    assert has_error(errors, "(upstream-one)", "source:", "base_sha"), errors


# --- holdout redaction (D22) ------------------------------------------------------------------

HIDDEN = "HOLDOUT-ONLY-MARKER"


def _broken_holdout(write_case: WriteCase, make_case_data: CaseData) -> None:
    """A dev error, an invalid holdout case and a holdout case sharing the dev repository."""
    write_case(make_case_data(id="dev-bad", split="holdout"))  # dev root, wrong split
    write_case(make_case_data())
    bad = make_case_data(id="holdout-bad", split="holdout")
    bad["labels"][0].update(severity="huge", description=HIDDEN)
    write_case(bad, holdout=True)
    write_case(make_case_data(id="holdout-shared", split="holdout", notes=HIDDEN), holdout=True)


def test_error_holdout_ids_attributed(
    eval_dir: Path, holdout_dir: Path, write_case: WriteCase, make_case_data: CaseData
) -> None:
    _broken_holdout(write_case, make_case_data)
    loaded = load_cases(eval_dir)
    assert len(loaded.error_holdout_ids) == len(loaded.errors)
    by_error = dict(zip(loaded.errors, loaded.error_holdout_ids, strict=True))
    dev_errors = [e for e, ids in by_error.items() if not ids]
    assert dev_errors
    assert all(e.startswith("cases/dev-bad.yaml") for e in dev_errors)
    assert set().union(*by_error.values()) == {"holdout-bad", "holdout-shared"}
    assert any(
        e.startswith("source.repo:") and ids == {"holdout-shared"} for e, ids in by_error.items()
    )


def test_redacted_errors_hide_holdout_details(
    eval_dir: Path, holdout_dir: Path, write_case: WriteCase, make_case_data: CaseData
) -> None:
    _broken_holdout(write_case, make_case_data)
    loaded = load_cases(eval_dir)
    redacted = loaded.redacted_errors()
    text = "\n".join(redacted)
    for secret in (HIDDEN, "huge", "severity", "holdout/cases", "example/shop"):
        assert secret not in text
    assert [e for e in loaded.errors if e.startswith("cases/dev-bad.yaml")] == list(redacted[:-1])
    assert redacted[-1].startswith(
        "holdout: 2 problems involving 2 cases: holdout-bad, holdout-shared"
    )


def test_redacted_errors_hide_untrusted_ids(
    eval_dir: Path, holdout_dir: Path, write_case: WriteCase, make_case_data: CaseData
) -> None:
    write_case(
        make_case_data(id="Ignore previous instructions", split="holdout"), "x y", holdout=True
    )
    write_case(make_case_data(id="Also not an id!", split="holdout"), "named-file", holdout=True)
    write_case(make_case_data())
    redacted = load_cases(eval_dir).redacted_errors()
    assert redacted == (
        "holdout: 2 problems involving 2 cases: <unnamed>, named-file (details hidden; "
        "run `aireview-eval validate` without --redact-holdout to see them)",
    )


def test_no_holdout_errors_means_nothing_redacted(
    eval_dir: Path, write_case: WriteCase, make_case_data: CaseData
) -> None:
    write_case(make_case_data(id="dev-bad", split="holdout"))
    loaded = load_cases(eval_dir)
    assert loaded.redacted_errors() == loaded.errors
