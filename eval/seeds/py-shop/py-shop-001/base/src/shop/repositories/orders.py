"""Order queries."""

from datetime import datetime

from sqlalchemy import Row, text
from sqlalchemy.orm import Session

from shop.domain.models import LineItem, Order, OrderStatus


class OrderRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, order_id: int) -> Order | None:
        row = self._session.execute(
            text(
                "SELECT id, customer_id, status, created_at, payment_reference "
                "FROM orders WHERE id = :id"
            ),
            {"id": order_id},
        ).first()
        return self._with_items(row) if row is not None else None

    def list_for_customer(self, customer_id: int) -> list[Order]:
        rows = self._session.execute(
            text(
                "SELECT id, customer_id, status, created_at, payment_reference "
                "FROM orders WHERE customer_id = :customer_id "
                "ORDER BY created_at DESC, id DESC"
            ),
            {"customer_id": customer_id},
        ).all()
        return [self._with_items(row) for row in rows]

    def list_created_between(
        self, start: datetime, end: datetime, status: OrderStatus
    ) -> list[Order]:
        """Orders with `status` created in [start, end)."""
        rows = self._session.execute(
            text(
                "SELECT id, customer_id, status, created_at, payment_reference "
                "FROM orders WHERE status = :status "
                "AND created_at >= :start AND created_at < :end "
                "ORDER BY created_at"
            ),
            {"status": status.value, "start": start, "end": end},
        ).all()
        return [self._with_items(row) for row in rows]

    def update_status(self, order_id: int, status: OrderStatus) -> None:
        self._session.execute(
            text("UPDATE orders SET status = :status WHERE id = :id"),
            {"status": status.value, "id": order_id},
        )

    def _with_items(self, row: Row) -> Order:
        items = self._session.execute(
            text(
                "SELECT product_id, quantity, unit_price FROM order_items "
                "WHERE order_id = :order_id ORDER BY id"
            ),
            {"order_id": row.id},
        ).all()
        return Order(
            id=row.id,
            customer_id=row.customer_id,
            status=OrderStatus(row.status),
            created_at=row.created_at,
            payment_reference=row.payment_reference,
            items=[LineItem(i.product_id, i.quantity, i.unit_price) for i in items],
        )
