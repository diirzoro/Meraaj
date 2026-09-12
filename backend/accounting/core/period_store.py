"""Persistence for accounting periods, fiscal settings and year-close operation state.

TRACEABILITY
  periods collection        ← Rahaal `closed_years` array on tenant_settings   PORT + HARDEN (real documents)
  fiscal settings           ← Rahaal hardcoded Jan–Dec year                    HARDEN (configurable)
  year-close operation state← (no Rahaal equivalent: Rahaal had no recovery)    NEW
"""
from typing import List, Optional

from pymongo import ASCENDING, ReturnDocument

from .periods import PERIOD_CLOSED

PERIOD_CODE_INDEX = "uniq_entity_period_code"
PERIOD_RANGE_INDEX = "entity_period_range"
YEAR_OP_INDEX = "uniq_entity_year_currency"


class PeriodStore:
    def __init__(self, database, collection_prefix: str = "accounting_"):
        self._db = database
        self._prefix = collection_prefix

    @property
    def periods(self):
        return self._db[f"{self._prefix}periods"]

    @property
    def settings(self):
        return self._db[f"{self._prefix}entity_settings"]

    @property
    def year_ops(self):
        return self._db[f"{self._prefix}year_close_ops"]

    async def ensure_indexes(self) -> List[str]:
        created = []
        await self.periods.create_index([("entity_id", ASCENDING), ("code", ASCENDING)],
                                        unique=True, name=PERIOD_CODE_INDEX)
        created.append(PERIOD_CODE_INDEX)
        # The guard's only query pattern: entity + status + date containment.
        await self.periods.create_index(
            [("entity_id", ASCENDING), ("status", ASCENDING),
             ("start_date", ASCENDING), ("end_date", ASCENDING)],
            name=PERIOD_RANGE_INDEX)
        created.append(PERIOD_RANGE_INDEX)
        await self.periods.create_index([("entity_id", ASCENDING), ("id", ASCENDING)],
                                        unique=True, name="uniq_entity_period_id")
        created.append("uniq_entity_period_id")
        # ONE year-close operation per (entity, fiscal_year, currency) — enforced by the DB,
        # so a double year close is impossible, not merely guarded in code.
        await self.year_ops.create_index(
            [("entity_id", ASCENDING), ("fiscal_year", ASCENDING),
             ("currency", ASCENDING)], unique=True, name=YEAR_OP_INDEX)
        created.append(YEAR_OP_INDEX)
        return created

    # ------------------------------------------------------------------- periods
    async def insert_many(self, docs: List[dict]) -> int:
        if not docs:
            return 0
        await self.periods.insert_many([dict(d) for d in docs], ordered=True)
        return len(docs)

    async def get(self, entity_id: str, period_id: str) -> Optional[dict]:
        return await self.periods.find_one({"entity_id": entity_id, "id": period_id},
                                           {"_id": 0})

    async def get_by_code(self, entity_id: str, code: str) -> Optional[dict]:
        return await self.periods.find_one({"entity_id": entity_id, "code": code},
                                           {"_id": 0})

    async def list_periods(self, entity_id: str,
                           fiscal_year: Optional[int] = None) -> List[dict]:
        q = {"entity_id": entity_id}
        if fiscal_year is not None:
            q["fiscal_year"] = int(fiscal_year)
        return await self.periods.find(q, {"_id": 0}) \
            .sort([("start_date", ASCENDING)]).to_list(length=None)

    async def find_containing(self, entity_id: str, date) -> Optional[dict]:
        return await self.periods.find_one(
            {"entity_id": entity_id, "start_date": {"$lte": date},
             "end_date": {"$gte": date}}, {"_id": 0})

    async def find_closed_containing(self, entity_id: str, date) -> Optional[dict]:
        return await self.periods.find_one(
            {"entity_id": entity_id, "status": PERIOD_CLOSED,
             "start_date": {"$lte": date}, "end_date": {"$gte": date}}, {"_id": 0})

    async def count_by_status(self, entity_id: str, fiscal_year: int,
                              status: str) -> int:
        return await self.periods.count_documents(
            {"entity_id": entity_id, "fiscal_year": int(fiscal_year),
             "status": status})

    async def set_status(self, entity_id: str, period_id: str, from_status: str,
                         to_status: str, event: dict) -> Optional[dict]:
        """Atomic status transition. The expected current status is part of the FILTER, so
        two concurrent close/reopen requests can never both succeed. History is APPENDED —
        a close record is never erased by a later reopen."""
        return await self.periods.find_one_and_update(
            {"entity_id": entity_id, "id": period_id, "status": from_status},
            {"$set": {**event.get("set", {}), "status": to_status,
                      "updated_at": event.get("at")},
             "$push": {"history": event.get("entry")}},
            return_document=ReturnDocument.AFTER, projection={"_id": 0})

    async def close_all_open(self, entity_id: str, fiscal_year: int,
                             event: dict) -> int:
        r = await self.periods.update_many(
            {"entity_id": entity_id, "fiscal_year": int(fiscal_year),
             "status": {"$ne": PERIOD_CLOSED}},
            {"$set": {**event.get("set", {}), "status": PERIOD_CLOSED,
                      "updated_at": event.get("at")},
             "$push": {"history": event.get("entry")}})
        return r.modified_count

    # ----------------------------------------------------------- fiscal settings
    async def get_fiscal(self, entity_id: str) -> Optional[dict]:
        doc = await self.settings.find_one({"entity_id": entity_id}, {"_id": 0})
        return (doc or {}).get("fiscal")

    async def set_fiscal(self, entity_id: str, fiscal: dict) -> None:
        import uuid
        from datetime import datetime, timezone
        await self.settings.update_one(
            {"entity_id": entity_id},
            {"$set": {"fiscal": fiscal},
             "$setOnInsert": {"id": str(uuid.uuid4()), "entity_id": entity_id,
                              "created_at": datetime.now(timezone.utc)}},
            upsert=True)

    # -------------------------------------------------- year-close operation state
    async def start_year_op(self, doc: dict) -> Optional[dict]:
        """Upsert-on-first-attempt, read-existing-on-retry: the unique index makes the
        operation state itself idempotent, which is what makes a resumable workflow safe
        without database transactions."""
        from pymongo.errors import DuplicateKeyError
        try:
            await self.year_ops.insert_one(dict(doc))
            return dict(doc)
        except DuplicateKeyError:
            return await self.get_year_op(doc["entity_id"], doc["fiscal_year"],
                                          doc["currency"])

    async def get_year_op(self, entity_id: str, fiscal_year: int,
                          currency: str) -> Optional[dict]:
        return await self.year_ops.find_one(
            {"entity_id": entity_id, "fiscal_year": int(fiscal_year),
             "currency": currency}, {"_id": 0})

    async def update_year_op(self, entity_id: str, fiscal_year: int, currency: str,
                             fields: dict) -> Optional[dict]:
        return await self.year_ops.find_one_and_update(
            {"entity_id": entity_id, "fiscal_year": int(fiscal_year),
             "currency": currency},
            {"$set": fields}, return_document=ReturnDocument.AFTER,
            projection={"_id": 0})

    async def list_year_ops(self, entity_id: str,
                            fiscal_year: Optional[int] = None) -> List[dict]:
        q = {"entity_id": entity_id}
        if fiscal_year is not None:
            q["fiscal_year"] = int(fiscal_year)
        return await self.year_ops.find(q, {"_id": 0}).to_list(length=None)
