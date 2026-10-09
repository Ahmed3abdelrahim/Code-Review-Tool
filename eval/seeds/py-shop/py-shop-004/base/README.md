# shop

Small order-management service: catalog, carts, orders and sales reports.

## Layout

- `src/shop/api` - HTTP handlers (FastAPI routers)
- `src/shop/services` - business logic
- `src/shop/repositories` - data access
- `src/shop/db` - engine and sessions
- `src/shop/domain` - domain types
- `src/shop/schemas` - request and response models
- `src/shop/integrations` - clients for external providers

Handlers talk to services only; services get their repositories from a unit of work
(`shop.services.deps`).

## Development

    uv sync
    uv run pytest
    uv run fastapi dev src/shop/main.py
