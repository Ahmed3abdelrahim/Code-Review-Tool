"""Anchor IDs (plan section 5.2): canonical formatting and strict parsing."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from aireviewer.contracts.anchors import (
    ContextAnchor,
    DiffAnchor,
    LineKind,
    format_anchor,
    parse_anchor,
)
from aireviewer.contracts.findings import Side
from aireviewer.errors import MalformedAnchorId

pytestmark = pytest.mark.p0

# Written independently of the implementation: section 5.2 with canonical numbers.
NUMBER = r"[1-9][0-9]{0,8}"
GRAMMAR = rf"(?:F{NUMBER}:H{NUMBER}:[-+=]{NUMBER}|C{NUMBER}:{NUMBER})"

numbers = st.integers(min_value=1, max_value=999_999_999)
diff_anchors = st.builds(
    DiffAnchor, file=numbers, hunk=numbers, kind=st.sampled_from(LineKind), line=numbers
)
context_anchors = st.builds(ContextAnchor, snippet=numbers, line=numbers)


@given(st.one_of(diff_anchors, context_anchors))
def test_roundtrip(anchor: DiffAnchor | ContextAnchor) -> None:
    assert parse_anchor(format_anchor(anchor)) == anchor


@given(st.from_regex(GRAMMAR, fullmatch=True))
def test_canonical_string_roundtrip(text: str) -> None:
    assert format_anchor(parse_anchor(text)) == text


def test_format_matches_section_5_2() -> None:
    assert format_anchor(DiffAnchor(2, 3, LineKind.ADDED, 42)) == "F2:H3:+42"
    assert format_anchor(DiffAnchor(2, 3, LineKind.DELETED, 42)) == "F2:H3:-42"
    assert format_anchor(DiffAnchor(2, 3, LineKind.CONTEXT, 40)) == "F2:H3:=40"
    assert format_anchor(ContextAnchor(1, 17)) == "C1:17"


def test_side_and_commentable() -> None:
    added, deleted, context = (DiffAnchor(1, 1, kind, 5) for kind in LineKind)
    assert (added.side, added.is_commentable) == (Side.RIGHT, True)
    assert (deleted.side, deleted.is_commentable) == (Side.LEFT, True)
    assert (context.side, context.is_commentable) == (Side.RIGHT, False)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "F",
        "F2",
        "F2:H3",
        "F2:H3:42",
        "F2:H3:*42",
        "F2:H3:+-42",
        "F2:H3:+4a",
        "F2:H3:+42:1",
        "F0:H1:+1",
        "F1:H0:+1",
        "F1:H1:+0",
        "F02:H3:+42",
        "F2:H03:+42",
        "F2:H3:+042",
        "F-1:H3:+42",
        "f2:h3:+42",
        " F2:H3:+42",
        "F2:H3:+42 ",
        "F2:H3:+42\n",
        "F2:H3:+42\x00",
        "F2:H3:+1234567890",
        "F2:H3:+٤٢",  # Arabic-Indic digits must not count as digits
        "F2: H3:+42",
        "C",
        "C1",
        "C0:1",
        "C1:0",
        "C01:5",
        "C1:+5",
        "C1:5:6",
        "H3:+42",
        "src/orders.py:42",
    ],
)
def test_malformed_rejected(text: str) -> None:
    with pytest.raises(MalformedAnchorId):
        parse_anchor(text)


def test_malformed_message_is_bounded() -> None:
    with pytest.raises(MalformedAnchorId) as excinfo:
        parse_anchor("F" * 10_000)
    assert len(str(excinfo.value)) < 200


@pytest.mark.parametrize("bad", [0, -1, 1_000_000_000])
def test_out_of_range_numbers_rejected_at_construction(bad: int) -> None:
    with pytest.raises(MalformedAnchorId):
        DiffAnchor(1, 1, LineKind.ADDED, bad)
    with pytest.raises(MalformedAnchorId):
        ContextAnchor(bad, 1)
