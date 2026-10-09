import pytest

from shop.services.cart import CartService
from shop.services.errors import NotFound


def test_add_item_creates_a_line(uow) -> None:
    cart = CartService(uow).add_item(customer_id=7, product_id=1, quantity=2)
    assert [(i.product_id, i.quantity) for i in cart.items] == [(1, 2)]


def test_add_item_merges_with_existing_line(uow) -> None:
    service = CartService(uow)
    service.add_item(customer_id=7, product_id=1, quantity=2)
    cart = service.add_item(customer_id=7, product_id=1, quantity=3)
    assert [(i.product_id, i.quantity) for i in cart.items] == [(1, 5)]


def test_add_unknown_product(uow) -> None:
    with pytest.raises(NotFound):
        CartService(uow).add_item(customer_id=7, product_id=99, quantity=1)
