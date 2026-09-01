"""Batch 3 — Programs & seats management for the Super Admin.
Additive: never edits seller-side endpoints; all changes are audited into `package_events`
and guarded (allocated seats can never fall below sold seats).
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from db import db, serialize, oid, now_iso
from security import require_admin

router = APIRouter(prefix="/api/admin", tags=["admin-programs"])

EDITABLE = {"title", "description", "departure_date", "return_date", "departure_city",
            "route", "transport", "net_cost_per_seat", "final_sale_price",
            "buyer_office_commission", "child_net_cost", "child_sale_price", "child_commission",
            "infant_net_cost", "infant_sale_price", "infant_commission", "currency",
            "total_seats", "images", "features", "fx_rate", "authorization_expires_at"}


async def _log(pkg_id: str, action: str, admin: dict, before=None, after=None, reason=""):
    await db.package_events.insert_one({
        "package_id": pkg_id, "action": action, "reason": reason,
        "before": before, "after": after,
        "actor": admin.get("email"), "actor_id": str(admin["_id"]), "at": now_iso()})


async def _sold(pkg_id: str) -> int:
    n = 0
    async for r in db.bookings.aggregate([
            {"$match": {"package_id": pkg_id, "status": {"$ne": "cancelled"}}},
            {"$group": {"_id": None, "s": {"$sum": "$seats"}}}]):
        n = int(r["s"] or 0)
    return n


@router.get("/programs")
async def list_programs(q: Optional[str] = None, source: Optional[str] = None,
                        status: Optional[str] = None, currency: Optional[str] = None,
                        seller_id: Optional[str] = None, expired: Optional[bool] = None,
                        page: int = 1, limit: int = Query(25, le=200),
                        admin: dict = Depends(require_admin)):
    f = {}
    if q:
        f["$or"] = [{"title": {"$regex": q, "$options": "i"}},
                    {"seller_office_name": {"$regex": q, "$options": "i"}},
                    {"rahal_ref": {"$regex": q, "$options": "i"}}]
    if source == "rahal":
        f["source"] = "rahal"
    elif source == "meraaj":
        f["source"] = {"$ne": "rahal"}
    if status:
        f["status"] = status
    if currency in ("SAR", "USD"):
        f["currency"] = currency
    if seller_id:
        f["seller_id"] = seller_id
    today = now_iso()[:10]
    if expired is True:
        f["departure_date"] = {"$lt": today}
    elif expired is False:
        f["departure_date"] = {"$gte": today}

    total = await db.packages.count_documents(f)
    docs = await db.packages.find(f).sort("created_at", -1) \
        .skip(max(0, (page - 1) * limit)).limit(limit).to_list(limit)
    items = []
    for p in docs:
        pid = str(p["_id"])
        sold = await _sold(pid)
        d = serialize(p)
        allocated = int(p.get("total_seats") or 0)
        d["sold_seats"] = sold
        d["allocated_seats"] = allocated
        d["remaining_seats"] = max(0, allocated - sold)
        d["availability"] = "available" if (allocated - sold) > 0 else "full"
        d["is_expired"] = str(p.get("departure_date") or "") < today
        d["price_mismatch"] = bool(p.get("_price_warnings"))
        items.append(d)
    return {"items": items, "total": total, "page": page, "limit": limit}


@router.get("/programs/{pkg_id}")
async def program_detail(pkg_id: str, admin: dict = Depends(require_admin)):
    p = await db.packages.find_one({"_id": oid(pkg_id)})
    if not p:
        raise HTTPException(404, "البرنامج غير موجود")
    sold = await _sold(pkg_id)
    events = serialize(await db.package_events.find({"package_id": pkg_id})
                       .sort("at", -1).to_list(200))
    bookings = serialize(await db.bookings.find(
        {"package_id": pkg_id},
        {"buyer_office_name": 1, "seats": 1, "status": 1, "amount_charged": 1,
         "currency": 1, "created_at": 1}).sort("created_at", -1).to_list(100))
    d = serialize(p)
    d.update({"sold_seats": sold, "allocated_seats": int(p.get("total_seats") or 0),
              "remaining_seats": max(0, int(p.get("total_seats") or 0) - sold),
              "price_warnings": p.get("_price_warnings")})
    return {"package": d, "events": events, "bookings": bookings}


class ProgramPatch(BaseModel):
    changes: dict
    reason: str = Field(min_length=3)


@router.patch("/programs/{pkg_id}")
async def patch_program(pkg_id: str, payload: ProgramPatch, admin: dict = Depends(require_admin)):
    p = await db.packages.find_one({"_id": oid(pkg_id)})
    if not p:
        raise HTTPException(404, "البرنامج غير موجود")
    bad = set(payload.changes) - EDITABLE
    if bad:
        raise HTTPException(400, f"حقول غير قابلة للتعديل: {', '.join(sorted(bad))}")
    if not payload.changes:
        raise HTTPException(400, "لا توجد تغييرات")
    if "total_seats" in payload.changes:
        sold = await _sold(pkg_id)
        if int(payload.changes["total_seats"]) < sold:
            raise HTTPException(400, f"لا يمكن تخفيض المقاعد المخصصة ({payload.changes['total_seats']}) "
                                     f"دون المقاعد المباعة ({sold})")
    if payload.changes.get("currency") not in (None, "SAR", "USD"):
        raise HTTPException(400, "عملة غير مدعومة")
    before = {k: p.get(k) for k in payload.changes}
    upd = dict(payload.changes)
    if "total_seats" in upd:
        sold = await _sold(pkg_id)
        upd["available_seats"] = max(0, int(upd["total_seats"]) - sold)
    upd["updated_at"] = now_iso()
    upd["last_admin_edit"] = {"by": admin.get("email"), "at": now_iso(),
                              "reason": payload.reason.strip()}
    await db.packages.update_one({"_id": p["_id"]}, {"$set": upd})
    await _log(pkg_id, "admin_edit", admin, before, payload.changes, payload.reason.strip())
    return await program_detail(pkg_id, admin)


class StateIn(BaseModel):
    state: str          # listed | unlisted | archived
    reason: str = Field(min_length=3)


@router.post("/programs/{pkg_id}/state")
async def set_state(pkg_id: str, payload: StateIn, admin: dict = Depends(require_admin)):
    if payload.state not in ("listed", "unlisted", "archived"):
        raise HTTPException(400, "حالة غير صالحة")
    p = await db.packages.find_one({"_id": oid(pkg_id)})
    if not p:
        raise HTTPException(404, "البرنامج غير موجود")
    upd = {"status": payload.state, "updated_at": now_iso()}
    if payload.state == "archived":
        upd["is_active"] = False
        upd["archived_at"] = now_iso()
    elif payload.state == "unlisted":
        upd["is_active"] = False
    else:
        upd["is_active"] = True
        upd["archived_at"] = None
    await db.packages.update_one({"_id": p["_id"]}, {"$set": upd})
    await _log(pkg_id, f"state_{payload.state}", admin, {"status": p.get("status")},
               {"status": payload.state}, payload.reason.strip())
    return {"ok": True, "status": payload.state}


class ExtendIn(BaseModel):
    departure_date: Optional[str] = None
    return_date: Optional[str] = None
    authorization_expires_at: Optional[str] = None
    reason: str = Field(min_length=3)


@router.post("/programs/{pkg_id}/extend")
async def extend(pkg_id: str, payload: ExtendIn, admin: dict = Depends(require_admin)):
    p = await db.packages.find_one({"_id": oid(pkg_id)})
    if not p:
        raise HTTPException(404, "البرنامج غير موجود")
    upd = {k: v for k, v in payload.model_dump().items()
           if k != "reason" and v}
    if not upd:
        raise HTTPException(400, "حدّد تاريخاً واحداً على الأقل")
    before = {k: p.get(k) for k in upd}
    upd["updated_at"] = now_iso()
    await db.packages.update_one({"_id": p["_id"]}, {"$set": upd})
    await _log(pkg_id, "extend_dates", admin, before, upd, payload.reason.strip())
    return {"ok": True, "applied": upd}


class ImageIn(BaseModel):
    images: list
    reason: str = "تحديث صور البرنامج"


@router.post("/programs/{pkg_id}/images")
async def set_images(pkg_id: str, payload: ImageIn, admin: dict = Depends(require_admin)):
    p = await db.packages.find_one({"_id": oid(pkg_id)}, {"images": 1})
    if not p:
        raise HTTPException(404, "البرنامج غير موجود")
    await db.packages.update_one({"_id": p["_id"]},
                                {"$set": {"images": payload.images, "updated_at": now_iso()}})
    await _log(pkg_id, "images_updated", admin, {"count": len(p.get("images") or [])},
               {"count": len(payload.images)}, payload.reason)
    return {"ok": True, "images": payload.images}


@router.get("/programs/{pkg_id}/events")
async def program_events(pkg_id: str, admin: dict = Depends(require_admin)):
    return serialize(await db.package_events.find({"package_id": pkg_id})
                     .sort("at", -1).to_list(300))
