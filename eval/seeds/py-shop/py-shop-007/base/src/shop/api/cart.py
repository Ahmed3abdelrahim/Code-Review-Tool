from fastapi import APIRouter, Depends, HTTPException

from shop.schemas.cart import AddItemIn, CartOut
from shop.services.cart import CartService
from shop.services.deps import get_cart_service
from shop.services.errors import NotFound

router = APIRouter(prefix="/customers/{customer_id}/cart", tags=["cart"])


@router.get("")
def get_cart(customer_id: int, service: CartService = Depends(get_cart_service)) -> CartOut:
    return CartOut.model_validate(service.get_cart(customer_id))


@router.post("/items")
def add_item(
    customer_id: int, body: AddItemIn, service: CartService = Depends(get_cart_service)
) -> CartOut:
    try:
        cart = service.add_item(customer_id, body.product_id, body.quantity)
    except NotFound:
        raise HTTPException(status_code=404, detail="product not found") from None
    return CartOut.model_validate(cart)
