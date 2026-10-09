from datetime import datetime
from decimal import Decimal

from shop.domain.models import LineItem
from shop.services.pricing import calc_total

from conftest import make_order


def test_calc_total_sums_line_items() -> None:
    order = make_order(
        1,
        datetime(2025, 3, 1),
        LineItem(1, 3, Decimal("1.50")),
        LineItem(2, 2, Decimal("4.20")),
    )
    assert calc_total(order) == Decimal("12.90")


def test_calc_total_of_empty_order_is_zero() -> None:
    assert calc_total(make_order(1, datetime(2025, 3, 1))) == Decimal("0")
