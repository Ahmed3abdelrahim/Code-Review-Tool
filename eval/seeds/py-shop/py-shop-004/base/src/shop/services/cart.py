from dataclasses import replace

from shop.domain.models import Cart, LineItem
from shop.repositories.unit_of_work import UnitOfWork
from shop.services.errors import NotFound


class CartService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def get_cart(self, customer_id: int) -> Cart:
        return self._uow.carts.get_or_create(customer_id)

    def add_item(self, customer_id: int, product_id: int, quantity: int) -> Cart:
        """Add `quantity` units of a product, merging with an existing line."""
        product = self._uow.products.get(product_id)
        if product is None:
            raise NotFound(f"product {product_id}")
        cart = self._uow.carts.get_or_create(customer_id)
        for index, item in enumerate(cart.items):
            if item.product_id == product.id:
                cart.items[index] = replace(item, quantity=item.quantity + quantity)
                return cart
        cart.items.append(LineItem(product.id, quantity, product.price))
        return cart
