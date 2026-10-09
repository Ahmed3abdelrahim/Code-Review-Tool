from datetime import datetime
from decimal import Decimal

import pytest

from shop.domain.models import LineItem, OrderStatus
from shop.services.errors import InvalidRequest
from shop.services.refunds import RefundService

from conftest import FakeUnitOfWork, make_order


class RecordingGateway:
    def __init__(self) -> None:
        self.refunds: list[tuple[str, Decimal]] = []

    def refund(self, payment_reference: str, amount: Decimal) -> str:
        self.refunds.append((payment_reference, amount))
        return "re_1"


def test_refund_paid_order() -> None:
    order = make_order(1, datetime(2025, 3, 1), LineItem(1, 2, Decimal("1.50")))
    order.payment_reference = "pay_123"
    uow = FakeUnitOfWork([], [order])
    gateway = RecordingGateway()
    refunded = RefundService(uow, gateway).refund_order(1)
    assert gateway.refunds == [("pay_123", Decimal("3.00"))]
    assert refunded.status is OrderStatus.REFUNDED


def test_pending_order_cannot_be_refunded() -> None:
    order = make_order(1, datetime(2025, 3, 1), status=OrderStatus.PENDING)
    with pytest.raises(InvalidRequest):
        RefundService(FakeUnitOfWork([], [order]), RecordingGateway()).refund_order(1)
