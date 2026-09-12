"""Configurable ACCOUNT LINKS between business concepts and chart accounts.

TRACEABILITY
  account links        ← Rahaal `settings.accounts = {cash: '1101', bank: '1102', ...}`  PORT + HARDEN
  hardcoded numbers    ← Rahaal `'4104'`, `'3102'`, `'1101'` inline in routes            LEAVE (never)
  silent fallback acct ← Rahaal `|| defaultAccount`                                      LEAVE (refused)

NO HARDCODED ACCOUNT NUMBER EXISTS HERE. A link is either configured explicitly for the
entity, or resolved from a SEMANTIC ROLE in the chart. If neither exists, the financial
effect FAILS BEFORE it happens — a wrong account is worse than a refused operation.
"""
import uuid
from typing import List, Optional

from pymongo import ASCENDING

from ..core import AccountingError
from ..core.journal import utc_now
from ..core.roles import (BANKS_AND_WALLETS, CANCELLATION_FEE_REVENUE, CASH_ON_HAND,
                          OPERATING_EXPENSES, PAYABLES, RECEIVABLES, SERVICE_REVENUE)
from ..core.types import AccountType

LINK_INDEX = "uniq_entity_link_key"


class LinkKey:
    """The business concepts that can carry an accounting effect in Meraaj V1."""
    OFFICE_WALLET_LIABILITY = "office_wallet_liability"
    CASH = "cash"
    BANK = "bank"
    WITHDRAWAL_CLEARING = "withdrawal_clearing"
    COMMISSION_REVENUE = "commission_revenue"
    ADS_REVENUE = "ads_revenue"
    CANCELLATION_FEE_REVENUE = "cancellation_fee_revenue"
    SELLER_PAYABLE = "seller_payable"
    B2B_CLEARING = "b2b_clearing"
    REFUND_CLEARING = "refund_clearing"
    ADJUSTMENT_EXPENSE = "adjustment_expense"
    RECEIVABLE = "receivable"


#: `role_chain` = the semantic roles tried, in order, when no explicit link is configured.
LINK_DEFINITIONS = {
    LinkKey.OFFICE_WALLET_LIABILITY: {
        "label_ar": "التزام محافظ المكاتب",
        "types": (AccountType.LIABILITY.value,), "role_chain": (PAYABLES,),
        "meaning": "رصيد المحفظة هو التزام على المنصة تجاه المكتب — وليس إيراداً"},
    LinkKey.CASH: {"label_ar": "الصندوق", "types": (AccountType.ASSET.value,),
                   "role_chain": (CASH_ON_HAND,)},
    LinkKey.BANK: {"label_ar": "البنك/المحافظ الإلكترونية",
                   "types": (AccountType.ASSET.value,),
                   "role_chain": (BANKS_AND_WALLETS,)},
    LinkKey.WITHDRAWAL_CLEARING: {
        "label_ar": "وسيط السحوبات", "types": (AccountType.ASSET.value,
                                                AccountType.LIABILITY.value),
        "role_chain": (BANKS_AND_WALLETS,)},
    LinkKey.COMMISSION_REVENUE: {"label_ar": "إيراد العمولات",
                                 "types": (AccountType.REVENUE.value,),
                                 "role_chain": (SERVICE_REVENUE,)},
    LinkKey.ADS_REVENUE: {"label_ar": "إيراد الإعلانات",
                          "types": (AccountType.REVENUE.value,),
                          "role_chain": (SERVICE_REVENUE,)},
    LinkKey.CANCELLATION_FEE_REVENUE: {
        "label_ar": "إيراد رسوم الإلغاء", "types": (AccountType.REVENUE.value,),
        "role_chain": (CANCELLATION_FEE_REVENUE, SERVICE_REVENUE)},
    LinkKey.SELLER_PAYABLE: {"label_ar": "مستحقات البائعين",
                             "types": (AccountType.LIABILITY.value,),
                             "role_chain": (PAYABLES,)},
    LinkKey.B2B_CLEARING: {"label_ar": "وسيط التحويلات بين المكاتب",
                           "types": (AccountType.LIABILITY.value,),
                           "role_chain": (PAYABLES,)},
    LinkKey.REFUND_CLEARING: {"label_ar": "وسيط الاستردادات",
                              "types": (AccountType.LIABILITY.value,),
                              "role_chain": (PAYABLES,)},
    LinkKey.ADJUSTMENT_EXPENSE: {"label_ar": "مصروف التسويات",
                                 "types": (AccountType.EXPENSE.value,),
                                 "role_chain": (OPERATING_EXPENSES,)},
    LinkKey.RECEIVABLE: {"label_ar": "مدينون", "types": (AccountType.ASSET.value,),
                         "role_chain": (RECEIVABLES,)},
}


class AccountLinkService:
    def __init__(self, database, account_store, chart, collection_prefix="accounting_"):
        self._db = database
        self._prefix = collection_prefix
        self._accounts = account_store
        self._chart = chart

    @property
    def links(self):
        return self._db[f"{self._prefix}account_links"]

    async def ensure_indexes(self) -> List[str]:
        await self.links.create_index([("entity_id", ASCENDING), ("key", ASCENDING)],
                                      unique=True, name=LINK_INDEX)
        return [LINK_INDEX]

    # ------------------------------------------------------------------ configure
    async def set_link(self, entity_id: str, key: str, account_code: str,
                       by: Optional[str] = None) -> dict:
        if key not in LINK_DEFINITIONS:
            raise AccountingError("UNKNOWN_ACCOUNT_LINK",
                                  f"مفتاح ربط غير معروف: {key}", 400)
        account = await self._validate(entity_id, key, str(account_code).strip())
        await self.links.update_one(
            {"entity_id": entity_id, "key": key},
            {"$set": {"account_code": account["code"], "updated_at": utc_now(),
                      "updated_by": by},
             "$setOnInsert": {"id": str(uuid.uuid4()), "entity_id": entity_id,
                              "key": key, "created_at": utc_now()}},
            upsert=True)
        return {"key": key, "account_code": account["code"],
                "label_ar": LINK_DEFINITIONS[key]["label_ar"],
                "source": "explicit_link"}

    async def clear_link(self, entity_id: str, key: str) -> dict:
        r = await self.links.delete_one({"entity_id": entity_id, "key": key})
        return {"key": key, "removed": r.deleted_count == 1,
                "note": "سيُعاد الاعتماد على الدور المحاسبي إن وُجد"}

    # ------------------------------------------------------------------- resolve
    async def resolve(self, entity_id: str, key: str) -> dict:
        """VALIDATE-THEN-USE. Every financial effect resolves its accounts through here,
        so an inactive, group, missing or wrong-type account can never receive a posting."""
        spec = LINK_DEFINITIONS.get(key)
        if not spec:
            raise AccountingError("UNKNOWN_ACCOUNT_LINK",
                                  f"مفتاح ربط غير معروف: {key}", 400)
        doc = await self.links.find_one({"entity_id": entity_id, "key": key},
                                        {"_id": 0})
        if doc:
            account = await self._validate(entity_id, key, doc["account_code"])
            return {"key": key, "account_code": account["code"],
                    "source": "explicit_link", "account": account}
        for role in spec["role_chain"]:
            account = await self._accounts.find_one_by_role(entity_id, role)
            if not account:
                continue
            if account.get("is_group"):
                # A group role (e.g. "payables") is a container: resolve its first
                # postable child rather than refusing, but NEVER post to the group.
                child = await self._first_postable_child(entity_id, account["code"])
                if not child:
                    continue
                account = child
            account = await self._validate(entity_id, key, account["code"])
            return {"key": key, "account_code": account["code"],
                    "source": f"semantic_role:{role}", "account": account}
        raise AccountingError(
            "ACCOUNT_LINK_MISSING",
            f"لا يوجد حساب مرتبط بـ«{spec['label_ar']}» ({key}) ولا دور محاسبي بديل "
            f"({' / '.join(spec['role_chain'])}) — يجب ربط الحساب قبل تنفيذ أي أثر مالي "
            f"(لا يُستخدم حساب افتراضي بصمت)", 409, link_key=key)

    async def describe(self, entity_id: str) -> dict:
        rows = []
        for key, spec in LINK_DEFINITIONS.items():
            try:
                resolved = await self.resolve(entity_id, key)
                rows.append({"key": key, "label_ar": spec["label_ar"],
                             "expected_types": list(spec["types"]),
                             "account_code": resolved["account_code"],
                             "source": resolved["source"], "ready": True})
            except AccountingError as exc:
                rows.append({"key": key, "label_ar": spec["label_ar"],
                             "expected_types": list(spec["types"]),
                             "account_code": None, "source": None, "ready": False,
                             "error": exc.code, "message": exc.message})
        return {"entity_id": entity_id, "links": rows,
                "ready": all(r["ready"] for r in rows),
                "policy": "no hardcoded account numbers; explicit link → semantic role → "
                          "FAIL BEFORE FINANCIAL EFFECT"}

    # ------------------------------------------------------------------ internals
    async def _validate(self, entity_id: str, key: str, code: str) -> dict:
        spec = LINK_DEFINITIONS[key]
        account = await self._accounts.get_by_code(entity_id, code)
        if not account:
            raise AccountingError("ACCOUNT_NOT_FOUND",
                                  f"الحساب {code} غير موجود في دليل هذه الجهة", 404)
        if account["entity_id"] != entity_id:
            raise AccountingError("CROSS_ENTITY_ACCOUNT",
                                  "الحساب يتبع جهة محاسبية أخرى", 409)
        if account.get("is_group"):
            raise AccountingError("GROUP_ACCOUNT_NOT_POSTABLE",
                                  f"الحساب {code} حساب مجموعة ولا يقبل الترحيل", 409)
        if account.get("is_active") is False:
            raise AccountingError("ACCOUNT_INACTIVE",
                                  f"الحساب {code} غير نشط", 409)
        if account["type"] not in spec["types"]:
            raise AccountingError(
                "ACCOUNT_TYPE_MISMATCH",
                f"الحساب {code} نوعه {account['type']} والمتوقع لـ«{spec['label_ar']}» "
                f"{'/'.join(spec['types'])}", 409)
        return account

    async def _first_postable_child(self, entity_id: str, parent_code: str):
        rows = await self._accounts.list_all(entity_id, include_inactive=False)
        children = sorted([a for a in rows if a.get("parent") == parent_code
                           and not a.get("is_group")], key=lambda a: a["code"])
        return children[0] if children else None
