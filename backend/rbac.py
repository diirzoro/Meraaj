"""Batch 4 — Enterprise RBAC, sessions, 2FA and Maker–Checker.

ADDITIVE and non-breaking: the legacy roles (`super_admin` / `office` / `individual`) and the
Rahal per-office permission gate keep working exactly as before. Enterprise roles are an extra
layer stored in `user_roles`; `super_admin` implicitly holds every permission.
"""
import base64
import os
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from db import db, serialize, oid, now_iso
from security import require_admin, get_current_user

router = APIRouter(prefix="/api/admin", tags=["admin-rbac"])

PERMISSIONS = {
    "orders.view": "عرض الطلبات", "orders.decide": "اعتماد/رفض الطلبات",
    "orders.status": "تغيير حالة الطلب", "orders.cancel": "الإلغاء والاسترداد",
    "prices.edit": "تعديل الأسعار", "commissions.edit": "تعديل العمولات",
    "credit.edit": "تعديل السقف الائتماني", "funds.release": "تحرير الأموال",
    "withdrawals.approve": "اعتماد السحب", "documents.upload": "رفع المستندات",
    "documents.delete": "حذف المستندات", "documents.passport_view": "الاطلاع على بيانات الجوازات",
    "data.export": "تصدير البيانات", "settings.edit": "تعديل إعدادات النظام",
    "users.manage": "إدارة المستخدمين والصلاحيات", "orgs.manage": "إدارة المؤسسات والفروع",
    "integrations.retry": "إعادة معالجة التكاملات", "audit.view": "عرض سجل التدقيق",
    "reports.view": "عرض التقارير", "backup.run": "تشغيل النسخ الاحتياطي",
    "backup.restore": "الاستعادة من نسخة",
}

ROLES = {
    "super_admin": {"label": "Super Admin", "ar": "المدير العام", "perms": ["*"]},
    "operations_manager": {"label": "Operations Manager", "ar": "مدير العمليات",
                           "perms": ["orders.view", "orders.decide", "orders.status", "orders.cancel",
                                     "prices.edit", "documents.upload", "reports.view", "audit.view"]},
    "operations_officer": {"label": "Operations Officer", "ar": "موظف عمليات",
                           "perms": ["orders.view", "orders.status", "documents.upload", "reports.view"]},
    "finance_manager": {"label": "Finance Manager", "ar": "المدير المالي",
                        "perms": ["orders.view", "funds.release", "withdrawals.approve",
                                  "commissions.edit", "credit.edit", "reports.view", "data.export",
                                  "audit.view"]},
    "accountant": {"label": "Accountant", "ar": "محاسب",
                   "perms": ["orders.view", "reports.view", "data.export"]},
    "compliance_officer": {"label": "Compliance Officer", "ar": "مسؤول الالتزام",
                           "perms": ["orders.view", "audit.view", "documents.passport_view",
                                     "reports.view", "orgs.manage"]},
    "customer_support": {"label": "Customer Support", "ar": "خدمة العملاء",
                         "perms": ["orders.view", "documents.upload"]},
    "auditor": {"label": "Auditor (read only)", "ar": "مدقّق — قراءة فقط",
                "perms": ["orders.view", "audit.view", "reports.view"]},
    "seller_admin": {"label": "Seller Admin", "ar": "مدير حساب بائع",
                     "perms": ["orders.view", "orders.decide", "prices.edit", "documents.upload"]},
    "office_admin": {"label": "Office Admin", "ar": "مدير مكتب",
                     "perms": ["orders.view", "documents.upload", "reports.view"]},
    "branch_manager": {"label": "Branch Manager", "ar": "مدير فرع",
                       "perms": ["orders.view", "documents.upload"]},
    "limited_user": {"label": "Limited User", "ar": "مستخدم محدود", "perms": ["orders.view"]},
}

# Operations that can be configured to require a second approver (Maker–Checker)
DUAL_CONTROL = {
    "credit.edit": "تعديل السقف الائتماني", "commissions.edit": "تعديل العمولات",
    "withdrawals.approve": "اعتماد السحب", "orders.cancel": "الإلغاء والاسترداد",
    "funds.release": "تحرير الأموال", "documents.delete": "حذف المستندات",
    "settings.edit": "تعديل إعدادات النظام",
}


async def user_permissions(user: dict) -> List[str]:
    if user.get("role") == "super_admin":
        return ["*"]
    # A staff account acts inside the office identity, so `user` is the OFFICE document.
    # Enterprise permissions must still come from the STAFF member's own assignment.
    acting = user.get("_acting_staff")
    lookup_id = acting["id"] if acting else str(user["_id"])
    doc = await db.user_roles.find_one({"user_id": lookup_id})
    roles = list((doc or {}).get("roles", []))
    if acting and not roles:
        roles = list(acting.get("roles") or [])
    perms = set()
    for r in roles:
        for p in ROLES.get(r, {}).get("perms", []):
            perms.add(p)
    for p in (doc or {}).get("extra_permissions", []):
        if p in PERMISSIONS:
            perms.add(p)
    return sorted(perms)


async def has_perm(user: dict, key: str) -> bool:
    perms = await user_permissions(user)
    return "*" in perms or key in perms


def require_perm(key: str):
    """Gate for NEW enterprise endpoints only (existing endpoints are untouched)."""
    async def dep(user: dict = Depends(get_current_user)) -> dict:
        if not await has_perm(user, key):
            raise HTTPException(403, f"لا تملك صلاحية: {PERMISSIONS.get(key, key)}")
        return user
    return dep


# ---------------- catalog & assignment ----------------
@router.get("/rbac/catalog")
async def catalog(admin: dict = Depends(require_admin)):
    return {"permissions": PERMISSIONS, "roles": ROLES, "dual_control": DUAL_CONTROL,
            "settings": await _dual_settings()}


async def _dual_settings() -> dict:
    doc = await db.settings.find_one({"_id": "maker_checker"})
    return (doc or {}).get("required", {})


@router.get("/rbac/users")
async def rbac_users(q: Optional[str] = None, role: Optional[str] = None,
                     unassigned: Optional[bool] = None, staff_only: bool = False,
                     limit: int = 100, admin: dict = Depends(require_admin)):
    f = {}
    if q:
        f["$or"] = [{"email": {"$regex": q, "$options": "i"}},
                    {"office_name": {"$regex": q, "$options": "i"}}]
    if role:
        f["role"] = role
    if staff_only:
        f["is_staff_account"] = True
    users = await db.users.find(f, {"email": 1, "office_name": 1, "role": 1, "status": 1,
                                    "created_at": 1, "source": 1, "rahal_office_ref": 1,
                                    "twofa_enabled": 1, "force_logout_at": 1,
                                    "is_staff_account": 1, "parent_office_id": 1,
                                    "staff_name": 1, "wallet": 1}
                                ).sort("created_at", -1).to_list(min(limit, 500))
    assigns = {}
    async for a in db.user_roles.find({}):
        assigns[a["user_id"]] = a
    out = []
    for u in users:
        a = assigns.get(str(u["_id"]), {})
        d = serialize(u)
        d.pop("wallet", None)
        d["enterprise_roles"] = a.get("roles", [])
        d["extra_permissions"] = a.get("extra_permissions", [])
        d["branch_id"] = a.get("branch_id")
        d["office_id"] = a.get("office_id")
        d["permissions"] = await user_permissions(u)
        d["is_rahal"] = bool(u.get("rahal_office_ref")) or u.get("source") == "rahal"
        d["is_staff"] = bool(u.get("is_staff_account"))
        d["parent_office_id"] = u.get("parent_office_id")
        d["has_own_wallet"] = "wallet" in u
        d["is_qa_account"] = str(u.get("email") or "").endswith("@qa-example.com")
        # Explains an empty permission list instead of leaving it ambiguous in the UI
        if u.get("role") == "super_admin":
            d["roles_note"] = "المدير العام يملك كل الصلاحيات ضمناً"
        elif d["enterprise_roles"]:
            d["roles_note"] = None
        elif d["is_staff"]:
            d["roles_note"] = "حساب موظف بلا أدوار مؤسسية — امنحه دوراً لتفعيل صلاحياته"
        else:
            d["roles_note"] = ("حساب مالك (مكتب/فرد) بصلاحياته الأساسية فقط — الأدوار "
                               "المؤسسية تُمنح صراحةً عند الحاجة")
        out.append(d)
    if unassigned is True:
        out = [x for x in out if not x["enterprise_roles"] and x.get("role") != "super_admin"]
    elif unassigned is False:
        out = [x for x in out if x["enterprise_roles"]]
    summary = {
        "total_returned": len(out),
        "with_roles": sum(1 for x in out if x["enterprise_roles"]),
        "without_roles": sum(1 for x in out if not x["enterprise_roles"]),
        "staff_accounts": sum(1 for x in out if x["is_staff"]),
        "qa_accounts": sum(1 for x in out if x["is_qa_account"]),
    }
    return {"items": out, "total": len(out), "summary": summary}


class RolesIn(BaseModel):
    roles: List[str]
    branch_id: str = ""
    office_id: str = ""
    reason: str = Field(min_length=3)


@router.post("/rbac/users/{user_id}/roles")
async def assign_roles(user_id: str, payload: RolesIn, admin: dict = Depends(require_admin)):
    u = await db.users.find_one({"_id": oid(user_id)}, {"email": 1, "role": 1})
    if not u:
        raise HTTPException(404, "المستخدم غير موجود")
    bad = [r for r in payload.roles if r not in ROLES]
    if bad:
        raise HTTPException(400, f"أدوار غير معروفة: {', '.join(bad)}")
    before = await db.user_roles.find_one({"user_id": user_id})
    await db.user_roles.update_one({"user_id": user_id}, {"$set": {
        "roles": payload.roles, "branch_id": payload.branch_id, "office_id": payload.office_id,
        "granted_by": admin.get("email"), "at": now_iso()}}, upsert=True)
    await db.audit_log.insert_one({
        "entity": "user", "entity_id": user_id, "action": "roles_assigned",
        "actor": admin.get("email"), "actor_id": str(admin["_id"]),
        "reason": payload.reason.strip(),
        "before": {"roles": (before or {}).get("roles", [])}, "after": {"roles": payload.roles},
        "at": now_iso()})
    return {"ok": True, "roles": payload.roles,
            "permissions": await user_permissions(await db.users.find_one({"_id": oid(user_id)}))}


class ExtraPermsIn(BaseModel):
    permissions: list
    reason: str = Field(min_length=3)


@router.post("/rbac/users/{user_id}/permissions")
async def set_extra_permissions(user_id: str, payload: ExtraPermsIn,
                                admin: dict = Depends(require_admin)):
    """Grants/removes individual permissions ON TOP of the assigned roles. Only known
    permission keys are accepted, and `*` can never be granted this way."""
    u = await db.users.find_one({"_id": oid(user_id)}, {"email": 1})
    if not u:
        raise HTTPException(404, "المستخدم غير موجود")
    perms = sorted({str(p) for p in payload.permissions})
    bad = [p for p in perms if p not in PERMISSIONS]
    if bad:
        raise HTTPException(400, f"صلاحيات غير معروفة: {', '.join(bad)}")
    before = await db.user_roles.find_one({"user_id": user_id})
    await db.user_roles.update_one({"user_id": user_id}, {"$set": {
        "extra_permissions": perms, "granted_by": admin.get("email"), "at": now_iso()}},
        upsert=True)
    await db.audit_log.insert_one({
        "entity": "user", "entity_id": user_id, "action": "permissions_assigned",
        "actor": admin.get("email"), "actor_id": str(admin["_id"]),
        "reason": payload.reason.strip(),
        "before": {"extra_permissions": (before or {}).get("extra_permissions", [])},
        "after": {"extra_permissions": perms}, "at": now_iso()})
    return {"ok": True, "extra_permissions": perms,
            "permissions": await user_permissions(await db.users.find_one({"_id": oid(user_id)}))}


class UserCreateIn(BaseModel):
    email: str = Field(min_length=5)
    password: str = Field(min_length=8)
    role: str                       # office | individual | marketer | staff
    name: str = Field(min_length=2)
    phone: str = ""
    office_id: Optional[str] = None   # required for staff accounts
    roles: list = []
    reason: str = Field(min_length=3)


@router.post("/rbac/users")
async def create_user(payload: UserCreateIn, admin: dict = Depends(require_admin)):
    """Creates a user or an office employee. Staff accounts are linked to their office and
    never receive their own wallet — they operate on the office wallet."""
    from security import hash_password
    if payload.role not in ("office", "individual", "marketer", "staff"):
        raise HTTPException(400, "دور غير مدعوم")
    bad = [r for r in payload.roles if r not in ROLES]
    if bad:
        raise HTTPException(400, f"أدوار غير معروفة: {', '.join(bad)}")
    email = payload.email.strip().lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(400, "البريد مستخدم مسبقاً")
    doc = {"email": email, "password_hash": hash_password(payload.password),
           "status": "active", "source": "admin_created",
           "created_at": now_iso(), "created_by": admin.get("email")}
    if payload.role == "staff":
        if not payload.office_id:
            raise HTTPException(400, "حساب الموظف يحتاج تحديد المكتب")
        office = await db.users.find_one({"_id": oid(payload.office_id)},
                                         {"office_name": 1, "role": 1})
        if not office or office.get("role") != "office":
            raise HTTPException(404, "المكتب غير موجود")
        doc.update({"role": "office", "is_staff_account": True,
                    "parent_office_id": payload.office_id,
                    "staff_name": payload.name.strip(),
                    "office_name": office.get("office_name"),
                    "owner_name": payload.name.strip(), "phone": payload.phone.strip()})
    else:
        doc.update({"role": payload.role, "owner_name": payload.name.strip(),
                    "office_name": payload.name.strip() if payload.role == "office" else None,
                    "phone": payload.phone.strip(),
                    "wallet": {c: {"total": 0.0, "pending": 0.0, "available": 0.0}
                               for c in ("SAR", "USD")}})
    res = await db.users.insert_one(doc)
    uid = str(res.inserted_id)
    if payload.role == "staff":
        rec = await db.office_staff.insert_one({
            "office_id": payload.office_id, "name": payload.name.strip(),
            "job_title": "", "phone": payload.phone.strip(), "email": email,
            "login_email": email, "linked_user_id": uid, "roles": payload.roles,
            "active": True, "created_by": admin.get("email"), "created_at": now_iso()})
        assert rec.inserted_id
    if payload.roles:
        await db.user_roles.update_one({"user_id": uid}, {"$set": {
            "roles": payload.roles, "office_id": payload.office_id,
            "granted_by": admin.get("email"), "at": now_iso()}}, upsert=True)
    await db.audit_log.insert_one({
        "entity": "user", "entity_id": uid, "action": "user_created",
        "actor": admin.get("email"), "actor_id": str(admin["_id"]),
        "reason": payload.reason.strip(),
        "after": {"email": email, "role": payload.role, "roles": payload.roles,
                  "office_id": payload.office_id}, "at": now_iso()})
    return {"id": uid, "email": email, "role": doc["role"],
            "is_staff_account": bool(doc.get("is_staff_account"))}


class UserEditIn(BaseModel):
    owner_name: Optional[str] = None
    staff_name: Optional[str] = None
    phone: Optional[str] = None
    office_name: Optional[str] = None
    governorate: Optional[str] = None
    reason: str = Field(min_length=3)


@router.patch("/rbac/users/{user_id}")
async def edit_user(user_id: str, payload: UserEditIn, admin: dict = Depends(require_admin)):
    """Edits profile information only. Email, password hash, role, wallet, SSO reference and
    session state are protected and cannot be changed here."""
    u = await db.users.find_one({"_id": oid(user_id)})
    if not u:
        raise HTTPException(404, "المستخدم غير موجود")
    changes = {k: v.strip() for k, v in payload.model_dump(exclude={"reason"}).items()
               if v is not None}
    if not changes:
        raise HTTPException(400, "لا يوجد تغيير")
    await db.users.update_one({"_id": oid(user_id)}, {"$set": {
        **changes, "updated_by": admin.get("email"), "updated_at": now_iso()}})
    await db.audit_log.insert_one({
        "entity": "user", "entity_id": user_id, "action": "user_updated",
        "actor": admin.get("email"), "reason": payload.reason.strip(),
        "before": {k: u.get(k) for k in changes}, "after": changes, "at": now_iso()})
    return {"ok": True, "changes": changes}


class PasswordResetIn(BaseModel):
    new_password: str = Field(min_length=8)
    reason: str = Field(min_length=3)


@router.post("/rbac/users/{user_id}/password-reset")
async def admin_password_reset(user_id: str, payload: PasswordResetIn,
                               admin: dict = Depends(require_admin)):
    """Sets a temporary password using the EXISTING password policy/hasher, then revokes all
    active sessions of that user so the old tokens stop working. The password itself is
    never logged — only the fact that a reset happened."""
    from security import hash_password
    u = await db.users.find_one({"_id": oid(user_id)}, {"email": 1, "role": 1})
    if not u:
        raise HTTPException(404, "المستخدم غير موجود")
    if u.get("role") == "super_admin" and str(u["_id"]) != str(admin["_id"]):
        raise HTTPException(403, "لا يمكن تصفير كلمة مرور مدير عام آخر")
    await db.users.update_one({"_id": oid(user_id)}, {"$set": {
        "password_hash": hash_password(payload.new_password),
        "force_logout_at": now_iso(),
        "password_reset_by": admin.get("email"), "password_reset_at": now_iso()}})
    await db.sessions.update_many({"user_id": user_id},
                                 {"$set": {"revoked": True, "revoked_at": now_iso()}})
    await db.audit_log.insert_one({
        "entity": "user", "entity_id": user_id, "action": "password_reset",
        "actor": admin.get("email"), "actor_id": str(admin["_id"]),
        "reason": payload.reason.strip(),
        "after": {"email": u.get("email"), "sessions_revoked": True}, "at": now_iso()})
    return {"ok": True, "email": u.get("email"), "sessions_revoked": True}


class DualIn(BaseModel):
    required: dict
    reason: str = Field(min_length=3)


@router.post("/rbac/dual-control")
async def set_dual_control(payload: DualIn, admin: dict = Depends(require_admin)):
    bad = set(payload.required) - set(DUAL_CONTROL)
    if bad:
        raise HTTPException(400, f"عمليات غير معروفة: {', '.join(sorted(bad))}")
    before = await _dual_settings()
    await db.settings.update_one({"_id": "maker_checker"},
                                {"$set": {"required": payload.required, "updated_at": now_iso(),
                                          "updated_by": admin.get("email")}}, upsert=True)
    await db.audit_log.insert_one({
        "entity": "settings", "entity_id": "maker_checker", "action": "dual_control_updated",
        "actor": admin.get("email"), "actor_id": str(admin["_id"]),
        "reason": payload.reason.strip(), "before": before, "after": payload.required,
        "at": now_iso()})
    return {"ok": True, "required": payload.required}


# ---------------- Maker–Checker approvals ----------------
class ApprovalIn(BaseModel):
    operation: str
    target: str
    payload: dict = {}
    reason: str = Field(min_length=3)


@router.post("/approvals")
async def create_approval(payload: ApprovalIn, admin: dict = Depends(require_admin)):
    if payload.operation not in DUAL_CONTROL:
        raise HTTPException(400, "العملية غير خاضعة للموافقة المزدوجة")
    rec = {"operation": payload.operation, "operation_label": DUAL_CONTROL[payload.operation],
           "target": payload.target, "payload": payload.payload,
           "reason": payload.reason.strip(), "status": "pending",
           "maker": admin.get("email"), "maker_id": str(admin["_id"]),
           "checker": None, "checker_id": None, "decided_at": None,
           "created_at": now_iso()}
    res = await db.approvals.insert_one(rec)
    rec["_id"] = res.inserted_id
    return serialize(rec)


class DecisionIn(BaseModel):
    approve: bool
    note: str = ""


@router.post("/approvals/{approval_id}/decide")
async def decide_approval(approval_id: str, payload: DecisionIn,
                          admin: dict = Depends(require_admin)):
    a = await db.approvals.find_one({"_id": oid(approval_id)})
    if not a:
        raise HTTPException(404, "الطلب غير موجود")
    if a.get("status") != "pending":
        raise HTTPException(400, "تم اتخاذ القرار مسبقاً")
    if a.get("maker_id") == str(admin["_id"]):
        raise HTTPException(403, "لا يمكن لمنشئ العملية اعتمادها — مطلوب شخص ثانٍ (Maker–Checker)")
    await db.approvals.update_one({"_id": a["_id"]}, {"$set": {
        "status": "approved" if payload.approve else "rejected",
        "checker": admin.get("email"), "checker_id": str(admin["_id"]),
        "note": payload.note.strip(), "decided_at": now_iso()}})
    await db.audit_log.insert_one({
        "entity": "approval", "entity_id": approval_id,
        "action": "approval_approved" if payload.approve else "approval_rejected",
        "actor": admin.get("email"), "actor_id": str(admin["_id"]),
        "reason": payload.note.strip(), "before": {"status": "pending"},
        "after": {"status": "approved" if payload.approve else "rejected"}, "at": now_iso()})
    return {"ok": True, "status": "approved" if payload.approve else "rejected"}


@router.get("/approvals")
async def list_approvals(status: Optional[str] = None, admin: dict = Depends(require_admin)):
    f = {"status": status} if status else {}
    return serialize(await db.approvals.find(f).sort("created_at", -1).to_list(300))


# ---------------- sessions & account control ----------------
@router.get("/sessions")
async def sessions(active_only: bool = True, limit: int = 100,
                   admin: dict = Depends(require_admin)):
    f = {"revoked": {"$ne": True}} if active_only else {}
    docs = await db.sessions.find(f).sort("last_seen", -1).to_list(min(limit, 500))
    return serialize(docs)


class SessionActionIn(BaseModel):
    reason: str = Field(min_length=3)


@router.post("/users/{user_id}/force-logout")
async def force_logout(user_id: str, payload: SessionActionIn,
                       admin: dict = Depends(require_admin)):
    u = await db.users.find_one({"_id": oid(user_id)}, {"email": 1})
    if not u:
        raise HTTPException(404, "المستخدم غير موجود")
    stamp = now_iso()
    await db.users.update_one({"_id": oid(user_id)}, {"$set": {"force_logout_at": stamp}})
    await db.sessions.update_many({"user_id": user_id},
                                 {"$set": {"revoked": True, "revoked_at": stamp}})
    await db.audit_log.insert_one({
        "entity": "user", "entity_id": user_id, "action": "force_logout",
        "actor": admin.get("email"), "actor_id": str(admin["_id"]),
        "reason": payload.reason.strip(), "at": stamp})
    return {"ok": True, "force_logout_at": stamp}


class SuspendIn(BaseModel):
    suspend: bool
    reason: str = Field(min_length=3)


@router.post("/users/{user_id}/suspend")
async def suspend_user(user_id: str, payload: SuspendIn, admin: dict = Depends(require_admin)):
    u = await db.users.find_one({"_id": oid(user_id)}, {"email": 1, "status": 1, "role": 1})
    if not u:
        raise HTTPException(404, "المستخدم غير موجود")
    if u.get("role") == "super_admin":
        raise HTTPException(400, "لا يمكن تعليق حساب المدير العام")
    new_status = "suspended" if payload.suspend else "active"
    await db.users.update_one({"_id": oid(user_id)}, {"$set": {"status": new_status}})
    if payload.suspend:
        await db.users.update_one({"_id": oid(user_id)}, {"$set": {"force_logout_at": now_iso()}})
        await db.sessions.update_many({"user_id": user_id}, {"$set": {"revoked": True}})
    await db.audit_log.insert_one({
        "entity": "user", "entity_id": user_id, "action": f"user_{new_status}",
        "actor": admin.get("email"), "actor_id": str(admin["_id"]),
        "reason": payload.reason.strip(), "before": {"status": u.get("status")},
        "after": {"status": new_status}, "at": now_iso()})
    return {"ok": True, "status": new_status}


@router.get("/login-history")
async def login_history(email: Optional[str] = None, limit: int = 100,
                        admin: dict = Depends(require_admin)):
    f = {"email": email.lower()} if email else {}
    fails = serialize(await db.login_attempts.find(f).sort("updated_at", -1).to_list(100))
    logins = serialize(await db.sessions.find(f).sort("created_at", -1).to_list(min(limit, 300)))
    return {"sessions": logins, "failed_attempts": fails}


# ---------------- 2FA (TOTP) for admin accounts ----------------
def _totp_now(secret: str, drift: int = 0) -> str:
    import hashlib
    import hmac
    import struct
    import time
    key = base64.b32decode(secret, casefold=True)
    counter = int(time.time() // 30) + drift
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 1000000
    return f"{code:06d}"


@router.post("/2fa/setup")
async def twofa_setup(admin: dict = Depends(require_admin)):
    secret = base64.b32encode(os.urandom(20)).decode().rstrip("=")
    await db.users.update_one({"_id": admin["_id"]},
                              {"$set": {"twofa_secret": secret, "twofa_enabled": False}})
    label = f"Meraaj%20Network:{admin.get('email')}"
    return {"secret": secret,
            "otpauth_url": f"otpauth://totp/{label}?secret={secret}&issuer=Meraaj%20Network"}


class CodeIn(BaseModel):
    code: str


@router.post("/2fa/verify")
async def twofa_verify(payload: CodeIn, admin: dict = Depends(require_admin)):
    u = await db.users.find_one({"_id": admin["_id"]}, {"twofa_secret": 1})
    secret = (u or {}).get("twofa_secret")
    if not secret:
        raise HTTPException(400, "لم يتم إعداد المصادقة الثنائية")
    if payload.code not in (_totp_now(secret, d) for d in (-1, 0, 1)):
        raise HTTPException(400, "الرمز غير صحيح")
    await db.users.update_one({"_id": admin["_id"]}, {"$set": {"twofa_enabled": True}})
    await db.audit_log.insert_one({"entity": "user", "entity_id": str(admin["_id"]),
                                   "action": "2fa_enabled", "actor": admin.get("email"),
                                   "at": now_iso()})
    return {"ok": True, "enabled": True}


@router.post("/2fa/disable")
async def twofa_disable(payload: SessionActionIn, admin: dict = Depends(require_admin)):
    await db.users.update_one({"_id": admin["_id"]},
                              {"$set": {"twofa_enabled": False, "twofa_secret": None}})
    await db.audit_log.insert_one({"entity": "user", "entity_id": str(admin["_id"]),
                                   "action": "2fa_disabled", "actor": admin.get("email"),
                                   "reason": payload.reason.strip(), "at": now_iso()})
    return {"ok": True, "enabled": False}


@router.get("/my-permissions")
async def my_permissions(request: Request, user: dict = Depends(get_current_user)):
    acting = user.get("_acting_staff")
    return {"role": user.get("role"), "permissions": await user_permissions(user),
            "acting_staff": {"name": acting["name"], "email": acting["email"]} if acting else None,
            "office_id": str(user["_id"]),
            "twofa_enabled": bool(user.get("twofa_enabled"))}
