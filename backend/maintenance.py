"""Data retention & controlled cleanup (Maintenance).

Two classes of data:
  • PROTECTED  — audit, security, financial, orders, documents, webhook evidence.
                 These are NEVER deleted; they may only be ARCHIVED (append-only copy)
                 while the originals stay in place, immutable and retrievable.
  • OPERATIONAL — transient runtime rows (delivered webhook attempts, read notifications,
                 delivery logs, closed tasks, session rows). These may be cleaned up
                 according to an admin-configured retention period.

Every cleanup is preview-first, dry-run by default, type + date scoped, and always
recorded in the audit log.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from db import db, serialize, now_iso
from security import require_admin

router = APIRouter(prefix="/api/admin/maintenance", tags=["admin-maintenance"])

RETENTION_CHOICES = [30, 90, 180, 365]

# Cleanable operational data only. `extra` narrows the filter so nothing in-flight is lost.
CLEANABLE = {
    "webhook_attempts": {
        "ar": "محاولات Webhook المُسلَّمة", "collection": "rahal_outbox",
        "date_field": "created_at", "default_days": 90,
        "extra": {"status": "delivered"},
        "note": "الأحداث المُسلَّمة فقط — أي حدث فاشل أو معلّق يبقى كدليل للتحقيق.",
    },
    "inbound_log": {
        "ar": "سجل الطلبات الواردة من رحّال", "collection": "rahal_inbound_log",
        "date_field": "at", "default_days": 180, "extra": {"valid": True},
        "note": "الطلبات الصحيحة فقط — الطلبات المرفوضة تبقى كدليل أمني.",
    },
    "read_notifications": {
        "ar": "الإشعارات المقروءة", "collection": "notifications",
        "date_field": "at", "default_days": 90, "extra": {"read": True},
        "note": "الإشعارات غير المقروءة لا تُحذف.",
    },
    "notification_log": {
        "ar": "سجل تسليم الإشعارات", "collection": "notification_log",
        "date_field": "at", "default_days": 90, "extra": {"status": "delivered"},
        "note": "سجلات الفشل تبقى للتحليل.",
    },
    "closed_tasks": {
        "ar": "المهام المنتهية", "collection": "admin_tasks",
        "date_field": "created_at", "default_days": 365, "extra": {"status": "done"},
        "note": "المهام المفتوحة أو المتأخرة لا تُحذف.",
    },
    "revoked_sessions": {
        "ar": "الجلسات المُبطَلة", "collection": "sessions",
        "date_field": "created_at", "default_days": 90, "extra": {"revoked": True},
        "note": "سجل الدخول (login_history) محميّ ولا يُحذف.",
    },
    "sim_inbox": {
        "ar": "صندوق المستقبل التجريبي", "collection": "rahal_sim_inbox",
        "date_field": "received_at", "default_days": 30, "extra": {},
        "note": "بيانات محاكاة فقط.",
    },
}

# Never deletable. Archiving is allowed for the audit/security families.
PROTECTED = {
    "audit_log": {"ar": "سجل التدقيق", "archivable": True},
    "login_history": {"ar": "سجل محاولات الدخول", "archivable": True},
    "booking_events": {"ar": "سجل أحداث الطلبات", "archivable": True},
    "package_events": {"ar": "سجل أحداث البرامج", "archivable": True},
    "credit_events": {"ar": "سجل الائتمان", "archivable": True},
    "transactions": {"ar": "الحركات المالية", "archivable": False},
    "withdrawals": {"ar": "السحوبات", "archivable": False},
    "topups": {"ar": "الإيداعات", "archivable": False},
    "transfers": {"ar": "التحويلات", "archivable": False},
    "bookings": {"ar": "الطلبات والإلغاءات", "archivable": False},
    "traveler_documents": {"ar": "مستندات المسافرين", "archivable": False},
    "trip_passports": {"ar": "بيانات المسافرين", "archivable": False},
    "users": {"ar": "الحسابات", "archivable": False},
    "packages": {"ar": "البرامج", "archivable": False},
    "commission_events": {"ar": "سجل العمولات", "archivable": False},
    "backups": {"ar": "سجل النسخ الاحتياطي", "archivable": False},
}


async def _settings() -> dict:
    doc = await db.settings.find_one({"_id": "retention"}) or {}
    out = {k: int(doc.get(k) or v["default_days"]) for k, v in CLEANABLE.items()}
    return {"retention": out, "scheduled_enabled": bool(doc.get("scheduled_enabled")),
            "updated_by": doc.get("updated_by"), "updated_at": doc.get("updated_at")}


def _cutoff(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=int(days))).isoformat()


def _filter(kind: str, days: int, date_from: Optional[str], date_to: Optional[str]) -> dict:
    spec = CLEANABLE[kind]
    f = dict(spec["extra"])
    df = spec["date_field"]
    if date_from or date_to:
        rng = {}
        if date_from:
            rng["$gte"] = date_from
        if date_to:
            rng["$lte"] = date_to
        f[df] = rng
    else:
        f[df] = {"$lt": _cutoff(days)}
    return f


@router.get("/policies")
async def policies(admin: dict = Depends(require_admin)):
    s = await _settings()
    items = []
    for k, v in CLEANABLE.items():
        items.append({
            "kind": k, "label": v["ar"], "collection": v["collection"],
            "date_field": v["date_field"], "retention_days": s["retention"][k],
            "default_days": v["default_days"], "note": v["note"],
            "eligible_filter": {kk: vv for kk, vv in v["extra"].items()},
            "total_rows": await db[v["collection"]].count_documents({}),
            "eligible_now": await db[v["collection"]].count_documents(
                _filter(k, s["retention"][k], None, None)),
        })
    protected = []
    for c, v in PROTECTED.items():
        protected.append({"collection": c, "label": v["ar"], "archivable": v["archivable"],
                          "rows": await db[c].count_documents({})})
    return {"cleanable": items, "protected": protected,
            "retention_choices": RETENTION_CHOICES,
            "scheduled_enabled": s["scheduled_enabled"],
            "updated_by": s["updated_by"], "updated_at": s["updated_at"],
            "rules": [
                "لا يُحذف أي سجل أمني أو تدقيقي أو مالي أو طلب أو مستند أو دليل تحقيق.",
                "الحذف يقتصر على البيانات التشغيلية المؤقتة وحسب النوع والتاريخ.",
                "معاينة إلزامية قبل أي حذف، والوضع الافتراضي Dry-run.",
                "كل عملية تنظيف تُسجَّل في سجل التدقيق بمن نفّذها ومتى وماذا ولماذا.",
            ]}


class RetentionIn(BaseModel):
    retention: dict = {}
    scheduled_enabled: Optional[bool] = None
    reason: str = Field(min_length=3)


@router.post("/retention")
async def set_retention(payload: RetentionIn, admin: dict = Depends(require_admin)):
    bad = [k for k in payload.retention if k not in CLEANABLE]
    if bad:
        raise HTTPException(400, f"أنواع غير معروفة: {', '.join(bad)}")
    for k, v in payload.retention.items():
        if int(v) not in RETENTION_CHOICES:
            raise HTTPException(400, f"مدة احتفاظ غير مسموحة لـ{k} — المسموح: "
                                     f"{RETENTION_CHOICES}")
    before = await _settings()
    upd = {f"{k}": int(v) for k, v in payload.retention.items()}
    if payload.scheduled_enabled is not None:
        upd["scheduled_enabled"] = bool(payload.scheduled_enabled)
    upd.update({"updated_by": admin.get("email"), "updated_at": now_iso()})
    await db.settings.update_one({"_id": "retention"}, {"$set": upd}, upsert=True)
    await db.audit_log.insert_one({
        "entity": "settings", "entity_id": "retention", "action": "retention_updated",
        "actor": admin.get("email"), "actor_id": str(admin["_id"]),
        "reason": payload.reason.strip(),
        "before": before["retention"], "after": payload.retention, "at": now_iso()})
    return await _settings()


class PreviewIn(BaseModel):
    kind: str
    retention_days: Optional[int] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None


@router.post("/preview")
async def preview(payload: PreviewIn, admin: dict = Depends(require_admin)):
    """Mandatory preview: exact count + a sample of the rows that WOULD be removed."""
    if payload.kind in PROTECTED:
        raise HTTPException(400, "هذا النوع محميّ ولا يُحذف نهائياً")
    if payload.kind not in CLEANABLE:
        raise HTTPException(400, "نوع غير معروف")
    s = await _settings()
    days = payload.retention_days or s["retention"][payload.kind]
    spec = CLEANABLE[payload.kind]
    f = _filter(payload.kind, days, payload.date_from, payload.date_to)
    coll = db[spec["collection"]]
    count = await coll.count_documents(f)
    sample = serialize(await coll.find(f).sort(spec["date_field"], 1).to_list(10))
    oldest = await coll.find_one(f, sort=[(spec["date_field"], 1)])
    newest = await coll.find_one(f, sort=[(spec["date_field"], -1)])
    return {"kind": payload.kind, "label": spec["ar"], "collection": spec["collection"],
            "retention_days": days, "filter": {k: str(v) for k, v in f.items()},
            "matched": count, "total_rows": await coll.count_documents({}),
            "remaining_after": await coll.count_documents({}) - count,
            "oldest": (oldest or {}).get(spec["date_field"]),
            "newest": (newest or {}).get(spec["date_field"]),
            "sample": sample, "note": spec["note"],
            "generated_at": now_iso()}


class CleanupIn(BaseModel):
    kind: str
    retention_days: Optional[int] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    dry_run: bool = True
    confirm_phrase: str = ""
    reason: str = Field(min_length=5)


@router.post("/cleanup")
async def cleanup(payload: CleanupIn, admin: dict = Depends(require_admin)):
    """Dry-run by default. A real deletion additionally requires the literal confirmation
    phrase «أؤكد التنظيف» and is limited to non-protected operational data."""
    if payload.kind in PROTECTED:
        raise HTTPException(400, "هذا النوع محميّ ولا يُحذف نهائياً — يمكن أرشفته فقط")
    if payload.kind not in CLEANABLE:
        raise HTTPException(400, "نوع غير معروف")
    s = await _settings()
    days = payload.retention_days or s["retention"][payload.kind]
    spec = CLEANABLE[payload.kind]
    f = _filter(payload.kind, days, payload.date_from, payload.date_to)
    coll = db[spec["collection"]]
    matched = await coll.count_documents(f)
    if payload.dry_run:
        return {"dry_run": True, "kind": payload.kind, "matched": matched, "deleted": 0,
                "note": "معاينة فقط — لم يُحذف أي سجل."}
    if payload.confirm_phrase.strip() != "أؤكد التنظيف":
        raise HTTPException(400, "عبارة التأكيد غير مطابقة — اكتب: أؤكد التنظيف")
    res = await coll.delete_many(f)
    rec = {"kind": payload.kind, "label": spec["ar"], "collection": spec["collection"],
           "retention_days": days, "date_from": payload.date_from, "date_to": payload.date_to,
           "matched": matched, "deleted": res.deleted_count,
           "by": admin.get("email"), "reason": payload.reason.strip(),
           "source": "manual", "at": now_iso()}
    await db.maintenance_runs.insert_one(dict(rec))
    await db.audit_log.insert_one({
        "entity": "maintenance", "entity_id": payload.kind, "action": "cleanup_executed",
        "actor": admin.get("email"), "actor_id": str(admin["_id"]),
        "reason": payload.reason.strip(),
        "after": {"deleted": res.deleted_count, "collection": spec["collection"],
                  "retention_days": days}, "at": now_iso()})
    return serialize(rec)


class ArchiveIn(BaseModel):
    collection: str
    older_than_days: int = 365
    reason: str = Field(min_length=5)


@router.post("/archive")
async def archive(payload: ArchiveIn, admin: dict = Depends(require_admin)):
    """Append-only archive of protected audit/security rows. The ORIGINALS ARE KEPT — this
    only copies them into `<collection>_archive` so they stay retrievable and immutable."""
    meta = PROTECTED.get(payload.collection)
    if not meta:
        raise HTTPException(400, "هذه المجموعة ليست ضمن السجلات المحميّة")
    if not meta["archivable"]:
        raise HTTPException(400, "هذه المجموعة مالية/تشغيلية ولا تُؤرشف — تبقى كما هي")
    date_field = "at" if payload.collection != "sessions" else "created_at"
    cutoff = _cutoff(payload.older_than_days)
    src = db[payload.collection]
    dst = db[f"{payload.collection}_archive"]
    rows = await src.find({date_field: {"$lt": cutoff}}).to_list(20000)
    copied = 0
    for r in rows:
        exists = await dst.find_one({"_id": r["_id"]}, {"_id": 1})
        if not exists:
            await dst.insert_one({**r, "archived_at": now_iso(),
                                  "archived_by": admin.get("email")})
            copied += 1
    rec = {"collection": payload.collection, "label": meta["ar"],
           "older_than_days": payload.older_than_days, "matched": len(rows),
           "archived": copied, "originals_kept": True,
           "by": admin.get("email"), "reason": payload.reason.strip(), "at": now_iso()}
    await db.maintenance_runs.insert_one(dict(rec))
    await db.audit_log.insert_one({
        "entity": "maintenance", "entity_id": payload.collection, "action": "archived",
        "actor": admin.get("email"), "reason": payload.reason.strip(),
        "after": {"archived": copied, "originals_kept": True}, "at": now_iso()})
    return serialize(rec)


@router.get("/history")
async def history(limit: int = 50, admin: dict = Depends(require_admin)):
    return {"items": serialize(await db.maintenance_runs.find({})
                               .sort("at", -1).to_list(min(limit, 200))),
            "audit": serialize(await db.audit_log.find({"entity": "maintenance"})
                               .sort("at", -1).to_list(50))}


async def run_scheduled_cleanup() -> dict:
    """Used by the daily cron. Runs ONLY when an admin enabled scheduled cleanup, and only
    for eligible operational types with their configured retention."""
    s = await _settings()
    if not s["scheduled_enabled"]:
        return {"skipped": True, "reason": "التنظيف المجدول غير مُفعّل"}
    out = {}
    for kind, spec in CLEANABLE.items():
        f = _filter(kind, s["retention"][kind], None, None)
        res = await db[spec["collection"]].delete_many(f)
        out[kind] = res.deleted_count
    rec = {"kind": "scheduled", "label": "تنظيف مجدول", "results": out,
           "deleted": sum(out.values()), "by": "cron", "source": "scheduled",
           "reason": "تنظيف مجدول حسب مدة الاحتفاظ المعتمدة", "at": now_iso()}
    await db.maintenance_runs.insert_one(dict(rec))
    await db.audit_log.insert_one({
        "entity": "maintenance", "entity_id": "scheduled", "action": "cleanup_executed",
        "actor": "cron", "reason": rec["reason"], "after": out, "at": now_iso()})
    return serialize(rec)
