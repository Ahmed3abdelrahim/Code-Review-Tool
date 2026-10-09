from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class SalesSummaryOut(BaseModel):
    start: date
    end: date
    order_count: int
    revenue: Decimal
    average_order_value: Decimal
