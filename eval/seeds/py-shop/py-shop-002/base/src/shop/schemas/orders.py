from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from shop.domain.models import OrderStatus


class LineItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: int
    quantity: int
    unit_price: Decimal


class OrderOut(BaseModel):
    id: int
    status: OrderStatus
    created_at: datetime
    total: Decimal
    items: list[LineItemOut]
