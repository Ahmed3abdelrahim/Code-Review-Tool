class ShopError(Exception):
    """Base class for errors the API turns into client responses."""


class NotFound(ShopError):
    """The requested object does not exist."""


class InvalidRequest(ShopError):
    """The request is well-formed but not allowed."""
