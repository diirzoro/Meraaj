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
REVERSAL_INDEX = "uniq_entity_reversal_of"


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
        # Phase 5 — the ledger query pattern (entity + posted + account + date + seq).
        await self.entries.create_index(
            [("entity_id", ASCENDING), ("status", ASCENDING),
             ("lines.account_code", ASCENDING), ("date", ASCENDING),
             ("entry_seq", ASCENDING)], name="ledger_account_date_seq")
        created.append("ledger_account_date_seq")
        # Phase 6 — ONE reversal per original, enforced by the database.
        await self.entries.create_index(
            [("entity_id", ASCENDING), ("reversal_of", ASCENDING)],
            unique=True, name=REVERSAL_INDEX,
            partialFilterExpression={"reversal_of": {"$type": "string"}})
        created.append(REVERSAL_INDEX)
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

    # ---------------------------------------------------- ledger reads (Phase 5)
    # Additive READ-ONLY methods. Rahaal loaded every journal into memory and filtered in
    # JavaScript; these push the work into indexed aggregations (HARDEN) but apply exactly
    # the same matching rule: POSTED entries, one account code, one currency.
    @staticmethod
    def _line_match(entity_id, code, currency=None, from_date=None, to_date=None,
                    to_exclusive=None):
        stage = [{"$match": {"entity_id": entity_id, "status": "posted",
                             "lines.account_code": code}}]
        date_q = {}
        if from_date:
            date_q["$gte"] = from_date
        if to_date:
            date_q["$lte"] = to_date
        if to_exclusive:
            date_q["$lt"] = to_exclusive
        if date_q:
            stage[0]["$match"]["date"] = date_q
        stage.append({"$unwind": "$lines"})
        line_match = {"lines.account_code": code}
        if currency:
            line_match["lines.currency"] = currency
        stage.append({"$match": line_match})
        return stage

    async def line_currencies(self, entity_id: str, code: str) -> list:
        rows = await self.entries.aggregate(
            self._line_match(entity_id, code)
            + [{"$group": {"_id": "$lines.currency"}}]).to_list(length=None)
        return sorted([r["_id"] for r in rows if r["_id"]])

    async def sum_lines(self, entity_id: str, code: str, currency: str,
                        from_date=None, to_date=None, to_exclusive=None,
                        skip: int = 0, limit: int = 0) -> dict:
        from decimal import Decimal as D
        pipeline = self._line_match(entity_id, code, currency, from_date, to_date,
                                    to_exclusive)
        if skip or limit:
            pipeline += [{"$sort": {"date": 1, "entry_seq": 1, "lines.line_no": 1}}]
            if skip:
                pipeline.append({"$skip": int(skip)})
            if limit:
                pipeline.append({"$limit": int(limit)})
        pipeline.append({"$group": {"_id": None, "debit": {"$sum": "$lines.debit"},
                                    "credit": {"$sum": "$lines.credit"},
                                    "count": {"$sum": 1}}})
        rows = await self.entries.aggregate(pipeline).to_list(length=1)
        if not rows:
            return {"debit": D("0"), "credit": D("0"), "count": 0}
        r = rows[0]
        return {"debit": D(self.from_db_amount(r.get("debit") or 0)),
                "credit": D(self.from_db_amount(r.get("credit") or 0)),
                "count": int(r.get("count") or 0)}

    async def ledger_lines(self, entity_id: str, code: str, currency: str,
                           from_date=None, to_date=None, skip: int = 0,
                           limit: int = 50) -> list:
        from decimal import Decimal as D
        pipeline = self._line_match(entity_id, code, currency, from_date, to_date) + [
            # Deterministic ordering — never Mongo natural order.
            {"$sort": {"date": 1, "entry_seq": 1, "lines.line_no": 1}},
            {"$skip": int(skip)}, {"$limit": int(limit)},
            {"$project": {"_id": 0, "journal_id": "$id", "entry_no": 1, "entry_seq": 1,
                          "date": 1, "description": 1, "status": 1, "source_type": 1,
                          "source_id": 1, "posted_at": 1, "line": "$lines"}},
        ]
        rows = await self.entries.aggregate(pipeline).to_list(length=int(limit))
        out = []
        for r in rows:
            line = r.pop("line")
            r["debit"] = D(self.from_db_amount(line.get("debit") or 0))
            r["credit"] = D(self.from_db_amount(line.get("credit") or 0))
            r["currency"] = line.get("currency")
            r["memo"] = line.get("memo")
            r["line_no"] = line.get("line_no")
            out.append(r)
        return out

    # ------------------------------------------------- reversal ops (Phase 6)
    async def claim_for_reversal(self, entity_id: str, original_id: str,
                                 reversal_id: str, reason: str, by: str, at) -> Optional[dict]:
        """ATOMIC CLAIM — the only mutation ever allowed on a posted entry, and it touches
        reversal metadata ONLY (never an amount, a line, a date or a code).

        The filter itself is the concurrency guard: `status:"posted"` +
        `reversed_by_entry: None` means the second of two simultaneous requests matches
        nothing and receives None. No `if not reversed` read-then-write.
        """
        return await self.entries.find_one_and_update(
            {"entity_id": entity_id, "id": original_id, "status": "posted",
             "reversed_by_entry": None},
            {"$set": {"status": "reversed", "reversed_by_entry": reversal_id,
                      "reversed_at": at, "reversed_by": by,
                      "reversal_reason": reason}},
            return_document=ReturnDocument.BEFORE, projection={"_id": 0})

    async def release_reversal_claim(self, entity_id: str, original_id: str,
                                     reversal_id: str) -> bool:
        """Compensating action if the mirror insert fails: restores the original to POSTED,
        and only when the claim is still ours."""
        r = await self.entries.update_one(
            {"entity_id": entity_id, "id": original_id,
             "reversed_by_entry": reversal_id},
            {"$set": {"status": "posted", "reversed_by_entry": None,
                      "reversed_at": None, "reversed_by": None,
                      "reversal_reason": None}})
        return r.modified_count == 1

    async def find_reversal_of(self, entity_id: str, original_id: str) -> Optional[dict]:
        return await self.entries.find_one(
            {"entity_id": entity_id, "reversal_of": original_id}, {"_id": 0})

    # -------------------------------------------------- opening ops (Phase 7)
    async def count_by_source_type(self, entity_id: str, source_type: str,
                                    currency: Optional[str] = None,
                                    exclude_reversed: bool = True) -> int:
        q = {"entity_id": entity_id, "source_type": source_type}
        if currency:
            q["currency"] = currency
        if exclude_reversed:
            q["status"] = "posted"
        return await self.entries.count_documents(q)

    async def count_other_activity(self, entity_id: str, source_type: str) -> int:
        return await self.entries.count_documents(
            {"entity_id": entity_id, "source_type": {"$ne": source_type}})
