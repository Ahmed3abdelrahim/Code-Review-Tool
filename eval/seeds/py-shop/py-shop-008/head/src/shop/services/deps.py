"""FastAPI dependencies: services bound to one unit of work per request."""

import os
from collections.abc import Iterator
from functools import cache

from shop.integrations.payments import PaymentGateway
from shop.repositories.unit_of_work import unit_of_work
from shop.services.cart import CartService
from shop.services.catalog import CatalogService
from shop.services.orders import OrderService
from shop.services.refunds import RefundService
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


@cache
def _payment_gateway() -> PaymentGateway:
    return PaymentGateway(os.environ["PAYMENTS_BASE_URL"], os.environ["PAYMENTS_API_KEY"])


def get_refund_service() -> Iterator[RefundService]:
    with unit_of_work() as uow:
        yield RefundService(uow, _payment_gateway())
