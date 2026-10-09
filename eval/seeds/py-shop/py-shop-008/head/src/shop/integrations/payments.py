"""Client for the payment provider's HTTP API."""

from decimal import Decimal

import httpx


class PaymentError(Exception):
    """The provider rejected the request or could not be reached."""


class PaymentGateway:
    def __init__(self, base_url: str, api_key: str, timeout: float = 10.0) -> None:
        self._client = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    def refund(self, payment_reference: str, amount: Decimal) -> str:
        """Refund `amount` of a captured payment and return the refund id."""
        try:
            response = self._client.post(
                f"/payments/{payment_reference}/refunds", json={"amount": str(amount)}
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise PaymentError(str(exc)) from exc
        return str(response.json()["id"])
