"""FastAPI dependencies: services bound to one unit of work per request."""

from collections.abc import Iterator

from shop.repositories.unit_of_work import unit_of_work
from shop.services.cart import CartService
from shop.services.catalog import CatalogService
from shop.services.orders import OrderService
from shop.services.reports import ReportService


def get_catalog_service() -> Iterator[CatalogService]:
    with unit_of_work() as uow:
        yield CatalogService(uow)


def get_cart_service() -> Iterator[CartService]:
    with unit_of_work() as uow:
        yield CartService(uow)


def get_order_service() -> Iterator[OrderService]:
    with unit_of_work() as uow:
        yield OrderService(uow)


def get_report_service() -> Iterator[ReportService]:
    with unit_of_work() as uow:
        yield ReportService(uow)
