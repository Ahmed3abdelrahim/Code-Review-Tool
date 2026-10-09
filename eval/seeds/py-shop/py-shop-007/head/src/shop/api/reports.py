from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from shop.db.session import get_session
from shop.schemas.reports import LowStockOut, SalesSummaryOut
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
        start=start, end=end, order_count=summary.order_count, revenue=summary.revenue
    )


@router.get("/low-stock")
def low_stock(
    threshold: int = Query(5, ge=0), session: Session = Depends(get_session)
) -> list[LowStockOut]:
    rows = session.execute(
        text(
            "SELECT sku, name, stock FROM products "
            "WHERE stock <= :threshold ORDER BY stock, sku"
        ),
        {"threshold": threshold},
    ).all()
    return [LowStockOut(sku=row.sku, name=row.name, stock=row.stock) for row in rows]
