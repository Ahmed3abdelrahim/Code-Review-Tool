"""Finding fingerprint (plan section 5.5, D20).

    fingerprint = sha256(category, rule_id or normalized_title, canonical_path,
                         enclosing_symbol, normalized_excerpt)[:24]

Line numbers are deliberately excluded, so a finding keeps its fingerprint when code above
it moves. The five fields are encoded as a JSON array before hashing, so no field value can
shift into its neighbour (joining with "|" would make "a|b" + "c" equal "a" + "b|c").
Resolving the enclosing symbol is T2.8's job; callers pass it in.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import Final

from aireviewer.contracts.findings import Category, Finding

__all__ = [
    "FINGERPRINT_LENGTH",
    "digest",
    "finding_fingerprint",
    "fingerprint",
    "fingerprint_fields",
    "normalize_excerpt",
    "normalize_title",
]

FINGERPRINT_LENGTH: Final = 24
TITLE_TOKENS: Final = 8


def normalize_title(title: str) -> str:
    """Lowercase, punctuation and digits removed, first 8 tokens."""
    letters = "".join(c if c.isalpha() else " " for c in title.lower())
    return " ".join(letters.split()[:TITLE_TOKENS])


def normalize_excerpt(excerpt: str) -> str:
    return " ".join(excerpt.split())


def fingerprint_fields(
    *,
    category: Category | str,
    rule_id: str | None,
    title: str,
    canonical_path: str,
    enclosing_symbol: str,
    excerpt: str,
) -> list[str]:
    """The five normalized section 5.5 fields, in order."""
    return [
        str(category),
        rule_id if rule_id else normalize_title(title),
        canonical_path,
        enclosing_symbol,
        normalize_excerpt(excerpt),
    ]


def digest(fields: Sequence[str | int]) -> str:
    """sha256 of the fields encoded as a JSON array, first FINGERPRINT_LENGTH hex digits."""
    encoded = json.dumps(list(fields), ensure_ascii=True, separators=(",", ":")).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()[:FINGERPRINT_LENGTH]


def fingerprint(
    *,
    category: Category | str,
    rule_id: str | None,
    title: str,
    canonical_path: str,
    enclosing_symbol: str,
    excerpt: str,
) -> str:
    return digest(
        fingerprint_fields(
            category=category,
            rule_id=rule_id,
            title=title,
            canonical_path=canonical_path,
            enclosing_symbol=enclosing_symbol,
            excerpt=excerpt,
        )
    )


def finding_fingerprint(
    finding: Finding, *, canonical_path: str | None = None, enclosing_symbol: str = ""
) -> str:
    """Fingerprint of a finding; `canonical_path` defaults to its location's path."""
    return fingerprint(
        category=finding.category,
        rule_id=finding.rule_id,
        title=finding.title,
        canonical_path=canonical_path if canonical_path is not None else finding.location.path,
        enclosing_symbol=enclosing_symbol,
        excerpt=finding.evidence[0].excerpt,
    )
