from fastapi import FastAPI

from shop.api import cart, orders, products, reports

app = FastAPI(title="shop")
app.include_router(products.router)
app.include_router(cart.router)
app.include_router(orders.router)
app.include_router(reports.router)
