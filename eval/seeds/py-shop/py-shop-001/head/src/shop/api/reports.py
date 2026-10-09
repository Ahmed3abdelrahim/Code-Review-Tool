from datetime import date

from fastapi import APIRouter, Depends, HTTPException

from shop.schemas.reports import SalesSummaryOut
from shop.services.deps import get_report_service
from shop.services.reports import ReportService

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/sales")
def sales_summary(
    start: date, end: date, reports: ReportService = Depends(get_report_service)
) -> SalesSummaryOut:
    if end < start:
        raise HTTPException(status_code=422, detail="end must not be before start")
    summary = reports.sales_summary(start, end)
    return SalesSummaryOut(
        start=start,
        end=end,
        order_count=summary.order_count,
        revenue=summary.revenue,
        average_order_value=summary.average_order_value,
    )
