Add product search by name

Adds `GET /products/search?q=` so the storefront search box can look up products by part of their name (case-insensitive, at most 20 results, ordered by name). Blank queries return an empty list.
