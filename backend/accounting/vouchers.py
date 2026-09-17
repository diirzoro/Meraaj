"""Accounting vouchers (سند قبض / سند صرف) — Batch 2.

They are NOT a second financial engine: a voucher is a document whose ONLY financial effect
is a journal posted through the Core's single write gateway. Business (commercial) vouchers
in `finance.py` stay exactly as they are — they describe wallet/business movements, while
these post to the general ledger.

Maker–Checker REUSES the existing Meraaj engine (`db.settings.maker_checker` + the same
self-approval rule): when the operation is configured as dual-control the voucher is stored
as `pending_approval` with NO journal, and a second user posts it.
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from db import db, now_iso
from .adapters import (PLATFORM_ENTITY, accounting_perm, actor_label,
                       posting_service, reversal_service, record_accounting_audit)
from .core import JournalEntryDraft, JournalLineInput
from .scope import AccountScope, account_scope, assert_accounts_allowed

router = APIRouter(prefix="/api/accounting/vouchers", tags=["accounting-vouchers"])

RECEIPT, PAYMENT = "receipt", "payment"
KINDS = {RECEIPT: "سند قبض", PAYMENT: "سند صرف"}
SOURCE_TYPES = {RECEIPT: "accounting_receipt_voucher",
                PAYMENT: "accounting_payment_voucher"}
PERM = {RECEIPT: "accounting.vouchers.receipt", PAYMENT: "accounting.vouchers.payment"}
VIEW = "accounting.vouchers.view"
APPROVE = "accounting.vouchers.approve"
CANCEL = "accounting.vouchers.cancel"


class VoucherIn(BaseModel):
    kind: str
    cash_account: str = Field(min_length=1)      # الصندوق/البنك
    counter_account: str = Field(min_length=1)   # الطرف المقابل
    amount: str = Field(min_length=1)
    currency: str = Field(min_length=2, max_length=8)
    date: Optional[datetime] = None
    party: str = ""
    description: str = Field(default="", max_length=500)


async def _dual_required(operation: str) -> bool:
    doc = await db.settings.find_one({"_id": "maker_checker"})
    return bool(((doc or {}).get("required") or {}).get(operation))


def _amount(raw: str) -> Decimal:
    try:
        value = Decimal(str(raw)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise HTTPException(400, "قيمة غير صالحة")
    if value <= 0:
        raise HTTPException(400, "المبلغ يجب أن يكون أكبر من صفر")
    return value


def _lines(kind: str, cash: str, counter: str, amount: Decimal, currency: str):
    debit, credit = (cash, counter) if kind == RECEIPT else (counter, cash)
    return [JournalLineInput(account_code=debit, debit=amount, credit=Decimal("0"),
                             currency=currency, memo=KINDS[kind]),
            JournalLineInput(account_code=credit, debit=Decimal("0"), credit=amount,
                             currency=currency, memo=KINDS[kind])]


def _public(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if k != "_id"}


async def _post_journal(doc: dict, by: str) -> dict:
    amount = Decimal(doc["amount"])
    draft = JournalEntryDraft(
        date=datetime.fromisoformat(doc["date"]), currency=doc["currency"],
        source_type=SOURCE_TYPES[doc["kind"]], source_id=doc["id"],
        description=doc["description"] or f"{KINDS[doc['kind']]} — {doc.get('party') or ''}",
        lines=_lines(doc["kind"], doc["cash_account"], doc["counter_account"],
                     amount, doc["currency"]))
    return await posting_service().post(
        PLATFORM_ENTITY, draft, source_key=f"voucher:{doc['id']}", by=by,
        metadata={"voucher": {"id": doc["id"], "kind": doc["kind"],
                              "party": doc.get("party"),
                              "created_by_id": doc.get("created_by_id"),
                              "approved_by_id": doc.get("approved_by_id"),
                              "posted_by_id": doc.get("posted_by_id")}})


@router.get("")
async def list_vouchers(kind: Optional[str] = None, status: Optional[str] = None,
                        limit: int = Query(default=100, ge=1, le=500),
                        user: dict = Depends(accounting_perm(VIEW)),
                        scope: AccountScope = Depends(account_scope())):
    f = {"entity_id": PLATFORM_ENTITY}
    if kind in KINDS:
        f["kind"] = kind
    if status:
        f["status"] = status
    docs = await db.accounting_vouchers.find(f).sort("created_at", -1).to_list(limit)
    items = [_public(d) for d in docs]
    if not scope.unrestricted:
        from .scope import scoped_accounts
        allowed = {a["code"] for a in await scoped_accounts(scope, PLATFORM_ENTITY)}
        items = [v for v in items
                 if {v["cash_account"], v["counter_account"]} & allowed]
    return {"items": items, "kinds": KINDS,
            "dual_control": {k: await _dual_required(PERM[k]) for k in KINDS}}


@router.post("")
async def create_voucher(payload: VoucherIn, user: dict = Depends(accounting_perm(VIEW)),
                         scope: AccountScope = Depends(account_scope())):
    """Permission is per KIND (a cashier may hold receipt only), and both accounts must be
    inside the user's ACCOUNT SCOPE — supplying a code manually cannot widen it."""
    from rbac import has_perm
    if payload.kind not in KINDS:
        raise HTTPException(400, "نوع سند غير معروف")
    if not await has_perm(user, PERM[payload.kind]):
        raise HTTPException(403, f"لا تملك صلاحية: {KINDS[payload.kind]}")
    amount = _amount(payload.amount)
    await assert_accounts_allowed(scope, PLATFORM_ENTITY,
                                  [payload.cash_account, payload.counter_account])
    if payload.cash_account == payload.counter_account:
        raise HTTPException(400, "لا يمكن أن يكون الطرفان نفس الحساب")
    vid = str(uuid.uuid4())
    actor, actor_id = actor_label(user), str(user["_id"])
    doc = {"id": vid, "entity_id": PLATFORM_ENTITY, "kind": payload.kind,
           "kind_label": KINDS[payload.kind],
           "cash_account": payload.cash_account.strip(),
           "counter_account": payload.counter_account.strip(),
           "amount": str(amount), "currency": payload.currency.strip().upper(),
           "date": (payload.date or datetime.now(timezone.utc)).isoformat(),
           "party": payload.party.strip(), "description": payload.description.strip(),
           "status": "draft", "created_by": actor, "created_by_id": actor_id,
           "approved_by": None, "approved_by_id": None,
           "posted_by": None, "posted_by_id": None,
           "cancelled_by": None, "cancelled_by_id": None,
           "journal_id": None, "entry_no": None, "reversal_entry_no": None,
           "created_at": now_iso()}
    if await _dual_required(PERM[payload.kind]):
        doc["status"] = "pending_approval"
        await db.accounting_vouchers.insert_one(dict(doc))
        await record_accounting_audit(PLATFORM_ENTITY, "accounting.voucher.created",
                                      actor, after={"voucher_id": vid,
                                                    "status": "pending_approval"},
                                      reference=vid)
        return {**_public(doc), "requires_approval": True,
                "message": "السند بانتظار اعتماد شخص ثانٍ (Maker–Checker) — لم يُرحَّل بعد"}
    posted = await _post_journal(doc, actor)
    doc.update({"status": "posted", "posted_by": actor, "posted_by_id": actor_id,
                "journal_id": posted.get("id"), "entry_no": posted.get("entry_no"),
                "posted_at": now_iso()})
    await db.accounting_vouchers.insert_one(dict(doc))
    await record_accounting_audit(PLATFORM_ENTITY, "accounting.voucher.posted", actor,
                                  after={"voucher_id": vid,
                                         "entry_no": posted.get("entry_no")},
                                  reference=vid)
    return {**_public(doc), "requires_approval": False, "journal": posted}


@router.get("/{voucher_id}")
async def get_voucher(voucher_id: str, user: dict = Depends(accounting_perm(VIEW)),
                      scope: AccountScope = Depends(account_scope())):
    doc = await db.accounting_vouchers.find_one({"id": voucher_id,
                                                 "entity_id": PLATFORM_ENTITY})
    if not doc:
        raise HTTPException(404, "السند غير موجود")
    await assert_accounts_allowed(scope, PLATFORM_ENTITY,
                                  [doc["cash_account"], doc["counter_account"]])
    out = _public(doc)
    if doc.get("journal_id"):
        out["journal"] = await posting_service().get(PLATFORM_ENTITY, doc["journal_id"])
    return out


@router.post("/{voucher_id}/approve")
async def approve_voucher(voucher_id: str, user: dict = Depends(accounting_perm(APPROVE)),
                          scope: AccountScope = Depends(account_scope())):
    """Maker cannot be Checker: the same rule the existing approvals engine enforces."""
    doc = await db.accounting_vouchers.find_one({"id": voucher_id,
                                                 "entity_id": PLATFORM_ENTITY})
    if not doc:
        raise HTTPException(404, "السند غير موجود")
    if doc["status"] != "pending_approval":
        raise HTTPException(400, "السند ليس بانتظار الاعتماد")
    if doc.get("created_by_id") == str(user["_id"]):
        raise HTTPException(403, "لا يمكن لمنشئ السند اعتماده — مطلوب شخص ثانٍ "
                                 "(Maker–Checker)")
    await assert_accounts_allowed(scope, PLATFORM_ENTITY,
                                  [doc["cash_account"], doc["counter_account"]])
    actor, actor_id = actor_label(user), str(user["_id"])
    claimed = await db.accounting_vouchers.find_one_and_update(
        {"id": voucher_id, "status": "pending_approval"},
        {"$set": {"status": "approving", "approved_by": actor,
                  "approved_by_id": actor_id, "approved_at": now_iso()}})
    if not claimed:
        raise HTTPException(409, "تم اتخاذ القرار على هذا السند بالفعل")
    doc.update({"approved_by": actor, "approved_by_id": actor_id})
    posted = await _post_journal(doc, actor)
    await db.accounting_vouchers.update_one({"id": voucher_id}, {"$set": {
        "status": "posted", "posted_by": actor, "posted_by_id": actor_id,
        "journal_id": posted.get("id"), "entry_no": posted.get("entry_no"),
        "posted_at": now_iso()}})
    await record_accounting_audit(PLATFORM_ENTITY, "accounting.voucher.approved", actor,
                                  after={"voucher_id": voucher_id,
                                         "maker": doc.get("created_by"),
                                         "entry_no": posted.get("entry_no")},
                                  reference=voucher_id)
    return {"ok": True, "status": "posted", "entry_no": posted.get("entry_no"),
            "journal": posted}


@router.post("/{voucher_id}/cancel")
async def cancel_voucher(voucher_id: str,
                         reason: str = Query(..., min_length=3, max_length=500),
                         user: dict = Depends(accounting_perm(CANCEL)),
                         scope: AccountScope = Depends(account_scope())):
    """A POSTED voucher is never edited or deleted: its journal is REVERSED through the
    Core reversal engine and the document is marked cancelled."""
    doc = await db.accounting_vouchers.find_one({"id": voucher_id,
                                                 "entity_id": PLATFORM_ENTITY})
    if not doc:
        raise HTTPException(404, "السند غير موجود")
    if doc["status"] == "cancelled":
        raise HTTPException(400, "السند ملغى مسبقاً")
    await assert_accounts_allowed(scope, PLATFORM_ENTITY,
                                  [doc["cash_account"], doc["counter_account"]])
    actor, actor_id = actor_label(user), str(user["_id"])
    update = {"status": "cancelled", "cancelled_by": actor,
              "cancelled_by_id": actor_id, "cancelled_at": now_iso(),
              "cancel_reason": reason}
    reversal = None
    if doc.get("journal_id"):
        reversal = await reversal_service().reverse(
            PLATFORM_ENTITY, doc["journal_id"], reason=reason, by=actor,
            source_key=f"voucher_cancel:{voucher_id}")
        update["reversal_entry_no"] = reversal.get("entry_no")
    await db.accounting_vouchers.update_one({"id": voucher_id}, {"$set": update})
    await record_accounting_audit(PLATFORM_ENTITY, "accounting.voucher.cancelled", actor,
                                  reason=reason,
                                  after={"voucher_id": voucher_id,
                                         "reversal_entry_no":
                                             (reversal or {}).get("entry_no")},
                                  reference=voucher_id)
    return {"ok": True, "status": "cancelled", "reversal": reversal}
