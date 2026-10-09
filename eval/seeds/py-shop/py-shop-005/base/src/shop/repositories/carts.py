"""Carts are kept in memory until checkout."""

from shop.domain.models import Cart


class CartRepository:
    def __init__(self, carts: dict[int, Cart] | None = None) -> None:
        self._carts = carts if carts is not None else _CARTS

    def get_or_create(self, customer_id: int) -> Cart:
        cart = self._carts.get(customer_id)
        if cart is None:
            cart = self._carts[customer_id] = Cart(customer_id=customer_id)
        return cart


_CARTS: dict[int, Cart] = {}
