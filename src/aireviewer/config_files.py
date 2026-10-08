"""Hardened loading of YAML configuration files and readable validation errors (D19, D20).

Used for repository policies (untrusted) and benchmark case files. The loader only builds
JSON-compatible data and never executes anything; error messages give positions, key names
and rules, never the offending values.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Hashable, Sequence
from typing import Any, Final, NoReturn

import yaml
from pydantic import ValidationError

__all__ = [
    "MAX_YAML_DEPTH",
    "ConfigFileError",
    "load_yaml_document",
    "load_yaml_mapping",
    "quote_key",
    "validation_messages",
]

MAX_YAML_DEPTH: Final = 20
_MAX_KEY_CHARS: Final = 64
_PLAIN_KEY: Final = re.compile(r"[A-Za-z0-9_-]+")


class ConfigFileError(Exception):
    """The text cannot become the expected document; `messages` are safe to show."""

    def __init__(self, *messages: str) -> None:
        super().__init__(*messages)
        self.messages = messages


def load_yaml_mapping(text: str, *, max_bytes: int, what: str) -> dict[str, Any]:
    """Parse one YAML document that must be a mapping; empty or comment-only gives {}.

    `what` names the file in messages, for example "policy file".
    """
    document = load_yaml_document(text, max_bytes=max_bytes, what=what)
    if document is None:
        return {}
    if not isinstance(document, dict):
        raise ConfigFileError(f"the top level of the {what} must be a mapping of keys")
    return document


def load_yaml_document(text: str, *, max_bytes: int, what: str) -> Any:
    """Parse one YAML document of any shape (None when empty), with the same hardening."""
    size = len(text.encode("utf-8", errors="surrogatepass"))
    if size > max_bytes:
        raise ConfigFileError(f"the {what} is {size} bytes; the limit is {max_bytes} bytes")
    try:
        loader = _SafeConfigLoader(text)  # the reader rejects unprintable characters here
        try:
            return loader.get_single_data()
        finally:
            loader.dispose()
    except yaml.YAMLError as exc:
        raise ConfigFileError(_yaml_message(exc)) from None


def quote_key(key: object) -> str:
    """A key or tag as it appears in an error message: escaped and bounded."""
    text = str(key)
    if _PLAIN_KEY.fullmatch(text) and len(text) <= _MAX_KEY_CHARS:
        return text
    quoted = json.dumps(text[:_MAX_KEY_CHARS], ensure_ascii=True)
    return quoted + ("…" if len(text) > _MAX_KEY_CHARS else "")


_TYPE_MESSAGES: Final = {
    "extra_forbidden": "unknown key",
    "missing": "required",
    "model_type": "must be a mapping",
    "model_attributes_type": "must be a mapping",
    "dict_type": "must be a mapping",
    "tuple_type": "must be a list",
    "list_type": "must be a list",
}


def validation_messages(exc: ValidationError, *, top_level: str) -> list[str]:
    """`location: message` per error, without input values; `top_level` names loc ()."""
    errors = exc.errors(include_url=False, include_context=False, include_input=False)
    failed_items = {e["loc"][:-1] for e in errors if e["loc"] and isinstance(e["loc"][-1], int)}
    messages = []
    for error in errors:
        loc = error["loc"]
        if error["type"] == "too_short" and loc in failed_items:
            continue  # pydantic counts only the valid items; the item errors say more
        text = _TYPE_MESSAGES.get(error["type"]) or error["msg"]
        text = text.removeprefix("Value error, ").replace("Tuple should", "List should")
        messages.append(f"{_location(loc) or top_level}: {text}")
    return messages


def _location(loc: Sequence[int | str]) -> str:
    parts: list[str] = []
    for item in loc:
        if isinstance(item, int):
            parts.append(f"[{item}]")
        elif item == "[key]":
            parts.append(" (key)")
        else:
            parts.append(("." if parts else "") + quote_key(item))
    return "".join(parts)


class _YAMLProblem(yaml.MarkedYAMLError):
    def __init__(self, problem: str, mark: yaml.Mark | None) -> None:
        super().__init__(problem=problem, problem_mark=mark)


class _SafeConfigLoader(yaml.SafeLoader):
    """SafeLoader that only builds JSON-compatible data.

    Rejects aliases (an alias bomb in a small file still makes merging and validation
    exponential), nesting deeper than MAX_YAML_DEPTH (checked while composing, before a
    RecursionError can happen), duplicate and non-string keys, non-finite floats, and
    every tag outside the JSON-compatible core (python/*, timestamps, binary, sets, local
    tags).
    """

    def __init__(self, stream: str) -> None:
        super().__init__(stream)
        self._depth = 0

    def compose_node(self, parent: yaml.Node | None, index: int) -> yaml.Node | None:
        if self.check_event(yaml.AliasEvent):
            raise _YAMLProblem("YAML aliases (*name) are not supported", self._mark())
        self._depth += 1
        try:
            if self._depth > MAX_YAML_DEPTH:
                raise _YAMLProblem(
                    f"nesting deeper than {MAX_YAML_DEPTH} levels is not supported",
                    self._mark(),
                )
            return super().compose_node(parent, index)
        finally:
            self._depth -= 1

    def _mark(self) -> yaml.Mark | None:
        event = self.peek_event()  # type: ignore[no-untyped-call]
        return event.start_mark if event is not None else None

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Hashable, Any]:
        self.flatten_mapping(node)
        seen: set[str] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=True)
            if not isinstance(key, str):
                raise _YAMLProblem(
                    "keys must be strings (quote keys such as on, yes, no, null or numbers)",
                    key_node.start_mark,
                )
            if key in seen:
                raise _YAMLProblem(f"duplicate key {quote_key(key)}", key_node.start_mark)
            seen.add(key)
        return super().construct_mapping(node, deep=deep)

    def construct_yaml_float(self, node: yaml.ScalarNode) -> float:
        value = super().construct_yaml_float(node)
        if not math.isfinite(value):
            raise _YAMLProblem("numbers must be finite", node.start_mark)
        return value

    def construct_undefined(self, node: yaml.Node) -> NoReturn:
        raise _YAMLProblem(f"unsupported YAML tag {_tag_name(node.tag)}", node.start_mark)

    def construct_unsupported(self, node: yaml.Node) -> NoReturn:
        kind = _UNSUPPORTED_TYPES[node.tag]
        raise _YAMLProblem(
            f"{kind} values are not supported; quote the value to use it as a string",
            node.start_mark,
        )


_CORE_TAG_PREFIX: Final = "tag:yaml.org,2002:"
_UNSUPPORTED_TYPES: Final = {
    f"{_CORE_TAG_PREFIX}timestamp": "date and time",
    f"{_CORE_TAG_PREFIX}binary": "binary",
    f"{_CORE_TAG_PREFIX}set": "set",
    f"{_CORE_TAG_PREFIX}omap": "ordered map",
    f"{_CORE_TAG_PREFIX}pairs": "pairs",
}


def _tag_name(tag: str) -> str:
    """`!!name` for core-schema tags (how they are written), the full tag otherwise."""
    if tag.startswith(_CORE_TAG_PREFIX):
        tag = "!!" + tag.removeprefix(_CORE_TAG_PREFIX)
    return quote_key(tag)


# The base classes registered their own functions; point the tags at the overrides.
_SafeConfigLoader.add_constructor(
    f"{_CORE_TAG_PREFIX}float", _SafeConfigLoader.construct_yaml_float
)
for _tag in _UNSUPPORTED_TYPES:
    _SafeConfigLoader.add_constructor(_tag, _SafeConfigLoader.construct_unsupported)
_SafeConfigLoader.add_constructor(None, _SafeConfigLoader.construct_undefined)  # type: ignore[arg-type]


def _yaml_message(exc: yaml.YAMLError) -> str:
    """Position and problem only; never PyYAML's excerpt of the file."""
    if isinstance(exc, yaml.MarkedYAMLError):
        mark = exc.problem_mark or exc.context_mark
        problem = exc.problem or exc.context or "invalid YAML"
        if exc.context and problem.startswith("but "):  # e.g. "expected X", "but found Y"
            problem = f"{exc.context}, {problem}"
        if mark is None:
            return f"invalid YAML: {problem}"
        return f"invalid YAML at line {mark.line + 1}, column {mark.column + 1}: {problem}"
    if isinstance(exc, yaml.reader.ReaderError):
        return (
            f"invalid YAML at character {exc.position + 1}: "
            "the file contains a character that YAML does not allow"
        )
    return "invalid YAML"
