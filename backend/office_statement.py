"""كشف حساب المكتب — BUSINESS statement, NOT a general ledger.

It reads the EXISTING business sources only (`db.transactions` written by `log_txn`, plus the
office wallet) and presents the office's commercial relationship with Meraaj. It never reads
a journal, never exposes a chart of accounts, and no office receives an accounting entity:
`office_id` is NEVER translated into `entity_id`.

Office isolation is enforced in the backend: an office/staff account can only ever read its
OWN office, whatever `office_id` it sends.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from db import db, oid, wallet_available
from rbac import has_perm
from security import get_current_user

router = APIRouter(prefix="/api/office-statement", tags=["office-statement"])

#: how each business movement reads on an office statement (in = money toward the office)
MOVEMENT_LABELS = {
    "topup": ("شحن المحفظة", "in"), "withdrawal": ("سحب", "out"),
    "booking_debit": ("حجز (شراء)", "out"), "booking_escrow": ("إيراد معلّق (بيع)", "in"),
    "settlement": ("تسوية حجز", "in"), "cancel_refund": ("استرداد إلغاء", "in"),
    "cancel_deduction": ("خصم إلغاء", "in"), "dispute_refund": ("استرداد نزاع", "in"),
    "dispute_release": ("فك نزاع", "in"), "seller_compensation": ("تعويض بائع", "in"),
    "commission_adjustment": ("تعديل عمولة", "out"),
    "marketer_commission": ("عمولة تسويق (معلّقة)", "in"),
    "marketer_commission_release": ("تحرير عمولة تسويق", "in"),
    "marketer_commission_reversal": ("عكس عمولة تسويق", "out"),
    "p2p_out": ("تحويل صادر (B2B)", "out"), "p2p_in": ("تحويل وارد (B2B)", "in"),
    "ads_hold": ("تجنيب إعلان", "out"), "ads_capture": ("تحصيل إعلان", "out"),
    "ads_release": ("فك تجنيب إعلان", "in"), "adjustment": ("تسوية إدارية", "in"),
    "hold_release": ("فك تجنيب", "in"),
}


async def _resolve_office(user: dict, requested: Optional[str]) -> dict:
    """BUSINESS OFFICE SCOPE — never an accounting entity. An office user is pinned to its
    own office (staff act inside the office identity); a privileged user may pass an id."""
    own_id = str(user.get("parent_office_id") or user["_id"])
    if user.get("role") == "super_admin" or await has_perm(user, "office.statement.view"):
        target = (requested or "").strip() or own_id
    else:
        if requested and requested.strip() and requested.strip() != own_id:
            raise HTTPException(403, "لا تملك صلاحية الوصول إلى كشف حساب مكتب آخر")
        target = own_id
    office = await db.users.find_one({"_id": oid(target)})
    if not office:
        raise HTTPException(404, "المكتب غير موجود")
    return office


@router.get("")
async def office_statement(office_id: Optional[str] = None,
                           currency: str = Query(default="SAR"),
                           date_from: Optional[str] = None,
                           date_to: Optional[str] = None,
                           txn_type: Optional[str] = None,
                           limit: int = Query(default=300, ge=1, le=1000),
                           user: dict = Depends(get_current_user)):
    office = await _resolve_office(user, office_id)
    cur = "SAR" if currency == "SAR" else "USD"
    q = {"office_id": str(office["_id"]), "currency": cur}
    if txn_type:
        q["type"] = txn_type
    if date_from or date_to:
        rng = {}
        if date_from:
            rng["$gte"] = date_from
        if date_to:
            rng["$lte"] = f"{date_to}T23:59:59"
        q["created_at"] = rng
    # Opening business balance = everything BEFORE the window (never a journal figure).
    opening = 0.0
    if date_from:
        async for row in db.transactions.aggregate([
                {"$match": {"office_id": str(office["_id"]), "currency": cur,
                            "created_at": {"$lt": date_from}}},
                {"$group": {"_id": None, "total": {"$sum": "$amount"}}}]):
            opening = round(row["total"], 2)
    docs = await db.transactions.find(q).sort("created_at", 1).to_list(limit)
    running, rows, total_in, total_out = opening, [], 0.0, 0.0
    for d in docs:
        amount = round(float(d.get("amount") or 0), 2)
        running = round(running + amount, 2)
        label, direction = MOVEMENT_LABELS.get(d.get("type"),
                                               (d.get("type") or "حركة", "in"))
        if amount >= 0:
            total_in += amount
        else:
            total_out += -amount
        rows.append({
            "id": str(d["_id"]), "date": d.get("created_at"), "type": d.get("type"),
            "type_label": label, "direction": "in" if amount >= 0 else "out",
            "expected_direction": direction, "amount": amount,
            "inflow": amount if amount >= 0 else 0.0,
            "outflow": -amount if amount < 0 else 0.0,
            "running_balance": running, "currency": d.get("currency"),
            "description": d.get("description"), "reference": d.get("ref"),
            "actor": (d.get("meta") or {}).get("actor")
                     or (d.get("meta") or {}).get("by"),
            "status": (d.get("meta") or {}).get("status") or "executed",
        })
    wallet = office.get("wallet") or {}
    return {
        "scope": "business_office_statement",
        "note": "كشف حساب تجاري للمكتب — ليس أستاذاً محاسبياً ولا دليل حسابات",
        "office": {"id": str(office["_id"]),
                   "name": office.get("office_name") or office.get("owner_name"),
                   "email": office.get("email")},
        "currency": cur, "opening_balance": opening,
        "closing_balance": running,
        "totals": {"inflow": round(total_in, 2), "outflow": round(total_out, 2),
                   "net": round(total_in - total_out, 2)},
        "wallet": {"available": wallet_available(wallet, cur),
                   "pending": round(float((wallet.get(cur) or {}).get("pending") or 0), 2),
                   "total": round(float((wallet.get(cur) or {}).get("total") or 0), 2)},
        "movement_types": {k: v[0] for k, v in MOVEMENT_LABELS.items()},
        "count": len(rows), "items": rows,
    }


@router.get("/offices")
async def statement_offices(q: Optional[str] = None,
                            user: dict = Depends(get_current_user)):
    """Office picker for privileged users only — an office user gets its own office only."""
    if user.get("role") != "super_admin" and not await has_perm(user,
                                                                "office.statement.view"):
        own = await db.users.find_one({"_id": oid(str(user.get("parent_office_id")
                                                      or user["_id"]))},
                                      {"office_name": 1, "email": 1})
        return {"items": [{"id": str(own["_id"]), "name": own.get("office_name"),
                           "email": own.get("email")}], "restricted": True}
    f = {"role": "office", "is_staff_account": {"$ne": True}}
    if q:
        f["$or"] = [{"office_name": {"$regex": q, "$options": "i"}},
                    {"email": {"$regex": q, "$options": "i"}}]
    docs = await db.users.find(f, {"office_name": 1, "email": 1}).sort(
        "office_name", 1).to_list(500)
    return {"items": [{"id": str(d["_id"]), "name": d.get("office_name"),
                       "email": d.get("email")} for d in docs], "restricted": False}
