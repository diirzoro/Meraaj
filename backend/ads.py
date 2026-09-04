"""Advertisements & Promotions (agreed addition).

Admin-managed campaigns with a Maker–Checker publishing gate, scheduling, placements,
view/click counters and a read-only performance report. Public endpoints only ever return
approved + active + in-window items. Fully additive: no existing collection is modified.
"""
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import Response
from pydantic import BaseModel, Field

from db import db, serialize, oid, now_iso
from security import require_admin, get_current_user, get_optional_user

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
    "homepage": {"label": "الصفحة الرئيسية", "audience_scope": "public"},
    "programs": {"label": "سوق البرامج", "audience_scope": "public"},
    "program_details": {"label": "تفاصيل البرنامج", "audience_scope": "public"},
    "dashboard": {"label": "لوحة المستخدم", "audience_scope": "authenticated"},
    "orders": {"label": "صفحة الطلبات", "audience_scope": "authenticated"},
    "order_details": {"label": "تفاصيل الطلب", "audience_scope": "authenticated"},
    "wallet": {"label": "المحفظة", "audience_scope": "authenticated"},
    "notifications": {"label": "الإشعارات", "audience_scope": "authenticated"},
    "sales": {"label": "صفحة المبيعات (البائع)", "audience_scope": "offices"},
    "bookings": {"label": "حجوزاتي", "audience_scope": "authenticated"},
    "create_package": {"label": "إنشاء برنامج", "audience_scope": "offices"},
    "login": {"label": "صفحة الدخول", "audience_scope": "public"},
}
# Ready-made groups so an admin picks a set instead of ticking pages one by one.
PLACEMENT_GROUPS = {
    "all_eligible": {"label": "كل الصفحات المؤهلة",
                     "pages": list(PLACEMENTS.keys())},
    "public_pages": {"label": "الصفحات العامة (زوار)",
                     "pages": [k for k, v in PLACEMENTS.items()
                               if v["audience_scope"] == "public"]},
    "office_pages": {"label": "صفحات المكاتب",
                     "pages": [k for k, v in PLACEMENTS.items()
                               if v["audience_scope"] in ("offices", "authenticated")]},
    "individual_pages": {"label": "صفحات الأفراد",
                         "pages": ["homepage", "programs", "program_details", "dashboard",
                                   "bookings", "wallet", "notifications"]},
}
AUDIENCES = {"all": "جميع المستخدمين", "offices": "المكاتب فقط",
             "individuals": "الأفراد فقط", "specific": "مستخدمون/جهات محددة"}
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
    audience_user_ids: List[str] = []          # used when audience == "specific"
    audience_org_ids: List[str] = []
    placements: List[str] = ["homepage"]
    placement_group: Optional[str] = None      # optional shortcut, expands to pages
    advertiser_owner_id: Optional[str] = None  # the advertiser's user account
    advertiser_org_id: Optional[str] = None    # the advertiser's organisation/office
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
    if p.placement_group and p.placement_group not in PLACEMENT_GROUPS:
        raise HTTPException(400, "مجموعة صفحات غير معروفة")
    if p.placement_group:
        p.placements = PLACEMENT_GROUPS[p.placement_group]["pages"]
    bad = [x for x in p.placements if x not in PLACEMENTS]
    if bad:
        raise HTTPException(400, f"مكان عرض غير مدعوم: {', '.join(bad)}")
    if not p.placements:
        raise HTTPException(400, "اختر مكان عرض واحداً على الأقل")
    if p.audience == "specific" and not (p.audience_user_ids or p.audience_org_ids):
        raise HTTPException(400, "حدّد مستخدمين أو جهات عند اختيار استهداف محدد")
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
    d["placement_labels"] = [PLACEMENTS.get(p, {}).get("label", p)
                             for p in (d.get("placements") or [])]
    views = int(d.get("views") or 0)
    clicks = int(d.get("clicks") or 0)
    d["ctr"] = round((clicks / views) * 100, 2) if views else 0.0
    return d


# ---------------- admin ----------------
@router.get("/admin/ads/catalog")
async def catalog(admin: dict = Depends(require_admin)):
    return {"advertiser_types": AD_TYPES, "statuses": STATUSES,
            "placements": {k: v["label"] for k, v in PLACEMENTS.items()},
            "placement_meta": PLACEMENTS, "placement_groups": PLACEMENT_GROUPS,
            "audiences": AUDIENCES, "kinds": KINDS,
            "owner_exclusion": ("صاحب الإعلان لا يرى إعلانه: يُستبعد حساب المعلن ومؤسسته "
                                "وكل مستخدمي تلك المؤسسة على مستوى الخادم"),
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


async def _owner_excluded(ad: dict, user: Optional[dict]) -> bool:
    """MANDATORY RULE: an advertiser never sees its own campaign.
    Excluded: the advertiser account itself, the advertiser organisation, any user whose
    org_id is that organisation, and the office linked to the campaign."""
    if not user:
        return False
    uid = str(user.get("_id"))
    uorg = str(user.get("org_id") or "")
    owner = str(ad.get("advertiser_owner_id") or "")
    org = str(ad.get("advertiser_org_id") or "")
    linked_office = str(ad.get("linked_office_id") or "")
    if owner and owner == uid:
        return True
    if linked_office and linked_office == uid:
        return True
    if org and (org == uorg or org == uid):
        return True
    if org and not uorg:
        me = await db.users.find_one({"_id": user["_id"]}, {"org_id": 1})
        if str((me or {}).get("org_id") or "") == org:
            return True
    return False


def _audience_matches(ad: dict, user: Optional[dict]) -> bool:
    aud = ad.get("audience") or "all"
    if aud == "all":
        return True
    if not user:
        return False                       # targeted campaigns need a signed-in visitor
    role = user.get("role")
    if aud == "offices":
        return role in ("office", "staff")
    if aud == "individuals":
        return role == "individual"
    if aud == "specific":
        return (uid_in(user, ad.get("audience_user_ids"))
                or str(user.get("org_id") or "") in
                [str(x) for x in (ad.get("audience_org_ids") or [])])
    return True


def uid_in(user: dict, ids) -> bool:
    return str(user.get("_id")) in [str(x) for x in (ids or [])]


@router.get("/ads/public")
async def public_ads(placement: str = Query("homepage"), limit: int = 6,
                     user: Optional[dict] = Depends(get_optional_user)):
    """Only approved + active + in-window campaigns, filtered on the BACKEND by audience
    and by the advertiser-owner exclusion rule."""
    if placement not in PLACEMENTS:
        raise HTTPException(400, "مكان عرض غير مدعوم")
    docs = await db.advertisements.find(_live_filter(placement)) \
        .sort([("priority", 1), ("created_at", -1)]).to_list(60)
    out = []
    for d in docs:
        if not _audience_matches(d, user):
            continue
        if await _owner_excluded(d, user):
            continue
        out.append({"id": str(d["_id"]), "kind": d.get("kind"), "title": d.get("title"),
                    "description_ar": d.get("description_ar"),
                    "image_url": d.get("image_url"), "target_url": d.get("target_url"),
                    "cta_label": d.get("cta_label") or "التفاصيل",
                    "advertiser_name": d.get("advertiser_name"),
                    "end_date": d.get("end_date"),
                    "kind_label": KINDS.get(d.get("kind"), "إعلان"),
                    "paid": bool(d.get("paid")),
                    "linked_package_id": d.get("linked_package_id")})
        if len(out) >= min(limit, 20):
            break
    return {"items": out, "placement": placement,
            "placement_label": PLACEMENTS[placement]["label"]}


@router.post("/ads/{ad_id}/view")
async def count_view(ad_id: str, source: str = "public"):
    """Only public/user-facing impressions are counted. Admin previews pass source=admin
    (or anything else) and are ignored so Views/CTR stay clean."""
    if source != "public":
        return {"ok": True, "counted": False, "reason": "عرض إداري لا يُحتسب"}
    await db.advertisements.update_one({"_id": oid(ad_id), "status": "active"},
                                      {"$inc": {"views": 1}})
    return {"ok": True, "counted": True}


@router.post("/ads/{ad_id}/click")
async def count_click(ad_id: str, source: str = "public"):
    if source != "public":
        return {"ok": True, "counted": False, "reason": "نقرة إدارية لا تُحتسب"}
    await db.advertisements.update_one({"_id": oid(ad_id), "status": "active"},
                                       {"$inc": {"clicks": 1}})
    return {"ok": True, "counted": True}


@router.post("/admin/ads/upload-image")
async def upload_ad_image(file: UploadFile = File(...), admin: dict = Depends(require_admin)):
    """Direct banner upload from the admin's device (stored in GridFS). URL stays optional."""
    if (file.content_type or "") not in ("image/png", "image/jpeg", "image/webp", "image/gif"):
        raise HTTPException(400, "نوع الصورة غير مدعوم — استخدم PNG أو JPEG أو WEBP أو GIF")
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(400, "حجم الصورة يتجاوز 5 ميجابايت")
    from motor.motor_asyncio import AsyncIOMotorGridFSBucket
    bucket = AsyncIOMotorGridFSBucket(db, bucket_name="ad_images")
    fid = await bucket.upload_from_stream(file.filename or "banner",
                                          data, metadata={"content_type": file.content_type,
                                                          "by": admin.get("email"),
                                                          "at": now_iso()})
    return {"image_url": f"/api/ads/image/{fid}", "size": len(data),
            "content_type": file.content_type}


@router.get("/ads/image/{file_id}")
async def ad_image(file_id: str):
    from motor.motor_asyncio import AsyncIOMotorGridFSBucket
    bucket = AsyncIOMotorGridFSBucket(db, bucket_name="ad_images")
    try:
        stream = await bucket.open_download_stream(oid(file_id))
    except Exception:
        raise HTTPException(404, "الصورة غير موجودة")
    data = await stream.read()
    ctype = (stream.metadata or {}).get("content_type", "image/png")
    return Response(content=data, media_type=ctype,
                    headers={"Cache-Control": "public, max-age=86400"})


@router.get("/ads/mine")
async def my_promotions(user: dict = Depends(get_current_user)):
    """Promotions attached to the signed-in office (read-only)."""
    docs = await db.advertisements.find({"linked_office_id": str(user["_id"]),
                                         "kind": "promotion"}).to_list(100)
    return [_decorate(d) for d in serialize(docs)]
