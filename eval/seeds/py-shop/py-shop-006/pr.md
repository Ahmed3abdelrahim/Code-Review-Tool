Validate quantity when adding to cart

Adding a product to the cart now rejects quantities below 1 and caps each product at 99 units per cart (including units already in the cart). The API answers 422 with the reason.
