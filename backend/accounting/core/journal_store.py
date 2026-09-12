"""Persistence for POSTED journal entries — the first stored accounting truth.

TRACEABILITY
  JournalStore.insert_posted()  ← Rahaal `createJournalEntry` insert       PORT + HARDEN
  allocate_entry_no()           ← Rahaal `generateSubAccountCode` ($inc)   ADAPT (same atomic primitive, journal counter)
  find_by_source_key()          ← Rahaal `findOne({tenant_id, meraaj_booking_ref})`  PORT + HARDEN (DB-enforced)
  count_postings()              ← Rahaal `countDocuments({'lines.account_code': code})`  PORT
  ensure_indexes()              ← Rahaal startup createIndex block         PORT + HARDEN

HARDEN vs Rahaal:
  • Rahaal had NO index on `journal_entries` at all, and its idempotency marker
    (`meraaj_booking_ref`) was protected only by an application-level `findOne`. Here the
    idempotency key is enforced by a UNIQUE index, so a duplicate is impossible in the
    database, not merely unlikely in the code.
  • Amounts are stored as BSON Decimal128 (Rahaal stored JS floats).
  • DRAFTS ARE NOT STORED: only POSTED documents exist in this collection.
"""
from typing import List, Optional

from bson.decimal128 import Decimal128
from pymongo import ASCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError

IDEMPOTENCY_INDEX = "uniq_entity_source_key"
ENTRY_NO_INDEX = "uniq_entity_entry_no"
JOURNAL_ID_INDEX = "uniq_entity_journal_id"


class JournalStore:
    """The only object that touches the journal collection."""

    def __init__(self, database, collection_prefix: str = "accounting_"):
        self._db = database
        self._prefix = collection_prefix

    @property
    def entries(self):
        return self._db[f"{self._prefix}journal_entries"]

    @property
    def settings(self):
        return self._db[f"{self._prefix}entity_settings"]

    # ------------------------------------------------------------------ indexes
    async def ensure_indexes(self) -> List[str]:
        created = []
        await self.entries.create_index([("entity_id", ASCENDING), ("id", ASCENDING)],
                                        unique=True, name=JOURNAL_ID_INDEX)
        created.append(JOURNAL_ID_INDEX)
        await self.entries.create_index([("entity_id", ASCENDING), ("entry_no", ASCENDING)],
                                        unique=True, name=ENTRY_NO_INDEX)
        created.append(ENTRY_NO_INDEX)
        # PARTIAL unique index: only documents whose `source_key` is a string participate,
        # so any number of manual entries without a key can coexist. A plain sparse unique
        # index would be fragile the moment a `null` were written explicitly.
        await self.entries.create_index(
            [("entity_id", ASCENDING), ("source_key", ASCENDING)],
            unique=True, name=IDEMPOTENCY_INDEX,
            partialFilterExpression={"source_key": {"$type": "string"}})
        created.append(IDEMPOTENCY_INDEX)
        # Required by the usage probe (historical account protection) and by the ledger
        # derivation in a later phase. Not a "future" index: it is used in this phase.
        await self.entries.create_index(
            [("entity_id", ASCENDING), ("lines.account_code", ASCENDING)],
            name="entity_line_account")
        created.append("entity_line_account")
        return created

    # -------------------------------------------------------------- conversion
    @staticmethod
    def to_db_amount(value) -> Decimal128:
        """The ONE place Decimal becomes Decimal128 — no rounding happens here: the value
        was already quantised by the validator, and re-rounding at the storage boundary is
        exactly how ledgers drift."""
        return Decimal128(value)

    @staticmethod
    def from_db_amount(value) -> str:
        if isinstance(value, Decimal128):
            return format(value.to_decimal(), "f")
        return format(value, "f")

    # ------------------------------------------------------------------- writes
    async def allocate_entry_no(self, entity_id: str) -> int:
        """Atomic, entity-scoped counter. Never `count()+1`, never `max()+1`.
        Upserts the entity settings document so posting does not depend on the chart having
        been seeded through the settings path."""
        doc = await self.settings.find_one_and_update(
            {"entity_id": entity_id},
            {"$inc": {"journal_no_seq": 1}},
            upsert=True, return_document=ReturnDocument.AFTER)
        return int(doc.get("journal_no_seq") or 1)

    async def insert_posted(self, doc: dict) -> tuple:
        """Returns `(inserted: bool, duplicate_index: str|None)`.
        A DuplicateKeyError is a KNOWN, handled outcome (idempotency or a counter anomaly),
        never an unhandled 500."""
        try:
            await self.entries.insert_one(dict(doc))
            return True, None
        except DuplicateKeyError as exc:
            # Prefer the structured details (stable across driver/server versions) and fall
            # back to the message only if the key pattern is absent.
            details = exc.details or {}
            key_pattern = details.get("keyPattern") or {}
            if "source_key" in key_pattern:
                return False, IDEMPOTENCY_INDEX
            if "entry_no" in key_pattern:
                return False, ENTRY_NO_INDEX
            if "id" in key_pattern:
                return False, JOURNAL_ID_INDEX
            message = str(exc)
            for name in (IDEMPOTENCY_INDEX, ENTRY_NO_INDEX, JOURNAL_ID_INDEX):
                if name in message:
                    return False, name
            return False, "unknown"

    # -------------------------------------------------------------------- reads
    async def get(self, entity_id: str, entry_id: str) -> Optional[dict]:
        return await self.entries.find_one({"entity_id": entity_id, "id": entry_id},
                                           {"_id": 0})

    async def find_by_source_key(self, entity_id: str, source_key: str) -> Optional[dict]:
        return await self.entries.find_one(
            {"entity_id": entity_id, "source_key": source_key}, {"_id": 0})

    async def list_entries(self, entity_id: str, limit: int = 50,
                           source_type: Optional[str] = None) -> List[dict]:
        query = {"entity_id": entity_id}
        if source_type:
            query["source_type"] = source_type
        return await self.entries.find(query, {"_id": 0}) \
            .sort([("entry_no", ASCENDING)]).to_list(length=min(limit, 200))

    async def count_postings(self, entity_id: str, account_code: str) -> int:
        return await self.entries.count_documents(
            {"entity_id": entity_id, "lines.account_code": account_code})
