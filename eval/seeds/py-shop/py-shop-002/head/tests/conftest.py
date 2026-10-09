from datetime import datetime
from decimal import Decimal

import pytest

from shop.domain.models import LineItem, Order, OrderStatus, Product
from shop.repositories.carts import CartRepository


class FakeProducts:
    def __init__(self, products: list[Product]) -> None:
        self._products = {p.id: p for p in products}

    def get(self, product_id: int) -> Product | None:
        return self._products.get(product_id)

    def list_all(self, limit: int = 100) -> list[Product]:
        return sorted(self._products.values(), key=lambda p: p.name)[:limit]

    def search(self, term: str, limit: int = 20) -> list[Product]:
        found = [p for p in self.list_all() if term.lower() in p.name.lower()]
        return found[:limit]


class FakeOrders:
    def __init__(self, orders: list[Order]) -> None:
        self._orders = {o.id: o for o in orders}

    def get(self, order_id: int) -> Order | None:
        return self._orders.get(order_id)

    def list_for_customer(self, customer_id: int) -> list[Order]:
        orders = [o for o in self._orders.values() if o.customer_id == customer_id]
        return sorted(orders, key=lambda o: (o.created_at, o.id), reverse=True)

    def list_created_between(
        self, start: datetime, end: datetime, status: OrderStatus
    ) -> list[Order]:
        orders = self._orders.values()
        return [o for o in orders if o.status is status and start <= o.created_at < end]

    def update_status(self, order_id: int, status: OrderStatus) -> None:
        self._orders[order_id].status = status


class FakeUnitOfWork:
    def __init__(self, products: list[Product], orders: list[Order]) -> None:
        self.products = FakeProducts(products)
        self.orders = FakeOrders(orders)
        self.carts = CartRepository({})


PEN = Product(id=1, sku="PEN-01", name="Pen", price=Decimal("1.50"), stock=40)
NOTEBOOK = Product(id=2, sku="NB-A5", name="Notebook", price=Decimal("4.20"), stock=12)


def make_order(
    order_id: int,
    created_at: datetime,
    *items: LineItem,
    customer_id: int = 7,
    status: OrderStatus = OrderStatus.PAID,
) -> Order:
    return Order(
        id=order_id,
        customer_id=customer_id,
        status=status,
        created_at=created_at,
        items=list(items),
    )


@pytest.fixture
def uow() -> FakeUnitOfWork:
    orders = [
        make_order(1, datetime(2025, 3, 1, 9), LineItem(1, 2, Decimal("1.50"))),
        make_order(2, datetime(2025, 3, 2, 17), LineItem(2, 1, Decimal("4.20"))),
        make_order(
            3, datetime(2025, 3, 5, 12), LineItem(1, 1, Decimal("1.50")), status=OrderStatus.PENDING
        ),
    ]
    return FakeUnitOfWork([PEN, NOTEBOOK], orders)
