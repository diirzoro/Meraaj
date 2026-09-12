"""Closed-period GUARD — from a declared boundary (Phase 3) to REAL central enforcement.

TRACEABILITY
  PeriodGuard (protocol)   ← Rahaal per-route `if (isYearClosed) ...`         PORT + HARDEN (one choke point)
  DatabasePeriodGuard      ← Rahaal `closed_years` / soft period lock         PORT + HARDEN
  route-level period checks← Rahaal `/tickets`, `/visas`, opening route       LEAVE (never re-introduced)

Rahaal checked the closed year INSIDE individual business routes, so some write paths
checked it and `createManualJournal` did not. The Core keeps the check as a dependency of
the ONE central validator (and of the reversal engine), so EVERY write path — journal
posting, reversal, opening balances, year-closing journals and any future posting — is
covered without a single route-level `if`.

SCOPE RULE (explicit, not accidental): a date is blocked only when it falls inside a period
document whose status is CLOSED. A date with no period defined is NOT closed — the Core
never invents a period, because "no period exists" and "the period is closed" are different
accounting facts.
"""
from datetime import datetime
from typing import Protocol

from .errors import AccountingError

PERIOD_OPEN = "open"
PERIOD_CLOSED = "closed"


class PeriodGuard(Protocol):
    @property
    def enforced(self) -> bool: ...

    async def assert_open(self, entity_id: str, date: datetime) -> None:
        """Raise `AccountingError('PERIOD_CLOSED', ...)` when the date falls inside a
        closed period."""
        ...


class NullPeriodGuard:
    """Kept for hosts/entities that define no periods at all. Honest by construction: it
    never claims a period was checked."""

    @property
    def enforced(self) -> bool:
        return False

    async def assert_open(self, entity_id: str, date: datetime) -> None:
        return None


NULL_PERIOD_GUARD = NullPeriodGuard()


class DatabasePeriodGuard:
    """The real guard (Phase 9). One indexed query per write — no cache, because a stale
    cache would let a journal into a period that was closed a second ago."""

    def __init__(self, period_store):
        self._store = period_store

    @property
    def enforced(self) -> bool:
        return True

    async def assert_open(self, entity_id: str, date: datetime) -> None:
        if not entity_id or date is None:
            raise AccountingError("ENTITY_REQUIRED", "الجهة المحاسبية مطلوبة")
        period = await self._store.find_closed_containing(entity_id, date)
        if period:
            raise AccountingError(
                "PERIOD_CLOSED",
                f"الفترة المحاسبية {period.get('code')} مغلقة — لا يمكن ترحيل أو عكس "
                f"أي قيد بتاريخ داخلها قبل إعادة فتحها",
                409, period_code=period.get("code"),
                period_id=period.get("id"),
                fiscal_year=period.get("fiscal_year"))
