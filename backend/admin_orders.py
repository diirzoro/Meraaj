"""Enterprise Orders Center (Super Admin) — read/oversight layer over bookings.
ADDITIVE ONLY: does not alter the booking lifecycle, money engine, Rahal contract or
the seller decision authority (new → seller review → approve/reject stays intact).
"""
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from bson import ObjectId
from bson.errors import InvalidId

from db import db, serialize, oid, now_iso, audit
from security import require_admin
from finance import booking_financials

router = APIRouter(prefix="/api/admin", tags=["admin-orders"])

STATUSES = ("blue", "yellow", "green", "cancelled")


def _now():
    return datetime.now(timezone.utc)


def _parse(dt) -> Optional[datetime]:
    try:
        d = datetime.fromisoformat(str(dt))
    except Exception:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _attention(b: dict) -> List[str]:
    """Reasons a booking needs Super Admin intervention (computed, never stored)."""
    out = []
    now = _now()
    if b.get("approval_status") == "pending":
        exp = _parse(b.get("approval_expires_at"))
        if exp and exp <= now:
            out.append("انتهت مهلة اعتماد البائع")
        else:
            out.append("بانتظار مراجعة البائع")
    if b.get("cancellation_status") == "requested":
        out.append("طلب إلغاء بانتظار قرار الإدارة")
    if (b.get("dispute") or {}).get("status") == "open":
        out.append("نزاع مفتوح")
    dep = _parse(b.get("departure_date"))
    if b.get("status") in ("blue", "yellow") and dep and dep <= now:
        out.append("تاريخ السفر مضى والحجز لم يُفوَّج")
    if b.get("status") == "green" and not b.get("settled"):
        d = _parse(b.get("dispatched_at"))
        if d and (now - d) > timedelta(hours=48):
            out.append("مضى أكثر من 48 ساعة على التفويج بدون تسوية")
    if b.get("delivery_status") == "failed":
        out.append("فشل تسليم الحدث إلى رحّال")
    if b.get("escalated"):
        out.append("مُصعَّد إدارياً")
    return out


def _severity(reasons: List[str]) -> str:
    if not reasons:
        return "ok"
    hard = ("انتهت", "نزاع", "طلب إلغاء", "مضى", "فشل", "مُصعَّد")
    return "critical" if any(r.startswith(hard) for r in reasons) else "warning"


def _decorate(b: dict) -> dict:
    d = serialize(b)
    r = _attention(b)
    d["attention_reasons"] = r
    d["needs_attention"] = bool(r)
    d["severity"] = _severity(r)
    d["gross_total"] = round(float(b.get("amount_charged") or 0), 2)
    d["seller_net"] = round(float(b.get("net_cost_total") or 0), 2)
    d["platform_total"] = round(float(b.get("platform_fee") or 0)
                                + float(b.get("platform_profit") or 0), 2)
    return d


@router.get("/bookings")
async def admin_bookings(
    q: Optional[str] = None,
    status: Optional[str] = None,
    approval_status: Optional[str] = None,
    cancellation_status: Optional[str] = None,
    currency: Optional[str] = None,
    seller_id: Optional[str] = None,
    buyer_id: Optional[str] = None,
    package_id: Optional[str] = None,
    source: Optional[str] = None,
    attention: bool = False,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    sort: str = "newest",
    page: int = 1,
    limit: int = Query(25, le=200),
    admin: dict = Depends(require_admin),
):
    f: dict = {}
    if status in STATUSES:
        f["status"] = status
    if approval_status:
        f["approval_status"] = approval_status
    if cancellation_status:
        f["cancellation_status"] = cancellation_status
    if currency in ("SAR", "USD"):
        f["currency"] = currency
    if seller_id:
        f["seller_id"] = seller_id
    if buyer_id:
        f["buyer_id"] = buyer_id
    if package_id:
        f["package_id"] = package_id
    if source == "rahal":
        f["rahal_ref"] = {"$ne": None}
    elif source == "meraaj":
        f["rahal_ref"] = None
    if date_from or date_to:
        rng = {}
        if date_from:
            rng["$gte"] = date_from
        if date_to:
            rng["$lte"] = date_to + "T23:59:59.999999+00:00"
        f["created_at"] = rng
    if q:
        term = q.strip()
        ors = [
            {"package_title": {"$regex": term, "$options": "i"}},
            {"buyer_office_name": {"$regex": term, "$options": "i"}},
            {"seller_office_name": {"$regex": term, "$options": "i"}},
            {"registrants.name": {"$regex": term, "$options": "i"}},
            {"registrants.passport_no": {"$regex": term, "$options": "i"}},
            {"rahal_ref": {"$regex": term, "$options": "i"}},
        ]
        try:
            ors.append({"_id": ObjectId(term)})
        except (InvalidId, TypeError):
            pass
        f["$or"] = ors

    if attention:
        # Applied at DB level so total / pagination / amount_totals stay correct.
        now_s = _now().isoformat()
        today_s = _now().date().isoformat()
        att = [
            {"approval_status": "pending"},
            {"cancellation_status": "requested"},
            {"dispute.status": "open"},
            {"escalated": True},
            {"delivery_status": "failed"},
            {"status": {"$in": ["blue", "yellow"]}, "departure_date": {"$lte": today_s}},
            {"status": "green", "settled": {"$ne": True},
             "dispatched_at": {"$lte": (_now() - timedelta(hours=48)).isoformat()}},
        ]
        _ = now_s
        f = {"$and": [f, {"$or": att}]} if f else {"$or": att}

    order = {"newest": [("created_at", -1)], "oldest": [("created_at", 1)],
             "amount_desc": [("amount_charged", -1)], "amount_asc": [("amount_charged", 1)],
             "departure_asc": [("departure_date", 1)]}.get(sort, [("created_at", -1)])

    total = await db.bookings.count_documents(f)
    skip = max(0, (page - 1) * limit)
    docs = await db.bookings.find(f).sort(order).skip(skip).limit(limit).to_list(limit)
    items = [_decorate(d) for d in docs]

    tot = {"SAR": 0.0, "USD": 0.0}
    async for r in db.bookings.aggregate([{"$match": f}, {"$group": {
            "_id": "$currency", "t": {"$sum": "$amount_charged"}}}]):
        if r["_id"] in tot:
            tot[r["_id"]] = round(r["t"], 2)
    return {"items": items, "total": total, "page": page, "limit": limit,
            "amount_totals": tot}


@router.get("/bookings/{booking_id}/full")
async def admin_booking_full(booking_id: str, admin: dict = Depends(require_admin)):
    b = await db.bookings.find_one({"_id": oid(booking_id)})
    if not b:
        raise HTTPException(404, "الحجز غير موجود")
    async def by_id(coll, raw):
        """Legacy/Rahaal rows can carry a non-ObjectId reference; a bad id must render the
        page without that party instead of failing the whole request with a 500."""
        if not raw:
            return None
        try:
            return await coll.find_one({"_id": oid(raw)})
        except Exception:
            return await coll.find_one({"rahal_ref": raw}) or None

    pkg = await by_id(db.packages, b.get("package_id"))
    buyer = await by_id(db.users, b.get("buyer_id"))
    seller = await by_id(db.users, b.get("seller_id"))
    docs = await db.traveler_documents.find({"booking_id": booking_id}).sort("created_at", 1).to_list(500)
    events = await db.booking_events.find({"booking_id": booking_id}).sort("at", 1).to_list(500)
    notes = await db.admin_notes.find({"booking_id": booking_id}).sort("created_at", -1).to_list(200)
    tasks = await db.admin_tasks.find({"booking_id": booking_id}).sort("created_at", -1).to_list(200)
    txns = await db.transactions.find({"ref": booking_id}).sort("created_at", 1).to_list(200)

    def party(u):
        if not u:
            return None
        return {"id": str(u["_id"]), "name": u.get("office_name") or u.get("name"),
                "email": u.get("email"), "phone": u.get("phone"),
                "role": u.get("role"), "status": u.get("status"),
                "governorate": u.get("governorate")}

    missing = []
    for i, r in enumerate(b.get("registrants") or []):
        have = {d["doc_type"] for d in docs if d.get("registrant_index") == i}
        lack = [t for t in ("passport", "visa") if t not in have]
        if lack:
            missing.append({"index": i, "name": r.get("name"), "missing": lack})

    return {
        "booking": _decorate(b),
        "package": serialize(pkg) if pkg else None,
        "buyer": party(buyer), "seller": party(seller),
        "documents": serialize(docs), "missing_documents": missing,
        "timeline": serialize(events), "notes": serialize(notes),
        "tasks": serialize(tasks), "transactions": serialize(txns),
        "financials": {
            **booking_financials(b, txns),
            "platform_fee": round(float(b.get("platform_fee") or 0), 2),
            "platform_profit": round(float(b.get("platform_profit") or 0), 2),
        },
    }


class NoteIn(BaseModel):
    text: str = Field(min_length=2)


@router.post("/bookings/{booking_id}/notes")
async def add_note(booking_id: str, payload: NoteIn, admin: dict = Depends(require_admin)):
    b = await db.bookings.find_one({"_id": oid(booking_id)}, {"_id": 1})
    if not b:
        raise HTTPException(404, "الحجز غير موجود")
    rec = {"booking_id": booking_id, "text": payload.text.strip(), "internal": True,
           "author_id": str(admin["_id"]), "author_email": admin.get("email"),
           "created_at": now_iso()}
    res = await db.admin_notes.insert_one(rec)
    rec["_id"] = res.inserted_id
    await audit(booking_id, "admin_internal_note", "super_admin", actor_id=str(admin["_id"]),
                meta={"chars": len(rec["text"])})
    return serialize(rec)


class TaskIn(BaseModel):
    title: str = Field(min_length=2)
    assignee: str = ""
    due_date: Optional[str] = None
    priority: str = "normal"


@router.post("/bookings/{booking_id}/tasks")
async def add_task(booking_id: str, payload: TaskIn, admin: dict = Depends(require_admin)):
    b = await db.bookings.find_one({"_id": oid(booking_id)}, {"package_title": 1})
    if not b:
        raise HTTPException(404, "الحجز غير موجود")
    if payload.priority not in ("low", "normal", "high", "urgent"):
        raise HTTPException(400, "أولوية غير صالحة")
    rec = {"booking_id": booking_id, "package_title": b.get("package_title"),
           "title": payload.title.strip(), "assignee": payload.assignee.strip(),
           "due_date": payload.due_date, "priority": payload.priority,
           "status": "open", "created_by": str(admin["_id"]), "created_at": now_iso(),
           "closed_at": None}
    res = await db.admin_tasks.insert_one(rec)
    rec["_id"] = res.inserted_id
    await audit(booking_id, "admin_task_created", "super_admin", actor_id=str(admin["_id"]),
                meta={"title": rec["title"], "assignee": rec["assignee"]})
    return serialize(rec)


class TaskStatusIn(BaseModel):
    status: str


@router.patch("/tasks/{task_id}")
async def set_task_status(task_id: str, payload: TaskStatusIn, admin: dict = Depends(require_admin)):
    if payload.status not in ("open", "in_progress", "done", "cancelled"):
        raise HTTPException(400, "حالة غير صالحة")
    t = await db.admin_tasks.find_one_and_update(
        {"_id": oid(task_id)},
        {"$set": {"status": payload.status,
                  "closed_at": now_iso() if payload.status in ("done", "cancelled") else None}},
        return_document=True)
    if not t:
        raise HTTPException(404, "المهمة غير موجودة")
    await audit(t["booking_id"], "admin_task_updated", "super_admin", actor_id=str(admin["_id"]),
                meta={"task_id": task_id, "status": payload.status})
    return serialize(t)


@router.get("/tasks")
async def list_tasks(status: Optional[str] = None, assignee: Optional[str] = None,
                     admin: dict = Depends(require_admin)):
    f = {}
    if status:
        f["status"] = status
    if assignee:
        f["assignee"] = assignee
    docs = await db.admin_tasks.find(f).sort("created_at", -1).to_list(500)
    return serialize(docs)


class EscalateIn(BaseModel):
    reason: str = Field(min_length=3)


@router.post("/bookings/{booking_id}/escalate")
async def escalate(booking_id: str, payload: EscalateIn, admin: dict = Depends(require_admin)):
    """Flags a booking for management follow-up. Does NOT change its business status,
    money or the seller's decision — oversight only."""
    b = await db.bookings.find_one_and_update(
        {"_id": oid(booking_id)},
        {"$set": {"escalated": True, "escalated_at": now_iso(),
                  "escalation_reason": payload.reason.strip(),
                  "escalated_by": str(admin["_id"])}},
        return_document=True)
    if not b:
        raise HTTPException(404, "الحجز غير موجود")
    await audit(booking_id, "admin_escalated", "super_admin", actor_id=str(admin["_id"]),
                reason=payload.reason.strip())
    return _decorate(b)


@router.post("/bookings/{booking_id}/de-escalate")
async def de_escalate(booking_id: str, admin: dict = Depends(require_admin)):
    b = await db.bookings.find_one_and_update(
        {"_id": oid(booking_id)},
        {"$set": {"escalated": False, "resolved_at": now_iso()}}, return_document=True)
    if not b:
        raise HTTPException(404, "الحجز غير موجود")
    await audit(booking_id, "admin_escalation_closed", "super_admin", actor_id=str(admin["_id"]))
    return _decorate(b)
