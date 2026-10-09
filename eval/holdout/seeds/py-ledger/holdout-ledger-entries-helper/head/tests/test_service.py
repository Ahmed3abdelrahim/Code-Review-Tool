# tests/test_service.py
from decimal import Decimal

from ledger.models import User
from ledger.service import Ledger


def test_balance_sums_owner_entries() -> None:
    ledger = Ledger()
    ledger.add("ana", Decimal("10"))
    ledger.add("ana", Decimal("5"))
    assert ledger.balance("ana") == Decimal("15")


def test_entries_for_returns_only_owner_entries() -> None:
    ledger = Ledger()
    ledger.add("ana", Decimal("10"))
    ledger.add("bob", Decimal("3"))
    assert [e.owner for e in ledger.entries_for("ana")] == ["ana"]
