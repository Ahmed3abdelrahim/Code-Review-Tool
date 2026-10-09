from shop.domain.models import Product
from shop.repositories.unit_of_work import UnitOfWork
from shop.services.errors import NotFound


class CatalogService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def get_product(self, product_id: int) -> Product:
        product = self._uow.products.get(product_id)
        if product is None:
            raise NotFound(f"product {product_id}")
        return product

    def list_products(self) -> list[Product]:
        return self._uow.products.list_all()
