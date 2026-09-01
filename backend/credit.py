"""Credit Control (Batch 2) — per-office credit limit and exposure.

A credit limit is a CONTROL ceiling, not a separate money account: it only decides how far
an office's wallet may go negative. Default = 0 (current behaviour: no negative allowed).
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from db import db, serialize, oid, now_iso, wallet_available, CurrencyField
from security import require_admin

router = APIRouter(prefix="/api/admin", tags=["admin-credit"])

CCY = ("SAR", "USD")


async def get_limit(office_id: str, currency: str) -> dict:
    doc = await db.credit_limits.find_one({"office_id": str(office_id), "currency": currency})
    return doc or {"office_id": str(office_id), "currency": currency, "limit": 0.0,
                   "status": "active"}


async def credit_room(user: dict, currency: str) -> dict:
    """Available spending power = wallet available + remaining credit head-room."""
    lim = await get_limit(str(user["_id"]), currency)
    avail = wallet_available(user.get("wallet") or {}, currency)
    limit = float(lim.get("limit") or 0)
    used = max(0.0, -avail)
    headroom = max(0.0, round(limit - used, 2))
    return {
        "limit": round(limit, 2), "available_balance": round(avail, 2), "used": round(used, 2),
        "credit_headroom": headroom,
        "spending_power": round(max(0.0, avail) + headroom, 2),
        "utilization": round((used / limit) * 100, 1) if limit > 0 else 0.0,
        "frozen": lim.get("status") == "frozen",
    }


async def credit_frozen(user: dict, currency: str) -> bool:
    lim = await get_limit(str(user["_id"]), currency)
    return lim.get("status") == "frozen"


async def credit_allows(user: dict, currency: str, required: float) -> tuple:
    """(allowed, message, room) — used by the booking flow when the wallet alone is short."""
    room = await credit_room(user, currency)
    if room["frozen"]:
        return False, "حساب المكتب مجمّد ائتمانياً — لا يمكن إتمام الحجز", room
    if room["limit"] <= 0:
        return False, None, room
    if required <= room["spending_power"] + 0.01:
        return True, None, room
    return False, (f"تجاوز الحد المتاح. المطلوب {required} {currency} والمتاح "
                   f"{room['spending_power']} {currency} (سقف ائتماني {room['limit']})"), room


# ---------------- admin endpoints ----------------
@router.get("/credit")
async def list_credit(q: Optional[str] = None, currency: Optional[str] = None,
                      only_exposed: bool = False, page: int = 1, limit: int = 50,
                      admin: dict = Depends(require_admin)):
    f = {"role": "office"}
    if q:
        f["$or"] = [{"office_name": {"$regex": q, "$options": "i"}},
                    {"email": {"$regex": q, "$options": "i"}}]
    users = await db.users.find(f, {"office_name": 1, "email": 1, "role": 1, "status": 1,
                                    "wallet": 1}).sort("office_name", 1).to_list(5000)
    limits = {}
    async for l in db.credit_limits.find({}):
        limits[(l["office_id"], l["currency"])] = l
    ccys = [currency] if currency in CCY else list(CCY)
    out = []
    totals = {c: {"limit": 0.0, "used": 0.0, "headroom": 0.0} for c in CCY}
    for u in users:
        row = {"office_id": str(u["_id"]), "name": u.get("office_name") or u.get("email"),
               "email": u.get("email"), "role": u.get("role"), "status": u.get("status"),
               "currencies": {}}
        exposed = False
        for c in ccys:
            l = limits.get((str(u["_id"]), c)) or {}
            lim_val = float(l.get("limit") or 0)
            avail = wallet_available(u.get("wallet") or {}, c)
            used = max(0.0, -avail)
            headroom = max(0.0, round(lim_val - used, 2))
            util = round((used / lim_val) * 100, 1) if lim_val > 0 else (100.0 if used else 0.0)
            level = "ok"
            if util >= 100:
                level = "critical"
            elif util >= 90:
                level = "high"
            elif util >= 70:
                level = "warning"
            row["currencies"][c] = {
                "limit": round(lim_val, 2), "balance": round(avail, 2), "used": round(used, 2),
                "headroom": headroom, "utilization": util, "alert": level,
                "frozen": (l.get("status") == "frozen"),
            }
            totals[c]["limit"] += lim_val
            totals[c]["used"] += used
            totals[c]["headroom"] += headroom
            if used > 0 or lim_val > 0:
                exposed = True
        if only_exposed and not q and not exposed:
            continue
        out.append(row)
    for c in CCY:
        totals[c] = {k: round(v, 2) for k, v in totals[c].items()}
    total = len(out)
    limit = max(1, min(int(limit), 200))
    start = max(0, (int(page) - 1) * limit)
    return {"items": out[start:start + limit], "totals": totals,
            "total": total, "page": int(page), "limit": limit}


class LimitIn(BaseModel):
    currency: CurrencyField = "SAR"
    limit: float = Field(ge=0)
    reason: str = Field(min_length=3)


@router.post("/credit/{office_id}")
async def set_limit(office_id: str, payload: LimitIn, admin: dict = Depends(require_admin)):
    u = await db.users.find_one({"_id": oid(office_id)}, {"office_name": 1, "wallet": 1})
    if not u:
        raise HTTPException(404, "المكتب غير موجود")
    old = await get_limit(office_id, payload.currency)
    used = max(0.0, -wallet_available(u.get("wallet") or {}, payload.currency))
    if payload.limit < used - 0.01:
        raise HTTPException(400, f"لا يمكن تخفيض السقف دون المديونية الحالية ({round(used, 2)})")
    await db.credit_limits.update_one(
        {"office_id": str(office_id), "currency": payload.currency},
        {"$set": {"limit": round(payload.limit, 2), "status": old.get("status", "active"),
                  "updated_by": admin.get("email"), "updated_at": now_iso()},
         "$setOnInsert": {"created_at": now_iso()}}, upsert=True)
    await db.credit_events.insert_one({
        "office_id": str(office_id), "office_name": u.get("office_name"),
        "currency": payload.currency, "action": "limit_changed",
        "old_limit": round(float(old.get("limit") or 0), 2), "new_limit": round(payload.limit, 2),
        "reason": payload.reason.strip(), "by": admin.get("email"), "at": now_iso()})
    return serialize(await db.credit_limits.find_one(
        {"office_id": str(office_id), "currency": payload.currency}))


class FreezeIn(BaseModel):
    currency: CurrencyField = "SAR"
    frozen: bool = True
    reason: str = Field(min_length=3)


@router.post("/credit/{office_id}/freeze")
async def freeze(office_id: str, payload: FreezeIn, admin: dict = Depends(require_admin)):
    u = await db.users.find_one({"_id": oid(office_id)}, {"office_name": 1})
    if not u:
        raise HTTPException(404, "المكتب غير موجود")
    await db.credit_limits.update_one(
        {"office_id": str(office_id), "currency": payload.currency},
        {"$set": {"status": "frozen" if payload.frozen else "active",
                  "updated_by": admin.get("email"), "updated_at": now_iso()},
         "$setOnInsert": {"limit": 0.0, "created_at": now_iso()}}, upsert=True)
    await db.credit_events.insert_one({
        "office_id": str(office_id), "office_name": u.get("office_name"),
        "currency": payload.currency,
        "action": "frozen" if payload.frozen else "unfrozen",
        "reason": payload.reason.strip(), "by": admin.get("email"), "at": now_iso()})
    return {"ok": True, "frozen": payload.frozen}


@router.get("/credit/{office_id}/events")
async def credit_events(office_id: str, admin: dict = Depends(require_admin)):
    docs = await db.credit_events.find({"office_id": str(office_id)}).sort("at", -1).to_list(300)
    return serialize(docs)


@router.get("/credit-events")
async def all_credit_events(admin: dict = Depends(require_admin)):
    docs = await db.credit_events.find({}).sort("at", -1).to_list(500)
    return serialize(docs)
