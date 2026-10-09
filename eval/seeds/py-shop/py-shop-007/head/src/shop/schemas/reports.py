from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class SalesSummaryOut(BaseModel):
    start: date
    end: date
    order_count: int
    revenue: Decimal


class LowStockOut(BaseModel):
    sku: str
    name: str
    stock: int
