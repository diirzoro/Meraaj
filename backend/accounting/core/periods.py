"""Closed-period BOUNDARY — declared now, implemented by the period-closing phase.

Rahaal checked the closed year / soft period lock INSIDE individual business routes
(`/tickets`, `/visas`, `/services`, the opening-balance route), which meant some write paths
checked it and `createManualJournal` did not — a manual journal could be inserted into an
already-closed year.

The Core removes that whole class of bug by making the period check a dependency of the ONE
central validator instead of a copy-pasted route-level `if`. Phase 3 ships the open guard
(`NullPeriodGuard`), so behaviour is unchanged and nothing is silently blocked, but every
future journal already flows through the single choke point.

No `accounting_periods` collection is created in Phase 3 — nothing needs it yet.
"""
from datetime import datetime
from typing import Protocol


class PeriodGuard(Protocol):
    @property
    def enforced(self) -> bool: ...

    async def assert_open(self, entity_id: str, date: datetime) -> None:
        """Raise `AccountingError('PERIOD_CLOSED', ...)` when the date falls inside a locked
        or closed period. Implemented in the period-closing phase."""
        ...


class NullPeriodGuard:
    """Phase 3 default: no period is closed because no closing mechanism exists yet.
    Honest by construction — it never claims a period was checked."""

    @property
    def enforced(self) -> bool:
        return False

    async def assert_open(self, entity_id: str, date: datetime) -> None:
        return None


NULL_PERIOD_GUARD = NullPeriodGuard()
