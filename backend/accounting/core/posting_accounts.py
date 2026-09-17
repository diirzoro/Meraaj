"""Posting-account resolution for journal validation.

PORT — Rahaal `validateJournalLines` pre-loaded the whole chart into sets to avoid one query
per line:

    const acctCodes  = new Set(... accounts.find({tenant_id}).project({code:1}) ...)
    const groupCodes = new Set(... accounts.find({tenant_id, is_group:true}) ...)

The same batching strategy is kept (one entity-scoped query per validation, not per line),
but the resolver returns the full account facts, so the validator can additionally enforce
"active" — which Rahaal could not, having no usable active flag.

LEAVE — Rahaal also loaded `clients` / `suppliers` / `boxes` code sets, because a journal
line could post directly to a business party's account code. The Core has no business
parties: a line posts to a CHART ACCOUNT, full stop. Subject-to-account mapping arrives with
the account-linking phase.
"""
from typing import Dict, Iterable

from .errors import AccountingError
from .store import AccountStore
from .types import LEVEL_BY_CODE_LENGTH


class PostingAccountResolver:
    """Entity-scoped. A code that exists only in ANOTHER entity is reported as a
    cross-entity violation, never silently resolved."""

    def __init__(self, store: AccountStore):
        self._store = store

    async def load(self, entity_id: str, codes: Iterable[str]) -> Dict[str, dict]:
        wanted = {str(c).strip() for c in codes if str(c).strip()}
        if not wanted:
            return {}
        docs = await self._store.accounts.find(
            {"entity_id": entity_id, "code": {"$in": sorted(wanted)}},
            {"_id": 0, "code": 1, "type": 1, "is_group": 1, "is_active": 1,
             "level": 1, "parent": 1, "name_ar": 1, "origin": 1},
        ).to_list(length=None)
        return {d["code"]: d for d in docs}

    async def exists_in_other_entity(self, entity_id: str, code: str) -> bool:
        """Used only to turn a "not found" into the precise CROSS_ENTITY_ACCOUNT error,
        which is what actually happened when a caller passed the wrong entity."""
        return await self._store.accounts.count_documents(
            {"code": code, "entity_id": {"$ne": entity_id}}, limit=1) > 0

    @staticmethod
    def assert_postable(account: dict, *, line_no: int) -> None:
        """The posting guard that Phases 1-2 deliberately deferred, now active.

        PORT — Rahaal F-008: "group accounts NEVER receive direct postings — leaf accounts
        only."
        HARDEN — an INACTIVE account also refuses new postings (Rahaal had no such check),
        a root account refuses direct postings, and a row whose stored `level` disagrees
        with its own code refuses postings instead of being quietly accepted (that row is
        structurally broken and is reported by the chart audit).
        """
        code = account["code"]
        if account.get("is_active") is False:
            raise AccountingError(
                "ACCOUNT_INACTIVE",
                f"الحساب {code} — {account.get('name_ar')} غير نشط ولا يقبل قيوداً جديدة "
                f"(السطر {line_no})")
        if account.get("is_group"):
            raise AccountingError(
                "GROUP_ACCOUNT_NOT_POSTABLE",
                f"الحساب {code} حساب مجموعة (تصنيف) — الترحيل يكون على الحساب التفصيلي "
                f"النهائي فقط (السطر {line_no})")
        if account.get("parent") is None:
            raise AccountingError(
                "ACCOUNT_NOT_POSTABLE",
                f"الحساب {code} حساب جذري (بلا أب) ولا يقبل الترحيل المباشر "
                f"(السطر {line_no})")
        expected_level = LEVEL_BY_CODE_LENGTH.get(len(code))
        if expected_level is None or account.get("level") != expected_level:
            raise AccountingError(
                "ACCOUNT_STRUCTURE_INVALID",
                f"الحساب {code} بنيته غير سليمة (المستوى المحفوظ لا يطابق رمزه) — "
                f"راجع تقرير التدقيق البنيوي قبل الترحيل عليه (السطر {line_no})")

    @staticmethod
    def missing(entity_id: str, code: str, line_no: int, cross_entity: bool) -> AccountingError:
        if cross_entity:
            return AccountingError(
                "CROSS_ENTITY_ACCOUNT",
                f"الحساب {code} لا ينتمي إلى الجهة المحاسبية الحالية ({entity_id}) "
                f"(السطر {line_no})", 400)
        return AccountingError(
            "ACCOUNT_NOT_FOUND",
            f"الحساب \"{code}\" غير موجود في دليل الحسابات (السطر {line_no})", 404)
