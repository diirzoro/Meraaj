import uuid
import time
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from db import db, serialize, oid, now_iso, adjust_wallet, log_txn, wallet_available, log_platform_revenue, audit
from security import require_admin
from market import _room_customer_price, _room_num
from integration import notify_rahal

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/packages/resync")
async def resync_packages(admin: dict = Depends(require_admin)):
    """Batch re-sync: re-derive flat scalar pricing (final_sale_price / net / commission)
    from each package's room_pricing (adult) so corrected prices show in the market, and
    push an outbound update to Rahal for Rahal-origin packages."""
    docs = await db.packages.find({}).to_list(5000)
    updated, notified = 0, 0
    for d in docs:
        rooms = d.get("room_pricing") or []
        if not rooms:
            continue
        base = rooms[0]
        upd = {}
        def _needs(v):
            return v is None or isinstance(v, dict) or not v
        sale = _room_customer_price(base.get("customer"), "adult")
        net = _room_num(base.get("net"), "adult")
        comm = _room_num(base.get("commission"), "adult")
        if sale is not None and _needs(d.get("final_sale_price")):
            upd["final_sale_price"] = round(sale, 2)
        if net is not None and _needs(d.get("net_cost_per_seat")):
            upd["net_cost_per_seat"] = round(net, 2)
        if comm is not None and (d.get("buyer_office_commission") is None or isinstance(d.get("buyer_office_commission"), dict)):
            upd["buyer_office_commission"] = round(comm, 2)
        if upd:
            await db.packages.update_one({"_id": d["_id"]}, {"$set": upd})
            updated += 1
        if d.get("rahal_ref"):
            await notify_rahal("package.updated", {
                "meraaj_package_id": str(d["_id"]), "package_ref": d.get("rahal_ref"),
                "room_pricing": rooms,
            })
            notified += 1
    return {"ok": True, "total": len(docs), "updated": updated, "rahal_notified": notified}


@router.get("/dashboard")
async def dashboard(admin: dict = Depends(require_admin)):
    users = await db.users.find({"role": {"$in": ["office", "individual"]}}).to_list(5000)

    def _liq():
        return {"SAR": {"available": 0.0, "pending": 0.0, "total": 0.0},
                "USD": {"available": 0.0, "pending": 0.0, "total": 0.0}}

    liq = _liq()
    for u in users:
        w = u.get("wallet") or {}
        for c in ("SAR", "USD"):
            cw = w.get(c) or {}
            liq[c]["available"] += cw.get("available", 0.0)
            liq[c]["pending"] += cw.get("pending", 0.0)
            liq[c]["total"] += cw.get("total", 0.0)
    for c in ("SAR", "USD"):
        for k in liq[c]:
            liq[c][k] = round(liq[c][k], 2)

    pending_topups = await db.topups.count_documents({"status": "pending"})
    pending_transfers = await db.transfers.count_documents({"status": "pending"})
    pending_withdrawals = await db.withdrawals.count_documents({"status": "pending"})
    open_disputes = await db.bookings.count_documents({"dispute.status": "open"})
    rev_rows = await db.platform_revenue.aggregate(
        [{"$group": {"_id": "$currency", "t": {"$sum": "$amount"}}}]).to_list(10)
    platform_revenue = {"SAR": 0.0, "USD": 0.0}
    for r in rev_rows:
        c = r["_id"] if r["_id"] in ("SAR", "USD") else "USD"
        platform_revenue[c] = round(platform_revenue[c] + r["t"], 2)
    offices_count = await db.users.count_documents({"role": "office"})
    individuals_count = await db.users.count_documents({"role": "individual"})
    marketers_count = await db.users.count_documents({"role": "individual", "is_marketer": True})
    return {
        "liquidity": liq,
        "platform_revenue": platform_revenue,
        "offices_count": offices_count,
        "packages_count": await db.packages.count_documents({}),
        "bookings_count": await db.bookings.count_documents({}),
        "pending_topups": pending_topups,
        "pending_transfers": pending_transfers,
        "pending_withdrawals": pending_withdrawals,
        "open_disputes": open_disputes,
        "individuals_count": individuals_count,
        "marketers_count": marketers_count,
    }


# ---------- Offices ----------
@router.get("/offices")
async def offices(admin: dict = Depends(require_admin)):
    docs = await db.users.find({"role": "office"}).sort("created_at", -1).to_list(1000)
    return serialize(docs)


@router.patch("/offices/{office_id}/status")
async def set_office_status(office_id: str, payload: dict, admin: dict = Depends(require_admin)):
    status = payload.get("status")
    if status not in ("active", "suspended"):
        raise HTTPException(400, "حالة غير صالحة")
    await db.users.update_one({"_id": oid(office_id), "role": "office"}, {"$set": {"status": status}})
    return {"ok": True, "status": status}


# ---------- Top-ups ----------
@router.get("/topups")
async def topups(status: str = "pending", admin: dict = Depends(require_admin)):
    q = {} if status == "all" else {"status": status}
    docs = await db.topups.find(q).sort("created_at", -1).to_list(500)
    return serialize(docs)


@router.post("/topups/{topup_id}/review")
async def review_topup(topup_id: str, payload: dict, admin: dict = Depends(require_admin)):
    t = await db.topups.find_one({"_id": oid(topup_id)})
    if not t or t["status"] != "pending":
        raise HTTPException(404, "طلب الشحن غير موجود أو تمت مراجعته")
    approve = payload.get("approve", False)
    if approve:
        cur = t.get("currency", "USD")
        await adjust_wallet(oid(t["office_id"]), cur, available=t["amount"], total=t["amount"])
        await log_txn(t["office_id"], "topup", t["amount"], f"شحن محفظة ({t['method']})", topup_id, currency=cur)
    await db.topups.update_one({"_id": t["_id"]}, {"$set": {
        "status": "approved" if approve else "rejected", "reviewed_at": now_iso()}})
    return {"ok": True, "status": "approved" if approve else "rejected"}


# ---------- Transfers (P2P) ----------
@router.get("/transfers")
async def transfers(status: str = "pending", admin: dict = Depends(require_admin)):
    q = {} if status == "all" else {"status": status}
    docs = await db.transfers.find(q).sort("created_at", -1).to_list(500)
    return serialize(docs)


@router.post("/transfers/{transfer_id}/review")
async def review_transfer(transfer_id: str, payload: dict, admin: dict = Depends(require_admin)):
    tr = await db.transfers.find_one({"_id": oid(transfer_id)})
    if not tr or tr["status"] != "pending":
        raise HTTPException(404, "طلب التحويل غير موجود أو تمت مراجعته")
    approve = payload.get("approve", False)
    if approve:
        cur = tr.get("currency", "USD")
        sender = await db.users.find_one({"_id": oid(tr["from_office_id"])})
        if wallet_available(sender["wallet"], cur) < tr["amount"]:
            raise HTTPException(400, "رصيد المُرسِل غير كافٍ")
        await adjust_wallet(oid(tr["from_office_id"]), cur, available=-tr["amount"], total=-tr["amount"])
        await adjust_wallet(oid(tr["to_office_id"]), cur, available=tr["amount"], total=tr["amount"])
        await log_txn(tr["from_office_id"], "p2p_out", -tr["amount"], f"تحويل إلى {tr['to_office_name']}", transfer_id, currency=cur)
        await log_txn(tr["to_office_id"], "p2p_in", tr["amount"], f"تحويل من {tr['from_office_name']}", transfer_id, currency=cur)
    await db.transfers.update_one({"_id": tr["_id"]}, {"$set": {
        "status": "approved" if approve else "rejected", "reviewed_at": now_iso()}})
    return {"ok": True, "status": "approved" if approve else "rejected"}


# ---------- Withdrawals ----------
@router.get("/withdrawals")
async def withdrawals(status: str = "pending", admin: dict = Depends(require_admin)):
    q = {} if status == "all" else {"status": status}
    docs = await db.withdrawals.find(q).sort("created_at", -1).to_list(500)
    return serialize(docs)


@router.post("/withdrawals/{wid}/review")
async def review_withdrawal(wid: str, payload: dict, admin: dict = Depends(require_admin)):
    w = await db.withdrawals.find_one({"_id": oid(wid)})
    if not w or w["status"] != "pending":
        raise HTTPException(404, "طلب السحب غير موجود أو تمت مراجعته")
    approve = payload.get("approve", False)
    if approve:
        cur = w.get("currency", "USD")
        office = await db.users.find_one({"_id": oid(w["office_id"])})
        if wallet_available(office["wallet"], cur) < w["amount"]:
            raise HTTPException(400, "رصيد المكتب غير كافٍ")
        await adjust_wallet(oid(w["office_id"]), cur, available=-w["amount"], total=-w["amount"])
        await log_txn(w["office_id"], "withdrawal", -w["amount"], f"سحب أرباح ({w['method']})", wid, currency=cur)
    await db.withdrawals.update_one({"_id": w["_id"]}, {"$set": {
        "status": "approved" if approve else "rejected", "reviewed_at": now_iso()}})
    return {"ok": True, "status": "approved" if approve else "rejected"}


# ---------- Disputes ----------
@router.get("/disputes")
async def disputes(admin: dict = Depends(require_admin)):
    docs = await db.bookings.find({"dispute": {"$ne": None}}).sort("created_at", -1).to_list(500)
    return serialize(docs)


@router.post("/disputes/{booking_id}/resolve")
async def resolve_dispute(booking_id: str, payload: dict, admin: dict = Depends(require_admin)):
    """resolution: 'refund_buyer' | 'release_seller'"""
    b = await db.bookings.find_one({"_id": oid(booking_id)})
    if not b or not b.get("dispute"):
        raise HTTPException(404, "لا يوجد نزاع")
    if b["dispute"].get("status") != "open" or b.get("settled"):
        raise HTTPException(400, "تم حسم هذا النزاع مسبقاً")
    resolution = payload.get("resolution")
    net = b["net_cost_total"]
    fee = b["platform_fee"]
    cur = b.get("currency", "USD")
    if resolution == "refund_buyer":
        refund = round(b["net_cost_total"] + b["platform_fee"], 2)
        await adjust_wallet(oid(b["seller_id"]), cur, pending=-net, total=-net)
        await adjust_wallet(oid(b["buyer_id"]), cur, available=refund, total=refund)
        await db.packages.update_one({"_id": oid(b["package_id"])}, {"$inc": {"available_seats": b["seats"]}})
        await log_txn(b["buyer_id"], "dispute_refund", refund, f"استرداد نزاع: {b['package_title']}", booking_id, currency=cur)
        new_status = "cancelled"
    elif resolution == "release_seller":
        await adjust_wallet(oid(b["seller_id"]), cur, pending=-net, available=(net - fee), total=-fee)
        await log_txn(b["seller_id"], "dispute_release", net - fee, f"فك نزاع لصالح البائع: {b['package_title']}", booking_id, currency=cur)
        new_status = "green"
    else:
        raise HTTPException(400, "قرار غير صالح")
    await db.bookings.update_one({"_id": b["_id"]}, {"$set": {
        "dispute.status": "resolved", "dispute.resolution": resolution, "settled": True,
        "settled_at": now_iso(), "status": new_status}})
    return {"ok": True, "resolution": resolution}


@router.get("/cancellations")
async def list_cancellations(admin: dict = Depends(require_admin)):
    """Super Admin review queue: approved bookings with a pending cancellation request,
    including the buyer's reason and the Rahal owner's position/evidence/executed costs."""
    docs = await db.bookings.find({"cancellation_status": "requested"}).sort("cancellation_requested_at", -1).to_list(500)
    return serialize(docs)


class CancellationDecisionInput(BaseModel):
    decision: str            # cancelled | kept
    refund_amount: float = 0.0
    seller_compensation: float = 0.0
    reason: str = ""


@router.post("/bookings/{booking_id}/cancellation-decision")
async def decide_cancellation(booking_id: str, payload: CancellationDecisionInput,
                              admin: dict = Depends(require_admin)):
    """FINAL cancellation authority (Meraaj is source of truth for escrow). Validates the
    settlement identity, applies the split atomically (idempotent), and emits
    meraaj.booking.cancellation_finalized to Rahal."""
    b = await db.bookings.find_one({"_id": oid(booking_id)})
    if not b:
        raise HTTPException(404, "الحجز غير موجود")
    if b.get("cancellation_status") != "requested":
        raise HTTPException(400, "لا يوجد طلب إلغاء قيد المراجعة على هذا الحجز")
    if payload.decision not in ("cancelled", "kept"):
        raise HTTPException(400, "قرار غير صالح")
    cur = b.get("currency", "USD")
    original = round(b.get("amount_charged", 0) or 0, 2)     # escrow anchor = buyer's held total
    net_total = round(b.get("net_cost_total", 0) or 0, 2)

    if payload.decision == "kept":
        refund_amount = 0.0
        seller_compensation = net_total
        platform_adjustment = round(original - seller_compensation, 2)
    else:
        refund_amount = round(payload.refund_amount, 2)
        seller_compensation = round(payload.seller_compensation, 2)
        platform_adjustment = round(original - refund_amount - seller_compensation, 2)
        if refund_amount < 0 or seller_compensation < 0 or platform_adjustment < -0.01:
            raise HTTPException(400, "المبالغ غير صالحة (سالبة أو تتجاوز المبلغ الأصلي)")
    # Settlement identity (±0.01)
    if abs((refund_amount + seller_compensation + platform_adjustment) - original) > 0.01:
        raise HTTPException(400, "مجموع (الاسترداد + تعويض البائع + تسوية المنصة) يجب أن يساوي المبلغ الأصلي")

    # Atomic claim => idempotent final state (blocks duplicate decisions)
    claimed = await db.bookings.find_one_and_update(
        {"_id": b["_id"], "cancellation_status": "requested"},
        {"$set": {"cancellation_status": "decided" if payload.decision == "cancelled" else "rejected",
                  "status": "cancelled" if payload.decision == "cancelled" else b.get("status", "blue"),
                  "cancellation_final": {
                      "decision": payload.decision, "original_amount": original,
                      "refund_amount": refund_amount, "seller_compensation": seller_compensation,
                      "platform_adjustment": platform_adjustment, "currency": cur,
                      "reason": payload.reason, "decided_by": f"super_admin:{admin['_id']}",
                      "decided_at": now_iso()}}})
    if not claimed:
        raise HTTPException(409, "تم اتخاذ القرار على هذا الطلب بالفعل")

    if payload.decision == "cancelled":
        # 1) Reverse effects recognized at approval, then 2) redistribute the held amount.
        await adjust_wallet(oid(claimed["seller_id"]), cur, pending=-net_total, total=-net_total)
        if claimed.get("buyer_type") == "office" and claimed.get("platform_fee"):
            await log_platform_revenue(-claimed["platform_fee"], f"عكس عمولة منصة (إلغاء نهائي): {claimed.get('package_title','')}", booking_id, currency=cur)
        if claimed.get("buyer_type") != "office":
            if claimed.get("marketer_id") and claimed.get("marketer_commission"):
                await adjust_wallet(oid(claimed["marketer_id"]), cur, pending=-claimed["marketer_commission"], total=-claimed["marketer_commission"])
                await log_txn(claimed["marketer_id"], "marketer_commission_reversal", -claimed["marketer_commission"], f"عكس عمولة تسويق (إلغاء نهائي): {claimed.get('package_title','')}", booking_id, currency=cur)
            if claimed.get("platform_profit"):
                await log_platform_revenue(-claimed["platform_profit"], f"عكس أرباح (إلغاء نهائي): {claimed.get('package_title','')}", booking_id, currency=cur)
        if refund_amount:
            await adjust_wallet(oid(claimed["buyer_id"]), cur, available=refund_amount, total=refund_amount)
            await log_txn(claimed["buyer_id"], "cancel_refund", refund_amount, f"استرداد إلغاء نهائي: {claimed.get('package_title','')}", booking_id, currency=cur)
        if seller_compensation:
            await adjust_wallet(oid(claimed["seller_id"]), cur, available=seller_compensation, total=seller_compensation)
            await log_txn(claimed["seller_id"], "seller_compensation", seller_compensation, f"تعويض البائع (إلغاء): {claimed.get('package_title','')}", booking_id, currency=cur)
        if platform_adjustment:
            await log_platform_revenue(platform_adjustment, f"تسوية المنصة (إلغاء نهائي): {claimed.get('package_title','')}", booking_id, currency=cur)
        await db.packages.update_one({"_id": oid(claimed["package_id"])}, {"$inc": {"available_seats": claimed.get("seats", 0)}})
        await db.trip_passports.delete_many({"booking_id": booking_id})

    await audit(booking_id, f"cancellation_{payload.decision}", "super_admin", actor_id=str(admin["_id"]),
                reason=payload.reason, meta={"refund": refund_amount, "seller_compensation": seller_compensation,
                                             "platform_adjustment": platform_adjustment})
    if claimed.get("rahal_ref"):
        await notify_rahal("meraaj.booking.cancellation_finalized", {}, envelope={
            "id": str(uuid.uuid4()), "type": "meraaj.booking.cancellation_finalized",
            "timestamp": int(time.time()),
            "data": {"booking_ref": booking_id, "decision": payload.decision,
                     "original_amount": original, "refund_amount": refund_amount,
                     "seller_compensation": seller_compensation, "platform_adjustment": platform_adjustment,
                     "currency": cur, "reason": payload.reason,
                     "decided_by": f"super_admin:{admin['_id']}", "decided_at": now_iso()}})
    return {"ok": True, "decision": payload.decision, "original_amount": original,
            "refund_amount": refund_amount, "seller_compensation": seller_compensation,
            "platform_adjustment": platform_adjustment}
