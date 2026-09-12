"""Used-Account protection BOUNDARY — declared now, satisfied later.

Rahaal performed this check inline inside `DELETE /accounts/:id` and `PUT /accounts/:id`:

    await db.collection('journal_entries')
            .countDocuments({ tenant_id: T, 'lines.account_code': code })

There is no journal in this module yet, so the Core must not pretend to have checked it.
This module therefore defines the CONTRACT only:

  • `NullUsageProbe` — the Phase 2 default: reports `available = False`. Every guard that
    depends on posting history treats "unknown" as "not provable", and instead falls back
    to the conservative rule (structural changes are refused for anything but a childless
    CUSTOM account). No message ever claims a journal was inspected.
  • A later phase supplies a real probe implementing the same two methods; no guard has to
    be rewritten, and no rule has to be re-added.
"""
from typing import Protocol


class UsageProbe(Protocol):
    @property
    def available(self) -> bool: ...

    async def count_postings(self, entity_id: str, account_code: str) -> int: ...


class NullUsageProbe:
    """The only probe Phase 2 ships with: honest about knowing nothing."""

    @property
    def available(self) -> bool:
        return False

    async def count_postings(self, entity_id: str, account_code: str) -> int:
        raise NotImplementedError(
            "Journal usage cannot be probed: no journal exists in this phase")


NULL_USAGE_PROBE = NullUsageProbe()
