from shop.domain.models import Order
from shop.repositories.unit_of_work import UnitOfWork
from shop.services.errors import NotFound


class OrderService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def get_order(self, order_id: int) -> Order:
        order = self._uow.orders.get(order_id)
        if order is None:
            raise NotFound(f"order {order_id}")
        return order

    def list_customer_orders(self, customer_id: int, page: int, page_size: int) -> list[Order]:
        """One page of the customer's orders, newest first. Pages are numbered from 1."""
        offset = page * page_size
        return self._uow.orders.list_for_customer(customer_id, limit=page_size, offset=offset)
