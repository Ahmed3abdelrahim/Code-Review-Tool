"""Product queries."""

from sqlalchemy import Row, text
from sqlalchemy.orm import Session

from shop.domain.models import Product


def _to_product(row: Row) -> Product:
    return Product(id=row.id, sku=row.sku, name=row.name, price=row.price, stock=row.stock)


class ProductRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, product_id: int) -> Product | None:
        row = self._session.execute(
            text("SELECT id, sku, name, price, stock FROM products WHERE id = :id"),
            {"id": product_id},
        ).first()
        return _to_product(row) if row is not None else None

    def list_all(self, limit: int = 100) -> list[Product]:
        rows = self._session.execute(
            text("SELECT id, sku, name, price, stock FROM products ORDER BY name LIMIT :limit"),
            {"limit": limit},
        ).all()
        return [_to_product(row) for row in rows]
