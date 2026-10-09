import pytest

from shop.services.cart import MAX_UNITS_PER_PRODUCT, CartService
from shop.services.errors import InvalidRequest, NotFound


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


@pytest.mark.parametrize("quantity", [0, -3])
def test_quantity_must_be_positive(uow, quantity: int) -> None:
    with pytest.raises(InvalidRequest):
        CartService(uow).add_item(customer_id=7, product_id=1, quantity=quantity)


def test_quantity_up_to_the_limit_is_accepted(uow) -> None:
    cart = CartService(uow).add_item(customer_id=7, product_id=1, quantity=MAX_UNITS_PER_PRODUCT)
    assert cart.items[0].quantity == MAX_UNITS_PER_PRODUCT


def test_limit_applies_to_the_merged_line(uow) -> None:
    service = CartService(uow)
    service.add_item(customer_id=7, product_id=1, quantity=MAX_UNITS_PER_PRODUCT - 1)
    with pytest.raises(InvalidRequest):
        service.add_item(customer_id=7, product_id=1, quantity=2)
    assert service.get_cart(7).items[0].quantity == MAX_UNITS_PER_PRODUCT - 1
