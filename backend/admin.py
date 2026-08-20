from fastapi import APIRouter, HTTPException, Depends
from db import db, serialize, oid, now_iso, adjust_wallet, log_txn
from security import require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/dashboard")
async def dashboard(admin: dict = Depends(require_admin)):
    offices = await db.users.find({"role": "office"}).to_list(1000)
    total_available = sum(o["wallet"]["available"] for o in offices)
    total_pending = sum(o["wallet"]["pending"] for o in offices)
    total_system = sum(o["wallet"]["total"] for o in offices)
    pending_topups = await db.topups.count_documents({"status": "pending"})
    pending_transfers = await db.transfers.count_documents({"status": "pending"})
    pending_withdrawals = await db.withdrawals.count_documents({"status": "pending"})
    open_disputes = await db.bookings.count_documents({"dispute.status": "open"})
    return {
        "total_system_balance": round(total_system, 2),
        "total_available": round(total_available, 2),
        "total_pending": round(total_pending, 2),
        "offices_count": len(offices),
        "packages_count": await db.packages.count_documents({}),
        "bookings_count": await db.bookings.count_documents({}),
        "pending_topups": pending_topups,
        "pending_transfers": pending_transfers,
        "pending_withdrawals": pending_withdrawals,
        "open_disputes": open_disputes,
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
        await adjust_wallet(oid(t["office_id"]), available=t["amount"], total=t["amount"])
        await log_txn(t["office_id"], "topup", t["amount"], f"شحن محفظة ({t['method']})", topup_id)
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
        sender = await db.users.find_one({"_id": oid(tr["from_office_id"])})
        if sender["wallet"]["available"] < tr["amount"]:
            raise HTTPException(400, "رصيد المُرسِل غير كافٍ")
        await adjust_wallet(oid(tr["from_office_id"]), available=-tr["amount"], total=-tr["amount"])
        await adjust_wallet(oid(tr["to_office_id"]), available=tr["amount"], total=tr["amount"])
        await log_txn(tr["from_office_id"], "p2p_out", -tr["amount"], f"تحويل إلى {tr['to_office_name']}", transfer_id)
        await log_txn(tr["to_office_id"], "p2p_in", tr["amount"], f"تحويل من {tr['from_office_name']}", transfer_id)
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
        office = await db.users.find_one({"_id": oid(w["office_id"])})
        if office["wallet"]["available"] < w["amount"]:
            raise HTTPException(400, "رصيد المكتب غير كافٍ")
        await adjust_wallet(oid(w["office_id"]), available=-w["amount"], total=-w["amount"])
        await log_txn(w["office_id"], "withdrawal", -w["amount"], f"سحب أرباح ({w['method']})", wid)
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
    if resolution == "refund_buyer":
        refund = round(b["net_cost_total"] + b["platform_fee"], 2)
        await adjust_wallet(oid(b["seller_id"]), pending=-net, total=-net)
        await adjust_wallet(oid(b["buyer_id"]), available=refund, total=refund)
        await db.packages.update_one({"_id": oid(b["package_id"])}, {"$inc": {"available_seats": b["seats"]}})
        await log_txn(b["buyer_id"], "dispute_refund", refund, f"استرداد نزاع: {b['package_title']}", booking_id)
        new_status = "cancelled"
    elif resolution == "release_seller":
        await adjust_wallet(oid(b["seller_id"]), pending=-net, available=(net - fee), total=-fee)
        await log_txn(b["seller_id"], "dispute_release", net - fee, f"فك نزاع لصالح البائع: {b['package_title']}", booking_id)
        new_status = "green"
    else:
        raise HTTPException(400, "قرار غير صالح")
    await db.bookings.update_one({"_id": b["_id"]}, {"$set": {
        "dispute.status": "resolved", "dispute.resolution": resolution, "settled": True,
        "settled_at": now_iso(), "status": new_status}})
    return {"ok": True, "resolution": resolution}
