"""Repositories that share one database session."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy.orm import Session

from shop.db.session import session_scope
from shop.repositories.carts import CartRepository
from shop.repositories.orders import OrderRepository
from shop.repositories.products import ProductRepository


class UnitOfWork:
    def __init__(self, session: Session) -> None:
        self.orders = OrderRepository(session)
        self.products = ProductRepository(session)
        self.carts = CartRepository()


@contextmanager
def unit_of_work() -> Iterator[UnitOfWork]:
    with session_scope() as session:
        yield UnitOfWork(session)
