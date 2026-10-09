from fastapi import APIRouter, Depends, HTTPException

from shop.schemas.products import ProductOut
from shop.services.catalog import CatalogService
from shop.services.deps import get_catalog_service
from shop.services.errors import NotFound

router = APIRouter(prefix="/products", tags=["products"])


@router.get("")
def list_products(catalog: CatalogService = Depends(get_catalog_service)) -> list[ProductOut]:
    return [ProductOut.model_validate(p) for p in catalog.list_products()]


@router.get("/{product_id}")
def get_product(
    product_id: int, catalog: CatalogService = Depends(get_catalog_service)
) -> ProductOut:
    try:
        product = catalog.get_product(product_id)
    except NotFound:
        raise HTTPException(status_code=404, detail="product not found") from None
    return ProductOut.model_validate(product)
