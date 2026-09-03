"""Enterprise Finance Center (Batch 2) — unified ledger, reconciliation, vouchers and the
6-stage withdrawal cycle. ADDITIVE: the existing /api/admin/{topups,transfers,withdrawals}
review endpoints and their money logic are untouched; stages here are workflow tracking and
the receipt/closing steps that come after them.
"""
import csv
import io
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from db import db, serialize, oid, now_iso, wallet_available
from security import require_admin

router = APIRouter(prefix="/api/admin", tags=["admin-finance"])

CCY = ("SAR", "USD")

# Withdrawal workflow: request → review → internal approval → accounting → executed → receipt → closed
STAGES = ["requested", "under_review", "approved_internal", "sent_to_accounting",
          "executed", "closed"]
STAGE_LABEL = {
    "requested": "١. طلب البائع", "under_review": "٢. مراجعة الإدارة",
    "approved_internal": "٣. اعتماد داخلي", "sent_to_accounting": "٤. إحالة للمحاسبة",
    "executed": "٥. تنفيذ التحويل ورفع الإيصال", "closed": "٦. إغلاق الطلب",
}

TXN_LABEL = {
    "topup": "شحن محفظة", "booking_debit": "خصم حجز", "booking_escrow": "إيراد معلّق",
    "settlement": "تسوية بائع", "cancel_refund": "استرداد إلغاء", "hold_release": "فك حجز",
    "dispute_refund": "استرداد نزاع", "dispute_release": "فك نزاع",
    "seller_compensation": "تعويض بائع", "marketer_commission": "عمولة تسويق",
    "withdrawal": "سحب أرباح", "p2p_in": "تحويل وارد", "p2p_out": "تحويل صادر",
    "commission_adjustment": "تعديل عمولة",
}


# ---------------- unified ledger ----------------
def _ledger_filter(office_id, currency, txn_type, date_from, date_to, q):
    f = {}
    if office_id:
        f["office_id"] = office_id
    if currency in CCY:
        f["currency"] = currency
    if txn_type:
        f["type"] = txn_type
    if date_from or date_to:
        rng = {}
        if date_from:
            rng["$gte"] = date_from
        if date_to:
            rng["$lte"] = date_to + "T23:59:59.999999+00:00"
        f["created_at"] = rng
    if q:
        f["$or"] = [{"description": {"$regex": q, "$options": "i"}},
                    {"ref": {"$regex": q, "$options": "i"}}]
    return f


def booking_financials(b: dict, txns: list) -> dict:
    """READ-ONLY breakdown for display/audit. It only READS the booking fields and the
    already-posted transactions — it never recalculates, settles or changes any amount."""
    cur = b.get("currency") or "USD"
    gross = round(float(b.get("amount_charged") or 0), 2)
    seller_net = round(float(b.get("net_cost_total") or 0), 2)
    platform_fee = round(float(b.get("platform_fee") or 0), 2)
    marketer = round(float(b.get("marketer_commission") or 0), 2)

    def total(*types):
        return round(sum(abs(float(t.get("amount") or 0)) for t in txns
                         if t.get("type") in types), 2)

    paid = total("booking_debit")
    escrow_in = total("booking_escrow")
    released = total("hold_release", "dispute_release")
    refunded = total("cancel_refund", "dispute_refund")
    seller_deduction = total("cancel_deduction", "seller_compensation")
    pending = round(max(escrow_in - released - refunded, 0), 2)
    due_from_buyer = round(max(gross - paid, 0), 2)
    due_to_seller = round(max(seller_net - released - seller_deduction, 0), 2)
    platform_net = round(float(b.get("platform_profit") if b.get("platform_profit") is not None
                               else platform_fee - marketer), 2)
    return {
        "currency": cur,
        "status": b.get("status"),
        "settled": bool(b.get("settled")),
        "gross": gross,
        "paid": paid,                       # المدفوع فعلياً من المشتري
        "pending": pending,                 # المعلّق في الضمان
        "released": released,               # المحرر للبائع
        "refunded": refunded,               # المسترد للمشتري
        "due_from_buyer": due_from_buyer,   # المستحق على المشتري
        "due_to_seller": due_to_seller,     # المستحق للبائع
        "platform_commission": platform_fee,
        "platform_net": platform_net,
        "transferred": released,            # المبلغ المحوّل للبائع فعلياً
        "remaining": pending,               # المتبقي في الضمان
        "seller_net": seller_net,
        "buyer_commission": round(float(b.get("buyer_commission_total") or 0), 2),
        "marketer_commission": marketer,
        "seller_deduction": seller_deduction,
        "debit_split": b.get("debit_split") or {},
        "movements": len(txns),
        "note": "أرقام للعرض والتدقيق فقط — مشتقّة من الحركات المسجّلة دون أي إعادة حساب.",
    }


@router.get("/bookings/{booking_id}/financials")
async def booking_financials_endpoint(booking_id: str, admin: dict = Depends(require_admin)):
    """Read-only financial statement of one order: the ten headline figures plus the full
    movement history that produced them."""
    b = await db.bookings.find_one({"_id": oid(booking_id)})
    if not b:
        raise HTTPException(404, "الحجز غير موجود")
    txns = await db.transactions.find({"ref": booking_id}).sort("created_at", 1).to_list(300)
    parties = {}
    async def _party(raw):
        """Legacy/Rahaal rows can carry a non-ObjectId reference; that must not 404 the page."""
        try:
            return await db.users.find_one({"_id": oid(raw)}, {"office_name": 1, "email": 1})
        except Exception:
            return await db.users.find_one({"rahal_office_ref": raw},
                                           {"office_name": 1, "email": 1})

    for pid, label in (("buyer_id", "buyer"), ("seller_id", "seller")):
        if b.get(pid):
            u = await _party(b[pid])
            parties[label] = {"id": b[pid], "name": (u or {}).get("office_name"),
                              "email": (u or {}).get("email")}
    rows = []
    for t in txns:
        d = serialize(t)
        d["direction"] = "in" if float(t.get("amount") or 0) >= 0 else "out"
        d["party"] = ("buyer" if t.get("office_id") == b.get("buyer_id")
                      else "seller" if t.get("office_id") == b.get("seller_id") else "other")
        rows.append(d)
    return {"booking_id": booking_id, "package_title": b.get("package_title"),
            "parties": parties, "financials": booking_financials(b, txns),
            "movements": rows}


@router.get("/ledger")
async def ledger(office_id: Optional[str] = None, currency: Optional[str] = None,
                 txn_type: Optional[str] = None, date_from: Optional[str] = None,
                 date_to: Optional[str] = None, q: Optional[str] = None,
                 page: int = 1, limit: int = Query(50, le=500),
                 admin: dict = Depends(require_admin)):
    f = _ledger_filter(office_id, currency, txn_type, date_from, date_to, q)
    total = await db.transactions.count_documents(f)
    docs = await db.transactions.find(f).sort("created_at", -1) \
        .skip(max(0, (page - 1) * limit)).limit(limit).to_list(limit)
    names = {}
    for d in docs:
        oid_ = d.get("office_id")
        if oid_ and oid_ not in names:
            u = await db.users.find_one({"_id": oid(oid_)}, {"office_name": 1, "email": 1})
            names[oid_] = (u or {}).get("office_name") or (u or {}).get("email") or "—"
    items = []
    for d in serialize(docs):
        d["office_name"] = names.get(d.get("office_id"), "—")
        d["type_label"] = TXN_LABEL.get(d.get("type"), d.get("type"))
        items.append(d)
    inflow = {c: 0.0 for c in CCY}
    outflow = {c: 0.0 for c in CCY}
    async for r in db.transactions.aggregate([{"$match": f}, {"$group": {
            "_id": {"c": "$currency", "sign": {"$cond": [{"$gte": ["$amount", 0]}, "in", "out"]}},
            "t": {"$sum": "$amount"}}}]):
        c = r["_id"]["c"]
        if c not in CCY:
            continue
        (inflow if r["_id"]["sign"] == "in" else outflow)[c] = round(r["t"], 2)
    return {"items": items, "total": total, "page": page, "limit": limit,
            "inflow": inflow, "outflow": outflow,
            "net": {c: round(inflow[c] + outflow[c], 2) for c in CCY},
            "types": TXN_LABEL}


@router.get("/ledger/export")
async def export_ledger(office_id: Optional[str] = None, currency: Optional[str] = None,
                        txn_type: Optional[str] = None, date_from: Optional[str] = None,
                        date_to: Optional[str] = None, q: Optional[str] = None,
                        admin: dict = Depends(require_admin)):
    f = _ledger_filter(office_id, currency, txn_type, date_from, date_to, q)
    docs = await db.transactions.find(f).sort("created_at", -1).to_list(20000)
    buf = io.StringIO()
    buf.write("\ufeff")  # BOM so Excel opens Arabic correctly
    w = csv.writer(buf)
    w.writerow(["التاريخ", "الحساب", "نوع الحركة", "الوصف", "المرجع", "المبلغ", "العملة"])
    for d in docs:
        w.writerow([d.get("created_at"), d.get("office_id"),
                    TXN_LABEL.get(d.get("type"), d.get("type")), d.get("description"),
                    d.get("ref"), d.get("amount"), d.get("currency")])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": 'attachment; filename="meraaj-ledger.csv"'})


# ---------------- reconciliation ----------------
@router.get("/reconciliation")
async def reconciliation(admin: dict = Depends(require_admin), full: bool = False):
    """Compares wallet balances against the transaction ledger per currency and lists
    offices whose ledger sum does not match their wallet total."""
    wallets = {c: {"available": 0.0, "pending": 0.0, "total": 0.0} for c in CCY}
    per_office = {}
    users = await db.users.find({"role": {"$in": ["office", "individual"]}},
                               {"office_name": 1, "email": 1, "wallet": 1}).to_list(5000)
    for u in users:
        w = u.get("wallet") or {}
        for c in CCY:
            cw = w.get(c) or {}
            for k in ("available", "pending", "total"):
                wallets[c][k] += float(cw.get(k) or 0)
        per_office[str(u["_id"])] = {
            "name": u.get("office_name") or u.get("email"),
            "wallet": {c: round(float(((w.get(c) or {}).get("total")) or 0), 2) for c in CCY},
            "ledger": {c: 0.0 for c in CCY}}

    ledger_tot = {c: 0.0 for c in CCY}
    async for r in db.transactions.aggregate([{"$group": {
            "_id": {"o": "$office_id", "c": "$currency"}, "t": {"$sum": "$amount"}}}]):
        c = r["_id"]["c"]
        o = r["_id"]["o"]
        if c not in CCY:
            continue
        ledger_tot[c] += r["t"]
        if o in per_office:
            per_office[o]["ledger"][c] = round(r["t"], 2)

    mismatches = []
    for oid_, row in per_office.items():
        for c in CCY:
            diff = round(row["wallet"][c] - row["ledger"][c], 2)
            if abs(diff) > 0.5:
                mismatches.append({"office_id": oid_, "name": row["name"], "currency": c,
                                   "wallet_total": row["wallet"][c],
                                   "ledger_total": row["ledger"][c], "difference": diff})
    mismatches.sort(key=lambda x: -abs(x["difference"]))
    revenue = {c: 0.0 for c in CCY}
    async for r in db.platform_revenue.aggregate([{"$group": {"_id": "$currency", "t": {"$sum": "$amount"}}}]):
        if r["_id"] in CCY:
            revenue[r["_id"]] = round(r["t"], 2)
    return {
        "wallets": {c: {k: round(v, 2) for k, v in wallets[c].items()} for c in CCY},
        "ledger_totals": {c: round(ledger_tot[c], 2) for c in CCY},
        "platform_revenue": revenue,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches if full else mismatches[:100],
        "generated_at": now_iso(),
    }


# ---------------- vouchers ----------------
@router.get("/vouchers/{txn_id}")
async def voucher(txn_id: str, admin: dict = Depends(require_admin)):
    t = await db.transactions.find_one({"_id": oid(txn_id)})
    if not t:
        raise HTTPException(404, "الحركة غير موجودة")
    u = await db.users.find_one({"_id": oid(t["office_id"])}, {"office_name": 1, "email": 1, "phone": 1})
    amount = float(t.get("amount") or 0)
    kind = "receipt" if amount >= 0 else "payment"
    if t.get("type") in ("p2p_in", "p2p_out"):
        kind = "transfer"
    return {
        "voucher_no": f"MRJ-{str(t['_id'])[-8:].upper()}",
        "kind": kind,
        "kind_label": {"receipt": "سند قبض", "payment": "سند صرف", "transfer": "سند تحويل"}[kind],
        "date": t.get("created_at"),
        "party": {"name": (u or {}).get("office_name") or (u or {}).get("email"),
                  "email": (u or {}).get("email"), "phone": (u or {}).get("phone")},
        "amount": round(abs(amount), 2), "currency": t.get("currency"),
        "type_label": TXN_LABEL.get(t.get("type"), t.get("type")),
        "description": t.get("description"), "ref": t.get("ref"),
        "issued_by": admin.get("email"), "issued_at": now_iso(),
    }


@router.get("/vouchers/{txn_id}/pdf")
async def voucher_pdf(txn_id: str, admin: dict = Depends(require_admin)):
    v = await voucher(txn_id, admin)
    from pdfgen import build_voucher_pdf
    pdf = build_voucher_pdf(v)
    return StreamingResponse(iter([pdf]), media_type="application/pdf",
                             headers={"Content-Disposition":
                                      f'attachment; filename="{v["voucher_no"]}.pdf"'})


# ---------------- withdrawal 6-stage cycle ----------------
@router.get("/withdrawals/queue")
async def withdrawal_queue(status: str = "all", currency: Optional[str] = None,
                           stage: Optional[str] = None, admin: dict = Depends(require_admin)):
    f = {} if status == "all" else {"status": status}
    if currency in CCY:
        f["currency"] = currency
    docs = await db.withdrawals.find(f).sort("created_at", -1).to_list(500)
    out = []
    for d in serialize(docs):
        st = d.get("stage")
        if not st:
            st = "closed" if d.get("status") == "approved" else (
                "requested" if d.get("status") == "pending" else "closed")
        d["stage"] = st
        d["stage_label"] = STAGE_LABEL.get(st, st)
        d["stage_index"] = STAGES.index(st) if st in STAGES else 0
        out.append(d)
    if stage:
        out = [d for d in out if d["stage"] == stage]
    totals = {c: 0.0 for c in CCY}
    for d in out:
        if d.get("currency") in CCY:
            totals[d["currency"]] += float(d.get("amount") or 0)
    return {"items": out, "stages": STAGES, "stage_labels": STAGE_LABEL,
            "totals": {c: round(v, 2) for c, v in totals.items()}}


class StageIn(BaseModel):
    stage: str
    note: str = ""


@router.post("/withdrawals/{wid}/stage")
async def set_stage(wid: str, payload: StageIn, admin: dict = Depends(require_admin)):
    """Workflow tracking only — never moves money. The actual debit still happens in the
    existing POST /api/admin/withdrawals/{id}/review endpoint."""
    if payload.stage not in STAGES:
        raise HTTPException(400, "مرحلة غير صالحة")
    w = await db.withdrawals.find_one({"_id": oid(wid)})
    if not w:
        raise HTTPException(404, "طلب السحب غير موجود")
    cur_stage = w.get("stage") or ("closed" if w.get("status") == "approved" else "requested")
    if STAGES.index(payload.stage) < STAGES.index(cur_stage):
        raise HTTPException(400, "لا يمكن الرجوع لمرحلة سابقة")
    if payload.stage == "executed" and w.get("status") != "approved":
        raise HTTPException(400, "يجب اعتماد طلب السحب مالياً قبل تسجيل التنفيذ")
    if payload.stage == "closed" and not w.get("receipt_url"):
        raise HTTPException(400, "لا يمكن إغلاق الطلب قبل رفع إيصال التحويل")
    entry = {"stage": payload.stage, "label": STAGE_LABEL[payload.stage],
             "note": payload.note.strip(), "by": admin.get("email"), "at": now_iso()}
    await db.withdrawals.update_one({"_id": w["_id"]}, {
        "$set": {"stage": payload.stage, "stage_updated_at": now_iso()},
        "$push": {"stage_history": entry}})
    from orgs import notify
    await notify(w.get("office_id"), "withdrawal_stage", "تحديث طلب السحب",
                 f"انتقل طلب السحب {w.get('amount')} {w.get('currency')} إلى مرحلة: "
                 f"{STAGE_LABEL[payload.stage]}",
                 "/wallet", {"withdrawal_id": wid, "amount": w.get("amount"),
                             "currency": w.get("currency"),
                             "stage_label": STAGE_LABEL[payload.stage]})
    return {"ok": True, "stage": payload.stage, "history_entry": entry}


class ReceiptIn(BaseModel):
    receipt_url: str = Field(min_length=5)
    reference: str = ""


@router.post("/withdrawals/{wid}/receipt")
async def upload_receipt(wid: str, payload: ReceiptIn, admin: dict = Depends(require_admin)):
    w = await db.withdrawals.find_one({"_id": oid(wid)})
    if not w:
        raise HTTPException(404, "طلب السحب غير موجود")
    await db.withdrawals.update_one({"_id": w["_id"]}, {
        "$set": {"receipt_url": payload.receipt_url.strip(),
                 "bank_reference": payload.reference.strip(),
                 "receipt_uploaded_by": admin.get("email"), "receipt_uploaded_at": now_iso()},
        "$push": {"stage_history": {"stage": "receipt_uploaded",
                                    "label": "إيصال التحويل",
                                    "note": payload.reference.strip(),
                                    "by": admin.get("email"), "at": now_iso()}}})
    return {"ok": True}


class AdjustIn(BaseModel):
    office_id: str
    currency: str
    reason: str = Field(min_length=5)
    dry_run: bool = False


@router.post("/reconciliation/adjust")
async def adjust_reconciliation(payload: AdjustIn, admin: dict = Depends(require_admin)):
    """Documents a wallet/ledger difference with an OPENING-BALANCE ledger entry.
    It NEVER edits a wallet balance and never deletes historic data.
    Real execution is additionally gated by ALLOW_RECONCILIATION=true (client approval)."""
    import os as _os
    if not payload.dry_run and _os.environ.get("ALLOW_RECONCILIATION") != "true":
        raise HTTPException(403, "تشغيل قيود التسوية معطّل حتى الاعتماد الصريح "
                                 "(ALLOW_RECONCILIATION=false) — استخدم Dry-run للمعاينة")
    if payload.currency not in CCY:
        raise HTTPException(400, "عملة غير مدعومة")
    u = await db.users.find_one({"_id": oid(payload.office_id)},
                                {"office_name": 1, "email": 1, "wallet": 1})
    if not u:
        raise HTTPException(404, "الحساب غير موجود")
    wallet_total = round(float(((u.get("wallet") or {}).get(payload.currency) or {}).get("total") or 0), 2)
    ledger_total = 0.0
    async for r in db.transactions.aggregate([
            {"$match": {"office_id": payload.office_id, "currency": payload.currency}},
            {"$group": {"_id": None, "t": {"$sum": "$amount"}}}]):
        ledger_total = round(float(r["t"] or 0), 2)
    diff = round(wallet_total - ledger_total, 2)
    existing = await db.transactions.find_one({"office_id": payload.office_id,
                                              "currency": payload.currency,
                                              "type": "opening_balance"})
    if existing:
        raise HTTPException(400, "يوجد قيد افتتاحي مسجّل مسبقاً لهذا الحساب")
    if abs(diff) < 0.5:
        raise HTTPException(400, "لا يوجد فرق يستوجب قيد تسوية")
    if payload.dry_run:
        return {"dry_run": True, "office_id": payload.office_id, "currency": payload.currency,
                "wallet_total": wallet_total, "ledger_total": ledger_total, "difference": diff}
    txn = {"office_id": payload.office_id, "type": "opening_balance", "amount": diff,
           "currency": payload.currency,
           "description": f"قيد افتتاحي/تسوية موثّقة: {payload.reason.strip()}",
           "ref": None, "meta": {"wallet_total": wallet_total, "ledger_total": ledger_total,
                                 "by": admin.get("email")},
           "created_at": now_iso()}
    res = await db.transactions.insert_one(txn)
    await db.audit_log.insert_one({
        "entity": "reconciliation", "entity_id": payload.office_id,
        "action": "opening_balance_entry", "actor": admin.get("email"),
        "actor_id": str(admin["_id"]), "reason": payload.reason.strip(),
        "before": {"ledger_total": ledger_total}, "after": {"ledger_total": round(ledger_total + diff, 2)},
        "meta": {"currency": payload.currency, "amount": diff, "txn_id": str(res.inserted_id)},
        "at": now_iso()})
    return {"ok": True, "txn_id": str(res.inserted_id), "amount": diff,
            "office": u.get("office_name") or u.get("email"),
            "note": "لم يتم تعديل أي رصيد — تمت إضافة قيد افتتاحي موثّق فقط"}


@router.get("/reconciliation/preview")
async def reconciliation_preview(admin: dict = Depends(require_admin)):
    """Full pre-execution list of every proposed opening entry (no writes at all)."""
    import os as _os
    rec = await reconciliation(admin, full=True)
    rows, totals = [], {c: 0.0 for c in CCY}
    for m in rec["mismatches"]:
        exists = await db.transactions.find_one({"office_id": m["office_id"],
                                                 "currency": m["currency"],
                                                 "type": "opening_balance"})
        u = await db.users.find_one({"_id": oid(m["office_id"])},
                                    {"email": 1, "wallet": 1, "role": 1})
        cw = ((u or {}).get("wallet") or {}).get(m["currency"]) or {}
        rows.append({**m, "proposed_entry": m["difference"],
                     "already_adjusted": bool(exists),
                     "entry_type": "opening_balance",
                     "account_email": (u or {}).get("email"),
                     "account_role": (u or {}).get("role"),
                     # before/after preview — the WALLET never changes, only the ledger
                     "before": {"wallet_total": m["wallet_total"],
                                "wallet_available": round(float(cw.get("available") or 0), 2),
                                "wallet_pending": round(float(cw.get("pending") or 0), 2),
                                "ledger_total": m["ledger_total"]},
                     "after": {"wallet_total": m["wallet_total"],
                               "wallet_available": round(float(cw.get("available") or 0), 2),
                               "wallet_pending": round(float(cw.get("pending") or 0), 2),
                               "ledger_total": round(m["ledger_total"] + m["difference"], 2)},
                     "wallet_changed": False,
                     "description": "قيد افتتاحي/تسوية موثّقة"})
        if not exists:
            totals[m["currency"]] += m["difference"]
    return {"count": len(rows), "totals": {c: round(v, 2) for c, v in totals.items()},
            "execution_enabled": _os.environ.get("ALLOW_RECONCILIATION") == "true",
            "wallet_writes": 0,
            "idempotency": "قيد افتتاحي واحد فقط لكل (حساب + عملة) — أي تشغيل ثانٍ يُرفض",
            "note": "معاينة فقط — لا يوجد أي تعديل على الأرصدة ولا كتابة أي قيد. "
                    "التشغيل الفعلي يحتاج ALLOW_RECONCILIATION=true بعد اعتمادكم.",
            "items": rows}


@router.post("/reconciliation/adjust-all")
async def adjust_all(payload: AdjustIn, admin: dict = Depends(require_admin)):
    """Bulk opening entries for every mismatching account (same rules, one entry each)."""
    import os as _os
    if not payload.dry_run and _os.environ.get("ALLOW_RECONCILIATION") != "true":
        raise HTTPException(403, "تشغيل قيود التسوية معطّل حتى الاعتماد الصريح "
                                 "(ALLOW_RECONCILIATION=false) — استخدم Dry-run للمعاينة")
    from finance import reconciliation as _recon
    rec = await _recon(admin, full=True)
    done, skipped = [], 0
    for m in rec["mismatches"]:
        try:
            r = await adjust_reconciliation(AdjustIn(
                office_id=m["office_id"], currency=m["currency"],
                reason=payload.reason.strip(), dry_run=payload.dry_run), admin)
            done.append({"office": m["name"], "currency": m["currency"],
                         "amount": r.get("amount") or r.get("difference")})
        except HTTPException:
            skipped += 1
    return {"processed": len(done), "skipped": skipped, "dry_run": payload.dry_run,
            "entries": done[:100]}


@router.get("/withdrawals/{wid}/detail")
async def withdrawal_detail(wid: str, admin: dict = Depends(require_admin)):
    w = await db.withdrawals.find_one({"_id": oid(wid)})
    if not w:
        raise HTTPException(404, "طلب السحب غير موجود")
    u = await db.users.find_one({"_id": oid(w["office_id"])},
                                {"office_name": 1, "email": 1, "phone": 1, "wallet": 1})
    d = serialize(w)
    d["stage"] = w.get("stage") or ("closed" if w.get("status") == "approved" else "requested")
    d["stage_label"] = STAGE_LABEL.get(d["stage"], d["stage"])
    d["office"] = {"name": (u or {}).get("office_name"), "email": (u or {}).get("email"),
                   "phone": (u or {}).get("phone"),
                   "available": round(wallet_available((u or {}).get("wallet") or {},
                                                       w.get("currency", "USD")), 2)}
    return d
