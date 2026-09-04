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
from pymongo import ReturnDocument
from contextlib import asynccontextmanager

from db import db, serialize, oid, now_iso
from security import require_admin, get_current_user, get_optional_user

router = APIRouter(prefix="/api", tags=["ads"])


def ads_perm(key: str):
    """Real permission gate (not just UI hiding): a revoked `ads.*` makes the API answer 403."""
    async def dep(user: dict = Depends(get_current_user)) -> dict:
        from rbac import has_perm, PERMISSIONS as P
        if not await has_perm(user, key):
            raise HTTPException(403, f"لا تملك صلاحية: {P.get(key, key)}")
        return user
    return dep


async def _admin_ads_perm(admin: dict, key: str):
    from rbac import has_perm, PERMISSIONS as P
    if not await has_perm(admin, key):
        raise HTTPException(403, f"لا تملك صلاحية: {P.get(key, key)}")


@asynccontextmanager
async def _ad_lock(ad: dict, actor: dict):
    """Serialises every money-moving operation on ONE ad. The lock is taken with a conditional
    update that also pins the status we validated, so a concurrent request either waits its turn
    and re-validates, or is rejected with 409 — never a second wallet movement."""
    got = await db.advertisements.find_one_and_update(
        {"_id": ad["_id"], "status": ad.get("status"), "op_lock": None},
        {"$set": {"op_lock": {"by": actor.get("email"), "at": now_iso()}}},
        return_document=ReturnDocument.AFTER)
    if not got:
        raise HTTPException(409, "هناك عملية جارية على هذا الإعلان أو تغيّرت حالته — "
                                 "أعد تحميل الصفحة ثم حاول مرة أخرى")
    try:
        yield got
    finally:
        await db.advertisements.update_one({"_id": ad["_id"]}, {"$set": {"op_lock": None}})


AD_TYPES = {
    "paid": "إعلان مدفوع", "free": "إعلان مجاني", "company": "إعلان شركة",
    "office": "إعلان مكتب", "partner": "إعلان شريك", "individual": "معلن فرد",
}
STATUSES = {
    "draft": "مسودة", "pending_approval": "بانتظار الاعتماد", "active": "نشط",
    "paused": "موقوف مؤقتاً", "expired": "منتهي", "rejected": "مرفوض",
    "archived": "مؤرشف", "completed": "مكتمل (بلغ حدّ الباقة)",
    "cancellation_requested": "طلب إلغاء قيد المراجعة", "cancelled": "ملغى",
}
PLACEMENTS = {
    "homepage": {"label": "الصفحة الرئيسية", "audience_scope": "public"},
    "programs": {"label": "سوق البرامج", "audience_scope": "public"},
    "program_details": {"label": "تفاصيل البرنامج", "audience_scope": "public"},
    "login": {"label": "صفحة الدخول", "audience_scope": "public"},
    "dashboard": {"label": "لوحة المستخدم", "audience_scope": "authenticated"},
    "bookings": {"label": "حجوزاتي (الطلبات)", "audience_scope": "authenticated"},
    "wallet": {"label": "المحفظة", "audience_scope": "authenticated"},
    "sales": {"label": "مبيعاتي (البائع)", "audience_scope": "offices"},
    "create_package": {"label": "إنشاء/تعديل برنامج", "audience_scope": "offices"},
}
# NOTE: a placement is listed here ONLY when a real user-facing <AdSlot/> renders it.
# Pages without a public slot yet (لوحة الطلبات الإدارية، تفاصيل الطلب، مركز الإشعارات)
# are intentionally NOT selectable so an admin can never pick a dead placement.
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
                                   "bookings", "wallet"]},
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
    package_id: Optional[str] = None
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


async def _notify_ad(ad: dict, kind: str, title: str, body: str, meta: Optional[dict] = None):
    """In-app notification tied to the campaign itself (never a generic message)."""
    from orgs import notify
    uid = str(ad.get("advertiser_owner_id") or ad.get("created_by_id") or "")
    if not uid:
        return
    await notify(uid, kind, title, body, link="/my-ads",
                 meta={"advertisement_id": str(ad["_id"]), "title": ad.get("title"),
                       **(meta or {})})


def _money_line(b: dict) -> str:
    if not b or not b.get("held"):
        return "الباقة مجانية — لا يوجد مبلغ مستحق."
    return f"{round(float(b['held']), 2)} {b.get('currency')}"


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
    await _admin_ads_perm(admin, "ads.view")
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
    await _admin_ads_perm(admin, "ads.view")
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
    await _admin_ads_perm(admin, "ads.manage")
    _validate(payload)
    _require_owner_identity(payload)
    doc = {**payload.model_dump(exclude={"reason"}),
           "status": "draft", "views": 0, "clicks": 0, "source": "admin",
           "billing": {}, "package_snapshot": None,
           "created_by": admin.get("email"), "created_by_id": str(admin["_id"]),
           "approved_by": None, "approved_at": None, "rejection_reason": None,
           "created_at": now_iso(), "updated_at": now_iso()}
    res = await db.advertisements.insert_one(doc)
    await _audit(res.inserted_id, "ad_created", admin, payload.reason.strip(),
                 after={"title": payload.title, "status": "draft"})
    return _decorate(serialize({**doc, "_id": res.inserted_id}))


@router.patch("/admin/ads/{ad_id}")
async def update_ad(ad_id: str, payload: AdIn, admin: dict = Depends(require_admin)):
    await _admin_ads_perm(admin, "ads.manage")
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


def _require_owner_identity(p: AdIn):
    """Owner identity must be explicit BEFORE approval so the exclusion rule can work."""
    if p.advertiser_type == "individual" and not p.advertiser_owner_id:
        raise HTTPException(400, "المعلن الفرد يتطلب تحديد حساب المعلن (advertiser_owner_id)")
    if p.advertiser_type in ("office", "company", "partner") and not p.advertiser_org_id:
        raise HTTPException(400, "المعلن المكتب/الشركة/الشريك يتطلب تحديد مؤسسة المعلن "
                                 "(advertiser_org_id)")


async def _ready_for_approval(ad: dict):
    t = ad.get("advertiser_type")
    if t == "individual" and not ad.get("advertiser_owner_id"):
        raise HTTPException(400, "لا يمكن الإرسال للاعتماد: حساب المعلن الفرد غير محدد")
    if t in ("office", "company", "partner") and not ad.get("advertiser_org_id"):
        raise HTTPException(400, "لا يمكن الإرسال للاعتماد: مؤسسة المعلن غير محددة")
    if ad.get("kind") == "promotion" and ad.get("linked_office_id") in ("", None) \
            and t in ("office", "partner") and not ad.get("advertiser_org_id"):
        raise HTTPException(400, "الحملة المرتبطة بمكتب تتطلب تحديد المكتب")


async def _check_verified_org(ad: dict, pkg: dict):
    """Commercial campaigns require a verified organisation with licence data."""
    needs = bool(pkg.get("requires_verified_org")) or \
        ad.get("advertiser_type") in ("office", "company", "partner")
    if not needs:
        return
    org_id = str(ad.get("advertiser_org_id") or "")
    acc = await db.users.find_one({"_id": oid(org_id)}) if org_id else None
    org = await db.orgs.find_one({"_id": oid(org_id)}) if (org_id and not acc) else None
    holder = acc or org
    if not holder:
        raise HTTPException(400, "مؤسسة المعلن غير موجودة في النظام")
    if (holder.get("status") or "active") != "active":
        raise HTTPException(403, "حساب المؤسسة غير مفعّل — لا يمكن شراء إعلان تجاري")
    if not (holder.get("commercial_license") or holder.get("license")):
        raise HTTPException(403, "الحساب غير موثّق: بيانات السجل التجاري للمؤسسة مطلوبة "
                                 "لإطلاق إعلان تجاري")


class StatusIn(BaseModel):
    status: str
    reason: str = Field(min_length=3)


async def _apply_status(ad: dict, new: str, actor: dict, reason: str) -> dict:
    """Shared status engine for admin and office flows (hold/capture/release + limits)."""
    from ads_billing import hold_for_ad, capture_for_ad, release_for_ad
    upd = {"status": new, "updated_at": now_iso()}
    billing = dict(ad.get("billing") or {})

    if new == "pending_approval":
        await _ready_for_approval(ad)
        if billing.get("state") != "held" and ad.get("package_id"):
            pkg = await db.ad_packages.find_one({"_id": oid(ad["package_id"])})
            if not pkg or not pkg.get("active"):
                raise HTTPException(400, "الباقة غير متاحة — اختر باقة سارية")
            await _check_verified_org(ad, pkg)
            res = await hold_for_ad(ad, pkg, actor)
            billing = {**res, "state": "held" if res["held"] else "free",
                       "package_id": str(pkg["_id"]), "package_name": pkg.get("name"),
                       "held_at": now_iso()}
            upd["package_snapshot"] = __import__("ads_billing").snapshot(pkg)
            upd["max_views"] = pkg.get("max_views")
            upd["max_clicks"] = pkg.get("max_clicks")
            upd["duration_days"] = pkg.get("duration_days")
        elif not ad.get("package_id"):
            raise HTTPException(400, "اختر باقة إعلانية قبل الإرسال للاعتماد")

    if new == "active":
        cap = await capture_for_ad({**ad, "billing": billing}, reason)
        if cap:
            billing.update(cap)
    if new in ("rejected", "archived", "draft"):
        rel = await release_for_ad({**ad, "billing": billing}, reason)
        if rel:
            billing.update(rel)
    upd["billing"] = billing
    if new == "rejected":
        upd["rejection_reason"] = reason
    return upd


@router.post("/admin/ads/{ad_id}/status")
async def set_status(ad_id: str, payload: StatusIn, admin: dict = Depends(require_admin)):
    """Maker–Checker: only a DIFFERENT admin than the creator may activate an ad."""
    if payload.status not in STATUSES:
        raise HTTPException(400, "حالة غير مدعومة")
    if payload.status in ("cancellation_requested", "cancelled"):
        raise HTTPException(400, "الإلغاء يُدار من مسار طلبات الإلغاء وليس من تغيير الحالة")
    ad = await db.advertisements.find_one({"_id": oid(ad_id)})
    if not ad:
        raise HTTPException(404, "الإعلان غير موجود")
    # Guards run BEFORE any money moves so a rejected transition can never charge a wallet.
    if payload.status in ("active", "rejected"):
        await _admin_ads_perm(admin, "ads.approve")
    if payload.status == "active":
        if ad.get("status") not in ("pending_approval", "paused"):
            raise HTTPException(400, "يجب إرسال الإعلان للاعتماد قبل تنشيطه")
        if ad.get("created_by_id") == str(admin["_id"]) and ad.get("source") != "office":
            raise HTTPException(403, "مبدأ الفصل بين المنشئ والمعتمد: يعتمد الإعلان مسؤول آخر")
    async with _ad_lock(ad, admin) as locked:
        ad = locked
        upd = await _apply_status(ad, payload.status, admin, payload.reason.strip())
        if payload.status == "active":
            upd["approved_by"] = admin.get("email")
            upd["approved_at"] = now_iso()
        if payload.status == "rejected":
            upd["rejection_reason"] = payload.reason.strip()
        await db.advertisements.update_one({"_id": ad["_id"]}, {"$set": upd})
        await _audit(ad_id, f"ad_{payload.status}", admin, payload.reason.strip(),
                     before={"status": ad.get("status")}, after={"status": payload.status})
    b = upd.get("billing") or {}
    if payload.status == "active":
        snap = ad.get("package_snapshot") or {}
        await _notify_ad(ad, "ad_approved", "تم اعتماد إعلانك ونشره",
                         (f"تم قبول «{ad.get('title')}» بنجاح.\n"
                          f"الباقة: {b.get('package_name') or snap.get('name') or '—'}\n"
                          f"المدة: {snap.get('duration_days') or ad.get('duration_days') or '—'} يوم "
                          f"({ad.get('start_date')} ← {ad.get('end_date')})\n"
                          f"قيمة الباقة: {_money_line(b)}\n"
                          + ("تم تحويل المبلغ المحجوز إلى خصم نهائي من رصيدك."
                             if b.get("state") == "captured" else
                             "لا يوجد مبلغ مستحق على هذه الباقة.")),
                         meta={"package": b.get("package_name"),
                               "amount": b.get("held"), "currency": b.get("currency"),
                               "start_date": ad.get("start_date"), "end_date": ad.get("end_date"),
                               "billing_state": b.get("state")})
    if payload.status == "rejected":
        await _notify_ad(ad, "ad_rejected", "تم رفض إعلانك",
                         (f"تم رفض «{ad.get('title')}» للأسباب التالية: {payload.reason.strip()}\n"
                          + ("تم فكّ حجز المبلغ وإعادته إلى رصيدك المتاح."
                             if b.get("state") == "released" else
                             "لا يوجد مبلغ محجوز على هذا الإعلان.")),
                         meta={"reason": payload.reason.strip(),
                               "amount": b.get("held"), "currency": b.get("currency")})
    return _decorate(serialize(await db.advertisements.find_one({"_id": ad["_id"]})))


@router.get("/admin/ads/{ad_id}")
async def ad_detail(ad_id: str, admin: dict = Depends(require_admin)):
    await _admin_ads_perm(admin, "ads.view")
    ad = await db.advertisements.find_one({"_id": oid(ad_id)})
    if not ad:
        raise HTTPException(404, "الإعلان غير موجود")
    audit = serialize(await db.audit_log.find({"entity": "advertisement",
                                               "entity_id": ad_id}).sort("at", -1).to_list(50))
    return {"ad": _decorate(serialize(ad)), "audit": audit}


@router.get("/admin/ads-performance")
async def performance(admin: dict = Depends(require_admin)):
    await _admin_ads_perm(admin, "ads.view")
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
    if user:
        from rbac import has_perm
        if not await has_perm(user, "ads.view"):
            return {"items": [], "placement": placement,
                    "placement_label": PLACEMENTS[placement]["label"],
                    "note": "قسم الإعلانات غير متاح لصلاحيات حسابك"}
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
    """Only public/user-facing impressions are counted (server-authoritative), and the
    campaign stops itself when the package view/click limit is reached."""
    if source != "public":
        return {"ok": True, "counted": False, "reason": "عرض إداري لا يُحتسب"}
    ad = await db.advertisements.find_one_and_update(
        {"_id": oid(ad_id), "status": "active"}, {"$inc": {"views": 1}},
        return_document=True)
    if ad:
        await _enforce_limits(ad)
    return {"ok": True, "counted": bool(ad)}


@router.post("/ads/{ad_id}/click")
async def count_click(ad_id: str, source: str = "public"):
    if source != "public":
        return {"ok": True, "counted": False, "reason": "نقرة إدارية لا تُحتسب"}
    ad = await db.advertisements.find_one_and_update(
        {"_id": oid(ad_id), "status": "active"}, {"$inc": {"clicks": 1}},
        return_document=True)
    if ad:
        await _enforce_limits(ad)
    return {"ok": True, "counted": bool(ad)}


async def _enforce_limits(ad: dict):
    """Auto-stop on the FIRST met condition: end date, max views or max clicks."""
    snap = ad.get("package_snapshot") or {}
    mv, mc = snap.get("max_views") or ad.get("max_views"), snap.get("max_clicks") or ad.get("max_clicks")
    reason = None
    if mv and int(ad.get("views") or 0) >= int(mv):
        reason = f"بلغ الحد الأقصى للمشاهدات ({mv})"
    elif mc and int(ad.get("clicks") or 0) >= int(mc):
        reason = f"بلغ الحد الأقصى للنقرات ({mc})"
    elif ad.get("end_date") and ad["end_date"] < datetime.now(timezone.utc).strftime("%Y-%m-%d"):
        reason = "انتهت مدة الإعلان"
    if reason:
        await db.advertisements.update_one({"_id": ad["_id"]}, {"$set": {
            "status": "completed", "completion_reason": reason, "updated_at": now_iso()}})
        await db.audit_log.insert_one({
            "entity": "advertisement", "entity_id": str(ad["_id"]),
            "action": "ad_completed", "actor": "system", "reason": reason, "at": now_iso()})


@router.post("/ads/upload-image")
async def upload_my_ad_image(file: UploadFile = File(...),
                             user: dict = Depends(ads_perm("ads.manage"))):
    """Advertiser-side banner upload (same GridFS bucket, same limits)."""
    return await upload_ad_image(file, user)


@router.post("/admin/ads/upload-image")
async def upload_ad_image(file: UploadFile = File(...), admin: dict = Depends(require_admin)):
    await _admin_ads_perm(admin, "ads.manage")
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
async def my_promotions(user: dict = Depends(ads_perm("ads.view"))):
    """Advertiser workspace: only MY campaigns (never another office's)."""
    me = str(user["_id"])
    org = str(user.get("org_id") or "")
    f = {"$or": [{"advertiser_owner_id": me}, {"linked_office_id": me},
                 {"created_by_id": me}] + ([{"advertiser_org_id": org}] if org else [])
         + [{"advertiser_org_id": me}]}
    docs = await db.advertisements.find(f).sort("created_at", -1).to_list(200)
    items = []
    for d in serialize(docs):
        snap = d.get("package_snapshot") or {}
        mv, mc = snap.get("max_views"), snap.get("max_clicks")
        items.append({**_decorate(d),
                      "package_name": snap.get("name") or (d.get("billing") or {}).get("package_name"),
                      "package_price": snap.get("price"),
                      "package_currency": snap.get("currency"),
                      "duration_days": snap.get("duration_days"),
                      "held_amount": (d.get("billing") or {}).get("held", 0),
                      "billing_state": (d.get("billing") or {}).get("state", "—"),
                      "cancellation": d.get("cancellation"),
                      "remaining_views": (int(mv) - int(d.get("views") or 0)) if mv else None,
                      "remaining_clicks": (int(mc) - int(d.get("clicks") or 0)) if mc else None,
                      "completion_reason": d.get("completion_reason")})
    txns = await db.transactions.find({"type": {"$in": ["ad_hold", "ad_charge",
                                                        "ad_hold_release"]},
                                       "office_id": {"$in": [me, org]}}) \
        .sort("created_at", -1).to_list(100)
    return {"items": items,
            "wallet": {c: ((user.get("wallet") or {}).get(c) or {}) for c in ("SAR", "USD")},
            "transactions": serialize(txns),
            "placements": {k: v["label"] for k, v in PLACEMENTS.items()},
            "audiences": AUDIENCES, "kinds": KINDS, "statuses": STATUSES}


class OfficeAdIn(AdIn):
    advertiser_type: str = "office"


@router.post("/ads/mine")
async def create_my_ad(payload: OfficeAdIn, user: dict = Depends(ads_perm("ads.manage"))):
    """An office/individual creates its OWN campaign as a draft. It can never publish it."""
    if user.get("role") not in ("office", "staff", "individual"):
        raise HTTPException(403, "غير مصرح بإنشاء إعلانات")
    me = str(user["_id"])
    values = payload.model_dump(exclude={"reason"})
    # Ownership is forced from the session — an advertiser can never impersonate another.
    if user.get("role") == "individual":
        values["advertiser_type"] = "individual"
        values["advertiser_owner_id"] = me
        values["advertiser_org_id"] = None
    else:
        values["advertiser_owner_id"] = me
        values["advertiser_org_id"] = str(user.get("org_id") or me)
        values["linked_office_id"] = str(user.get("org_id") or me)
    p = OfficeAdIn(**{**values, "reason": payload.reason})
    _validate(p)
    doc = {**p.model_dump(exclude={"reason"}), "status": "draft", "views": 0, "clicks": 0,
           "source": "office", "billing": {}, "package_snapshot": None,
           "created_by": user.get("email"), "created_by_id": me,
           "approved_by": None, "approved_at": None, "rejection_reason": None,
           "created_at": now_iso(), "updated_at": now_iso()}
    res = await db.advertisements.insert_one(doc)
    await _audit(res.inserted_id, "ad_created", user, payload.reason.strip(),
                 after={"title": p.title, "status": "draft", "source": "office"})
    return _decorate(serialize({**doc, "_id": res.inserted_id}))


async def _own_ad_or_403(ad_id: str, user: dict) -> dict:
    ad = await db.advertisements.find_one({"_id": oid(ad_id)})
    if not ad:
        raise HTTPException(404, "الإعلان غير موجود")
    me, org = str(user["_id"]), str(user.get("org_id") or "")
    owners = {str(ad.get("advertiser_owner_id") or ""), str(ad.get("created_by_id") or ""),
              str(ad.get("advertiser_org_id") or ""), str(ad.get("linked_office_id") or "")}
    if me not in owners and (not org or org not in owners):
        raise HTTPException(403, "لا تملك صلاحية على هذا الإعلان")
    return ad


@router.patch("/ads/mine/{ad_id}")
async def update_my_ad(ad_id: str, payload: OfficeAdIn, user: dict = Depends(ads_perm("ads.manage"))):
    ad = await _own_ad_or_403(ad_id, user)
    if ad.get("status") == "pending_approval":
        raise HTTPException(400, "الإعلان قيد الاعتماد — لا يمكن تعديله الآن")
    _validate(payload)
    values = payload.model_dump(exclude={"reason", "advertiser_owner_id", "advertiser_org_id"})
    # A material edit after approval must go back through approval and stop showing.
    back = ad.get("status") in ("active", "completed")
    await db.advertisements.update_one({"_id": ad["_id"]}, {"$set": {
        **values, "updated_at": now_iso(),
        "status": "draft" if back else ad.get("status"),
        "approved_by": None if back else ad.get("approved_by")}})
    await _audit(ad_id, "ad_updated", user, payload.reason.strip(),
                 before={"status": ad.get("status")},
                 after={"status": "draft" if back else ad.get("status")})
    return {"ok": True, "back_to_draft": back,
            "note": ("تم إيقاف نشر النسخة القديمة وإرجاع الإعلان لمسودة لإعادة الاعتماد"
                     if back else "تم حفظ المسودة")}


class MyStatusIn(BaseModel):
    status: str                     # pending_approval | draft (cancel) | archived
    reason: str = Field(min_length=3)
    package_id: Optional[str] = None


@router.post("/ads/mine/{ad_id}/status")
async def my_ad_status(ad_id: str, payload: MyStatusIn,
                       user: dict = Depends(ads_perm("ads.manage"))):
    """Advertiser may only submit for approval, cancel back to draft, or archive.
    Publishing/approval stays exclusively with Meraaj admins."""
    if payload.status not in ("pending_approval", "draft", "archived"):
        raise HTTPException(403, "النشر والاعتماد من صلاحية إدارة معراج فقط")
    ad = await _own_ad_or_403(ad_id, user)
    if payload.status == "pending_approval":
        if ad.get("status") not in ("draft", "rejected"):
            raise HTTPException(400, "لا يمكن الإرسال للاعتماد من الحالة الحالية")
        if payload.package_id:
            await db.advertisements.update_one({"_id": ad["_id"]},
                                              {"$set": {"package_id": payload.package_id}})
            ad["package_id"] = payload.package_id
    async with _ad_lock(ad, user) as locked:
        ad = {**locked, "package_id": ad.get("package_id")}
        upd = await _apply_status(ad, payload.status, user, payload.reason.strip())
        await db.advertisements.update_one({"_id": ad["_id"]}, {"$set": upd})
        await _audit(ad_id, f"ad_{payload.status}", user, payload.reason.strip(),
                     before={"status": ad.get("status")}, after={"status": payload.status})
    fresh = await db.advertisements.find_one({"_id": ad["_id"]})
    b = fresh.get("billing") or {}
    if payload.status == "pending_approval":
        await _notify_ad(fresh, "ad_submitted", "تم إرسال إعلانك للاعتماد",
                         (f"«{fresh.get('title')}» بانتظار اعتماد إدارة معراج.\n"
                          f"الباقة: {b.get('package_name') or '—'} — المبلغ المحجوز: {_money_line(b)}"),
                         meta={"amount": b.get("held"), "currency": b.get("currency"),
                               "package": b.get("package_name")})
    return {"ok": True, "ad": _decorate(serialize(fresh)),
            "billing": fresh.get("billing") or {}}


class CancelRequestIn(BaseModel):
    reason: str = Field(min_length=3)


@router.post("/ads/mine/{ad_id}/cancellation-request")
async def request_cancellation(ad_id: str, payload: CancelRequestIn,
                               user: dict = Depends(ads_perm("ads.manage"))):
    """The advertiser ASKS to cancel. Nothing is deleted and no balance moves here —
    an admin decides, and any money movement goes only through the wallet/ledger logic."""
    ad = await _own_ad_or_403(ad_id, user)
    if ad.get("status") not in ("active", "pending_approval", "paused"):
        raise HTTPException(400, "طلب الإلغاء متاح للإعلان النشط أو الموقوف أو قيد الاعتماد فقط")
    if ad.get("status") == "cancellation_requested":
        raise HTTPException(400, "يوجد طلب إلغاء قيد المراجعة بالفعل")
    cancellation = {"state": "requested", "reason": payload.reason.strip(),
                    "requested_by": user.get("email"), "requested_by_id": str(user["_id"]),
                    "requested_at": now_iso(), "previous_status": ad.get("status"),
                    "decided_by": None, "decided_at": None, "decision_reason": None,
                    "refund_amount": None, "refund_currency": None, "refund_txn": None}
    res = await db.advertisements.update_one(
        {"_id": ad["_id"], "status": ad.get("status")},
        {"$set": {"status": "cancellation_requested", "cancellation": cancellation,
                  "updated_at": now_iso()}})
    if res.modified_count != 1:
        raise HTTPException(409, "تغيّرت حالة الإعلان — أعد تحميل الصفحة ثم حاول مرة أخرى")
    await _audit(ad_id, "ad_cancellation_requested", user, payload.reason.strip(),
                 before={"status": ad.get("status")}, after={"status": "cancellation_requested"})
    await _notify_ad({**ad, "_id": ad["_id"]}, "ad_cancellation_requested",
                     "تم استلام طلب إلغاء إعلانك",
                     (f"طلب إلغاء «{ad.get('title')}» قيد مراجعة إدارة معراج.\n"
                      f"سبب الطلب: {payload.reason.strip()}\n"
                      "الإعلان لم يُحذف، ولن يتغير رصيدك إلا بقرار معتمد."),
                     meta={"reason": payload.reason.strip()})
    return {"ok": True, "status": "cancellation_requested",
            "note": "الطلب بانتظار قرار الإدارة — لا حركة مالية حتى الآن"}


class CancelDecisionIn(BaseModel):
    decision: str                      # accept | reject
    reason: str = Field(min_length=3)


@router.get("/admin/ads-cancellations")
async def list_cancellations(admin: dict = Depends(require_admin)):
    await _admin_ads_perm(admin, "ads.view")
    docs = await db.advertisements.find({"status": "cancellation_requested"}) \
        .sort("updated_at", -1).to_list(200)
    return {"items": [_decorate(d) for d in serialize(docs)]}


@router.post("/admin/ads/{ad_id}/cancellation")
async def decide_cancellation(ad_id: str, payload: CancelDecisionIn,
                              admin: dict = Depends(require_admin)):
    """Accept → campaign stops showing and stays fully traceable.
    Refund: a still-HELD amount is released through the standard wallet logic; an already
    CAPTURED amount is NOT auto-refunded (refund policy needs a commercial decision)."""
    if payload.decision not in ("accept", "reject"):
        raise HTTPException(400, "القرار غير مدعوم")
    await _admin_ads_perm(admin, "ads.cancel")
    ad = await db.advertisements.find_one({"_id": oid(ad_id)})
    if not ad:
        raise HTTPException(404, "الإعلان غير موجود")
    if ad.get("status") != "cancellation_requested":
        raise HTTPException(400, "لا يوجد طلب إلغاء قيد المراجعة على هذا الإعلان")
    c = dict(ad.get("cancellation") or {})
    reason = payload.reason.strip()
    b = dict(ad.get("billing") or {})

    if payload.decision == "reject":
        upd = {"status": c.get("previous_status") or "active", "updated_at": now_iso(),
               "cancellation": {**c, "state": "rejected", "decided_by": admin.get("email"),
                                "decided_at": now_iso(), "decision_reason": reason}}
        res = await db.advertisements.update_one(
            {"_id": ad["_id"], "status": "cancellation_requested"}, {"$set": upd})
        if res.modified_count != 1:
            raise HTTPException(409, "تم اتخاذ قرار آخر على هذا الطلب — أعد تحميل الصفحة")
        await _audit(ad_id, "ad_cancellation_rejected", admin, reason,
                     before={"status": "cancellation_requested"},
                     after={"status": upd["status"]})
        await _notify_ad(ad, "ad_cancellation_rejected", "تم رفض طلب إلغاء إعلانك",
                         (f"تم رفض طلب إلغاء «{ad.get('title')}». السبب: {reason}\n"
                          f"يستمر الإعلان بحالته: {STATUSES.get(upd['status'], upd['status'])}"),
                         meta={"reason": reason, "status": upd["status"]})
        return {"ok": True, "status": upd["status"]}

    from ads_billing import release_for_ad
    refund = None
    pre_state = b.get("state")          # state BEFORE the decision decides the policy label
    # POLICY (approved): a still-HELD amount is released in full; an already CAPTURED amount is
    # NEVER refunded by the cancellation path — an exceptional refund must go through a separate
    # administrative refund process (own Maker/Checker), not through an ad status change.
    if pre_state == "held":
        policy = "full_hold_release_before_final_charge"
    elif pre_state == "captured":
        policy = "no_automatic_refund_after_final_charge"
    else:                               # free / released / no billing at all
        policy = "no_financial_movement"
    async with _ad_lock(ad, admin):
        if pre_state == "held":
            rel = await release_for_ad(ad, f"إلغاء معتمد: {reason}")
            if rel:
                b.update(rel)
                refund = {"refund_amount": b.get("held"), "refund_currency": b.get("currency"),
                          "refund_txn": "ad_hold_release"}
            else:                       # a concurrent request already released/captured it
                fresh = await db.advertisements.find_one({"_id": ad["_id"]})
                b = dict(fresh.get("billing") or {})
                policy = "no_financial_movement"
        upd = {"status": "cancelled", "billing": b, "updated_at": now_iso(),
               "cancellation": {**c, "state": "accepted", "decided_by": admin.get("email"),
                                "decided_at": now_iso(), "decision_reason": reason,
                                "billing_state_before": pre_state,
                                "refund_policy": policy,
                                **(refund or {"refund_amount": 0,
                                              "refund_currency": b.get("currency"),
                                              "refund_txn": None}),
                                "captured_not_refunded": pre_state == "captured"}}
        await db.advertisements.update_one({"_id": ad["_id"]}, {"$set": upd})
        await _audit(ad_id, "ad_cancellation_approved", admin, reason,
                     before={"status": "cancellation_requested", "billing_state": pre_state},
                     after={"status": "cancelled", "billing_state": b.get("state"),
                            "refund_policy": policy,
                            "refund_amount": (refund or {}).get("refund_amount", 0)})
    await _notify_ad(ad, "ad_cancellation_approved", "تم اعتماد إلغاء إعلانك",
                     (f"تم إلغاء «{ad.get('title')}» وتوقف ظهوره. السبب: {reason}\n"
                      + (f"تم فكّ حجز المبلغ وإعادته إلى رصيدك: {_money_line(b)}" if refund else
                         ("المبلغ كان قد خُصم نهائياً؛ أي استرجاع يتطلب قراراً من الإدارة "
                          "وفق سياسة الاسترجاع." if b.get("state") == "captured" else
                          "لا يوجد مبلغ مرتبط بهذا الإعلان."))),
                     meta={"reason": reason, "refund_amount": (refund or {}).get("refund_amount", 0),
                           "currency": b.get("currency")})
    return {"ok": True, "status": "cancelled",
            "refund": refund or {"refund_amount": 0},
            "note": ("المبلغ المحجوز أُعيد بالكامل" if refund else
                     "لا استرجاع تلقائي لمبلغ مخصوم نهائياً — سياسة الاسترجاع تحتاج قراراً تجارياً")}

