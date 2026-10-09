from datetime import date
from decimal import Decimal

from shop.services.reports import ReportService


def test_sales_summary_counts_paid_orders_in_range(uow) -> None:
    summary = ReportService(uow).sales_summary(date(2025, 3, 1), date(2025, 3, 31))
    assert summary.order_count == 2
    assert summary.revenue == Decimal("7.20")
    assert summary.average_order_value == Decimal("3.60")


def test_sales_summary_end_date_is_inclusive(uow) -> None:
    summary = ReportService(uow).sales_summary(date(2025, 3, 1), date(2025, 3, 1))
    assert summary.order_count == 1
