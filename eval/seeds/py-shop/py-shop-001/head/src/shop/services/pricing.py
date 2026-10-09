"""Order arithmetic."""

from decimal import Decimal

from shop.domain.models import Order


def calc_total(order: Order) -> Decimal:
    """Sum of the order's line items."""
    return sum((item.unit_price * item.quantity for item in order.items), Decimal("0"))
