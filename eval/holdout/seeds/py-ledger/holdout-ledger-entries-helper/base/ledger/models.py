from dataclasses import dataclass
from decimal import Decimal


@dataclass
class User:
    name: str
    is_admin: bool = False


@dataclass
class Entry:
    id: int
    owner: str
    amount: Decimal
