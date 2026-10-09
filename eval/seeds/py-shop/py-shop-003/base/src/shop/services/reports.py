from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from shop.domain.models import OrderStatus
from shop.repositories.unit_of_work import UnitOfWork
from shop.services.pricing import calc_total


@dataclass(frozen=True)
class SalesSummary:
    order_count: int
    revenue: Decimal


class ReportService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def sales_summary(self, start: date, end: date) -> SalesSummary:
        """Paid orders created from `start` up to and including `end`."""
        orders = self._uow.orders.list_created_between(
            datetime.combine(start, time.min),
            datetime.combine(end + timedelta(days=1), time.min),
            OrderStatus.PAID,
        )
        revenue = sum((calc_total(order) for order in orders), Decimal("0"))
        return SalesSummary(order_count=len(orders), revenue=revenue)
