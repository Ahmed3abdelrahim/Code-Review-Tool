from dataclasses import replace

from shop.domain.models import Cart, LineItem
from shop.repositories.unit_of_work import UnitOfWork
from shop.services.errors import InvalidRequest, NotFound

MAX_UNITS_PER_PRODUCT = 99


class CartService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def get_cart(self, customer_id: int) -> Cart:
        return self._uow.carts.get_or_create(customer_id)

    def add_item(self, customer_id: int, product_id: int, quantity: int) -> Cart:
        """Add `quantity` units of a product, merging with an existing line."""
        if quantity < 1:
            raise InvalidRequest("quantity must be at least 1")
        product = self._uow.products.get(product_id)
        if product is None:
            raise NotFound(f"product {product_id}")
        cart = self._uow.carts.get_or_create(customer_id)
        for index, item in enumerate(cart.items):
            if item.product_id == product.id:
                _check_limit(item.quantity + quantity)
                cart.items[index] = replace(item, quantity=item.quantity + quantity)
                return cart
        _check_limit(quantity)
        cart.items.append(LineItem(product.id, quantity, product.price))
        return cart


def _check_limit(quantity: int) -> None:
    if quantity > MAX_UNITS_PER_PRODUCT:
        raise InvalidRequest(f"at most {MAX_UNITS_PER_PRODUCT} units of a product per cart")
