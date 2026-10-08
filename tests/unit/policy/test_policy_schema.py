"""Policy models (plan section 5.3, D19): defaults, identifiers, globs, paths, detectors."""

from __future__ import annotations

import copy
from importlib import resources
from typing import Any

import pytest
import yaml

from aireviewer.contracts.findings import Category
from aireviewer.contracts.policy import Policy
from aireviewer.policy.loader import PolicyResult, PolicySource, default_policy, load_policy

pytestmark = pytest.mark.p0


def load_doc(doc: dict[str, Any]) -> PolicyResult:
    return load_policy(yaml.safe_dump(doc, sort_keys=False))


def errors_of(doc: dict[str, Any]) -> tuple[str, ...]:
    result = load_doc(doc)
    if result.errors:
        assert result.source is PolicySource.FALLBACK
    else:
        assert result.source is PolicySource.REPO
    return result.errors


def has_error(errors: tuple[str, ...], *fragments: str) -> bool:
    return any(all(f in e for f in fragments) for e in errors)


def layer(name: str, *, may_import: list[str] | None = None) -> dict[str, Any]:
    return {"name": name, "paths": [f"src/{name}/**"], "may_import": may_import or []}


def architecture(**fields: Any) -> dict[str, Any]:
    return {"architecture": fields}


def test_default_policy_valid_and_complete() -> None:
    assert resources.files("aireviewer.policy").joinpath("default_policy.yml").is_file()
    # Sections have no model defaults: the packaged file is the only source of defaults.
    assert all(field.is_required() for field in Policy.model_fields.values())

    policy = default_policy()
    assert policy.version == 1
    assert policy.languages == ("python", "typescript")
    assert policy.exclude_paths == (
        "**/migrations/**",
        "**/generated/**",
        "**/*.min.js",
        "**/vendor/**",
    )
    budgets = policy.budgets
    assert (
        budgets.max_files,
        budgets.max_file_bytes,
        budgets.max_changed_lines,
        budgets.max_llm_input_tokens,
        budgets.max_llm_calls,
    ) == (60, 200_000, 1500, 120_000, 12)
    assert policy.lint.python.select == ("E", "F", "B", "UP", "SIM", "BLE")
    assert policy.lint.python.ignore == ("E501",)
    assert policy.lint.typescript.preset == "recommended"
    assert dict(policy.lint.typescript.rules) == {}
    complexity = policy.complexity
    assert (
        complexity.max_ccn,
        complexity.max_function_lines,
        complexity.max_params,
        complexity.worsen_delta,
    ) == (12, 60, 5, 3)
    assert (policy.duplication.enabled, policy.duplication.min_tokens) == (True, 60)
    arch = policy.architecture
    assert arch.python.source_roots is None  # auto-detect
    assert arch.typescript.tsconfig == "tsconfig.json"
    assert (arch.layers, arch.forbidden) == ((), ())  # repository-specific: none by default
    assert arch.cycles.enabled is True
    assert arch.drift_threshold == 0.7
    assert policy.conventions == ()  # no default conventions
    review = policy.review
    assert set(review.categories) == set(Category)
    assert (review.inline_cap, review.min_inline_severity) == (5, "medium")
    assert review.promote_inline == ()
    assert review.skip_drafts is True
    assert review.check_run.fail_on_tool_error is False


def test_policy_is_immutable() -> None:
    policy = default_policy()
    with pytest.raises(ValueError, match="frozen"):
        policy.budgets.max_files = 1  # type: ignore[misc]


def test_layer_names_unique() -> None:
    errors = errors_of(architecture(layers=[layer("api"), layer("db"), layer("api")]))
    assert has_error(errors, "architecture", "duplicate layer name 'api'"), errors

    for bad in ["API", "1api", "api layer", "", "a" * 65]:
        errors = errors_of(architecture(layers=[layer("db"), {"name": bad, "paths": ["x/**"]}]))
        assert has_error(errors, "architecture.layers[1].name:"), (bad, errors)

    errors = errors_of(architecture(layers=[{"name": "api", "paths": []}]))
    assert has_error(errors, "architecture.layers[0].paths:"), errors


def test_rule_ids_unique() -> None:
    rule = {"id": "no.fastapi", "from": ["src/domain/**"], "to": ["ext:fastapi"]}
    # Deep copies: yaml.safe_dump writes an alias for a repeated object.
    errors = errors_of(architecture(forbidden=[rule, copy.deepcopy(rule)]))
    assert has_error(errors, "duplicate forbidden rule id 'no.fastapi'"), errors

    convention = {"id": "money.decimal-only", "description": "Use Decimal."}
    errors = errors_of({"conventions": [convention, copy.deepcopy(convention)]})
    assert has_error(errors, "duplicate convention id 'money.decimal-only'"), errors

    for bad in ["", "No.Caps", "-leading", "has space", "a" * 101]:
        errors = errors_of({"conventions": [{**convention, "id": bad}]})
        assert has_error(errors, "conventions[0].id:"), (bad, errors)

    assert errors_of({"conventions": [{**convention, "description": ""}]})
    assert errors_of({"conventions": [{**convention, "description": "d" * 501}]})
    # "from" is the only accepted spelling (the Python attribute name is not an alias).
    renamed = {"id": "r", "from_": ["src/**"], "to": ["ext:fastapi"]}
    assert has_error(errors_of(architecture(forbidden=[renamed])), "from_: unknown key")


@pytest.mark.parametrize(
    "glob",
    [
        "",
        "/abs/**",
        "a/../b",
        "..",
        "../x",
        "a\\b",
        "a\\",
        "!vendor/**",
        "a\x00b",
        "a\nb",
        "x" * 257,
    ],
)
def test_invalid_globs_rejected(glob: str) -> None:
    places = {
        "exclude_paths": {"exclude_paths": [glob]},
        "architecture.layers[0].paths[0]": architecture(layers=[{"name": "api", "paths": [glob]}]),
        "architecture.forbidden[0].from[0]": architecture(
            forbidden=[{"id": "r", "from": [glob], "to": ["ext:x"]}]
        ),
        "architecture.forbidden[0].to[0]": architecture(
            forbidden=[{"id": "r", "from": ["src/**"], "to": [glob]}]
        ),
        "conventions[0].paths[0]": {
            "conventions": [{"id": "c", "description": "d", "paths": [glob]}]
        },
    }
    for location, doc in places.items():
        errors = errors_of(doc)
        assert has_error(errors, location.split("[")[0]), (location, errors)


@pytest.mark.parametrize(
    "glob", ["**/*.min.js", "src/app/**", "docs", "*.py", "src/[ab]/*.ts", "a b/**", "**"]
)
def test_valid_globs_accepted(glob: str) -> None:
    assert errors_of({"exclude_paths": [glob]}) == ()


def test_relative_paths_only() -> None:
    ok = architecture(python={"source_roots": ["src", ".", "packages/api/src"]})
    assert errors_of(ok) == ()
    assert errors_of(architecture(typescript={"tsconfig": "web/tsconfig.json"})) == ()

    for bad in ["/src", "../src", "src/../..", "", "a\\b", "src/*", "a\x00"]:
        errors = errors_of(architecture(python={"source_roots": [bad]}))
        assert has_error(errors, "architecture.python.source_roots[0]:"), (bad, errors)
        errors = errors_of(architecture(typescript={"tsconfig": bad}))
        assert has_error(errors, "architecture.typescript.tsconfig:"), (bad, errors)
    errors = errors_of(architecture(python={"source_roots": []}))
    assert has_error(errors, "architecture.python.source_roots:"), errors


def test_forbidden_targets_validated() -> None:
    def rule(*to: str) -> dict[str, Any]:
        return architecture(forbidden=[{"id": "r", "from": ["src/**"], "to": list(to)}])

    ok = rule("ext:fastapi", "ext:sqlalchemy.orm", "ext:@nestjs/core", "ext:lodash", "src/db/**")
    assert errors_of(ok) == ()
    for bad in ["ext:", "ext:bad name", "ext:../x", "ext:@scope/", "ext:a/b/c", "/abs/**"]:
        errors = errors_of(rule(bad))
        assert has_error(errors, "architecture.forbidden[0].to[0]:"), (bad, errors)
    assert errors_of(architecture(forbidden=[{"id": "r", "from": [], "to": ["ext:x"]}]))
    assert errors_of(architecture(forbidden=[{"id": "r", "from": ["src/**"], "to": []}]))
    severity = architecture(
        forbidden=[{"id": "r", "from": ["a/**"], "to": ["ext:x"], "severity": "urgent"}]
    )
    assert has_error(errors_of(severity), "architecture.forbidden[0].severity:")


def test_lint_codes_validated() -> None:
    def python_lint(**fields: Any) -> dict[str, Any]:
        return {"lint": {"python": fields}}

    assert errors_of(python_lint(select=["E", "F401", "ASYNC100", "PLR0913", "ALL"])) == ()
    for bad in ["e501", "E 501", "", "E501;x", "E-501", "ABCDEFGHI1"]:
        errors = errors_of(python_lint(ignore=[bad]))
        assert has_error(errors, "lint.python.ignore[0]:"), (bad, errors)

    def eslint(rules: dict[str, Any]) -> dict[str, Any]:
        return {"lint": {"typescript": {"rules": rules}}}

    good = {"no-console": "warn", "@typescript-eslint/no-explicit-any": "error", "eqeqeq": "off"}
    assert errors_of(eslint(good)) == ()
    for bad_rules in [
        {"no-console": 2},
        {"no-console": "fatal"},
        {"no-console": ["error", {"allow": ["warn"]}]},
        {"Bad Rule": "off"},
        {"../x": "off"},
        {"": "off"},
    ]:
        errors = errors_of(eslint(bad_rules))
        assert has_error(errors, "lint.typescript.rules"), (bad_rules, errors)


def test_set_like_lists_unique() -> None:
    assert has_error(errors_of({"languages": ["python", "python"]}), "languages:", "duplicate")
    errors = errors_of({"review": {"categories": ["lint", "security", "lint"]}})
    assert has_error(errors, "review.categories:", "duplicate"), errors
    assert has_error(errors_of({"languages": []}), "languages:")


def test_detector_must_compile() -> None:
    def convention(detector: Any) -> dict[str, Any]:
        return {"conventions": [{"id": "c", "description": "d", "detector": detector}]}

    assert errors_of(convention("float\\(")) == ()
    assert errors_of(convention(r"(?i)\bfloat\s*\(")) == ()
    for bad in ["(", "[a-", "x" * 501, "", 5]:
        errors = errors_of(convention(bad))
        assert has_error(errors, "conventions[0].detector:"), (bad, errors)
