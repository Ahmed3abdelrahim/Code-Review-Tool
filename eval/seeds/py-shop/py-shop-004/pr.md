Track applied discount codes

Adds `POST /orders/{order_id}/quote`, which takes a list of discount codes and returns the order total, the discounted total and which codes were actually applied (unknown codes are skipped, each code counts once). Checkout will use it to show the price before payment.
