"""Batch 5 — Reports center, unified audit trail, settings/feature flags, system health
and encrypted database backup/restore. All additive.
"""
import csv
import hashlib
import io
import shutil
import tempfile
import uuid
import os
import subprocess
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from db import db, serialize, oid, now_iso, wallet_available, platform_pct
from security import require_admin

router = APIRouter(prefix="/api/admin", tags=["admin-enterprise"])

CCY = ("SAR", "USD")
BACKUP_DIR = os.environ.get("BACKUP_DIR", "/app/backups")
RETENTION = 7

ENV_LABEL = {"preview": "بيئة المعاينة (Emergent)", "test": "بيئة الاختبار (Test)",
             "live": "البيئة الحقيقية (Live)", "unknown": "غير معروفة"}

# Human labels for the audit log — shared by the audit screen AND the audit report,
# so both always read identically.
ENTITY_AR = {"settings": "الإعدادات", "booking": "طلب", "credit": "الائتمان",
             "commission": "العمولات", "package": "برنامج", "backup": "نسخة احتياطية",
             "integration": "التكامل", "user": "مستخدم", "org": "مؤسسة",
             "advertisement": "إعلان", "reconciliation": "تسوية", "maintenance": "صيانة",
             "withdrawal": "سحب", "role": "دور"}
ACTION_AR = {"settings_updated": "تحديث إعدادات", "backup_run": "تنفيذ نسخة احتياطية",
             "backup_uploaded": "استيراد نسخة احتياطية", "webhook_probe": "فحص وجهة رحّال",
             "webhook_target_updated": "تحديث وجهة رحّال",
             "outbox_manual_retry": "إعادة إرسال حدث", "user_created": "إنشاء مستخدم",
             "user_updated": "تعديل مستخدم", "password_reset": "إعادة كلمة المرور",
             "force_logout": "إخراج قسري", "org_created": "إنشاء مؤسسة",
             "org_updated": "تعديل مؤسسة", "credit_granted": "منح سقف ائتماني",
             "credit_frozen": "تجميد سقف", "ad_created": "إنشاء إعلان",
             "ad_updated": "تعديل إعلان", "ad_active": "اعتماد ونشر إعلان",
             "ad_pending_approval": "إرسال إعلان للاعتماد",
             "ad_paused": "إيقاف إعلان مؤقتاً", "ad_archived": "أرشفة إعلان",
             "ad_draft": "إرجاع إعلان لمسودة", "technical_view": "عرض تفاصيل تقنية",
             "ad_rejected": "رفض إعلان", "opening_balance_entry": "قيد افتتاحي موثّق"}


def _audit_label(v):
    from reporting import label as _lbl
    return _lbl(v)


def audit_human(v) -> str:
    """Readable one-line summary instead of a raw JSON dump."""
    from reporting import label as _lbl, FIELD_LABELS as _FL
    if v is None or v == {} or v == "":
        return "—"
    if isinstance(v, dict):
        return " • ".join(
            f"{_FL.get(k, k)}: {_lbl(x) if not isinstance(x, (dict, list)) else '…'}"
            for k, x in list(v.items())[:6])
    if isinstance(v, list):
        return "، ".join(str(_lbl(x)) for x in v[:6])
    return str(_lbl(v))


def _environment() -> str:
    """Explicit environment — read from ENVIRONMENT only, never inferred from data."""
    v = (os.environ.get("ENVIRONMENT") or "").strip().lower()
    return v if v in ("preview", "test", "live") else "unknown"


def _environment_rules() -> dict:
    env = _environment()
    return {
        "preview": {"working_db_restore": "يحتاج تأكيداً صريحاً + ALLOW_RESTORE=true",
                    "isolated_restore": "متاح"},
        "test": {"working_db_restore": "لا يتم تلقائياً — يحتاج تأكيداً صريحاً",
                 "isolated_restore": "متاح"},
        "live": {"working_db_restore": "محجوب نهائياً (HARD BLOCKED)",
                 "isolated_restore": "متاح للقراءة فقط"},
        "unknown": {"working_db_restore": "محجوب — البيئة غير محددة (اضبط ENVIRONMENT)",
                    "isolated_restore": "متاح"},
    }[env]

REPORTS = {
    "sales": "المبيعات والطلبات", "profit": "الأرباح والعمولات",
    "wallets": "المحافظ والأرصدة", "credit": "الانكشاف والسقوف الائتمانية",
    "programs": "البرامج والمقاعد", "travelers": "المسافرون والتأشيرات",
    "cancellations": "الإلغاءات والاستردادات", "withdrawals": "السحوبات والتسويات",
    "offices": "أداء المكاتب والبائعين", "users": "نشاط المستخدمين",
    "audit": "سجل التدقيق", "escrow": "الأموال المعلقة والمحررة",
    "fx": "مقارنة العملات وأسعار الصرف",
    "order_financials": "التفصيل المالي للطلبات (مدين/دائن/معلّق/محرَّر)",
}


def _rng(date_from, date_to, field: str = "created_at"):
    """Inclusive date range on the collection's own timestamp field.
    `date_to` covers the whole selected day."""
    f = {}
    if date_from:
        f["$gte"] = date_from
    if date_to:
        f["$lte"] = date_to + "T23:59:59.999999z"
    return {field: f} if f else {}


# Reports that show CURRENT state (balances, limits, exposure) rather than dated rows.
# A date range cannot apply to them, so they are flagged instead of silently returning
# rows that fall outside the selected period.
SNAPSHOT_REPORTS = {"wallets", "credit", "offices", "fx"}


async def _run(report: str, date_from: Optional[str], date_to: Optional[str],
               currency: Optional[str], office_id: Optional[str]) -> dict:
    rng = _rng(date_from, date_to)
    base = dict(rng)
    if currency in CCY:
        base["currency"] = currency

    if report in ("sales", "profit", "escrow", "cancellations"):
        f = dict(base)
        if office_id:
            f["$or"] = [{"buyer_id": office_id}, {"seller_id": office_id}]
        if report == "cancellations":
            f["status"] = "cancelled"
        docs = await db.bookings.find(f).sort("created_at", -1).to_list(5000)
        if report == "profit":
            cols = ["التاريخ", "البرنامج", "المشتري", "البائع", "عمولة المشتري",
                    "عمولة المنصة", "أرباح المنصة", "عمولة المسوّق", "العملة"]
            rows = [[d.get("created_at", "")[:10], d.get("package_title"), d.get("buyer_office_name"),
                     d.get("seller_office_name"), d.get("buyer_commission_total", 0),
                     d.get("platform_fee", 0), d.get("platform_profit", 0),
                     d.get("marketer_commission", 0), d.get("currency")] for d in docs]
        else:
            cols = ["التاريخ", "البرنامج", "المشتري", "البائع", "المقاعد", "المبلغ",
                    "صافي البائع", "الحالة", "قرار البائع", "العملة"]
            rows = [[d.get("created_at", "")[:10], d.get("package_title"), d.get("buyer_office_name"),
                     d.get("seller_office_name"), d.get("seats"), d.get("amount_charged", 0),
                     d.get("net_cost_total", 0), d.get("status"),
                     d.get("approval_status") or "legacy", d.get("currency")] for d in docs]
        return {"columns": cols, "rows": rows}

    if report == "order_financials":
        # READ-ONLY: reuses the existing statement helper, no formula or balance is touched.
        from finance import booking_financials
        f = dict(base)
        if office_id:
            f["$or"] = [{"buyer_id": office_id}, {"seller_id": office_id}]
        docs = await db.bookings.find(f).sort("created_at", -1).to_list(2000)
        cols = ["التاريخ", "الطلب", "البرنامج", "المشتري", "البائع", "مدين (خصم)",
                "دائن (استرداد)", "المدفوع", "المعلّق", "المحرَّر", "المسترد",
                "المستحق على المشتري", "المستحق للبائع", "عمولة المنصة", "صافي المنصة",
                "المحوَّل", "المتبقي", "مرجع معراج", "مرجع رحّال", "الفرق مع رحّال",
                "حالة المطابقة", "سعر الصرف", "الحالة", "العملة"]
        rows = []
        fx = float((await db.settings.find_one({"_id": "system"}) or {})
                   .get("currencies", {}).get("fx_rate_sar_per_usd") or 3.75)
        for d in docs:
            ref = str(d["_id"])
            txns = await db.transactions.find({"ref": ref}).to_list(300)
            fin = booking_financials(d, txns)
            debit = round(sum(abs(float(t.get("amount") or 0)) for t in txns
                              if float(t.get("amount") or 0) < 0), 2)
            credit = round(sum(float(t.get("amount") or 0) for t in txns
                               if float(t.get("amount") or 0) > 0), 2)
            rahal_ref = d.get("rahal_ref") or d.get("rahal_booking_ref") or "—"
            sent = None
            ev = await db.rahal_outbox.find_one({"ref": ref, "event": {"$regex": "settle|cancel"}})
            if ev:
                sent = ((ev.get("payload") or {}).get("data") or {}).get("settlement_amount")
            gap = (round(float(sent) - fin["released"], 2) if sent is not None else 0.0)
            state = ("لا يوجد حدث تسوية مُرسَل" if sent is None
                     else "مطابق" if abs(gap) < 0.01 else "فرق يحتاج مراجعة")
            rows.append([d.get("created_at", "")[:10], ref[-6:], d.get("package_title"),
                         d.get("buyer_office_name"), d.get("seller_office_name"),
                         debit, credit, fin["paid"], fin["pending"], fin["released"],
                         fin["refunded"], fin["due_from_buyer"], fin["due_to_seller"],
                         fin["platform_commission"], fin["platform_net"],
                         fin["transferred"], fin["remaining"], ref[-6:], rahal_ref, gap,
                         state, fx, fin["status"], fin["currency"]])
        # Totals section at the bottom, kept STRICTLY separate per currency and summed from
        # the same read-only booking_financials figures above (no recalculation).
        for c in CCY:
            cur_rows = [r for r in rows if r[23] == c]
            if not cur_rows:
                continue

            def col(i):
                return round(sum(float(r[i] or 0) for r in cur_rows), 2)
            rows.append(["—", f"الإجمالي {c}", f"عدد الطلبات: {len(cur_rows)}", "", ""]
                        + [col(i) for i in range(5, 17)]
                        + ["—", "—", col(19), "—", fx, "إجمالي", c])
        return {"columns": cols, "rows": rows}

    if report == "wallets":
        users = await db.users.find({"role": {"$in": ["office", "individual"]}}).to_list(3000)
        cols = ["الحساب", "النوع", "متاح SAR", "معلّق SAR", "متاح USD", "معلّق USD", "الحالة"]
        rows = []
        for u in users:
            w = u.get("wallet") or {}
            rows.append([u.get("office_name") or u.get("email"), u.get("role"),
                         round(float((w.get("SAR") or {}).get("available") or 0), 2),
                         round(float((w.get("SAR") or {}).get("pending") or 0), 2),
                         round(float((w.get("USD") or {}).get("available") or 0), 2),
                         round(float((w.get("USD") or {}).get("pending") or 0), 2),
                         u.get("status")])
        return {"columns": cols, "rows": rows}

    if report == "credit":
        cols = ["المكتب", "العملة", "السقف", "الرصيد", "المستخدم", "المتاح", "الحالة"]
        rows = []
        async for l in db.credit_limits.find({}):
            u = await db.users.find_one({"_id": oid(l["office_id"])}, {"office_name": 1, "wallet": 1})
            if not u:
                continue
            avail = wallet_available(u.get("wallet") or {}, l["currency"])
            used = max(0.0, -avail)
            rows.append([u.get("office_name"), l["currency"], l.get("limit", 0),
                         round(avail, 2), round(used, 2),
                         round(max(0.0, float(l.get("limit") or 0) - used), 2),
                         l.get("status", "active")])
        return {"columns": cols, "rows": rows}

    if report == "programs":
        pkgs = await db.packages.find(dict(rng)).sort("created_at", -1).to_list(3000)
        cols = ["البرنامج", "المكتب", "المصدر", "الانطلاق", "السعر", "مخصص", "مباع", "متبقٍ", "الحالة", "العملة"]
        rows = []
        for p in pkgs:
            pid = str(p["_id"])
            sold = 0
            async for r in db.bookings.aggregate([
                    {"$match": {"package_id": pid, "status": {"$ne": "cancelled"}}},
                    {"$group": {"_id": None, "s": {"$sum": "$seats"}}}]):
                sold = int(r["s"] or 0)
            alloc = int(p.get("total_seats") or 0)
            rows.append([p.get("title"), p.get("seller_office_name"),
                         "رحّال" if p.get("source") == "rahal" else "معراج",
                         p.get("departure_date"), p.get("final_sale_price"), alloc, sold,
                         max(0, alloc - sold), p.get("status"), p.get("currency")])
        return {"columns": cols, "rows": rows}

    if report == "travelers":
        cols = ["المسافر", "رقم الجواز", "الفئة", "التأشيرة", "البرنامج", "الطلب", "الانطلاق"]
        rows = []
        for b in await db.bookings.find(dict(rng), {"registrants": 1, "package_title": 1, "departure_date": 1}).to_list(3000):
            for r in b.get("registrants") or []:
                rows.append([r.get("name"), r.get("passport_no"), r.get("category") or "adult",
                             r.get("visa_no") or "—", b.get("package_title"), str(b["_id"])[-6:],
                             b.get("departure_date")])
        return {"columns": cols, "rows": rows}

    if report == "withdrawals":
        docs = await db.withdrawals.find(dict(base)).sort("created_at", -1).to_list(3000)
        cols = ["التاريخ", "المكتب", "المبلغ", "العملة", "الطريقة", "الحالة", "المرحلة", "مرجع الحوالة"]
        rows = [[d.get("created_at", "")[:10], d.get("office_name"), d.get("amount"),
                 d.get("currency"), d.get("method"), d.get("status"),
                 d.get("stage") or "—", d.get("bank_reference") or "—"] for d in docs]
        return {"columns": cols, "rows": rows}

    if report == "offices":
        cols = ["المكتب", "طلبات كمشتري", "طلبات كبائع", "إجمالي المبيعات SAR",
                "إجمالي المبيعات USD", "نزاعات", "الحالة"]
        rows = []
        async for u in db.users.find({"role": "office"}, {"office_name": 1, "status": 1}):
            uid = str(u["_id"])
            as_buyer = await db.bookings.count_documents({"buyer_id": uid})
            as_seller = await db.bookings.count_documents({"seller_id": uid})
            tot = {"SAR": 0.0, "USD": 0.0}
            async for r in db.bookings.aggregate([{"$match": {"seller_id": uid}},
                                                  {"$group": {"_id": "$currency",
                                                              "t": {"$sum": "$amount_charged"}}}]):
                if r["_id"] in tot:
                    tot[r["_id"]] = round(r["t"], 2)
            disputes = await db.bookings.count_documents({"dispute.status": "open",
                                                          "$or": [{"buyer_id": uid}, {"seller_id": uid}]})
            if as_buyer or as_seller:
                rows.append([u.get("office_name"), as_buyer, as_seller, tot["SAR"], tot["USD"],
                             disputes, u.get("status")])
        return {"columns": cols, "rows": rows}

    if report == "users":
        cols = ["البريد", "الاسم/المكتب", "النوع", "الحالة", "تاريخ الإنشاء", "آخر جلسة"]
        rows = []
        for u in await db.users.find(dict(rng), {"email": 1, "office_name": 1, "role": 1, "status": 1, "created_at": 1}).sort("created_at", -1).to_list(3000):
            s = await db.sessions.find_one({"user_id": str(u["_id"])}, sort=[("created_at", -1)])
            rows.append([u.get("email"), u.get("office_name"), u.get("role"), u.get("status"),
                         str(u.get("created_at") or "")[:10],
                         str((s or {}).get("created_at") or "—")[:16]])
        return {"columns": cols, "rows": rows}

    if report == "audit":
        cols = ["التاريخ", "الكيان", "الإجراء", "المنفّذ", "السبب", "قبل", "بعد"]
        rows = []
        f = _rng(date_from, date_to, "at")
        for a in await db.audit_log.find(f).sort("at", -1).to_list(3000):
            rows.append([str(a.get("at"))[:19],
                         ENTITY_AR.get(a.get("entity"), a.get("entity")),
                         ACTION_AR.get(a.get("action"), _audit_label(a.get("action"))),
                         a.get("actor"), a.get("reason") or "",
                         audit_human(a.get("before")), audit_human(a.get("after"))])
        return {"columns": cols, "rows": rows}

    if report == "fx":
        cols = ["العملة", "إجمالي المبيعات", "عمولة المنصة", "المحافظ (إجمالي)", "عدد الطلبات"]
        rows = []
        for c in CCY:
            g = p = 0.0
            n = 0
            async for r in db.bookings.aggregate([{"$match": {**rng, "currency": c}},
                                                  {"$group": {"_id": None,
                                                              "g": {"$sum": "$amount_charged"},
                                                              "p": {"$sum": "$platform_fee"},
                                                              "n": {"$sum": 1}}}]):
                g, p, n = round(r["g"], 2), round(r["p"], 2), r["n"]
            wtot = 0.0
            async for u in db.users.find({"role": {"$in": ["office", "individual"]}}, {"wallet": 1}):
                wtot += float(((u.get("wallet") or {}).get(c) or {}).get("total") or 0)
            rows.append([c, g, p, round(wtot, 2), n])
        return {"columns": cols, "rows": rows}

    raise HTTPException(400, "تقرير غير معروف")


@router.get("/reports")
async def report_catalog(admin: dict = Depends(require_admin)):
    saved = serialize(await db.saved_reports.find({}).sort("created_at", -1).to_list(100))
    return {"reports": REPORTS, "saved": saved}


class RunIn(BaseModel):
    report: str
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    currency: Optional[str] = None
    office_id: Optional[str] = None


@router.post("/reports/run")
async def run_report(payload: RunIn, admin: dict = Depends(require_admin)):
    """Screen dataset — the SAME builder every exporter uses, so figures can never differ."""
    from reporting import build_dataset, summary_rows
    ds = await build_dataset(payload.report, payload.model_dump(exclude={"report"}))
    return {**ds, "rows": ds["rows"][:500], "summary": summary_rows(ds),
            "truncated": ds["row_count"] > 500}


@router.post("/reports/export")
async def export_report(payload: RunIn, admin: dict = Depends(require_admin)):
    """CSV data export — same dataset/filters/labels as the screen (reporting.build_dataset)."""
    from reporting import build_dataset, to_csv
    ds = await build_dataset(payload.report, payload.model_dump(exclude={"report"}))
    await db.report_exports.insert_one({"report": payload.report, "rows": ds["row_count"],
                                        "format": "csv", "by": admin.get("email"),
                                        "at": now_iso()})
    return StreamingResponse(iter([to_csv(ds)]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition":
                                      f'attachment; filename="meraaj-{payload.report}.csv"'})


@router.post("/reports/export-xlsx")
async def export_report_xlsx(payload: RunIn, admin: dict = Depends(require_admin)):
    """Real Excel workbook (summary + details + data dictionary) from the same dataset."""
    from reporting import build_dataset, to_xlsx
    ds = await build_dataset(payload.report, payload.model_dump(exclude={"report"}))
    data = to_xlsx(ds)
    await db.report_exports.insert_one({"report": payload.report, "rows": ds["row_count"],
                                        "format": "xlsx", "by": admin.get("email"),
                                        "at": now_iso()})
    return StreamingResponse(
        iter([data]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition":
                 f'attachment; filename="meraaj-{payload.report}.xlsx"'})


@router.post("/reports/export-pdf")
async def export_report_pdf(payload: RunIn, admin: dict = Depends(require_admin)):
    """Official Arabic RTL PDF from the same dataset (shaped + bidi ordered)."""
    from reporting import build_dataset, summary_rows
    from pdfgen import build_report_pdf
    ds = await build_dataset(payload.report, payload.model_dump(exclude={"report"}))
    ds["summary"] = summary_rows(ds)
    ds["issued_by"] = admin.get("email")
    pdf = build_report_pdf(ds)
    await db.report_exports.insert_one({"report": payload.report, "rows": ds["row_count"],
                                        "format": "pdf", "by": admin.get("email"),
                                        "at": now_iso()})
    return StreamingResponse(iter([pdf]), media_type="application/pdf",
                             headers={"Content-Disposition":
                                      f'attachment; filename="meraaj-{payload.report}.pdf"'})


class SaveIn(BaseModel):
    name: str
    report: str
    filters: dict = {}


@router.post("/reports/save")
async def save_report(payload: SaveIn, admin: dict = Depends(require_admin)):
    rec = {**payload.model_dump(), "by": admin.get("email"), "created_at": now_iso()}
    res = await db.saved_reports.insert_one(rec)
    rec["_id"] = res.inserted_id
    return serialize(rec)


# ---------------- unified audit trail ----------------
@router.get("/audit")
async def audit_trail(entity: Optional[str] = None, actor: Optional[str] = None,
                      q: Optional[str] = None, limit: int = 100,
                      admin: dict = Depends(require_admin)):
    """Merges the immutable audit sources into one chronological view."""
    out = []
    f = {}
    if entity:
        f["entity"] = entity
    if actor:
        f["actor"] = {"$regex": actor, "$options": "i"}
    for a in await db.audit_log.find(f).sort("at", -1).to_list(limit):
        out.append({"source": "audit_log", "at": a.get("at"), "entity": a.get("entity"),
                    "entity_id": a.get("entity_id"), "action": a.get("action"),
                    "actor": a.get("actor"), "reason": a.get("reason"),
                    "before": a.get("before"), "after": a.get("after")})
    if not entity or entity == "booking":
        for e in await db.booking_events.find({}).sort("at", -1).to_list(limit):
            out.append({"source": "booking_events", "at": e.get("at"), "entity": "booking",
                        "entity_id": e.get("booking_id"), "action": e.get("event"),
                        "actor": e.get("actor_type"), "reason": e.get("reason"),
                        "before": None, "after": e.get("meta")})
    for coll, ent, act_field in (("credit_events", "credit", "action"),
                                 ("commission_events", "commission", "action"),
                                 ("package_events", "package", "action")):
        if entity and entity != ent:
            continue
        for e in await db[coll].find({}).sort("at", -1).to_list(limit):
            out.append({"source": coll, "at": e.get("at"), "entity": ent,
                        "entity_id": e.get("office_id") or e.get("rule_id") or e.get("package_id"),
                        "action": e.get(act_field), "actor": e.get("by") or e.get("actor"),
                        "reason": e.get("reason"), "before": e.get("before"),
                        "after": e.get("after")})
    if q:
        ql = q.lower()
        out = [x for x in out if ql in str(x).lower()]
    if actor:
        al = actor.lower()
        out = [x for x in out if al in str(x.get("actor") or "").lower()]
    out.sort(key=lambda x: str(x.get("at") or ""), reverse=True)
    items = []
    for x in out[:limit]:
        items.append({**x,
                      "entity_label": ENTITY_AR.get(x.get("entity"), x.get("entity")),
                      "action_label": ACTION_AR.get(x.get("action"), _audit_label(x.get("action"))),
                      "before_text": audit_human(x.get("before")),
                      "after_text": audit_human(x.get("after")),
                      "technical": {"before": x.get("before"), "after": x.get("after")}})
    return {"items": items, "total": len(out)}


@router.get("/anomalies")
async def anomalies(admin: dict = Depends(require_admin)):
    """Simple abnormal-activity detection: repeated identical bookings, high-value spikes,
    repeated failed logins and undelivered integration bursts."""
    out = []
    async for r in db.bookings.aggregate([
            {"$group": {"_id": {"b": "$buyer_id", "p": "$package_id", "s": "$seats"},
                        "n": {"$sum": 1}}},
            {"$match": {"n": {"$gte": 3}}}, {"$sort": {"n": -1}}, {"$limit": 10}]):
        out.append({"type": "duplicate_bookings", "level": "warning",
                    "message": f"{r['n']} حجوزات متطابقة (نفس المشتري/البرنامج/المقاعد)"})
    for a in await db.login_attempts.find({"count": {"$gte": 3}}).to_list(10):
        out.append({"type": "failed_logins", "level": "warning",
                    "message": f"{a.get('count')} محاولات دخول فاشلة لـ {a.get('email')}"})
    und = await db.rahal_outbox.count_documents({"status": {"$in": ["pending", "failed"]}})
    if und > 20:
        out.append({"type": "integration_burst", "level": "critical",
                    "message": f"{und} حدثاً غير مُسلَّم إلى رحّال"})
    big = await db.bookings.find({"amount_charged": {"$gte": 100000}},
                                 {"package_title": 1, "amount_charged": 1, "currency": 1}
                                 ).sort("amount_charged", -1).to_list(5)
    for b in big:
        out.append({"type": "high_value", "level": "info",
                    "message": f"عملية مرتفعة: {b.get('package_title')} — {b.get('amount_charged')} {b.get('currency')}"})
    return {"items": out, "total": len(out)}


# ---------------- settings & feature flags ----------------
DEFAULT_SETTINGS = {
    "currencies": {"base": "USD", "supported": ["SAR", "USD"], "fx_rate_sar_per_usd": 3.75},
    "commission": {"platform_pct_default": None},
    "order_flow": {"statuses": ["blue", "yellow", "green", "cancelled"],
                   "transitions": {"blue": ["yellow", "cancelled"],
                                   "yellow": ["green", "cancelled"], "green": [], "cancelled": []},
                   "approval_timeout_hours": None},
    "reasons": {"rejection": ["مقاعد غير متاحة", "بيانات ناقصة", "سعر غير صحيح", "أخرى"],
                "cancellation": ["طلب العميل", "عدم اكتمال المستندات", "قرار إداري", "أخرى"]},
    "documents": {"per_file_mb": 10, "per_batch_mb": 20,
                  "types": ["passport", "visa", "ticket", "authorization", "receipt", "voucher"]},
    "credit": {"max_limit_sar": 100000, "max_limit_usd": 30000,
               "alert_thresholds": [70, 90, 100]},
    "funds_release": {"stages": ["visa_issued", "dispatched", "settled"]},
    "numbering": {"booking_prefix": "MRJ-B", "voucher_prefix": "MRJ-V", "next_seq": 1},
    "locale": {"language": "ar", "direction": "rtl", "timezone": "Asia/Riyadh"},
    "integrations": {"rahal_enabled": True, "email_enabled": False, "whatsapp_enabled": False},
    "feature_flags": {"orders_center": True, "finance_center": True, "commission_engine": True,
                      "credit_control": True, "programs_admin": True, "travelers_admin": True,
                      "rbac": True, "notifications": True, "reports": True, "backup": True,
                      "scanner_bridge": False},
}


SETTINGS_SCHEMA = {
    "currencies": {"label": "العملات", "desc": "العملة الأساسية والعملات المدعومة وسعر الصرف",
                   "fields": [
                       {"key": "base", "label": "العملة الأساسية", "type": "select",
                        "options": [["USD", "دولار أمريكي"], ["SAR", "ريال سعودي"]]},
                       {"key": "supported", "label": "العملات المدعومة", "type": "multiselect",
                        "options": [["SAR", "ريال سعودي"], ["USD", "دولار أمريكي"]]},
                       {"key": "fx_rate_sar_per_usd", "label": "سعر الصرف (ريال لكل دولار)",
                        "type": "number", "step": 0.01}]},
    "documents": {"label": "المستندات والمرفقات", "desc": "الحد الأقصى للحجم والأنواع المسموحة",
                  "fields": [
                      {"key": "per_file_mb", "label": "أقصى حجم للملف (ميجابايت)", "type": "number"},
                      {"key": "per_batch_mb", "label": "أقصى حجم للدفعة (ميجابايت)", "type": "number"},
                      {"key": "types", "label": "أنواع المستندات المسموحة", "type": "tags"}]},
    "credit": {"label": "الائتمان والسقوف", "desc": "أقصى سقف مسموح وحدود التنبيه",
               "fields": [
                   {"key": "max_limit_sar", "label": "أقصى سقف بالريال", "type": "number"},
                   {"key": "max_limit_usd", "label": "أقصى سقف بالدولار", "type": "number"},
                   {"key": "alert_thresholds", "label": "نِسَب التنبيه (%)", "type": "tags"}]},
    "locale": {"label": "اللغة والتوقيت", "desc": "اللغة والاتجاه والمنطقة الزمنية",
               "fields": [
                   {"key": "language", "label": "اللغة", "type": "select",
                    "options": [["ar", "العربية"], ["en", "الإنجليزية"]]},
                   {"key": "direction", "label": "اتجاه الواجهة", "type": "select",
                    "options": [["rtl", "من اليمين إلى اليسار"], ["ltr", "من اليسار إلى اليمين"]]},
                   {"key": "timezone", "label": "المنطقة الزمنية", "type": "select",
                    "options": [["Asia/Riyadh", "الرياض (+3)"], ["UTC", "التوقيت العالمي"]]}]},
    "numbering": {"label": "ترقيم المستندات", "desc": "بادئات أرقام الطلبات والسندات",
                  "fields": [
                      {"key": "booking_prefix", "label": "بادئة رقم الطلب", "type": "text"},
                      {"key": "voucher_prefix", "label": "بادئة رقم السند", "type": "text"},
                      {"key": "next_seq", "label": "الرقم التالي", "type": "number"}]},
    "order_flow": {"label": "دورة الطلب", "desc": "مراحل الطلب ومهلة موافقة البائع",
                   "fields": [
                       {"key": "approval_timeout_hours", "label": "مهلة موافقة البائع (ساعات)",
                        "type": "number"},
                       {"key": "statuses", "label": "مراحل الطلب (قراءة فقط)", "type": "tags",
                        "readonly": True}]},
    "funds_release": {"label": "تحرير الأموال", "desc": "شروط تحرير أموال البائع",
                      "fields": [{"key": "stages", "label": "مراحل التحرير", "type": "tags"}]},
    "reasons": {"label": "قوائم الأسباب", "desc": "أسباب الرفض والإلغاء المتاحة للمستخدمين",
                "fields": [
                    {"key": "rejection", "label": "أسباب الرفض", "type": "tags"},
                    {"key": "cancellation", "label": "أسباب الإلغاء", "type": "tags"}]},
    "integrations": {"label": "التكامل", "desc": "تشغيل/تعطيل قنوات التكامل — لا تُعرض أي أسرار",
                     "fields": [
                         {"key": "rahal_enabled", "label": "تكامل رحّال", "type": "switch"},
                         {"key": "email_enabled", "label": "البريد الإلكتروني الخارجي",
                          "type": "switch"},
                         {"key": "whatsapp_enabled", "label": "واتساب", "type": "switch"}],
                     "note": "المفاتيح والأسرار تُدار في متغيّرات البيئة ولا تظهر هنا إطلاقاً"},
    "commission": {"label": "العمولة الافتراضية", "desc": "نسبة المنصة الافتراضية (للعلم فقط)",
                   "fields": [{"key": "platform_pct_default", "label": "النسبة الافتراضية",
                               "type": "number", "readonly": True}]},
}

FLAG_LABELS = {
    "orders_center": ("مركز الطلبات", "سجل الطلبات وملف الطلب المالي والتشغيلي"),
    "finance_center": ("المركز المالي", "الدفتر والسحوبات والسندات والمطابقة"),
    "commission_engine": ("محرك العمولات", "قواعد العمولة والمعاينة والتجاوز"),
    "credit_control": ("الائتمان والسقوف", "منح السقوف ومراقبة الانكشاف"),
    "programs_admin": ("إدارة البرامج", "إنشاء وتعديل البرامج والمقاعد"),
    "travelers_admin": ("إدارة المسافرين", "المسافرون والمستندات والتأشيرات"),
    "rbac": ("الصلاحيات والأدوار", "المستخدمون والأدوار والفصل بين المهام"),
    "notifications": ("الإشعارات والمهام", "القوالب والفحص والمهام الإدارية"),
    "reports": ("التقارير", "مركز التقارير والتصدير"),
    "backup": ("النسخ الاحتياطي", "إنشاء واستيراد وفحص النسخ"),
    "scanner_bridge": ("الماسح الضوئي", "جسر الماسح على أجهزة المكاتب (غير مُفعَّل)"),
    "ads": ("الإعلانات والعروض", "إدارة الحملات الإعلانية والعروض الترويجية"),
}


@router.get("/settings/schema")
async def settings_schema(admin: dict = Depends(require_admin)):
    """Field-level schema so the admin UI renders real forms instead of raw JSON."""
    return {"sections": SETTINGS_SCHEMA, "flags": FLAG_LABELS,
            "note": ("JSON الخام مُستخدَم داخلياً فقط — كل إعداد يُحرَّر عبر حقل مخصّص، "
                     "والأسرار لا تُعرض في الواجهة.")}


@router.get("/settings")
async def get_settings(admin: dict = Depends(require_admin)):
    doc = await db.settings.find_one({"_id": "system"}) or {}
    merged = {**DEFAULT_SETTINGS,
              **{k: v for k, v in doc.items() if k != "_id" and not k.startswith("updated_")}}
    merged["commission"]["platform_pct_default"] = platform_pct()
    return {"settings": merged, "updated_at": doc.get("updated_at"),
            "updated_by": doc.get("updated_by")}


class SettingsIn(BaseModel):
    section: str
    values: dict
    reason: str = Field(min_length=3)


@router.post("/settings")
async def update_settings(payload: SettingsIn, admin: dict = Depends(require_admin)):
    if payload.section not in DEFAULT_SETTINGS:
        raise HTTPException(400, "قسم إعدادات غير معروف")
    doc = await db.settings.find_one({"_id": "system"}) or {}
    before = doc.get(payload.section, DEFAULT_SETTINGS[payload.section])
    await db.settings.update_one({"_id": "system"}, {"$set": {
        payload.section: payload.values, "updated_at": now_iso(),
        "updated_by": admin.get("email")}}, upsert=True)
    await db.audit_log.insert_one({
        "entity": "settings", "entity_id": payload.section, "action": "settings_updated",
        "actor": admin.get("email"), "actor_id": str(admin["_id"]),
        "reason": payload.reason.strip(), "before": before, "after": payload.values,
        "at": now_iso()})
    return {"ok": True, "section": payload.section, "values": payload.values}


@router.get("/system/health")
async def system_health(admin: dict = Depends(require_admin)):
    checks = []
    try:
        await db.command("ping")
        checks.append({"service": "MongoDB", "status": "ok"})
    except Exception as e:
        checks.append({"service": "MongoDB", "status": "fail", "error": str(e)[:200]})
    checks.append({"service": "Backend API", "status": "ok"})
    und = await db.rahal_outbox.count_documents({"status": {"$in": ["pending", "failed"]}})
    checks.append({"service": "تكامل رحّال (Outbox)",
                   "status": "warn" if und else "ok",
                   "detail": f"{und} حدث غير مُسلَّم"})
    st = os.statvfs("/app")
    free_gb = round((st.f_bavail * st.f_frsize) / (1024 ** 3), 2)
    checks.append({"service": "مساحة القرص", "status": "ok" if free_gb > 1 else "warn",
                   "detail": f"{free_gb} GB متاح"})
    last_backup = await db.backups.find_one({}, sort=[("at", -1)])
    checks.append({"service": "النسخ الاحتياطي",
                   "status": "ok" if last_backup else "warn",
                   "detail": f"آخر نسخة: {(last_backup or {}).get('at', 'لا يوجد')}"})
    counts = {c: await db[c].count_documents({}) for c in
              ("users", "bookings", "packages", "transactions", "audit_log", "notifications")}
    return {"checks": checks, "collections": counts, "generated_at": now_iso()}


@router.get("/system/test-data-report")
async def test_data_report(admin: dict = Depends(require_admin)):
    """Read-only classification of QA/test records vs real records in THIS database.
    Nothing is deleted; this exists so any cleanup decision is documented first."""
    qa_email = {"email": {"$regex": r"@qa-example\.com$", "$options": "i"}}
    qa_title = {"title": {"$regex": r"^TEST_"}}
    users_total = await db.users.count_documents({})
    users_qa = await db.users.count_documents(qa_email)
    pkgs_total = await db.packages.count_documents({})
    pkgs_qa = await db.packages.count_documents(qa_title)
    qa_ids = [str(u["_id"]) async for u in db.users.find(qa_email, {"_id": 1})]
    bookings_total = await db.bookings.count_documents({})
    bookings_qa = await db.bookings.count_documents(
        {"$or": [{"buyer_id": {"$in": qa_ids}}, {"seller_id": {"$in": qa_ids}}]})
    dup_titles = []
    async for r in db.packages.aggregate([
            {"$group": {"_id": "$title", "n": {"$sum": 1}}},
            {"$match": {"n": {"$gt": 1}}}, {"$sort": {"n": -1}}, {"$limit": 10}]):
        dup_titles.append({"title": r["_id"], "count": r["n"]})
    return {
        "database": os.environ["DB_NAME"],
        "environment": os.environ.get("ENVIRONMENT", "unknown"),
        "isolation_note": ("قاعدة بيانات هذه البيئة محلية ومنفصلة تمامًا عن قاعدتي Test و Live "
                           "على السيرفر (ملفات بيئة مختلفة لكل بيئة)."),
        "rows": [
            {"collection": "users", "total": users_total, "qa": users_qa,
             "real": users_total - users_qa, "rule": "البريد ينتهي بـ@qa-example.com"},
            {"collection": "packages", "total": pkgs_total, "qa": pkgs_qa,
             "real": pkgs_total - pkgs_qa, "rule": "العنوان يبدأ بـTEST_"},
            {"collection": "bookings", "total": bookings_total, "qa": bookings_qa,
             "real": bookings_total - bookings_qa, "rule": "المشتري أو البائع حساب QA"},
        ],
        "repeated_titles": dup_titles,
        "repetition_verdict": ("التكرار مقصود: كل تشغيل لمجموعة الاختبار يُنشئ مكتبًا وبرنامجًا "
                               "جديدين بمعرّفات فريدة — وليس تكرارًا مرضيًا في منطق النظام."),
        "deletion_policy": "لم يُحذف أي سجل. أي تنظيف يتم على Test فقط وبتقرير موثّق قبل/بعد.",
        "generated_at": now_iso(),
    }


# ---------------- backup & restore ----------------
def _passphrase() -> Optional[str]:
    return os.environ.get("BACKUP_PASSPHRASE")


@router.get("/backups")
async def list_backups(admin: dict = Depends(require_admin)):
    docs = serialize(await db.backups.find({}).sort("at", -1).to_list(100))
    drills = serialize(await db.backup_drills.find({}).sort("at", -1).to_list(20))
    files = []
    if os.path.isdir(BACKUP_DIR):
        for f in sorted(os.listdir(BACKUP_DIR), reverse=True):
            if f.startswith("meraaj-"):
                files.append({"file": f, "size": os.path.getsize(f"{BACKUP_DIR}/{f}")})
    last_ok = await db.backups.find_one({"result": "success"}, sort=[("at", -1)])
    schedule = {"cron": "0 22 * * *", "local_time": "01:00 بتوقيت الرياض (22:00 UTC)",
                "endpoint": "/api/cron/backup", "enabled": True,
                "source": ".emergent/crons.yml"}
    return {"items": docs, "retention": RETENTION,
            "encrypted": bool(_passphrase()),
            "cloud": _cloud_config(),
            "encryption": {"enabled": bool(_passphrase()),
                           "algorithm": "AES-256-CBC + PBKDF2 (openssl)",
                           "passphrase_source": "BACKUP_PASSPHRASE"},
            "schedule": schedule,
            "last_successful": {"file": (last_ok or {}).get("file"),
                                "at": (last_ok or {}).get("at"),
                                "size": (last_ok or {}).get("size")},
            "pruned_count": await db.backups.count_documents({"pruned": True}),
            "restore_enabled": os.environ.get("ALLOW_RESTORE") == "true",
            "restore_guards": ["ALLOW_RESTORE=true", "عبارة تأكيد حرفية: أؤكد الاستعادة",
                               "سبب إلزامي", "رفض قاطع على بيئة Live"],
            "environment": _environment(),
            "environment_label": ENV_LABEL.get(_environment(), "غير معروفة"),
            "environment_source": "متغيّر البيئة ENVIRONMENT",
            "environment_rules": _environment_rules(),
            "tools": {"mongodump": bool(shutil.which("mongodump")),
                      "mongorestore": bool(shutil.which("mongorestore")),
                      "openssl": bool(shutil.which("openssl")),
                      "note": ("mongodump/mongorestore يجب أن تكون مثبّتة داخل صورة الخادم "
                               "(حزمة mongodb-database-tools) وإلا تتعطّل النسخ والاستعادة.")},
            "files_on_disk": files,
            "files_imported": [{"file": r["file"], "size": r.get("size", 0)}
                               for r in docs if r.get("storage") == "gridfs"],
            "drills": drills,
            "dir": BACKUP_DIR}


class BackupIn(BaseModel):
    reason: str = Field(min_length=3)
    destination: str = "server"   # server | download | cloud | server_and_download


@router.post("/backups/run")
async def run_backup(payload: BackupIn, admin: dict = Depends(require_admin)):
    """Database-only backup (mongodump archive + gzip), encrypted with BACKUP_PASSPHRASE
    when configured. Keeps the newest RETENTION files.
    The chosen destination is recorded; `download`/`server_and_download` return a
    `download_url` the authorized user fetches through the browser (any computer/folder)."""
    dest = payload.destination
    if dest not in ("server", "download", "cloud", "server_and_download"):
        raise HTTPException(400, "وجهة غير مدعومة")
    if dest == "cloud" and not _cloud_config()["configured"]:
        raise HTTPException(400, _cloud_config()["note"])
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    dbname = os.environ["DB_NAME"]
    raw_path = f"{BACKUP_DIR}/meraaj-{dbname}-{stamp}.archive.gz"
    cmd = ["mongodump", f"--uri={os.environ['MONGO_URL']}", f"--db={dbname}",
           f"--archive={raw_path}", "--gzip"]
    tool = shutil.which("mongodump")
    if not tool:
        raise HTTPException(503,
                            "أداة mongodump غير مثبّتة في بيئة تشغيل الخادم — النسخ الاحتياطي "
                            "معطّل حتى تثبيت حزمة mongodb-database-tools في صورة الخادم "
                            "(Dockerfile.backend). لم يتم إنشاء أي ملف ولم تُلمس أي بيانات.")
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=600)
        if p.returncode != 0:
            raise RuntimeError(p.stderr.decode()[:300])
        final_path, encrypted = raw_path, False
        pw = _passphrase()
        if pw:
            enc_path = raw_path + ".enc"
            e = subprocess.run(["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-salt",
                                "-in", raw_path, "-out", enc_path, "-pass", f"pass:{pw}"],
                               capture_output=True, timeout=600)
            if e.returncode == 0:
                os.remove(raw_path)
                final_path, encrypted = enc_path, True
        size = os.path.getsize(final_path)
        check = _inspect(final_path)
        rec = {"file": os.path.basename(final_path), "path": final_path, "size": size,
               "encrypted": encrypted, "result": "success", "error": None,
               "source": "manual", "destination": dest,
               "integrity": "valid" if check["ok"] else "invalid",
               "sha256": check.get("sha256"),
               "by": admin.get("email"), "reason": payload.reason.strip(), "at": now_iso()}
    except Exception as e:
        rec = {"file": None, "path": None, "size": 0, "encrypted": False, "result": "failed",
               "error": str(e)[:300], "source": "manual", "destination": dest,
               "integrity": None, "by": admin.get("email"),
               "reason": payload.reason.strip(), "at": now_iso()}
    res = await db.backups.insert_one(rec)
    rec["_id"] = res.inserted_id
    await db.audit_log.insert_one({"entity": "backup", "entity_id": str(res.inserted_id),
                                   "action": "backup_run", "actor": admin.get("email"),
                                   "reason": payload.reason.strip(),
                                   "after": {"result": rec["result"], "file": rec["file"],
                                             "destination": dest,
                                             "integrity": rec.get("integrity"),
                                             "encrypted": rec.get("encrypted")},
                                   "at": now_iso()})
    # retention
    files = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith("meraaj-")], reverse=True)
    for old in files[RETENTION:]:
        try:
            os.remove(f"{BACKUP_DIR}/{old}")
            await db.backups.update_many({"file": old}, {"$set": {"pruned": True}})
        except Exception:
            pass
    if rec["result"] == "failed":
        raise HTTPException(500, f"فشل النسخ الاحتياطي: {rec['error']}")
    out = serialize(rec)
    out["destination_label"] = {
        "server": "حُفظت على سيرفر التطبيق",
        "download": "جاهزة للتنزيل إلى جهاز المستخدم",
        "cloud": "أُرسلت إلى التخزين السحابي المُهيَّأ",
        "server_and_download": "حُفظت على السيرفر وجاهزة للتنزيل",
    }[dest]
    if dest in ("download", "server_and_download"):
        out["download_url"] = f"/admin/backups/{rec['file']}/download"
    return out


def _cloud_config() -> dict:
    """Object-storage destination configuration. Nothing is implemented against a provider
    here — the destination is only offered once credentials are configured (Release B)."""
    provider = os.environ.get("BACKUP_CLOUD_PROVIDER", "").strip()
    bucket = os.environ.get("BACKUP_CLOUD_BUCKET", "").strip()
    key = os.environ.get("BACKUP_CLOUD_ACCESS_KEY", "").strip()
    configured = bool(provider and bucket and key)
    return {"configured": configured, "provider": provider or None, "bucket": bucket or None,
            "required_env": ["BACKUP_CLOUD_PROVIDER", "BACKUP_CLOUD_BUCKET",
                             "BACKUP_CLOUD_ACCESS_KEY", "BACKUP_CLOUD_SECRET_KEY",
                             "BACKUP_CLOUD_REGION"],
            "note": ("التخزين السحابي غير مُهيَّأ — أضيفوا مفاتيح التخزين في متغيّرات البيئة "
                     "ليصبح هذا الخيار متاحًا. لم يُفعَّل أي مزوّد تلقائيًا.")}


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _inspect(path: str) -> dict:
    """Encryption + integrity check WITHOUT restoring anything: decrypts to a temp file when
    encrypted, then confirms the payload is a real gzip mongodump archive."""
    encrypted = path.endswith(".enc")
    tmp = f"{BACKUP_DIR}/.inspect.tmp"
    try:
        if encrypted:
            pw = _passphrase()
            if not pw:
                return {"ok": False, "encrypted": True, "reason": "لا يوجد BACKUP_PASSPHRASE"}
            d = subprocess.run(["openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2",
                                "-in", path, "-out", tmp, "-pass", f"pass:{pw}"],
                               capture_output=True, timeout=600)
            if d.returncode != 0:
                return {"ok": False, "encrypted": True,
                        "reason": "فشل فك التشفير — الملف تالف أو مفتاح مختلف"}
            probe = tmp
        else:
            probe = path
        with open(probe, "rb") as fh:
            magic = fh.read(2)
        gz = magic == b"\x1f\x8b"
        return {"ok": gz, "encrypted": encrypted, "gzip_archive": gz,
                "size": os.path.getsize(path), "sha256": _sha256(path),
                "reason": None if gz else "المحتوى ليس أرشيف mongodump مضغوطاً"}
    except Exception as e:
        return {"ok": False, "encrypted": encrypted, "reason": str(e)[:200]}
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


@router.get("/backups/storage")
async def storage_options(admin: dict = Depends(require_admin)):
    """Destinations offered when creating a backup. Shown BEFORE confirmation."""
    cloud = _cloud_config()
    return {"destinations": [
        {"key": "download", "ar": "تنزيل إلى جهاز المستخدم المصرَّح له",
         "available": True,
         "note": ("يُنشأ الملف المشفّر ثم يُنزَّل عبر المتصفح، ويختار المستخدم المجلد أو "
                  "القرص أو الوسائط الخارجية من نافذة التنزيل. لا يُكتب أي ملف على جهاز "
                  "المستخدم بدون إجراء تنزيل صريح، ولا يقتصر التنزيل على جهاز الإدارة.")},
        {"key": "server", "ar": "حفظ على سيرفر التطبيق", "available": True,
         "note": f"يُحفظ في {BACKUP_DIR} على السيرفر نفسه ويخضع لسياسة الاحتفاظ."},
        {"key": "cloud", "ar": "حفظ في التخزين السحابي المُهيَّأ",
         "available": cloud["configured"], "note": cloud["note"]},
        {"key": "server_and_download", "ar": "حفظ على السيرفر + تنزيل نسخة",
         "available": True, "note": "الوجهتان معًا في عملية واحدة."},
    ], "cloud": cloud, "encrypted": bool(_passphrase()), "retention": RETENTION,
        "environment": os.environ.get("ENVIRONMENT", "unknown")}


async def _materialize(filename: str) -> Optional[str]:
    """Returns a readable local path for a backup file: the server copy when it exists,
    otherwise a temporary copy pulled out of GridFS (caller deletes it)."""
    safe = os.path.basename(filename)
    disk = f"{BACKUP_DIR}/{safe}"
    if os.path.exists(disk):
        return disk
    rec = await db.backups.find_one({"file": safe, "storage": "gridfs"})
    if not rec:
        return None
    tmp = f"{tempfile.gettempdir()}/{uuid.uuid4().hex}-{safe}"
    with open(tmp, "wb") as out:
        await _gridfs().download_to_stream(oid(rec["gridfs_id"]), out)
    return tmp


@router.get("/backups/{filename}/download")
async def download_backup(filename: str, admin: dict = Depends(require_admin)):
    """Streams the ENCRYPTED archive to the authorized user's browser so they can store it
    on any computer, folder or external drive through the normal download dialog."""
    safe = os.path.basename(filename)
    if not safe.startswith("meraaj-"):
        raise HTTPException(404, "ملف النسخة غير موجود")
    disk = f"{BACKUP_DIR}/{safe}"
    on_disk = os.path.exists(disk)
    rec = await db.backups.find_one({"file": safe})
    if not on_disk and not (rec and rec.get("storage") == "gridfs"):
        raise HTTPException(404, "ملف النسخة غير موجود")
    size = os.path.getsize(disk) if on_disk else int(rec.get("size") or 0)
    await db.backups.update_many({"file": safe}, {"$set": {
        "last_downloaded_by": admin.get("email"), "last_downloaded_at": now_iso()}})
    await db.audit_log.insert_one({
        "entity": "backup", "entity_id": safe, "action": "backup_downloaded",
        "actor": admin.get("email"), "actor_id": str(admin["_id"]),
        "after": {"file": safe, "size": size, "destination": "download",
                  "source_storage": "server" if on_disk else "gridfs",
                  "encrypted": safe.endswith(".enc")}, "at": now_iso()})

    async def stream_gridfs():
        gout = await _gridfs().open_download_stream(oid(rec["gridfs_id"]))
        while True:
            chunk = await gout.readchunk()
            if not chunk:
                break
            yield chunk

    def stream_disk():
        with open(disk, "rb") as fh:
            while True:
                chunk = fh.read(1024 * 512)
                if not chunk:
                    break
                yield chunk

    return StreamingResponse(stream_disk() if on_disk else stream_gridfs(),
                             media_type="application/octet-stream", headers={
                                 "Content-Disposition": f'attachment; filename="{safe}"',
                                 "Content-Length": str(size)})


def _gridfs():
    """Durable storage for IMPORTED backup archives: kept in MongoDB GridFS instead of the
    app pod's disk, so an uploaded file survives redeploys and stays retrievable."""
    from motor.motor_asyncio import AsyncIOMotorGridFSBucket
    return AsyncIOMotorGridFSBucket(db, bucket_name="backup_files")


@router.post("/backups/upload")
async def upload_backup(file: UploadFile = File(...), reason: str = Form(...),
                        admin: dict = Depends(require_admin)):
    """Imports an encrypted backup file. The file is validated (encryption + integrity)
    BEFORE it is accepted; a file that fails validation is discarded and never stored.
    Accepted files are stored in GridFS (not on the pod disk)."""
    if len(reason.strip()) < 3:
        raise HTTPException(422, "السبب إلزامي")
    name = os.path.basename(file.filename or "")
    if not (name.endswith(".archive.gz") or name.endswith(".archive.gz.enc")):
        raise HTTPException(400, "امتداد غير مدعوم — المسموح .archive.gz أو .archive.gz.enc")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    stored = name if name.startswith("meraaj-") else f"meraaj-uploaded-{stamp}-{name}"
    scratch = f"{tempfile.gettempdir()}/{uuid.uuid4().hex}-{stored}"
    size = 0
    try:
        with open(scratch, "wb") as out:
            while True:
                chunk = await file.read(1024 * 512)
                if not chunk:
                    break
                size += len(chunk)
                out.write(chunk)
        check = _inspect(scratch)
        if not check["ok"]:
            await db.audit_log.insert_one({
                "entity": "backup", "entity_id": stored, "action": "backup_upload_rejected",
                "actor": admin.get("email"), "reason": reason.strip(),
                "after": {"error": check["reason"], "file": stored, "size": size},
                "at": now_iso()})
            raise HTTPException(400, f"الملف مرفوض ولم يُخزَّن — {check['reason']} "
                                     f"(الاسم: {stored}، الحجم: {round(size / 1048576, 2)} "
                                     f"ميجابايت). ارفع ملف نسخة صالحاً أنشأه النظام "
                                     f"بامتداد .archive.gz أو .archive.gz.enc، وتأكد أنه "
                                     f"مشفّر بنفس مفتاح BACKUP_PASSPHRASE.")
        with open(scratch, "rb") as fh:
            gid = await _gridfs().upload_from_stream(stored, fh, metadata={
                "by": admin.get("email"), "at": now_iso(), "sha256": check["sha256"]})
    finally:
        try:
            os.remove(scratch)
        except OSError:
            pass
    rec = {"file": stored, "path": None, "gridfs_id": str(gid), "storage": "gridfs",
           "size": size, "encrypted": check["encrypted"],
           "result": "success", "error": None, "source": "uploaded", "destination": "gridfs",
           "integrity": "valid", "sha256": check["sha256"],
           "by": admin.get("email"), "reason": reason.strip(), "at": now_iso()}
    res = await db.backups.insert_one(dict(rec))
    await db.audit_log.insert_one({
        "entity": "backup", "entity_id": str(res.inserted_id), "action": "backup_uploaded",
        "actor": admin.get("email"), "actor_id": str(admin["_id"]), "reason": reason.strip(),
        "after": {"file": stored, "size": size, "integrity": "valid", "storage": "gridfs",
                  "encrypted": check["encrypted"]}, "at": now_iso()})
    return {**serialize(rec), "id": str(res.inserted_id), "validation": check}


class ValidateIn(BaseModel):
    file: str


@router.post("/backups/validate")
async def validate_backup(payload: ValidateIn, admin: dict = Depends(require_admin)):
    """Encryption + integrity verification of a stored file (server copy or imported copy).
    Read-only: nothing is restored, written over, or deleted."""
    safe = os.path.basename(payload.file)
    path = await _materialize(safe)
    if not path:
        raise HTTPException(404, "ملف النسخة غير موجود")
    try:
        check = _inspect(path)
    finally:
        if path.startswith(tempfile.gettempdir()):
            try:
                os.remove(path)
            except OSError:
                pass
    await db.backups.update_many({"file": safe}, {"$set": {
        "integrity": "valid" if check["ok"] else "invalid",
        "sha256": check.get("sha256"),
        "validated_by": admin.get("email"), "validated_at": now_iso()}})
    await db.audit_log.insert_one({
        "entity": "backup", "entity_id": safe, "action": "backup_validated",
        "actor": admin.get("email"), "actor_id": str(admin["_id"]),
        "after": {"file": safe, "result": "valid" if check["ok"] else "invalid",
                  "reason": check.get("reason")}, "at": now_iso()})
    return {"file": safe, "valid": check["ok"], "encrypted": check.get("encrypted"),
            "gzip_archive": check.get("gzip_archive"), "size": check.get("size"),
            "sha256": check.get("sha256"), "reason": check.get("reason"),
            "checked_at": now_iso()}


class VerifyIn(BaseModel):
    file: str
    reason: str = Field(min_length=3)


@router.post("/backups/verify")
async def verify_backup(payload: VerifyIn, admin: dict = Depends(require_admin)):
    """Restore DRILL: decrypts the archive and restores it into a THROWAWAY database
    (`<DB>_restore_drill`), reports the collection counts, then drops that database.
    The live/preview database is never touched. Refuses to run on a live environment."""
    if _environment() == "live":
        raise HTTPException(403, "ممنوع تشغيل اختبار الاستعادة على بيئة Live")
    if not shutil.which("mongorestore"):
        raise HTTPException(503, "أداة mongorestore غير مثبّتة في بيئة تشغيل الخادم — "
                                 "اختبار الاستعادة المعزول معطّل حتى تثبيت "
                                 "mongodb-database-tools في صورة الخادم.")
    path = await _materialize(os.path.basename(payload.file))
    if not path:
        raise HTTPException(404, "ملف النسخة غير موجود")
    dbname = os.environ["DB_NAME"]
    drill_db = f"{dbname}_restore_drill"
    work = f"{BACKUP_DIR}/.drill.archive.gz"
    started = now_iso()
    try:
        if path.endswith(".enc"):
            pw = _passphrase()
            if not pw:
                raise RuntimeError("النسخة مشفّرة ولا يوجد BACKUP_PASSPHRASE")
            d = subprocess.run(["openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2",
                                "-in", path, "-out", work, "-pass", f"pass:{pw}"],
                               capture_output=True, timeout=600)
            if d.returncode != 0:
                raise RuntimeError("فشل فك التشفير: " + d.stderr.decode()[:200])
        else:
            subprocess.run(["cp", path, work], capture_output=True, timeout=600)
        r = subprocess.run(["mongorestore", f"--uri={os.environ['MONGO_URL']}",
                            f"--archive={work}", "--gzip", "--drop",
                            f"--nsFrom={dbname}.*", f"--nsTo={drill_db}.*"],
                           capture_output=True, timeout=900)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.decode()[-400:])
        client = db.client
        counts = {}
        for c in await client[drill_db].list_collection_names():
            counts[c] = await client[drill_db][c].count_documents({})
        await client.drop_database(drill_db)
        rec = {"file": os.path.basename(path), "result": "success",
               "drill_db": drill_db, "collections": len(counts),
               "documents": sum(counts.values()), "counts": counts,
               "decrypted": path.endswith(".enc"), "error": None,
               "by": admin.get("email"), "reason": payload.reason.strip(),
               "started_at": started, "at": now_iso()}
    except Exception as e:
        rec = {"file": os.path.basename(path), "result": "failed", "error": str(e)[:400],
               "by": admin.get("email"), "reason": payload.reason.strip(),
               "started_at": started, "at": now_iso()}
    finally:
        for f in (work,):
            try:
                os.remove(f)
            except OSError:
                pass
    await db.backup_drills.insert_one(dict(rec))
    await db.audit_log.insert_one({"entity": "backup", "entity_id": rec["file"],
                                   "action": "restore_drill", "actor": admin.get("email"),
                                   "reason": payload.reason.strip(),
                                   "after": {"result": rec["result"],
                                             "documents": rec.get("documents")},
                                   "at": now_iso()})
    if rec["result"] == "failed":
        raise HTTPException(500, f"فشل اختبار الاستعادة: {rec['error']}")
    return rec


class RestoreIn(BaseModel):
    file: str
    confirm_phrase: str
    reason: str = Field(min_length=5)


@router.post("/backups/restore")
async def restore_backup(payload: RestoreIn, admin: dict = Depends(require_admin)):
    """Triple-guarded restore: ALLOW_RESTORE=true env, an exact confirmation phrase and a
    reason. Refuses to run when the environment is marked as live."""
    if os.environ.get("ALLOW_RESTORE") != "true":
        raise HTTPException(403, "الاستعادة معطّلة في هذه البيئة (ALLOW_RESTORE غير مفعّل) — "
                                 "تُجرى على Test فقط")
    env = _environment()
    if env == "live":
        raise HTTPException(403, "ممنوع الاستعادة على بيئة Live (محجوب نهائياً)")
    if env == "unknown":
        raise HTTPException(403, "البيئة غير محددة (ENVIRONMENT غير مضبوط) — "
                                 "الاستعادة محجوبة حتى تحديد البيئة صراحةً")
    if payload.confirm_phrase.strip() != "أؤكد الاستعادة":
        raise HTTPException(400, "عبارة التأكيد غير صحيحة")
    path = await _materialize(os.path.basename(payload.file))
    if not path:
        raise HTTPException(404, "ملف النسخة غير موجود")
    await db.audit_log.insert_one({"entity": "backup", "entity_id": payload.file,
                                   "action": "restore_requested", "actor": admin.get("email"),
                                   "reason": payload.reason.strip(), "at": now_iso()})
    return {"ok": True, "status": "authorized",
            "note": "تم تسجيل الطلب والتحقق من الحواجز. التنفيذ الفعلي يتم على بيئة Test بأمر "
                    "mongorestore خارج التطبيق لتفادي أي استعادة خاطئة أثناء التشغيل.",
            "command": f"mongorestore --uri=$MONGO_URL --archive={path} --gzip --drop"}
