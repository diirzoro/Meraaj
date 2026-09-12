"""Used-Account protection BOUNDARY — declared in Phase 2, wired in the posting phase.

Rahaal performed this check inline inside `DELETE /accounts/:id` and `PUT /accounts/:id`:

    await db.collection('journal_entries')
            .countDocuments({ tenant_id: T, 'lines.account_code': code })

There is no POSTED journal in this module yet, so the Core must not pretend to have checked
it. This module therefore defines the CONTRACT only:

  • `NullUsageProbe` — the default: reports `available = False`. Every guard that depends on
    posting history treats "unknown" as "not provable" and falls back to the conservative
    rule (structural changes and deletion are refused for anything but a childless CUSTOM
    account). No message ever claims a journal was inspected.
  • The posting phase supplies a probe that counts POSTED entries referencing the code, and
    every COA guard starts enforcing history without being rewritten.

Phase 3 note (journal model exists, posting does not):
The dependency direction is deliberately one-way —
    COA lifecycle  →  UsageProbe (this protocol)  ←  journal storage implementation
The Core's chart never imports the journal implementation, and the journal implementation
never imports the chart lifecycle, so no circular dependency can form. A DRAFT journal must
NOT make an account "used": a draft has no accounting effect, so only POSTED (and REVERSED,
which keeps its original) entries may ever count.
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
