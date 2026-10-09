"""Discount codes."""

from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal

RATES = {
    "WELCOME10": Decimal("0.10"),
    "SPRING5": Decimal("0.05"),
}


def apply_discounts(
    total: Decimal, codes: Iterable[str], applied: list[str] = []
) -> tuple[Decimal, list[str]]:
    """Apply each known code at most once.

    Returns the discounted total and the codes that were applied.
    """
    for raw in codes:
        code = raw.strip().upper()
        rate = RATES.get(code)
        if rate is None or code in applied:
            continue
        total -= (total * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        applied.append(code)
    return total, applied
