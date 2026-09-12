"""Persistence for the Accounting Core.

PORT of every database access pattern the reference implementation (Rahaal) used for the
chart of accounts:
  • Rahaal `db.collection('accounts')` scoped by `{ tenant_id }`         → scoped by entity_id
  • Rahaal atomic `findOneAndUpdate({$inc:{next_child_seq:1}})`          → bump_child_sequence()
  • Rahaal startup `createIndex accounts(tenant_id, code) unique`        → ensure_indexes()
  • Rahaal `stampVersion()` upsert on tenant_settings                    → stamp_chart_version()
  • Rahaal `auditTenantSettingsDuplicates` / `ensureTenantSettingsUniqueIndex`
    (read-only duplicate audit, refuses to delete/merge, refuses to create the index on
    ambiguity)                                                           → PORTED verbatim in behaviour

ADAPT (technology only, no accounting behaviour changed):
  • JS `uuidv4()` → Python `uuid4()`; `new Date()` → timezone-aware `datetime`.
  • JS collection names `accounts`/`tenant_settings` → prefixed `accounting_*` collections so
    the module can live inside a host database without colliding with host collections.
"""
import logging
from datetime import datetime, timezone
from typing import Optional, List

from pymongo import ASCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError

from .errors import AccountingError

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AccountStore:
    """The ONLY place in the Accounting Core that touches the database.

    The database handle and collection prefix are injected, so the Core holds no knowledge
    of the host project's connection, database name or naming conventions.
    """

    def __init__(self, database, collection_prefix: str = "accounting_"):
        self._db = database
        self._prefix = collection_prefix

    @property
    def accounts(self):
        return self._db[f"{self._prefix}accounts"]

    @property
    def settings(self):
        """PORT of Rahaal `tenant_settings` — but ONLY the accounting-owned part of it
        (chart version stamping). Host-project settings never enter this collection."""
        return self._db[f"{self._prefix}entity_settings"]

    # ------------------------------------------------------------------ indexes
    async def ensure_indexes(self) -> dict:
        """Phase 1 indexes only. Nothing is created here for later phases."""
        created = []
        # PORT — Rahaal: accounts(tenant_id, code) unique. Final line of defence for
        # uniqueness: a code is unique WITHIN an entity, and two different entities may
        # legitimately hold the very same code.
        await self.accounts.create_index(
            [("entity_id", ASCENDING), ("code", ASCENDING)],
            unique=True, name="uniq_entity_account_code")
        created.append("uniq_entity_account_code")
        # Parent lookup + ordered tree fetch.
        await self.accounts.create_index(
            [("entity_id", ASCENDING), ("parent", ASCENDING), ("code", ASCENDING)],
            name="entity_parent_code")
        created.append("entity_parent_code")
        # Stable identifier lookup (UUID strings, as in Rahaal — not ObjectIds — so the
        # Core stays portable and its ids survive an export/import).
        await self.accounts.create_index(
            [("entity_id", ASCENDING), ("id", ASCENDING)],
            unique=True, name="uniq_entity_account_id")
        created.append("uniq_entity_account_id")
        # PORT — Rahaal `ensureTenantSettingsUniqueIndex`: audit first, never delete, never
        # merge, and do NOT create the index when the data is ambiguous.
        settings_index = await self.ensure_settings_unique_index()
        return {"account_indexes": created, "settings_index": settings_index}

    async def audit_settings_duplicates(self) -> List[dict]:
        """PORT — Rahaal `auditTenantSettingsDuplicates`: READ-ONLY. Never deletes, never
        merges. Returns every entity that holds more than one settings document."""
        rows = await self.settings.aggregate([
            {"$match": {"entity_id": {"$ne": None}}},
            {"$group": {"_id": "$entity_id", "n": {"$sum": 1}, "ids": {"$push": "$id"}}},
            {"$match": {"n": {"$gt": 1}}},
        ]).to_list(length=None)
        return [{"entity_id": r["_id"], "count": r["n"], "ids": r["ids"]} for r in rows]

    async def ensure_settings_unique_index(self) -> dict:
        """PORT — Rahaal `ensureTenantSettingsUniqueIndex`, behaviour preserved exactly:
        on duplicates nothing is deleted, nothing is merged, the index is NOT created, and
        a loud warning is logged with classification `manual_review`."""
        duplicates = await self.audit_settings_duplicates()
        if duplicates:
            logger.warning(
                "[accounting] unique index NOT created — %d entity(ies) hold DUPLICATE "
                "settings documents and need MANUAL REVIEW (nothing deleted or merged): %s",
                len(duplicates), ", ".join(f"{d['entity_id']}x{d['count']}" for d in duplicates))
            return {"created": False, "classification": "manual_review", "duplicates": duplicates}
        await self.settings.create_index([("entity_id", ASCENDING)], unique=True,
                                         sparse=True, name="uniq_entity_settings")
        return {"created": True, "classification": "ok", "duplicates": []}

    # ------------------------------------------------------------------ reads
    async def get_by_code(self, entity_id: str, code: str) -> Optional[dict]:
        return await self.accounts.find_one({"entity_id": entity_id, "code": code})

    async def get_by_id(self, entity_id: str, account_id: str) -> Optional[dict]:
        return await self.accounts.find_one({"entity_id": entity_id, "id": account_id})

    async def list_all(self, entity_id: str, include_inactive: bool = True) -> List[dict]:
        q = {"entity_id": entity_id}
        if not include_inactive:
            q["is_active"] = True
        return await self.accounts.find(q).sort("code", ASCENDING).to_list(length=None)

    async def code_exists(self, entity_id: str, code: str) -> bool:
        """PORT — Rahaal `accountCodeExists`. In Rahaal the code space was shared with the
        business party collections (clients/suppliers/boxes), so it probed FOUR collections.
        ADAPT: the Core owns no business parties, so the probe is over the chart only; the
        party/subject code space returns in a later phase through generic account linking."""
        return await self.accounts.count_documents(
            {"entity_id": entity_id, "code": code}, limit=1) > 0

    async def count_children(self, entity_id: str, code: str) -> int:
        return await self.accounts.count_documents({"entity_id": entity_id, "parent": code})

    async def count_accounts(self, entity_id: str) -> int:
        return await self.accounts.count_documents({"entity_id": entity_id})

    async def list_entities(self) -> List[str]:
        return await self.accounts.distinct("entity_id")

    async def get_settings(self, entity_id: str) -> Optional[dict]:
        return await self.settings.find_one({"entity_id": entity_id})

    # ------------------------------------------------------------------ writes
    async def insert_many(self, docs: List[dict]) -> int:
        if not docs:
            return 0
        try:
            await self.accounts.insert_many([dict(d) for d in docs], ordered=True)
        except DuplicateKeyError as exc:
            raise AccountingError("coa.duplicate_code",
                                  f"رمز حساب مكرر أثناء التهيئة: {exc.details}", 409)
        return len(docs)

    async def insert(self, doc: dict) -> dict:
        try:
            await self.accounts.insert_one(dict(doc))
        except DuplicateKeyError:
            # Reached only if two concurrent writers landed on the same code. The unique
            # index is the authority, so the loser receives a clean, actionable error.
            raise AccountingError(
                "coa.duplicate_code",
                f"رمز الحساب \"{doc.get('code')}\" مستخدم بالفعل في هذه الجهة",
                409)
        return doc

    async def update_fields(self, entity_id: str, account_id: str,
                            fields: dict) -> Optional[dict]:
        return await self.accounts.find_one_and_update(
            {"entity_id": entity_id, "id": account_id},
            {"$set": fields},
            return_document=ReturnDocument.AFTER)

    async def set_child_sequence(self, entity_id: str, code: str, seq: int) -> None:
        await self.accounts.update_one({"entity_id": entity_id, "code": code},
                                       {"$set": {"next_child_seq": int(seq)}})

    async def delete(self, entity_id: str, account_id: str) -> bool:
        r = await self.accounts.delete_one({"entity_id": entity_id, "id": account_id})
        return r.deleted_count == 1

    async def bump_child_sequence(self, entity_id: str, parent_code: str) -> Optional[int]:
        """PORT (verbatim behaviour) — Rahaal:
            findOneAndUpdate({tenant_id, code: parent},
                             {$inc:{next_child_seq:1}, $set:{is_parent:true}},
                             {returnDocument:'after'})

        This is the concurrency-safe primitive behind code generation: no `count()+1`, no
        read-then-write. Two simultaneous requests can never receive the same number,
        because the increment and the read are one atomic Mongo operation.
        """
        doc = await self.accounts.find_one_and_update(
            {"entity_id": entity_id, "code": parent_code},
            {"$inc": {"next_child_seq": 1},
             "$set": {"is_parent": True, "updated_at": utc_now()}},
            return_document=ReturnDocument.AFTER)
        if not doc:
            return None
        return int(doc.get("next_child_seq") or 1)

    async def stamp_chart_version(self, entity_id: str, version: int, mode: str,
                                  result: str, by: Optional[str]) -> None:
        """PORT — Rahaal `stampVersion()` including its BLOCKER-1 fix: ALWAYS upsert on
        `{entity_id}` (never a bare insert) and give the upserted document a stable uuid
        `id`, so exactly ONE settings document per entity can ever exist.

        The hard rule is preserved: the version is stamped ONLY after the operation and its
        validation have both succeeded.
        """
        import uuid
        await self.settings.update_one(
            {"entity_id": entity_id},
            {"$set": {"coa_version": int(version),
                      "coa_seeded_at": utc_now(),
                      "coa_seeded_by": by or "system",
                      "coa_seed_mode": mode,
                      "coa_seed_result": result},
             "$setOnInsert": {"id": str(uuid.uuid4()), "entity_id": entity_id,
                              "created_at": utc_now()}},
            upsert=True)
