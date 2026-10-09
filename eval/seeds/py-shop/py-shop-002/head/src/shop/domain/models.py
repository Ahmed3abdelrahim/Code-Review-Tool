"""Domain types."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum


class OrderStatus(StrEnum):
    PENDING = "pending"
    PAID = "paid"
    SHIPPED = "shipped"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


@dataclass(frozen=True)
class Product:
    id: int
    sku: str
    name: str
    price: Decimal
    stock: int


@dataclass(frozen=True)
class LineItem:
    product_id: int
    quantity: int
    unit_price: Decimal


@dataclass
class Order:
    id: int
    customer_id: int
    status: OrderStatus
    created_at: datetime
    payment_reference: str | None = None
    items: list[LineItem] = field(default_factory=list)


@dataclass
class Cart:
    customer_id: int
    items: list[LineItem] = field(default_factory=list)
