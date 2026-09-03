"""Advertisements & Promotions (agreed addition).

Admin-managed campaigns with a Maker–Checker publishing gate, scheduling, placements,
view/click counters and a read-only performance report. Public endpoints only ever return
approved + active + in-window items. Fully additive: no existing collection is modified.
"""
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from db import db, serialize, oid, now_iso
from security import require_admin, get_current_user

router = APIRouter(prefix="/api", tags=["ads"])

AD_TYPES = {
    "paid": "إعلان مدفوع", "free": "إعلان مجاني", "company": "إعلان شركة",
    "office": "إعلان مكتب", "partner": "إعلان شريك", "individual": "معلن فرد",
}
STATUSES = {
    "draft": "مسودة", "pending_approval": "بانتظار الاعتماد", "active": "نشط",
    "paused": "موقوف مؤقتاً", "expired": "منتهي", "rejected": "مرفوض",
    "archived": "مؤرشف",
}
PLACEMENTS = {
    "homepage": "الصفحة الرئيسية", "programs": "صفحة البرامج",
    "program_details": "تفاصيل البرنامج", "dashboard": "لوحة المستخدم",
}
AUDIENCES = {"all": "الجميع", "offices": "المكاتب", "individuals": "الأفراد",
             "marketers": "المسوّقون"}
KINDS = {"ad": "إعلان", "promotion": "عرض ترويجي"}


class AdIn(BaseModel):
    kind: str = "ad"                      # ad | promotion
    title: str = Field(min_length=3)
    description_ar: str = ""
    advertiser_name: str = Field(min_length=2)
    advertiser_type: str = "office"
    paid: bool = False
    contract_value: float = 0.0
    currency: str = "SAR"
    start_date: str
    end_date: str
    image_url: str = ""
    target_url: str = ""
    audience: str = "all"
    placements: List[str] = ["homepage"]
    priority: int = 10
    cta_label: str = ""
    linked_package_id: Optional[str] = None
    linked_office_id: Optional[str] = None
    reason: str = Field(min_length=3)


def _validate(p: AdIn):
    if p.kind not in KINDS:
        raise HTTPException(400, "نوع العنصر غير مدعوم")
    if p.advertiser_type not in AD_TYPES:
        raise HTTPException(400, "نوع المعلن غير مدعوم")
    if p.audience not in AUDIENCES:
        raise HTTPException(400, "الجمهور المستهدف غير مدعوم")
    bad = [x for x in p.placements if x not in PLACEMENTS]
    if bad:
        raise HTTPException(400, f"مكان عرض غير مدعوم: {', '.join(bad)}")
    if p.end_date < p.start_date:
        raise HTTPException(400, "تاريخ النهاية قبل تاريخ البداية")
    if p.paid and p.contract_value <= 0:
        raise HTTPException(400, "الإعلان المدفوع يحتاج قيمة عقد أكبر من صفر")


async def _audit(entity_id, action, actor, reason, before=None, after=None):
    await db.audit_log.insert_one({
        "entity": "advertisement", "entity_id": str(entity_id), "action": action,
        "actor": actor.get("email"), "actor_id": str(actor["_id"]),
        "reason": reason, "before": before, "after": after, "at": now_iso()})


def _decorate(d: dict) -> dict:
    d["status_label"] = STATUSES.get(d.get("status"), d.get("status"))
    d["advertiser_type_label"] = AD_TYPES.get(d.get("advertiser_type"), d.get("advertiser_type"))
    d["kind_label"] = KINDS.get(d.get("kind"), d.get("kind"))
    d["audience_label"] = AUDIENCES.get(d.get("audience"), d.get("audience"))
    d["placement_labels"] = [PLACEMENTS.get(p, p) for p in (d.get("placements") or [])]
    views = int(d.get("views") or 0)
    clicks = int(d.get("clicks") or 0)
    d["ctr"] = round((clicks / views) * 100, 2) if views else 0.0
    return d


# ---------------- admin ----------------
@router.get("/admin/ads/catalog")
async def catalog(admin: dict = Depends(require_admin)):
    return {"advertiser_types": AD_TYPES, "statuses": STATUSES, "placements": PLACEMENTS,
            "audiences": AUDIENCES, "kinds": KINDS,
            "maker_checker": "النشر يحتاج اعتماد مستخدم آخر غير من أنشأ الإعلان"}


@router.get("/admin/ads")
async def list_ads(kind: Optional[str] = None, status: Optional[str] = None,
                   admin: dict = Depends(require_admin)):
    f = {}
    if kind:
        f["kind"] = kind
    if status:
        f["status"] = status
    docs = serialize(await db.advertisements.find(f).sort("created_at", -1).to_list(500))
    items = [_decorate(d) for d in docs]
    stats = {
        "total": len(items),
        "active": sum(1 for i in items if i["status"] == "active"),
        "pending": sum(1 for i in items if i["status"] == "pending_approval"),
        "views": sum(int(i.get("views") or 0) for i in items),
        "clicks": sum(int(i.get("clicks") or 0) for i in items),
        "paid_value": round(sum(float(i.get("contract_value") or 0) for i in items
                                if i.get("paid")), 2),
    }
    return {"items": items, "stats": stats}


@router.post("/admin/ads")
async def create_ad(payload: AdIn, admin: dict = Depends(require_admin)):
    _validate(payload)
    doc = {**payload.model_dump(exclude={"reason"}),
           "status": "draft", "views": 0, "clicks": 0,
           "created_by": admin.get("email"), "created_by_id": str(admin["_id"]),
           "approved_by": None, "approved_at": None, "rejection_reason": None,
           "created_at": now_iso(), "updated_at": now_iso()}
    res = await db.advertisements.insert_one(doc)
    await _audit(res.inserted_id, "ad_created", admin, payload.reason.strip(),
                 after={"title": payload.title, "status": "draft"})
    return _decorate(serialize({**doc, "_id": res.inserted_id}))


@router.patch("/admin/ads/{ad_id}")
async def update_ad(ad_id: str, payload: AdIn, admin: dict = Depends(require_admin)):
    _validate(payload)
    cur = await db.advertisements.find_one({"_id": oid(ad_id)})
    if not cur:
        raise HTTPException(404, "الإعلان غير موجود")
    values = payload.model_dump(exclude={"reason"})
    # Any content edit of a published item sends it back through approval.
    new_status = "pending_approval" if cur.get("status") == "active" else cur.get("status")
    await db.advertisements.update_one({"_id": cur["_id"]}, {"$set": {
        **values, "status": new_status, "updated_at": now_iso(),
        "approved_by": None if new_status == "pending_approval" else cur.get("approved_by")}})
    await _audit(ad_id, "ad_updated", admin, payload.reason.strip(),
                 before={"title": cur.get("title"), "status": cur.get("status")},
                 after={"title": payload.title, "status": new_status})
    return _decorate(serialize(await db.advertisements.find_one({"_id": cur["_id"]})))


class StatusIn(BaseModel):
    status: str
    reason: str = Field(min_length=3)


@router.post("/admin/ads/{ad_id}/status")
async def set_status(ad_id: str, payload: StatusIn, admin: dict = Depends(require_admin)):
    """Maker–Checker: only a DIFFERENT admin than the creator may activate an ad."""
    if payload.status not in STATUSES:
        raise HTTPException(400, "حالة غير مدعومة")
    ad = await db.advertisements.find_one({"_id": oid(ad_id)})
    if not ad:
        raise HTTPException(404, "الإعلان غير موجود")
    upd = {"status": payload.status, "updated_at": now_iso()}
    if payload.status == "active":
        if ad.get("status") not in ("pending_approval", "paused"):
            raise HTTPException(400, "يجب إرسال الإعلان للاعتماد قبل تنشيطه")
        if ad.get("created_by_id") == str(admin["_id"]):
            raise HTTPException(403, "مبدأ الفصل بين المنشئ والمعتمد: يعتمد الإعلان مسؤول آخر")
        upd["approved_by"] = admin.get("email")
        upd["approved_at"] = now_iso()
    if payload.status == "rejected":
        upd["rejection_reason"] = payload.reason.strip()
    await db.advertisements.update_one({"_id": ad["_id"]}, {"$set": upd})
    await _audit(ad_id, f"ad_{payload.status}", admin, payload.reason.strip(),
                 before={"status": ad.get("status")}, after={"status": payload.status})
    return _decorate(serialize(await db.advertisements.find_one({"_id": ad["_id"]})))


@router.get("/admin/ads/{ad_id}")
async def ad_detail(ad_id: str, admin: dict = Depends(require_admin)):
    ad = await db.advertisements.find_one({"_id": oid(ad_id)})
    if not ad:
        raise HTTPException(404, "الإعلان غير موجود")
    audit = serialize(await db.audit_log.find({"entity": "advertisement",
                                               "entity_id": ad_id}).sort("at", -1).to_list(50))
    return {"ad": _decorate(serialize(ad)), "audit": audit}


@router.get("/admin/ads-performance")
async def performance(admin: dict = Depends(require_admin)):
    rows = []
    async for a in db.advertisements.find({}):
        v, c = int(a.get("views") or 0), int(a.get("clicks") or 0)
        rows.append({"id": str(a["_id"]), "title": a.get("title"),
                     "advertiser": a.get("advertiser_name"),
                     "kind_label": KINDS.get(a.get("kind"), a.get("kind")),
                     "status_label": STATUSES.get(a.get("status"), a.get("status")),
                     "paid": bool(a.get("paid")),
                     "contract_value": round(float(a.get("contract_value") or 0), 2),
                     "currency": a.get("currency"), "views": v, "clicks": c,
                     "ctr": round((c / v) * 100, 2) if v else 0.0,
                     "start_date": a.get("start_date"), "end_date": a.get("end_date")})
    rows.sort(key=lambda r: -r["views"])
    return {"items": rows, "generated_at": now_iso()}


# ---------------- public (read-only, only approved & live) ----------------
def _live_filter(placement: str) -> dict:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return {"status": "active", "placements": placement,
            "start_date": {"$lte": today}, "end_date": {"$gte": today}}


@router.get("/ads/public")
async def public_ads(placement: str = Query("homepage"), limit: int = 6):
    if placement not in PLACEMENTS:
        raise HTTPException(400, "مكان عرض غير مدعوم")
    docs = await db.advertisements.find(_live_filter(placement)) \
        .sort([("priority", 1), ("created_at", -1)]).to_list(min(limit, 20))
    out = []
    for d in docs:
        out.append({"id": str(d["_id"]), "kind": d.get("kind"), "title": d.get("title"),
                    "description_ar": d.get("description_ar"),
                    "image_url": d.get("image_url"), "target_url": d.get("target_url"),
                    "cta_label": d.get("cta_label") or "التفاصيل",
                    "advertiser_name": d.get("advertiser_name"),
                    "paid": bool(d.get("paid")),
                    "linked_package_id": d.get("linked_package_id")})
    return {"items": out, "placement": placement,
            "placement_label": PLACEMENTS[placement]}


@router.post("/ads/{ad_id}/view")
async def count_view(ad_id: str):
    await db.advertisements.update_one({"_id": oid(ad_id), "status": "active"},
                                      {"$inc": {"views": 1}})
    return {"ok": True}


@router.post("/ads/{ad_id}/click")
async def count_click(ad_id: str):
    await db.advertisements.update_one({"_id": oid(ad_id), "status": "active"},
                                       {"$inc": {"clicks": 1}})
    return {"ok": True}


@router.get("/ads/mine")
async def my_promotions(user: dict = Depends(get_current_user)):
    """Promotions attached to the signed-in office (read-only)."""
    docs = await db.advertisements.find({"linked_office_id": str(user["_id"]),
                                         "kind": "promotion"}).to_list(100)
    return [_decorate(d) for d in serialize(docs)]
