from pydantic import BaseModel, ConfigDict

from shop.schemas.orders import LineItemOut


class AddItemIn(BaseModel):
    product_id: int
    quantity: int = 1


class CartOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    customer_id: int
    items: list[LineItemOut]
