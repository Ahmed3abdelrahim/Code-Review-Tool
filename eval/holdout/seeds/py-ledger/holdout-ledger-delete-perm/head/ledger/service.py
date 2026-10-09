from decimal import Decimal

from ledger.models import Entry, User


class Ledger:
    def __init__(self) -> None:
        self._entries: dict[int, Entry] = {}
        self._next_id = 1
	self.audit_log: list[str] = []

    def add(self, owner: str, amount: Decimal) -> Entry:
        entry = Entry(self._next_id, owner, amount)
        self._entries[entry.id] = entry
        self._next_id += 1
        return entry

    def delete(self, user: User, entry_id: int) -> None:
        entry = self._entries.pop(entry_id)
        self.audit_log.append(f"{user.name} deleted entry {entry.id}")

    def balance(self, owner: str) -> Decimal:
        return sum(
            (e.amount for e in self._entries.values() if e.owner == owner),
            Decimal("0"),
        )
