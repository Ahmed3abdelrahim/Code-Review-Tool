"""Policy loader (plan section 5.3, T0.4, D19): defaults, merge, safe YAML, version."""

from __future__ import annotations

import copy
import json
import random
import time
from pathlib import Path
from typing import Any

import pytest
import yaml
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from aireviewer.contracts.findings import Severity
from aireviewer.policy.loader import (
    MAX_ERRORS,
    MAX_POLICY_BYTES,
    PolicyResult,
    PolicySource,
    default_policy,
    load_policy,
    merge_policy,
    policy_version,
)

pytestmark = pytest.mark.p0

DEFAULT_VERSION = policy_version(default_policy())


def load_doc(doc: dict[str, Any]) -> PolicyResult:
    return load_policy(yaml.safe_dump(doc, sort_keys=False))


def assert_fallback(result: PolicyResult, *fragments: str) -> None:
    """The file was rejected: defaults apply and one error mentions every fragment."""
    assert result.source is PolicySource.FALLBACK
    assert result.effective == default_policy()
    assert result.version == DEFAULT_VERSION
    assert any(all(f in error for f in fragments) for error in result.errors), result.errors


def assert_valid(result: PolicyResult) -> None:
    assert result.errors == ()
    assert result.source is PolicySource.REPO


# --- AC1 ----------------------------------------------------------------------------------


def test_missing_file_uses_defaults() -> None:
    result = load_policy(None)
    assert result.source is PolicySource.DEFAULT
    assert result.errors == ()
    assert result.effective == default_policy()
    assert result.version == DEFAULT_VERSION
    assert len(result.version) == 16
    assert int(result.version, 16) >= 0


@pytest.mark.parametrize("text", ["", "\n", "   \n\n", "# only a comment\n", "---\n", "--- # c\n"])
def test_empty_file_equals_defaults(text: str) -> None:
    result = load_policy(text)
    assert_valid(result)
    assert result.effective == default_policy()
    assert result.version == DEFAULT_VERSION


def test_invalid_file_source_is_fallback(section_5_3_example: str) -> None:
    assert load_policy(None).source is PolicySource.DEFAULT
    assert load_policy(section_5_3_example).source is PolicySource.REPO
    assert load_policy("budgets: [").source is PolicySource.FALLBACK
    assert load_policy("budgets: {max_files: 0}").source is PolicySource.FALLBACK


# --- AC2 ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "budgets: [",
        "budgets: {max_files: 1",
        "a: b: c",
        "languages: 'unterminated",
        "\tlanguages: [python]",
        "languages: [python]\n  - typescript",
        "---\nlanguages: [python]\n---\nlanguages: [typescript]\n",
        "languages: [python]\x00",
    ],
)
def test_invalid_yaml_falls_back_with_errors(text: str) -> None:
    result = load_policy(text)
    assert_fallback(result)
    assert result.errors
    assert all(isinstance(e, str) and e for e in result.errors)
    # Errors come from the parser's problem description, never its excerpt of the file.
    assert not any("^" in e for e in result.errors)


def test_unknown_key_reported(section_5_3_example: str) -> None:
    assert_fallback(load_policy("budget:\n  max_files: 10\n"), "budget: unknown key")
    assert_fallback(load_policy("budgets:\n  max_file: 10\n"), "budgets.max_file: unknown key")
    typo = section_5_3_example.replace("may_import: [services, schemas]", "may_imports: [x]")
    assert_fallback(load_policy(typo), "architecture.layers[0].may_imports: unknown key")
    # An unknown key is reported even when everything else is valid.
    assert_fallback(load_policy(section_5_3_example + "extra_section: {}\n"), "extra_section")


@pytest.mark.parametrize(
    ("doc", "location"),
    [
        ({"budgets": {"max_files": "many"}}, "budgets.max_files"),
        ({"budgets": [1, 2]}, "budgets"),
        ({"budgets": {"max_files": 0}}, "budgets.max_files"),
        ({"budgets": {"max_llm_calls": 1.5}}, "budgets.max_llm_calls"),
        ({"languages": "python"}, "languages"),
        ({"languages": ["cobol"]}, "languages[0]"),
        ({"review": {"min_inline_severity": "urgent"}}, "review.min_inline_severity"),
        ({"review": {"inline_cap": -1}}, "review.inline_cap"),
        ({"architecture": {"drift_threshold": 1.5}}, "architecture.drift_threshold"),
        ({"architecture": {"layers": {"name": "api"}}}, "architecture.layers"),
        ({"version": 2}, "version"),
        ({"lint": {"typescript": {"preset": "strict"}}}, "lint.typescript.preset"),
    ],
)
def test_wrong_types_reported(doc: dict[str, Any], location: str) -> None:
    assert_fallback(load_doc(doc), f"{location}:")


@pytest.mark.parametrize(
    ("text", "location"),
    [
        ('budgets: {max_files: "60"}', "budgets.max_files"),
        ("review: {inline_cap: true}", "review.inline_cap"),
        ("review: {skip_drafts: 1}", "review.skip_drafts"),
        ('review: {skip_drafts: "yes"}', "review.skip_drafts"),
        ("duplication: {enabled: 'false'}", "duplication.enabled"),
        ("architecture: {drift_threshold: true}", "architecture.drift_threshold"),
    ],
)
def test_scalars_are_not_coerced(text: str, location: str) -> None:
    assert_fallback(load_policy(text), f"{location}:")


def test_lossless_scalars_accepted() -> None:
    result = load_policy("architecture: {drift_threshold: 1}\nreview: {skip_drafts: false}\n")
    assert_valid(result)
    assert result.effective.architecture.drift_threshold == 1.0
    assert result.effective.review.skip_drafts is False


def test_oversized_file_rejected() -> None:
    assert MAX_POLICY_BYTES == 64 * 1024
    at_limit = "# " + "x" * (MAX_POLICY_BYTES - 3) + "\n"
    assert len(at_limit.encode()) == MAX_POLICY_BYTES
    assert_valid(load_policy(at_limit))

    over_limit = "# " + "x" * (MAX_POLICY_BYTES - 2) + "\n"
    assert_fallback(load_policy(over_limit), str(MAX_POLICY_BYTES), "bytes")

    # The limit counts UTF-8 bytes, not characters.
    multibyte = "# " + "é" * (MAX_POLICY_BYTES // 2) + "\n"
    assert len(multibyte) < MAX_POLICY_BYTES < len(multibyte.encode())
    assert_fallback(load_policy(multibyte), str(MAX_POLICY_BYTES))


@pytest.mark.parametrize("text", ["- python\n- typescript\n", "42\n", "just text\n", "[]\n"])
def test_non_mapping_document_rejected(text: str) -> None:
    assert_fallback(load_policy(text), "mapping")


# --- YAML hardening (D19) -----------------------------------------------------------------


def test_yaml_aliases_rejected() -> None:
    text = "exclude_paths: &x ['a/**']\nlint:\n  python:\n    ignore: *x\n"
    assert_fallback(load_policy(text), "alias")

    # A "billion laughs" document is refused at the first alias, not expanded.
    bomb = ["a0: &a0 [x, x, x, x, x, x, x, x, x]"]
    for i in range(1, 10):
        refs = ", ".join([f"*a{i - 1}"] * 9)
        bomb.append(f"a{i}: &a{i} [{refs}]")
    started = time.monotonic()
    assert_fallback(load_policy("\n".join(bomb) + "\n"), "alias")
    assert time.monotonic() - started < 2


def test_duplicate_keys_rejected() -> None:
    nested = "budgets:\n  max_files: 1\n  max_files: 2\n"
    assert_fallback(load_policy(nested), "duplicate key", "max_files")
    top_level = "languages: [python]\nlanguages: [typescript]\n"
    assert_fallback(load_policy(top_level), "duplicate key", "languages")


def test_deep_nesting_rejected() -> None:
    deep = "exclude_paths: " + "[" * 30_000 + "]" * 30_000 + "\n"
    assert len(deep.encode()) <= MAX_POLICY_BYTES
    assert_fallback(load_policy(deep), "nest")
    deep_maps = "a:\n" + "".join("  " * i + f"k{i}:\n" for i in range(1, 40))
    assert_fallback(load_policy(deep_maps), "nest")


@pytest.mark.parametrize(
    "text",
    [
        "exclude_paths: [2024-01-01]\n",
        "exclude_paths: [2024-01-01 10:00:00]\n",
        "exclude_paths: [!!binary aGVsbG8=]\n",
        "exclude_paths: !!set {a, b}\n",
        "exclude_paths: !!omap [{a: 1}]\n",
        "budgets: {max_files: .inf}\n",
        "architecture: {drift_threshold: .nan}\n",
        "1: a\n",
        "on: true\n",
        "? [a, b]\n: c\n",
        "budgets: {null: 1}\n",
    ],
)
def test_non_json_scalars_rejected(text: str) -> None:
    result = load_policy(text)
    assert_fallback(result)


def test_errors_bounded_and_values_not_echoed() -> None:
    many_unknown = {f"unknown_{i:02d}": 1 for i in range(MAX_ERRORS + 10)}
    result = load_doc(many_unknown)
    assert_fallback(result, "unknown_00: unknown key")
    assert len(result.errors) == MAX_ERRORS + 1
    assert result.errors[-1] == "… and 10 more errors"

    secret = "sk-live-0123456789abcdef-SECRET"
    leaky = {
        "budgets": {"max_files": secret},
        "exclude_paths": [f"/{secret}/**"],
        "review": {"min_inline_severity": secret},
        "conventions": [{"id": "c.one", "description": "d", "detector": f"({secret}"}],
    }
    result = load_doc(leaky)
    assert result.source is PolicySource.FALLBACK
    assert len(result.errors) >= 4
    assert not any(secret in e for e in result.errors), result.errors

    long_key = "k" * 500
    result = load_doc({long_key: 1})
    assert_fallback(result, "unknown key")
    assert max(len(e) for e in result.errors) < 120


# --- AC3 ----------------------------------------------------------------------------------

GLOBS = ["src/**", "**/migrations/**", "**/*.min.js", "docs", "tests/fixtures/**"]
_ints = st.integers(min_value=1, max_value=1_000_000)

partial_policies = st.fixed_dictionaries(
    {},
    optional={
        "version": st.just(1),
        "languages": st.lists(st.sampled_from(["python", "typescript"]), min_size=1, unique=True),
        "exclude_paths": st.lists(st.sampled_from(GLOBS), unique=True, max_size=4),
        "budgets": st.fixed_dictionaries(
            {},
            optional=dict.fromkeys(
                (
                    "max_files",
                    "max_file_bytes",
                    "max_changed_lines",
                    "max_llm_input_tokens",
                    "max_llm_calls",
                ),
                _ints,
            ),
        ),
        "complexity": st.fixed_dictionaries(
            {},
            optional=dict.fromkeys(
                ("max_ccn", "max_function_lines", "max_params", "worsen_delta"), _ints
            ),
        ),
        "duplication": st.fixed_dictionaries(
            {}, optional={"enabled": st.booleans(), "min_tokens": _ints}
        ),
        "architecture": st.fixed_dictionaries(
            {},
            optional={
                # Plain decimals: PyYAML reads YAML 1.1, where JSON's "1e-05" is a string.
                "drift_threshold": st.integers(0, 1000).map(lambda n: n / 1000),
                "cycles": st.fixed_dictionaries({"enabled": st.booleans()}),
                "python": st.fixed_dictionaries(
                    {
                        "source_roots": st.lists(
                            st.sampled_from(["src", "lib", "."]), min_size=1, unique=True
                        )
                    }
                ),
            },
        ),
        "review": st.fixed_dictionaries(
            {},
            optional={
                "inline_cap": st.integers(min_value=0, max_value=50),
                "min_inline_severity": st.sampled_from([s.value for s in Severity]),
                "skip_drafts": st.booleans(),
                "check_run": st.fixed_dictionaries({"fail_on_tool_error": st.booleans()}),
            },
        ),
    },
)


def _shuffled(value: Any, rng: random.Random) -> Any:
    """Same mapping, with keys in a random order at every level."""
    if isinstance(value, dict):
        items = list(value.items())
        rng.shuffle(items)
        return {k: _shuffled(v, rng) for k, v in items}
    if isinstance(value, list):
        return [_shuffled(v, rng) for v in value]
    return value


def _render(doc: dict[str, Any], style: int) -> str:
    fresh = json.loads(json.dumps(doc))  # distinct objects: safe_dump must not emit aliases
    match style:
        case 0:
            return yaml.safe_dump(fresh, sort_keys=False, default_flow_style=False)
        case 1:
            return yaml.safe_dump(fresh, sort_keys=False, default_flow_style=True, width=40)
        case 2:
            return yaml.safe_dump(fresh, sort_keys=False, indent=4, explicit_start=True)
        case 3:
            return "# policy\n\n" + json.dumps(fresh, indent=2) + "\n\n# end\n"
        case _:
            return json.dumps(fresh)


@settings(max_examples=150, suppress_health_check=[HealthCheck.too_slow])
@given(doc=partial_policies, rng=st.randoms(use_true_random=False), style=st.integers(0, 4))
def test_version_stable_across_key_order(
    doc: dict[str, Any], rng: random.Random, style: int
) -> None:
    reference = load_policy(yaml.safe_dump(json.loads(json.dumps(doc)), sort_keys=True))
    assert_valid(reference)
    variant = load_policy(_render(_shuffled(doc, rng), style))
    assert_valid(variant)
    assert variant.effective == reference.effective
    assert variant.version == reference.version


# Leaves whose type has no single generic change. Every list, mapping and null leaf of the
# default policy must appear here, so a new field cannot silently escape this test.
NON_SCALAR_CHANGES: dict[tuple[str, ...], Any] = {
    ("languages",): ["python"],
    ("exclude_paths",): ["**/migrations/**"],
    ("lint", "python", "select"): ["E", "F"],
    ("lint", "python", "ignore"): [],
    ("lint", "typescript", "rules"): {"no-console": "warn"},
    ("architecture", "python", "source_roots"): ["src"],
    ("architecture", "layers"): [{"name": "api", "paths": ["src/api/**"], "may_import": []}],
    ("architecture", "forbidden"): [
        {"id": "no.fastapi", "from": ["src/domain/**"], "to": ["ext:fastapi"]}
    ],
    ("conventions",): [{"id": "money.decimal-only", "description": "Use Decimal."}],
    ("review", "categories"): ["correctness", "security"],
    ("review", "promote_inline"): ["C901"],
}
# Leaves that have exactly one valid value, so no value change is possible.
FIXED_LEAVES = {("version",), ("lint", "typescript", "preset")}
STRING_CHANGES: dict[tuple[str, ...], str] = {
    ("architecture", "typescript", "tsconfig"): "web/tsconfig.json",
    ("review", "min_inline_severity"): "high",
}


def _leaves(value: Any, path: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], Any]]:
    if isinstance(value, dict) and path not in NON_SCALAR_CHANGES:
        return [leaf for k, v in value.items() for leaf in _leaves(v, (*path, k))]
    return [(path, value)]


def _changed(path: tuple[str, ...], value: Any) -> Any:
    if path in NON_SCALAR_CHANGES:
        return NON_SCALAR_CHANGES[path]
    if path in STRING_CHANGES:
        return STRING_CHANGES[path]
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    if isinstance(value, float):
        return value / 2 if value else 0.5
    raise AssertionError(f"no change defined for {path} = {value!r}; extend the tables")


def _nested(path: tuple[str, ...], value: Any) -> dict[str, Any]:
    doc: Any = value
    for key in reversed(path):
        doc = {key: doc}
    return doc


def test_version_changes_on_value_change() -> None:
    defaults = default_policy().model_dump(mode="json", by_alias=True)
    leaves = [(p, v) for p, v in _leaves(defaults) if p not in FIXED_LEAVES]
    assert {p for p, _ in leaves} >= set(NON_SCALAR_CHANGES) | set(STRING_CHANGES)

    versions = {}
    for path, value in leaves:
        new_value = _changed(path, value)
        assert new_value != value, path
        result = load_doc(_nested(path, new_value))
        assert_valid(result)
        assert result.version != DEFAULT_VERSION, path
        versions[path] = result.version
    # Different changes give different versions too.
    assert len(set(versions.values())) == len(versions)


# --- AC4 ----------------------------------------------------------------------------------


def test_unknown_layer_reference(section_5_3_example: str) -> None:
    result = load_policy(section_5_3_example)
    assert_valid(result)
    assert [layer.name for layer in result.effective.architecture.layers] == [
        "api",
        "services",
        "repositories",
        "domain",
        "schemas",
        "db",
    ]

    without_db = section_5_3_example.replace(
        '    - name: db\n      paths: ["src/app/db/**"]\n      may_import: [domain]\n', ""
    )
    assert without_db != section_5_3_example
    assert_fallback(load_policy(without_db), "architecture", "unknown layer 'db'")

    typo = section_5_3_example.replace("[repositories, domain, schemas]", "[repository]")
    assert_fallback(load_policy(typo), "architecture", "unknown layer 'repository'")


# --- AC5 ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "template",
    [
        "exclude_paths: !!python/object/apply:os.mkdir ['{marker}']\n",
        "budgets:\n  max_files: !!python/object/apply:os.mkdir ['{marker}']\n",
        "exclude_paths: !!python/object/new:os.mkdir ['{marker}']\n",
        "exclude_paths: !!python/object:argparse.Namespace {{x: '{marker}'}}\n",
        "exclude_paths: !!python/name:os.mkdir ''\n",
        "exclude_paths: !!python/module:os ''\n",
        "exclude_paths: !!python/tuple ['{marker}']\n",
        "exclude_paths: !include '{marker}'\n",
    ],
)
def test_python_object_tag_rejected(template: str, tmp_path: Path) -> None:
    marker = tmp_path / "pwned"
    result = load_policy(template.format(marker=marker))
    assert_fallback(result, "unsupported YAML tag")
    assert not marker.exists()


# --- merge --------------------------------------------------------------------------------


def test_merge_semantics(section_5_3_example: str) -> None:
    base = {"a": {"b": 1, "c": [1, 2], "d": {"e": 1}}, "f": [1], "g": {"h": 1}}
    overlay = {"a": {"c": [3], "d": {"x": 2}}, "f": [], "g": 5, "n": None}
    base_before, overlay_before = copy.deepcopy(base), copy.deepcopy(overlay)
    merged = merge_policy(base, overlay)
    assert merged == {"a": {"b": 1, "c": [3], "d": {"e": 1, "x": 2}}, "f": [], "g": 5, "n": None}
    assert (base, overlay) == (base_before, overlay_before)  # inputs untouched
    merged["a"]["d"]["e"] = 99
    assert base["a"]["d"]["e"] == 1  # result shares no mutable state with the inputs

    defaults = default_policy()
    # Maps merge: one budget changes, the others keep their defaults.
    result = load_policy("budgets:\n  max_files: 10\n")
    assert_valid(result)
    assert result.effective.budgets.max_files == 10
    assert result.effective.budgets.max_llm_calls == defaults.budgets.max_llm_calls
    assert result.effective.lint == defaults.lint

    # Lists replace: the default excludes are dropped, not extended.
    result = load_policy("exclude_paths: ['build/**']\n")
    assert_valid(result)
    assert result.effective.exclude_paths == ("build/**",)

    # Lists of mappings replace wholesale: no element-wise merge.
    layers = merge_policy(
        {"layers": [{"name": "a", "paths": ["a/**"], "may_import": ["b"]}, {"name": "b"}]},
        {"layers": [{"name": "c", "paths": ["c/**"]}]},
    )
    assert layers == {"layers": [{"name": "c", "paths": ["c/**"]}]}
    full = load_policy(section_5_3_example).effective
    assert len(full.architecture.layers) == 6
    assert default_policy().architecture.layers == ()

    # A nested map is merged key by key, also inside lint.
    result = load_policy("lint:\n  typescript:\n    rules: {no-console: warn}\n")
    assert_valid(result)
    assert dict(result.effective.lint.typescript.rules) == {"no-console": "warn"}
    assert result.effective.lint.typescript.preset == defaults.lint.typescript.preset
    assert result.effective.lint.python == defaults.lint.python

    # null replaces too: source_roots null means auto-detect.
    result = load_policy("architecture:\n  python:\n    source_roots: null\n")
    assert_valid(result)
    assert result.effective.architecture.python.source_roots is None

    # null where a mapping is required is an error, not "use the default".
    assert_fallback(load_policy("budgets: null\n"), "budgets:")


# --- never raises -------------------------------------------------------------------------

YAMLISH = st.text(
    alphabet=st.sampled_from(list("abklnpsuy01:-[]{}&*!|>'\"#,?%@`.~ \t\n\\é\x00\x85")),
    max_size=300,
)


@settings(max_examples=300, suppress_health_check=[HealthCheck.too_slow])
@given(text=st.one_of(st.text(max_size=500), YAMLISH))
def test_arbitrary_text_never_raises(text: str) -> None:
    result = load_policy(text)
    assert isinstance(result, PolicyResult)
    if result.errors:
        assert result.source is PolicySource.FALLBACK
        assert result.effective == default_policy()
        assert not any("internal error" in e for e in result.errors), result.errors
    else:
        assert result.source is PolicySource.REPO
