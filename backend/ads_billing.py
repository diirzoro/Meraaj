"""Advertising packages + wallet hold/capture/refund for Ads & Promotions.

Money flow (server-authoritative, never from the frontend):
  Draft → choose package → Submit  ⇒ HOLD  (available −price, pending +price)
  Admin approve                    ⇒ CAPTURE (pending −price, total −price)
  Admin reject / advertiser cancel ⇒ RELEASE (pending −price, available +price)
Every step writes a transaction carrying the advertisement id, package id and reason.
Nothing else in the financial engine is touched.
"""
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from db import (db, serialize, oid, now_iso, adjust_wallet, log_txn, wallet_available)
from security import require_admin, get_current_user

router = APIRouter(prefix="/api", tags=["ads-billing"])

HOLD = "ad_hold"
CAPTURE = "ad_charge"
RELEASE = "ad_hold_release"


class PackageIn(BaseModel):
    name: str = Field(min_length=2)
    kind: str = "ad"                     # ad | promotion | both
    price: float = 0.0
    currency: str = "SAR"
    duration_days: int = Field(ge=1)
    max_views: Optional[int] = None
    max_clicks: Optional[int] = None
    max_placements: int = 1
    allowed_placements: List[str] = []   # empty = any selectable placement
    allowed_audiences: List[str] = ["all"]
    priority: int = 10
    paid: bool = True
    for_account_type: str = "all"        # all | offices | individuals
    requires_verified_org: bool = False
    active: bool = True
    reason: str = Field(min_length=3)


def snapshot(p: dict) -> dict:
    """Frozen commercial terms at purchase time — later admin edits never change an old ad."""
    return {k: p.get(k) for k in ("name", "kind", "price", "currency", "duration_days",
                                  "max_views", "max_clicks", "max_placements",
                                  "allowed_placements", "allowed_audiences", "priority",
                                  "paid")} | {"package_id": str(p["_id"]),
                                              "captured_at": None,
                                              "snapshot_at": now_iso()}


# ---------------- admin: package management ----------------
@router.get("/admin/ad-packages")
async def list_packages(admin: dict = Depends(require_admin)):
    from ads import _admin_ads_perm
    await _admin_ads_perm(admin, "ads.view")
    return serialize(await db.ad_packages.find({}).sort("price", 1).to_list(200))


@router.post("/admin/ad-packages")
async def create_package(payload: PackageIn, admin: dict = Depends(require_admin)):
    from ads import _admin_ads_perm
    await _admin_ads_perm(admin, "ads.manage")
    if payload.paid and payload.price <= 0:
        raise HTTPException(400, "الباقة المدفوعة تحتاج سعراً أكبر من صفر")
    doc = {**payload.model_dump(exclude={"reason"}),
           "created_by": admin.get("email"), "created_at": now_iso()}
    res = await db.ad_packages.insert_one(doc)
    await db.audit_log.insert_one({"entity": "ad_package", "entity_id": str(res.inserted_id),
                                   "action": "ad_package_created", "actor": admin.get("email"),
                                   "reason": payload.reason.strip(),
                                   "after": {"name": payload.name, "price": payload.price},
                                   "at": now_iso()})
    return serialize({**doc, "_id": res.inserted_id})


@router.patch("/admin/ad-packages/{pid}")
async def update_package(pid: str, payload: PackageIn, admin: dict = Depends(require_admin)):
    from ads import _admin_ads_perm
    await _admin_ads_perm(admin, "ads.manage")
    cur = await db.ad_packages.find_one({"_id": oid(pid)})
    if not cur:
        raise HTTPException(404, "الباقة غير موجودة")
    await db.ad_packages.update_one({"_id": cur["_id"]},
                                    {"$set": {**payload.model_dump(exclude={"reason"}),
                                              "updated_at": now_iso()}})
    await db.audit_log.insert_one({"entity": "ad_package", "entity_id": pid,
                                   "action": "ad_package_updated", "actor": admin.get("email"),
                                   "reason": payload.reason.strip(),
                                   "before": {"price": cur.get("price")},
                                   "after": {"price": payload.price}, "at": now_iso()})
    return {"ok": True, "note": "التعديل لا يؤثر على الإعلانات القائمة (لكل إعلان نسخة شروطه)"}


# ---------------- advertiser-facing catalogue ----------------
@router.get("/ad-packages")
async def my_packages(kind: str = "ad", user: dict = Depends(get_current_user)):
    from rbac import has_perm
    if not await has_perm(user, "ads.manage"):
        raise HTTPException(403, "لا تملك صلاحية: إنشاء وإدارة الإعلانات")
    acc = "offices" if user.get("role") in ("office", "staff") else "individuals"
    docs = await db.ad_packages.find({
        "active": True,
        "kind": {"$in": [kind, "both"]},
        "for_account_type": {"$in": ["all", acc]}}).sort("price", 1).to_list(100)
    ccy = "SAR"
    return {"items": serialize(docs),
            "wallet": {c: wallet_available(user.get("wallet"), c) for c in ("SAR", "USD")},
            "default_currency": ccy}


# ---------------- hold / capture / release ----------------
async def hold_for_ad(ad: dict, pkg: dict, actor: dict) -> dict:
    """Reserves the package price from the advertiser's available balance."""
    price = round(float(pkg.get("price") or 0), 2)
    ccy = "SAR" if (pkg.get("currency") or "SAR") == "SAR" else "USD"
    payer_id = str(ad.get("advertiser_org_id") or ad.get("advertiser_owner_id")
                   or ad.get("linked_office_id") or actor["_id"])
    if not pkg.get("paid") or price <= 0:
        return {"held": 0.0, "currency": ccy, "payer_id": payer_id, "free": True}
    payer = await db.users.find_one({"_id": oid(payer_id)})
    if not payer:
        raise HTTPException(400, "حساب الدفع غير معروف — حدّد هوية المعلن أولاً")
    avail = wallet_available(payer.get("wallet"), ccy)
    if avail + 1e-9 < price:
        raise HTTPException(400, f"الرصيد غير كافٍ: المطلوب {price} {ccy} والمتاح "
                                 f"{round(avail, 2)} {ccy} — اشحن المحفظة ثم أعد الإرسال")
    await adjust_wallet(payer_id, ccy, available=-price, pending=price)
    await log_txn(payer_id, HOLD, -price,
                  f"حجز قيمة باقة إعلانية: {pkg.get('name')}", ref=str(ad["_id"]),
                  currency=ccy, meta={"advertisement_id": str(ad["_id"]),
                                      "package_id": str(pkg["_id"]),
                                      "reason": "حجز عند إرسال الإعلان للاعتماد",
                                      "status": "held"})
    return {"held": price, "currency": ccy, "payer_id": payer_id, "free": False}


async def capture_for_ad(ad: dict, reason: str) -> Optional[dict]:
    b = ad.get("billing") or {}
    if not b.get("held") or b.get("state") != "held":
        return None
    price, ccy, payer = b["held"], b["currency"], b["payer_id"]
    await adjust_wallet(payer, ccy, pending=-price, total=-price)
    await log_txn(payer, CAPTURE, -price,
                  f"تحصيل قيمة الباقة الإعلانية بعد الاعتماد: {b.get('package_name')}",
                  ref=str(ad["_id"]), currency=ccy,
                  meta={"advertisement_id": str(ad["_id"]), "package_id": b.get("package_id"),
                        "reason": reason, "status": "captured"})
    return {"state": "captured", "captured_at": now_iso()}


async def release_for_ad(ad: dict, reason: str) -> Optional[dict]:
    b = ad.get("billing") or {}
    if not b.get("held") or b.get("state") != "held":
        return None
    price, ccy, payer = b["held"], b["currency"], b["payer_id"]
    await adjust_wallet(payer, ccy, pending=-price, available=price)
    await log_txn(payer, RELEASE, price,
                  f"فكّ حجز قيمة الباقة الإعلانية: {b.get('package_name')}",
                  ref=str(ad["_id"]), currency=ccy,
                  meta={"advertisement_id": str(ad["_id"]), "package_id": b.get("package_id"),
                        "reason": reason, "status": "released"})
    return {"state": "released", "released_at": now_iso()}
