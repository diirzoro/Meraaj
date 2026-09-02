"""Batch 4 — Organisations (offices), branches, staff records and notifications.

The `offices` entity is introduced as first-class WITHOUT touching wallets: an office document
uses the office user's id as `_id` link (`user_id`), so all existing money/ledger code keeps
working unchanged. Staff are management records under an office/branch; giving a staff member a
LOGIN that shares the office wallet remains the documented structural refactor (see DEV_NOTES).
"""
import re
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from db import db, serialize, oid, now_iso, wallet_available
from security import require_admin, get_current_user

router = APIRouter(prefix="/api", tags=["admin-orgs"])

RISK = ("low", "medium", "high")


# ---------------- organisations ----------------
@router.get("/admin/orgs")
async def list_orgs(q: Optional[str] = None, status: Optional[str] = None,
                    risk: Optional[str] = None, page: int = 1,
                    limit: int = Query(25, le=200), admin: dict = Depends(require_admin)):
    f = {"role": "office"}
    if q:
        f["$or"] = [{"office_name": {"$regex": q, "$options": "i"}},
                    {"email": {"$regex": q, "$options": "i"}},
                    {"commercial_license": {"$regex": q, "$options": "i"}}]
    if status:
        f["status"] = status
    total = await db.users.count_documents(f)
    users = await db.users.find(f).sort("office_name", 1) \
        .skip(max(0, (page - 1) * limit)).limit(limit).to_list(limit)
    profiles = {}
    async for p in db.offices.find({}):
        profiles[p["user_id"]] = p
    items = []
    for u in users:
        uid = str(u["_id"])
        p = profiles.get(uid, {})
        if risk and p.get("risk_class") != risk:
            continue
        bookings = await db.bookings.count_documents({"$or": [{"buyer_id": uid}, {"seller_id": uid}]})
        disputes = await db.bookings.count_documents({"dispute.status": "open",
                                                     "$or": [{"buyer_id": uid}, {"seller_id": uid}]})
        items.append({
            "id": uid, "name": u.get("office_name"), "owner": u.get("owner_name"),
            "email": u.get("email"), "phone": u.get("phone"),
            "governorate": u.get("governorate"), "status": u.get("status"),
            "is_rahal": bool(u.get("rahal_office_ref")) or u.get("source") == "rahal",
            "license": u.get("commercial_license"),
            "risk_class": p.get("risk_class") or "medium",
            "account_manager": p.get("account_manager"),
            "legal_docs": p.get("legal_docs") or [],
            "branches_count": await db.office_branches.count_documents({"office_id": uid}),
            "staff_count": await db.office_staff.count_documents({"office_id": uid}),
            "bookings_count": bookings, "open_disputes": disputes,
            "balance": {c: round(wallet_available(u.get("wallet") or {}, c), 2)
                        for c in ("SAR", "USD")},
        })
    return {"items": items, "total": total, "page": page, "limit": limit}


@router.get("/admin/orgs/{office_id}")
async def org_detail(office_id: str, admin: dict = Depends(require_admin)):
    u = await db.users.find_one({"_id": oid(office_id)})
    if not u or u.get("role") != "office":
        raise HTTPException(404, "المؤسسة غير موجودة")
    p = await db.offices.find_one({"user_id": office_id}) or {}
    branches = serialize(await db.office_branches.find({"office_id": office_id}).to_list(200))
    staff = serialize(await db.office_staff.find({"office_id": office_id}).to_list(300))
    bookings = serialize(await db.bookings.find(
        {"$or": [{"buyer_id": office_id}, {"seller_id": office_id}]},
        {"package_title": 1, "status": 1, "amount_charged": 1, "currency": 1, "created_at": 1}
        ).sort("created_at", -1).to_list(30))
    txns = serialize(await db.transactions.find({"office_id": office_id})
                     .sort("created_at", -1).to_list(30))
    credit = serialize(await db.credit_limits.find({"office_id": office_id}).to_list(10))
    return {"office": {**serialize(u), "password_hash": None},
            "profile": serialize(p) if p else {}, "branches": branches, "staff": staff,
            "recent_bookings": bookings, "recent_transactions": txns, "credit": credit}


class ProfileIn(BaseModel):
    risk_class: str = "medium"
    account_manager: str = ""
    relationship_manager: str = ""
    notes: str = ""
    legal_docs: list = []          # [{type,number,expires_at,url}]
    reason: str = Field(min_length=3)


@router.post("/admin/orgs/{office_id}/profile")
async def upsert_profile(office_id: str, payload: ProfileIn, admin: dict = Depends(require_admin)):
    u = await db.users.find_one({"_id": oid(office_id)}, {"office_name": 1, "role": 1})
    if not u or u.get("role") != "office":
        raise HTTPException(404, "المؤسسة غير موجودة")
    if payload.risk_class not in RISK:
        raise HTTPException(400, "تصنيف مخاطر غير صالح")
    before = await db.offices.find_one({"user_id": office_id}) or {}
    doc = payload.model_dump()
    doc.pop("reason")
    doc.update({"user_id": office_id, "office_name": u.get("office_name"),
                "updated_by": admin.get("email"), "updated_at": now_iso()})
    await db.offices.update_one({"user_id": office_id}, {"$set": doc}, upsert=True)
    await db.audit_log.insert_one({
        "entity": "office", "entity_id": office_id, "action": "profile_updated",
        "actor": admin.get("email"), "actor_id": str(admin["_id"]),
        "reason": payload.reason.strip(),
        "before": {k: before.get(k) for k in ("risk_class", "account_manager", "legal_docs")},
        "after": {k: doc.get(k) for k in ("risk_class", "account_manager", "legal_docs")},
        "at": now_iso()})
    return serialize(await db.offices.find_one({"user_id": office_id}))


class BranchIn(BaseModel):
    name: str = Field(min_length=2)
    city: str = ""
    phone: str = ""
    manager: str = ""
    active: bool = True


@router.post("/admin/orgs/{office_id}/branches")
async def add_branch(office_id: str, payload: BranchIn, admin: dict = Depends(require_admin)):
    if not await db.users.find_one({"_id": oid(office_id)}, {"_id": 1}):
        raise HTTPException(404, "المؤسسة غير موجودة")
    rec = {**payload.model_dump(), "office_id": office_id,
           "created_by": admin.get("email"), "created_at": now_iso()}
    res = await db.office_branches.insert_one(rec)
    rec["_id"] = res.inserted_id
    await db.audit_log.insert_one({"entity": "office", "entity_id": office_id,
                                   "action": "branch_added", "actor": admin.get("email"),
                                   "after": {"branch": payload.name}, "at": now_iso()})
    return serialize(rec)


@router.delete("/admin/branches/{branch_id}")
async def del_branch(branch_id: str, admin: dict = Depends(require_admin)):
    b = await db.office_branches.find_one_and_delete({"_id": oid(branch_id)})
    if not b:
        raise HTTPException(404, "الفرع غير موجود")
    await db.audit_log.insert_one({"entity": "office", "entity_id": b["office_id"],
                                   "action": "branch_removed", "actor": admin.get("email"),
                                   "before": {"branch": b.get("name")}, "at": now_iso()})
    return {"ok": True}


class StaffAccountIn(BaseModel):
    email: str = Field(min_length=5)
    password: str = Field(min_length=8)
    roles: list = []


@router.post("/admin/staff/{staff_id}/account")
async def create_staff_account(staff_id: str, payload: StaffAccountIn,
                               admin: dict = Depends(require_admin)):
    """Creates a LOGIN account for an office staff member.
    The account has NO wallet of its own: at authentication it acts inside the office identity,
    so it shares the office wallet, ledger and bookings. Rahal users are untouched."""
    from security import hash_password
    from rbac import ROLES
    s = await db.office_staff.find_one({"_id": oid(staff_id)})
    if not s:
        raise HTTPException(404, "الموظف غير موجود")
    if s.get("linked_user_id"):
        raise HTTPException(400, "للموظف حساب دخول بالفعل")
    email = payload.email.strip().lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(400, "البريد مستخدم مسبقاً — لا يُسمح بحساب مكرر")
    bad = [r for r in payload.roles if r not in ROLES]
    if bad:
        raise HTTPException(400, f"أدوار غير معروفة: {', '.join(bad)}")
    office = await db.users.find_one({"_id": oid(s["office_id"])}, {"office_name": 1, "role": 1})
    if not office:
        raise HTTPException(404, "المكتب غير موجود")
    doc = {
        "email": email, "password_hash": hash_password(payload.password),
        "role": "office", "status": "active",
        "parent_office_id": s["office_id"], "office_name": office.get("office_name"),
        "staff_name": s.get("name"), "staff_roles": payload.roles,
        "staff_record_id": staff_id, "is_staff_account": True,
        # deliberately NO wallet key: staff never own a wallet
        "created_by": admin.get("email"), "created_at": now_iso(),
    }
    res = await db.users.insert_one(doc)
    await db.office_staff.update_one({"_id": s["_id"]},
                                     {"$set": {"linked_user_id": str(res.inserted_id),
                                               "login_email": email, "roles": payload.roles}})
    await db.user_roles.update_one({"user_id": str(res.inserted_id)}, {"$set": {
        "roles": payload.roles, "office_id": s["office_id"],
        "branch_id": s.get("branch_id", ""), "granted_by": admin.get("email"),
        "at": now_iso()}}, upsert=True)
    await db.audit_log.insert_one({
        "entity": "office", "entity_id": s["office_id"], "action": "staff_account_created",
        "actor": admin.get("email"), "actor_id": str(admin["_id"]),
        "after": {"staff": s.get("name"), "email": email, "roles": payload.roles,
                  "shared_wallet": True}, "at": now_iso()})
    return {"ok": True, "user_id": str(res.inserted_id), "email": email,
            "shares_office_wallet": True}


@router.post("/admin/staff/{staff_id}/account/disable")
async def disable_staff_account(staff_id: str, admin: dict = Depends(require_admin)):
    s = await db.office_staff.find_one({"_id": oid(staff_id)})
    if not s or not s.get("linked_user_id"):
        raise HTTPException(404, "لا يوجد حساب دخول لهذا الموظف")
    await db.users.update_one({"_id": oid(s["linked_user_id"])},
                              {"$set": {"status": "suspended", "force_logout_at": now_iso()}})
    await db.audit_log.insert_one({
        "entity": "office", "entity_id": s["office_id"], "action": "staff_account_disabled",
        "actor": admin.get("email"), "after": {"staff": s.get("name")}, "at": now_iso()})
    return {"ok": True}


class StaffIn(BaseModel):
    name: str = Field(min_length=2)
    job_title: str = ""
    phone: str = ""
    email: str = ""
    branch_id: str = ""
    roles: list = []
    active: bool = True


@router.post("/admin/orgs/{office_id}/staff")
async def add_staff(office_id: str, payload: StaffIn, admin: dict = Depends(require_admin)):
    if not await db.users.find_one({"_id": oid(office_id)}, {"_id": 1}):
        raise HTTPException(404, "المؤسسة غير موجودة")
    rec = {**payload.model_dump(), "office_id": office_id, "linked_user_id": None,
           "created_by": admin.get("email"), "created_at": now_iso()}
    res = await db.office_staff.insert_one(rec)
    rec["_id"] = res.inserted_id
    await db.audit_log.insert_one({"entity": "office", "entity_id": office_id,
                                   "action": "staff_added", "actor": admin.get("email"),
                                   "after": {"staff": payload.name, "roles": payload.roles},
                                   "at": now_iso()})
    return serialize(rec)


@router.delete("/admin/staff/{staff_id}")
async def del_staff(staff_id: str, admin: dict = Depends(require_admin)):
    s = await db.office_staff.find_one_and_delete({"_id": oid(staff_id)})
    if not s:
        raise HTTPException(404, "الموظف غير موجود")
    await db.audit_log.insert_one({"entity": "office", "entity_id": s["office_id"],
                                   "action": "staff_removed", "actor": admin.get("email"),
                                   "before": {"staff": s.get("name")}, "at": now_iso()})
    return {"ok": True}


# ---------------- notifications ----------------
def _render(text: str, meta: Optional[dict]) -> str:
    out = text or ""
    for k, v in (meta or {}).items():
        out = out.replace("{{" + str(k) + "}}", str(v))
    return out


async def notify(user_id: Optional[str], kind: str, title: str, body: str = "",
                 link: str = "", meta: Optional[dict] = None, channel: str = "in_app"):
    """Fire-and-forget in-app notification + delivery log. Never raises.
    An active template for the kind overrides the default text; `{{var}}` placeholders are
    filled from `meta` (unknown placeholders are left untouched)."""
    try:
        tpl = await db.notification_templates.find_one({"kind": kind, "active": True})
        if tpl:
            title = _render(tpl.get("title") or title, meta)
            body = _render(tpl.get("body") or body, meta)
        rec = {"user_id": user_id, "kind": kind, "title": title, "body": body, "link": link,
               "meta": meta or {}, "read": False, "at": now_iso()}
        res = await db.notifications.insert_one(rec)
        await db.notification_log.insert_one({
            "notification_id": str(res.inserted_id), "user_id": user_id, "kind": kind,
            "channel": channel, "status": "delivered", "error": None, "at": now_iso()})
        return str(res.inserted_id)
    except Exception as e:  # logging must never break a business flow
        try:
            await db.notification_log.insert_one({
                "user_id": user_id, "kind": kind, "channel": channel,
                "status": "failed", "error": str(e)[:300], "at": now_iso()})
        except Exception:
            pass
        return None


@router.get("/notifications")
async def my_notifications(unread_only: bool = False, limit: int = 50,
                           user: dict = Depends(get_current_user)):
    f = {"user_id": {"$in": [str(user["_id"]), None]}}
    if user.get("role") != "super_admin":
        f = {"user_id": str(user["_id"])}
    if unread_only:
        f["read"] = False
    docs = await db.notifications.find(f).sort("at", -1).to_list(min(limit, 200))
    unread = await db.notifications.count_documents({**f, "read": False})
    return {"items": serialize(docs), "unread": unread}


@router.post("/notifications/{note_id}/read")
async def mark_read(note_id: str, user: dict = Depends(get_current_user)):
    await db.notifications.update_one({"_id": oid(note_id)}, {"$set": {"read": True}})
    return {"ok": True}


@router.post("/notifications/read-all")
async def mark_all_read(user: dict = Depends(get_current_user)):
    await db.notifications.update_many({"user_id": str(user["_id"]), "read": False},
                                       {"$set": {"read": True}})
    return {"ok": True}


KINDS = {
    "booking_created": "إنشاء طلب", "booking_approved": "قبول طلب",
    "booking_rejected": "رفض طلب", "booking_cancelled": "إلغاء طلب",
    "cancellation_requested": "طلب إلغاء", "documents_missing": "مستندات ناقصة",
    "passport_expiring": "جواز قارب الانتهاء", "credit_threshold": "تجاوز حد ائتماني",
    "withdrawal_stage": "تحديث طلب سحب", "task_overdue": "مهمة متأخرة",
    "escalation": "تصعيد إداري",
}

# Who receives each kind (recipient rules). buyer/seller/admin are resolved at send time.
RECIPIENTS = {
    "booking_created": ["seller", "admin"],
    "booking_approved": ["buyer"],
    "booking_rejected": ["buyer"],
    "booking_cancelled": ["buyer", "seller"],
    "cancellation_requested": ["seller", "admin"],
    "documents_missing": ["buyer"],
    "passport_expiring": ["buyer"],
    "credit_threshold": ["admin"],
    "withdrawal_stage": ["seller"],
    "task_overdue": ["admin"],
    "escalation": ["admin"],
}

# Editable defaults, seeded once so the screen is never empty and text is fully editable.
DEFAULT_TEMPLATES = {
    "booking_created": ("طلب حجز جديد", "طلب جديد على: {{package_title}} — عدد المقاعد {{seats}}"),
    "booking_approved": ("تم قبول طلبك", "قبل البائع طلبك على: {{package_title}}"),
    "booking_rejected": ("تم رفض طلبك", "رفض البائع طلبك على: {{package_title}} — {{reason}}"),
    "booking_cancelled": ("تم إلغاء الطلب", "أُلغي الطلب على: {{package_title}} — {{reason}}"),
    "cancellation_requested": ("طلب إلغاء بانتظار القرار",
                               "طلب إلغاء على: {{package_title}} — السبب: {{reason}}"),
    "documents_missing": ("مستندات ناقصة", "لا يوجد جواز مرفوع في الطلب: {{package_title}}"),
    "passport_expiring": ("جواز قارب الانتهاء", "{{name}} — تاريخ الانتهاء {{expiry}}"),
    "credit_threshold": ("تنبيه سقف ائتماني",
                         "{{office_name}} بلغ {{pct}}% من السقف ({{currency}})"),
    "withdrawal_stage": ("تحديث طلب السحب",
                         "انتقل طلب السحب {{amount}} {{currency}} إلى مرحلة: {{stage_label}}"),
    "task_overdue": ("مهمة متأخرة", "{{title}} — المسؤول {{assignee}}"),
    "escalation": ("تصعيد إداري", "{{message}}"),
}


async def seed_notification_templates() -> int:
    """Idempotent: creates any missing default template. Never overwrites admin edits."""
    created = 0
    for kind, (title, body) in DEFAULT_TEMPLATES.items():
        res = await db.notification_templates.update_one(
            {"kind": kind},
            {"$setOnInsert": {"kind": kind, "title": title, "body": body,
                              "channels": ["in_app"], "active": True,
                              "recipients": RECIPIENTS.get(kind, []),
                              "is_default": True, "updated_by": "system",
                              "updated_at": now_iso()}}, upsert=True)
        if res.upserted_id:
            created += 1
    return created


class TemplateIn(BaseModel):
    kind: str
    title: str
    body: str = ""
    channels: list = ["in_app"]
    recipients: Optional[list] = None
    active: bool = True


@router.get("/admin/notification-templates")
async def templates(admin: dict = Depends(require_admin)):
    return {"kinds": KINDS, "recipients_rules": RECIPIENTS,
            "variables": {k: sorted(set(re.findall(r"{{(\w+)}}", f"{t[0]} {t[1]}")))
                          for k, t in DEFAULT_TEMPLATES.items()},
            "items": serialize(await db.notification_templates.find({}).to_list(200))}


@router.post("/admin/notification-templates/seed")
async def seed_templates(admin: dict = Depends(require_admin)):
    created = await seed_notification_templates()
    await db.audit_log.insert_one({
        "entity": "settings", "entity_id": "notification_templates",
        "action": "templates_seeded", "actor": admin.get("email"),
        "after": {"created": created}, "at": now_iso()})
    return {"ok": True, "created": created,
            "total": await db.notification_templates.count_documents({})}


@router.post("/admin/notification-templates")
async def upsert_template(payload: TemplateIn, admin: dict = Depends(require_admin)):
    if payload.kind not in KINDS:
        raise HTTPException(400, "نوع إشعار غير معروف")
    doc = payload.model_dump()
    if doc.get("recipients") is None:
        doc["recipients"] = RECIPIENTS.get(payload.kind, [])
    await db.notification_templates.update_one({"kind": payload.kind}, {"$set": {
        **doc, "is_default": False, "updated_by": admin.get("email"), "updated_at": now_iso()}},
        upsert=True)
    await db.audit_log.insert_one({
        "entity": "settings", "entity_id": f"notification_template:{payload.kind}",
        "action": "template_updated", "actor": admin.get("email"),
        "after": {"title": payload.title, "active": payload.active}, "at": now_iso()})
    return serialize(await db.notification_templates.find_one({"kind": payload.kind}))


@router.get("/admin/notification-log")
async def notification_log(status: Optional[str] = None, limit: int = 100,
                           admin: dict = Depends(require_admin)):
    f = {"status": status} if status else {}
    docs = await db.notification_log.find(f).sort("at", -1).to_list(min(limit, 500))
    stats = {}
    async for r in db.notification_log.aggregate([{"$group": {"_id": "$status", "n": {"$sum": 1}}}]):
        stats[r["_id"] or "unknown"] = r["n"]
    return {"items": serialize(docs), "stats": stats}


@router.post("/admin/notifications/scan")
async def scan_alerts(admin: dict = Depends(require_admin)):
    """Generates alerts for missing documents, expiring passports, credit thresholds and
    overdue tasks. Idempotent per (kind, target) within the same day."""
    created = {"documents_missing": 0, "passport_expiring": 0, "credit_threshold": 0,
               "task_overdue": 0}
    today = now_iso()[:10]

    async def once(kind, target, user_id, title, body, link):
        if await db.notifications.find_one({"kind": kind, "meta.target": target,
                                            "at": {"$gte": today}}):
            return False
        await notify(user_id, kind, title, body, link, {"target": target})
        return True

    for b in await db.bookings.find({"status": {"$in": ["blue", "yellow"]}}, {"registrants": 1, "package_title": 1, "buyer_id": 1}).to_list(500):
        bid = str(b["_id"])
        have = set()
        async for d in db.traveler_documents.find({"booking_id": bid}, {"doc_type": 1}):
            have.add(d["doc_type"])
        if "passport" not in have:
            if await once("documents_missing", bid, b.get("buyer_id"),
                          "مستندات ناقصة", f"لا يوجد جواز مرفوع في الطلب: {b.get('package_title')}",
                          f"/admin/orders/{bid}"):
                created["documents_missing"] += 1

    pa = await db.bookings.find({"status": {"$ne": "cancelled"}},
                                {"registrants": 1, "package_title": 1, "buyer_id": 1}).to_list(500)
    from datetime import date, timedelta as _td
    horizon = (date.fromisoformat(today) + _td(days=365)).isoformat()
    for b in pa:
        for r in b.get("registrants") or []:
            exp = str(r.get("passport_expiry") or "")[:10]
            if exp and exp <= horizon:
                if await once("passport_expiring", f"{b['_id']}:{r.get('passport_no')}",
                              b.get("buyer_id"), "جواز قارب الانتهاء",
                              f"{r.get('name')} — انتهاء {exp}", f"/admin/travelers"):
                    created["passport_expiring"] += 1

    async for l in db.credit_limits.find({"limit": {"$gt": 0}}):
        u = await db.users.find_one({"_id": oid(l["office_id"])}, {"office_name": 1, "wallet": 1})
        if not u:
            continue
        used = max(0.0, -wallet_available(u.get("wallet") or {}, l["currency"]))
        pct = (used / float(l["limit"])) * 100 if l.get("limit") else 0
        if pct >= 70:
            if await once("credit_threshold", f"{l['office_id']}:{l['currency']}", None,
                          "تنبيه سقف ائتماني",
                          f"{u.get('office_name')} بلغ {round(pct)}% من السقف ({l['currency']})",
                          "/admin/credit"):
                created["credit_threshold"] += 1

    async for t in db.admin_tasks.find({"status": {"$in": ["open", "in_progress"]}}):
        if t.get("due_date") and str(t["due_date"])[:10] < today:
            if await once("task_overdue", str(t["_id"]), None, "مهمة متأخرة",
                          f"{t.get('title')} — المسؤول {t.get('assignee') or 'غير محدد'}",
                          f"/admin/orders/{t.get('booking_id')}"):
                created["task_overdue"] += 1
                await db.admin_tasks.update_one({"_id": t["_id"]},
                                                {"$set": {"escalated": True,
                                                          "escalated_at": now_iso()}})
    return {"created": created, "total": sum(created.values())}
