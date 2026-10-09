from dataclasses import dataclass
from decimal import Decimal

from shop.domain.models import Order
from shop.repositories.unit_of_work import UnitOfWork
from shop.services.discounts import apply_discounts
from shop.services.errors import NotFound
from shop.services.pricing import calc_total


@dataclass(frozen=True)
class Quote:
    total: Decimal
    discounted_total: Decimal
    applied_codes: list[str]


class OrderService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def get_order(self, order_id: int) -> Order:
        order = self._uow.orders.get(order_id)
        if order is None:
            raise NotFound(f"order {order_id}")
        return order

    def list_customer_orders(self, customer_id: int) -> list[Order]:
        return self._uow.orders.list_for_customer(customer_id)

    def quote(self, order_id: int, codes: list[str]) -> Quote:
        total = calc_total(self.get_order(order_id))
        discounted, applied = apply_discounts(total, codes)
        return Quote(total=total, discounted_total=discounted, applied_codes=applied)
