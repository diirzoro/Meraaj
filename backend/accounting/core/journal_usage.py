"""The real Used-Account probe — historical account protection becomes enforceable.

TRACEABILITY
  JournalUsageProbe.count_postings ← Rahaal inline
      `journal_entries.countDocuments({tenant_id, 'lines.account_code': code})`   PORT

It satisfies the Protocol declared in `usage.py`, so the chart lifecycle guards written in
Phase 2 start enforcing posting history without a single line of them changing.

Dependency direction (unchanged, still acyclic):
    chart lifecycle → UsageProbe (protocol) ← this implementation → journal store
The chart never imports the journal, and the journal never imports the chart lifecycle.

A DRAFT can never make an account "used" — drafts are not stored at all, so only POSTED
(and later REVERSED, which keeps its original document) entries can ever be counted.
"""
from .journal_store import JournalStore


class JournalUsageProbe:
    def __init__(self, journal_store: JournalStore):
        self._store = journal_store

    @property
    def available(self) -> bool:
        return True

    async def count_postings(self, entity_id: str, account_code: str) -> int:
        return await self._store.count_postings(entity_id, account_code)
