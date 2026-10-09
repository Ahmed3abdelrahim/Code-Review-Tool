from decimal import Decimal

from ledger.models import Entry, User


class Ledger:
    def __init__(self) -> None:
        self._entries: dict[int, Entry] = {}
        self._next_id = 1

    def add(self, owner: str, amount: Decimal) -> Entry:
        entry = Entry(self._next_id, owner, amount)
        self._entries[entry.id] = entry
        self._next_id += 1
        return entry

    def delete(self, user: User, entry_id: int) -> None:
        if not user.is_admin:
            raise PermissionError("only admins can delete entries")
        self._entries.pop(entry_id)

    def balance(self, owner: str) -> Decimal:
        return sum(
            (e.amount for e in self._entries.values() if e.owner == owner),
            Decimal("0"),
        )
