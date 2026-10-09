from fastapi import APIRouter, Depends, HTTPException, Query

from shop.domain.models import Order
from shop.schemas.orders import LineItemOut, OrderOut
from shop.services.deps import get_order_service
from shop.services.errors import NotFound
from shop.services.orders import OrderService
from shop.services.pricing import calc_total

router = APIRouter(tags=["orders"])


def _to_out(order: Order) -> OrderOut:
    return OrderOut(
        id=order.id,
        status=order.status,
        created_at=order.created_at,
        total=calc_total(order),
        items=[LineItemOut.model_validate(item) for item in order.items],
    )


@router.get("/orders/{order_id}")
def get_order(order_id: int, service: OrderService = Depends(get_order_service)) -> OrderOut:
    try:
        order = service.get_order(order_id)
    except NotFound:
        raise HTTPException(status_code=404, detail="order not found") from None
    return _to_out(order)


@router.get("/customers/{customer_id}/orders")
def list_customer_orders(
    customer_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    service: OrderService = Depends(get_order_service),
) -> list[OrderOut]:
    orders = service.list_customer_orders(customer_id, page=page, page_size=page_size)
    return [_to_out(order) for order in orders]
