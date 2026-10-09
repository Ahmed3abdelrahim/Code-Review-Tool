from decimal import Decimal

from shop.services.discounts import apply_discounts


def test_known_code_is_applied() -> None:
    assert apply_discounts(Decimal("100.00"), ["welcome10"]) == (Decimal("90.00"), ["WELCOME10"])


def test_unknown_code_is_ignored() -> None:
    total, _ = apply_discounts(Decimal("20.00"), ["NOPE"])
    assert total == Decimal("20.00")


def test_codes_are_applied_one_after_another() -> None:
    total, _ = apply_discounts(Decimal("100.00"), ["SPRING5"], applied=["WELCOME10"])
    assert total == Decimal("95.00")
