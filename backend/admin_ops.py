"""Batch 3 — operations & integrity center (Super Admin).
Additive: integration health + guarded retry, documented reconciliation adjustments
(ledger-only opening entries, never a direct balance edit), and data-integrity guards.
"""
from typing import Optional
import hashlib
import hmac
import json
import re
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from db import db, serialize, oid, now_iso
from security import require_admin

router = APIRouter(prefix="/api/admin", tags=["admin-ops"])

CCY = ("SAR", "USD")


async def ensure_indexes():
    """Called on startup. Prevents duplicate credit-limit rows per office+currency."""
    try:
        await db.credit_limits.create_index([("office_id", 1), ("currency", 1)], unique=True)
    except Exception:
        pass
    for coll, idx in (("audit_log", [("at", -1)]), ("notifications", [("user_id", 1), ("at", -1)]),
                      ("sessions", [("jti", 1)]),
                      ("package_events", [("package_id", 1), ("at", -1)])):
        try:
            await db[coll].create_index(idx)
        except Exception:
            pass


# ---------------- integration health ----------------
@router.get("/integrations/health")
async def integration_health(admin: dict = Depends(require_admin)):
    total = await db.rahal_outbox.count_documents({})
    by_status = {}
    async for r in db.rahal_outbox.aggregate([{"$group": {"_id": "$status", "n": {"$sum": 1}}}]):
        by_status[r["_id"] or "unknown"] = r["n"]
    by_event = []
    async for r in db.rahal_outbox.aggregate([
            {"$match": {"status": {"$in": ["pending", "failed"]}}},
            {"$group": {"_id": {"e": "$event", "err": "$last_error"}, "n": {"$sum": 1}}},
            {"$sort": {"n": -1}}, {"$limit": 20}]):
        by_event.append({"event": r["_id"]["e"], "last_error": r["_id"]["err"], "count": r["n"]})
    inbound_total = await db.rahal_inbound_log.count_documents({})
    by_destination = []
    async for r in db.rahal_outbox.aggregate([
            {"$group": {"_id": {"u": {"$ifNull": ["$url", "—"]},
                                "s": {"$ifNull": ["$status", "unknown"]}},
                        "n": {"$sum": 1}}},
            {"$sort": {"n": -1}}]):
        by_destination.append({"url": r["_id"]["u"] or "—", "status": r["_id"]["s"],
                               "count": r["n"]})
    inbound_recent = serialize(await db.rahal_inbound_log.find({}).sort("at", -1).to_list(15))
    last_delivered = await db.rahal_outbox.find_one({"status": "delivered"}, sort=[("created_at", -1)])
    return {
        "outbox": {"total": total, "by_status": by_status,
                   "undelivered": by_status.get("pending", 0) + by_status.get("failed", 0),
                   "failure_groups": by_event,
                   "by_destination": by_destination,
                   "last_delivered_at": (last_delivered or {}).get("created_at")},
        "inbound": {"total": inbound_total, "recent": inbound_recent},
        "generated_at": now_iso(),
    }


@router.get("/integrations/outbox")
async def outbox_list(status: Optional[str] = None, limit: int = 100,
                      admin: dict = Depends(require_admin)):
    f = {"status": status} if status else {"status": {"$in": ["pending", "failed"]}}
    docs = await db.rahal_outbox.find(f).sort("created_at", -1).to_list(min(limit, 300))
    out = []
    for x in docs:
        d = serialize(x)
        d["diagnosis"] = classify_outbox_error(x.get("http_status"), x.get("last_error"))
        out.append(d)
    return out


class RetryIn(BaseModel):
    reason: str = Field(min_length=3)


@router.get("/integrations/diagnose")
async def diagnose(admin: dict = Depends(require_admin)):
    """Classifies every undelivered outbox event by root cause and states who must fix it."""
    causes = {
        "hmac": {"key": "توقيع HMAC مرفوض من رحّال", "owner": "rahal",
                 "action": "على رحّال ضبط MERAAJ_SHARED_SECRET بنفس قيمة معراج والتحقق من "
                           "أنه يتحقق من التوقيع على الجسم الخام (JSON مضغوط بدون مسافات)."},
        "not_found": {"key": "المسار غير موجود (404) على رحّال", "owner": "rahal",
                      "action": "على رحّال تنفيذ/تصحيح مسار الـWebhook لهذا النوع من الأحداث "
                                "(مثل meraaj.booking.cancellation_finalized)."},
        "unknown_ref": {"key": "مرجع غير معروف لدى رحّال", "owner": "rahal",
                        "action": "الحجز/البرنامج غير موجود في بيئة رحّال (بيانات معاينة) — "
                                  "يُعاد الإرسال بعد مزامنة المراجع."},
        "network": {"key": "تعذّر الوصول للخادم", "owner": "shared",
                    "action": "تحقق من RAHAL_WEBHOOK_URL وتوفر خادم رحّال."},
        "pending": {"key": "لم تُرسل بعد", "owner": "meraaj",
                    "action": "أعد المعالجة من هذه الشاشة (يعيد التوقيع بالسر الحالي)."},
        "other": {"key": "سبب آخر", "owner": "shared", "action": "راجع نص الخطأ."},
    }

    def classify(item):
        if item.get("status") == "pending":
            return "pending"
        e = (item.get("last_error") or "").lower()
        if "signature" in e or "hmac" in e or "401" in e or "403" in e:
            return "hmac"
        if "404" in e or "not found" in e:
            return "not_found"
        if "unknown" in e or ("ref" in e and "not" in e):
            return "unknown_ref"
        if "timeout" in e or "connect" in e or "resolve" in e:
            return "network"
        return "other"

    groups = {}
    items = await db.rahal_outbox.find({"status": {"$in": ["pending", "failed"]}}).to_list(500)
    for it in items:
        c = classify(it)
        g = groups.setdefault(c, {"cause": c, **causes[c], "count": 0, "events": {},
                                  "samples": []})
        g["count"] += 1
        g["events"][it.get("event")] = g["events"].get(it.get("event"), 0) + 1
        if len(g["samples"]) < 3:
            g["samples"].append({"id": str(it["_id"]), "event": it.get("event"),
                                 "attempts": it.get("attempts"),
                                 "last_error": (it.get("last_error") or "")[:160]})
    out = sorted(groups.values(), key=lambda x: -x["count"])
    return {"undelivered": len(items), "groups": out,
             "meraaj_side_fixable": sum(g["count"] for g in out if g["owner"] == "meraaj"),
             "rahal_side_fixable": sum(g["count"] for g in out if g["owner"] == "rahal"),
             "generated_at": now_iso()}


def classify_outbox_error(status, last_error: str) -> dict:
    """Turns a raw endpoint error into an actionable statement: what went wrong, who owns
    the fix, which reference is required and what the next step is. No guessing, no retry."""
    raw = str(last_error or "")
    detail = {}
    try:
        detail = json.loads(raw) if raw.strip().startswith("{") else {}
    except ValueError:
        detail = {}
    code = detail.get("error") or ""
    if code == "unknown_package_ref":
        ref = detail.get("received_package_ref")
        return {
            "cause": "business",
            "code": code,
            "title": "مرجع باكج غير معروف عند رحّال",
            "reason_ar": (f"رحّال لا يعرف مرجع الباكج «{ref}» — الحدث وصل وتم التحقق من "
                          "توقيعه، لكن المرجع غير موجود في قاعدة رحّال."),
            "required_reference": ref,
            "owner": "rahal",
            "next_action": ("لا تُعِد المعالجة قبل الحصول على مرجع باكج صحيح من رحّال لهذا "
                            "البرنامج. إن كان المرجع من بيانات اختبار QA فلا إجراء مطلوب."),
            "retry_useful": False,
        }
    if status == 404 and "page not found" in raw.lower():
        return {"cause": "endpoint", "code": "route_not_found",
                "title": "المسار غير موجود على خادم رحّال",
                "reason_ar": "الخادم لا يُخدّم مسار الـWebhook المضبوط (404 على مستوى التوجيه).",
                "required_reference": None, "owner": "rahal",
                "next_action": "تأكيد عنوان/مسار Webhook حيّ من رحّال ثم إعادة المعالجة.",
                "retry_useful": True}
    if status == 409 or "conflict" in raw.lower() or code in ("duplicate", "already_exists"):
        low = raw.lower()
        if "price" in low or "amount" in low or "سعر" in raw:
            return {"cause": "business", "code": "price_mismatch",
                    "title": "اختلاف في السعر بين معراج ورحّال",
                    "reason_ar": ("رحّال رفض الحدث لاختلاف السعر/المبلغ المُرسل عن المسجّل "
                                  "لديه لنفس الطلب."),
                    "required_reference": detail.get("booking_ref"), "owner": "shared",
                    "next_action": ("استخدم «تتبّع مبلغ التسوية» لتحديد الرقم المعتمد ثم "
                                    "اتفق مع رحّال على القيمة الصحيحة قبل أي إعادة إرسال."),
                    "retry_useful": False}
        if "settle" in low or "تسوية" in raw:
            return {"cause": "business", "code": "settlement_mismatch",
                    "title": "اختلاف في مبلغ التسوية",
                    "reason_ar": "مبلغ التسوية المُرسل لا يطابق ما يتوقعه رحّال لهذا الطلب.",
                    "required_reference": detail.get("booking_ref"), "owner": "shared",
                    "next_action": ("راجع «تتبّع مبلغ التسوية» للطلب وحدّد مصدر الفرق قبل "
                                    "أي إعادة إرسال."),
                    "retry_useful": False}
        return {"cause": "business", "code": "conflict",
                "title": "تعارض في حالة الطلب لدى رحّال (409)",
                "reason_ar": ("رحّال يرى الطلب في حالة مختلفة (مُعالَج مسبقاً أو مكرر) "
                              "فرفض الحدث."),
                "required_reference": detail.get("booking_ref"), "owner": "rahal",
                "next_action": ("لا تُعِد الإرسال: تأكد أولاً من حالة الطلب لدى رحّال "
                                "لتجنّب ازدواج القيود."),
                "retry_useful": False}
    if status in (401, 403) or "signature" in raw.lower() or "hmac" in raw.lower():
        return {"cause": "signature", "code": "signature_rejected",
                "title": "التوقيع أو المصادقة مرفوضة (HMAC)",
                "reason_ar": "الخادم موجود لكنه رفض التوقيع — تحقق من تطابق السر المشترك.",
                "required_reference": None, "owner": "shared",
                "next_action": "مطابقة بصمة السر بين الطرفين ثم إعادة المعالجة.",
                "retry_useful": True}
    if status == 404:
        return {"cause": "endpoint", "code": "not_found_404",
                "title": "غير موجود على خادم رحّال (404)",
                "reason_ar": ("الخادم رد بـ404: إمّا المسار غير مُخدَّم أو المرجع المُرسل غير "
                              "موجود في قاعدة رحّال."),
                "required_reference": detail.get("booking_ref") or detail.get("package_ref"),
                "owner": "rahal",
                "next_action": "تأكيد المسار والمرجع من رحّال ثم إعادة المعالجة بقرار موثّق.",
                "retry_useful": True}
    if status is None:
        return {"cause": "transport", "code": "unreachable",
                "title": "تعذّر الوصول إلى الخادم",
                "reason_ar": raw[:200] or "انتهت المهلة أو تعذّر الاتصال.",
                "required_reference": None, "owner": "shared",
                "next_action": "التحقق من توفّر الخادم والشبكة ثم إعادة المعالجة.",
                "retry_useful": True}
    if status and 200 <= status < 300:
        return {"cause": "none", "code": "ok", "title": "مُسلَّم",
                "reason_ar": "", "required_reference": None, "owner": "ok",
                "next_action": "", "retry_useful": False}
    return {"cause": "unexpected", "code": f"http_{status}",
            "title": f"استجابة غير متوقعة ({status})",
            "reason_ar": raw[:200], "required_reference": None, "owner": "shared",
            "next_action": "مراجعة نص الاستجابة مع فريق رحّال.", "retry_useful": True}


@router.get("/integrations/settlement-trace/{booking_id}")
async def settlement_trace(booking_id: str, admin: dict = Depends(require_admin)):
    """READ-ONLY trace of every money figure for one order next to the amounts that were
    actually sent to Rahaal, so any settlement mismatch is located exactly. No writes,
    no re-send, no recalculation of balances."""
    from finance import booking_financials, booking_reconciliation
    b = await db.bookings.find_one({"_id": oid(booking_id)})
    if not b:
        raise HTTPException(404, "الحجز غير موجود")
    txns = await db.transactions.find({"ref": booking_id}).to_list(300)
    fin = booking_financials(b, txns)
    rec = booking_reconciliation(b, txns)
    authoritative = {
        "order_amount": fin["gross"], "platform_commission": fin["platform_commission"],
        "buyer_commission": fin["buyer_commission"], "seller_net": fin["seller_net"],
        "refund": fin["refunded"], "released": fin["released"],
        "settlement_amount": fin["released"],
        "currency": fin["currency"],
        "source": "حقول الطلب المسجّلة وقت التسعير + الحركات المسجّلة (المصدر المعتمد)",
    }
    events = []
    async for e in db.rahal_outbox.find({"$or": [{"payload.data.booking_ref": booking_id},
                                                 {"payload.data.booking_id": booking_id},
                                                 {"ref": booking_id}]}).sort("created_at", 1):
        data = ((e.get("payload") or {}).get("data") or {})
        sent = {k: data.get(k) for k in
                ("amount", "total", "settlement_amount", "refund_amount", "seller_net",
                 "platform_commission", "currency") if k in data}
        events.append({"id": str(e["_id"]), "event": e.get("event"),
                       "status": e.get("status"), "http_status": e.get("http_status"),
                       "at": e.get("created_at"), "sent_amounts": sent})
    diffs = []
    for ev in events:
        for key, ours in (("settlement_amount", authoritative["settlement_amount"]),
                          ("refund_amount", authoritative["refund"]),
                          ("platform_commission", authoritative["platform_commission"])):
            theirs = ev["sent_amounts"].get(key)
            if theirs is not None and abs(float(theirs) - float(ours)) > 0.01:
                diffs.append({"event_id": ev["id"], "event": ev["event"], "field": key,
                              "meraaj": ours, "sent_to_rahal": float(theirs),
                              "difference": round(float(theirs) - float(ours), 2)})
    return {"booking_id": booking_id, "status": b.get("status"),
            "authoritative": authoritative,
            "statement": fin, "reconciliation": rec,
            "outbox_events": events, "mismatches": diffs,
            "verdict": ("لا يوجد اختلاف بين أرقام معراج وما أُرسل لرحّال"
                        if not diffs else
                        f"{len(diffs)} اختلافاً بين رقم معراج المعتمد وما أُرسل لرحّال"),
            "generated_at": now_iso()}


@router.get("/integrations/outbox/classify")
async def outbox_classify(admin: dict = Depends(require_admin)):
    """Root-cause buckets for undelivered events, separating historic/unsendable events
    from live problems. Read-only: nothing is retried here."""
    items = await db.rahal_outbox.find({"status": {"$in": ["pending", "failed"]}}).to_list(1000)
    buckets = {}
    for it in items:
        diag = classify_outbox_error(it.get("http_status"), it.get("last_error"))
        key = diag["code"]
        g = buckets.setdefault(key, {
            "code": key, "title": diag["title"], "owner": diag["owner"],
            "retry_useful": diag["retry_useful"], "next_action": diag["next_action"],
            "count": 0, "events": {}, "oldest": None, "newest": None,
            "sample_ids": []})
        g["count"] += 1
        g["events"][it.get("event")] = g["events"].get(it.get("event"), 0) + 1
        at = it.get("created_at") or ""
        g["oldest"] = min(g["oldest"] or at, at)
        g["newest"] = max(g["newest"] or at, at)
        if len(g["sample_ids"]) < 5:
            g["sample_ids"].append(str(it["_id"]))
    groups = sorted(buckets.values(), key=lambda x: -x["count"])
    historic = [g for g in groups if not g["retry_useful"]]
    live = [g for g in groups if g["retry_useful"]]
    return {"undelivered": len(items),
            "historic_unsendable": {"count": sum(g["count"] for g in historic),
                                    "groups": historic,
                                    "note": ("أحداث قديمة/بيانات معاينة لا فائدة من إعادة "
                                             "إرسالها — تُترك موثّقة بلا إجراء.")},
            "actionable": {"count": sum(g["count"] for g in live), "groups": live,
                           "note": "قابلة لإعادة الإرسال بعد إصلاح السبب لدى الطرف المسؤول."},
            "retry_policy": "لا إعادة إرسال جماعية تلقائية — كل إعادة إرسال بقرار وسبب موثّق",
            "generated_at": now_iso()}


@router.get("/integrations/target")
async def get_target(admin: dict = Depends(require_admin)):
    """Exact effective outbound configuration, so the Rahaal endpoint can be verified
    (base URL, path, method, signature header, secret fingerprint) without guessing."""
    from integration import rahal_target, secret_fingerprint
    t = await rahal_target()
    url = t["url"]
    base, path = "", ""
    if url:
        m = re.match(r"^(https?://[^/]+)(/.*)?$", url)
        if m:
            base, path = m.group(1), m.group(2) or "/"
    return {**t, "base_url": base, "path": path, "method": "POST",
            "signature_header": "X-Meraaj-Signature",
            "signature_algo": "HMAC-SHA256 over the raw compact JSON body (hex, no prefix)",
            "secret_fingerprint": secret_fingerprint(),
            "content_type": "application/json"}


class TargetIn(BaseModel):
    webhook_url: str = Field(min_length=8)
    reason: str = Field(min_length=3)


@router.post("/integrations/target")
async def set_target(payload: TargetIn, admin: dict = Depends(require_admin)):
    url = payload.webhook_url.strip()
    if not re.match(r"^https?://[^\s]+$", url):
        raise HTTPException(400, "عنوان غير صالح — يجب أن يبدأ بـ http:// أو https://")
    before = await db.settings.find_one({"_id": "integration_target"}) or {}
    await db.settings.update_one({"_id": "integration_target"}, {"$set": {
        "webhook_url": url, "updated_by": admin.get("email"), "updated_at": now_iso()}},
        upsert=True)
    await db.audit_log.insert_one({
        "entity": "integration", "entity_id": "target", "action": "webhook_target_updated",
        "actor": admin.get("email"), "actor_id": str(admin["_id"]),
        "reason": payload.reason.strip(),
        "before": {"webhook_url": before.get("webhook_url")}, "after": {"webhook_url": url},
        "at": now_iso()})
    return {"ok": True, "webhook_url": url}


@router.post("/integrations/probe")
async def probe_target(admin: dict = Depends(require_admin)):
    """Sends a signed `meraaj.ping` to the configured endpoint and reports the EXACT
    response (status, body, latency) plus a verdict. Nothing is written to the outbox."""
    import time as _t
    import httpx
    from integration import rahal_target, _meraaj_secret, secret_fingerprint
    t = await rahal_target()
    url = t["url"]
    if not url:
        raise HTTPException(400, "لم يتم ضبط عنوان Webhook (RAHAL_WEBHOOK_URL أو إعداد الوجهة)")
    body = {"id": "probe", "type": "meraaj.ping", "timestamp": int(_t.time()),
            "data": {"source": "meraaj-admin-probe"}}
    raw = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    sig = hmac.new(_meraaj_secret().encode(), raw, hashlib.sha256).hexdigest()
    started = _t.time()
    status, text, err = None, "", None
    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=False) as c:
            r = await c.post(url, content=raw, headers={"Content-Type": "application/json",
                                                        "X-Meraaj-Signature": sig})
        status, text = r.status_code, r.text[:600]
    except Exception as e:
        err = str(e)[:400]
    ms = int((_t.time() - started) * 1000)
    if err:
        verdict, owner = "تعذّر الوصول للخادم", "shared"
    elif status == 404:
        verdict = ("المسار غير موجود على خادم رحّال (404) — الخدمة لا تُخدّم هذا المسار. "
                   "يلزم عنوان/مسار Webhook صحيح وحيّ من رحّال")
        owner = "rahal"
    elif status in (401, 403):
        verdict, owner = "الخادم موجود ولكنه رفض التوقيع/المصادقة — تحقق من تطابق السر", "rahal"
    elif status and 200 <= status < 300:
        verdict, owner = "الوجهة سليمة والتوقيع مقبول", "ok"
    else:
        verdict, owner = f"استجابة غير متوقعة ({status})", "shared"
    await db.audit_log.insert_one({
        "entity": "integration", "entity_id": "probe", "action": "webhook_probe",
        "actor": admin.get("email"), "actor_id": str(admin["_id"]),
        "after": {"url": url, "http_status": status, "error": err}, "at": now_iso()})
    return {"url": url, "target_source": t["source"], "method": "POST",
            "signature_header": "X-Meraaj-Signature",
            "secret_fingerprint": secret_fingerprint(),
            "http_status": status, "latency_ms": ms, "response_body": _sanitize_error(text),
            "transport_error": _sanitize_error(err) or None, "verdict": verdict, "owner": owner,
            "sent_body_note": "جسم الفحص لا يحتوي بيانات حساسة ولا يُعرض التوقيع",
            "checked_at": now_iso()}


@router.get("/integrations/outbox/{item_id}")
async def outbox_detail(item_id: str, technical: bool = False,
                        admin: dict = Depends(require_admin)):
    """Failure reason for ONE event. Signature material, the signed body and the reproduction
    command are SENSITIVE: they are never returned unless a super admin explicitly asks for
    the technical view (technical=true)."""
    item = await db.rahal_outbox.find_one({"_id": oid(item_id)})
    if not item:
        raise HTTPException(404, "الحدث غير موجود")
    d = serialize(item)
    d.pop("signature", None)
    d.pop("payload", None)
    from integration import rahal_target_url
    url = item.get("url") or await rahal_target_url()
    import re as _re
    d["endpoint"] = _re.sub(r"^(https?://[^/]+).*$", r"\1/…", url or "") or "—"
    d["attempt_history"] = [{k: v for k, v in (a or {}).items()
                             if k in ("at", "http_status", "error", "attempt")}
                            for a in (item.get("attempt_history") or [])]
    d["diagnosis"] = classify_outbox_error(item.get("http_status"), item.get("last_error"))
    d["last_error"] = _sanitize_error(item.get("last_error"))
    d["sensitive_hidden"] = True
    d["sensitive_note"] = ("بيانات التوقيع والجسم الموقّع وأمر إعادة الإنتاج محجوبة — "
                           "تُتاح للإدارة العليا فقط عند الحاجة التقنية.")
    audit_rows = await db.audit_log.find({"entity": "integration", "entity_id": item_id}
                                        ).sort("at", -1).to_list(20)
    d["audit"] = serialize(audit_rows)
    if technical:
        if admin.get("role") != "super_admin":
            raise HTTPException(403, "العرض التقني للتوقيع متاح للإدارة العليا فقط")
        import hashlib as _h
        import hmac as _hm
        from integration import _meraaj_secret
        raw = json.dumps(item["payload"], ensure_ascii=False, separators=(",", ":"))
        sig = _hm.new(_meraaj_secret().encode(), raw.encode("utf-8"), _h.sha256).hexdigest()
        d["technical"] = {"url": url, "payload": item.get("payload"),
                          "signature_prefix": sig[:8] + "…",
                          "signature_length": len(sig),
                          "body_bytes": len(raw.encode("utf-8")),
                          "note": ("التوقيع الكامل والجسم الخام لا يُرسلان للواجهة — "
                                   "استخدم سجلات الخادم عند التحقيق.")}
        d["sensitive_hidden"] = False
        await db.audit_log.insert_one({
            "entity": "integration", "entity_id": item_id, "action": "technical_view",
            "actor": admin.get("email"), "actor_id": str(admin["_id"]),
            "reason": "عرض تفاصيل تقنية للحدث", "at": now_iso()})
    return d


def _sanitize_error(raw) -> str:
    """Strips any signature/authorization material out of a stored error string."""
    s = str(raw or "")
    if not s:
        return ""
    s = re.sub(r"(?i)(signature|authorization|x-meraaj-signature|secret|token)"
               r"\s*[:=]\s*[^\s,;}\"']+", r"\1: ***", s)
    return s[:400]


@router.post("/integrations/outbox/{item_id}/retry")
async def retry_one(item_id: str, payload: RetryIn, admin: dict = Depends(require_admin)):
    """Manual re-processing of a failed integration event — requires a reason and is audited.
    Re-signs with the CURRENT secret using the same compact serialization as the dispatcher."""
    item = await db.rahal_outbox.find_one({"_id": oid(item_id)})
    if not item:
        raise HTTPException(404, "الحدث غير موجود")
    if item.get("status") == "delivered":
        raise HTTPException(400, "الحدث مُسلَّم بالفعل")
    from integration import _deliver, rahal_target_url, _meraaj_secret
    url = await rahal_target_url()
    if not url:
        raise HTTPException(400, "لم يتم ضبط عنوان Webhook الخاص برحال (RAHAL_WEBHOOK_URL)")
    raw = json.dumps(item["payload"], ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    sig = hmac.new(_meraaj_secret().encode(), raw, hashlib.sha256).hexdigest()
    await db.audit_log.insert_one({
        "entity": "integration", "entity_id": item_id, "action": "outbox_manual_retry",
        "actor": admin.get("email"), "actor_id": str(admin["_id"]),
        "reason": payload.reason.strip(), "before": {"status": item.get("status"),
                                                     "attempts": item.get("attempts")},
        "at": now_iso()})
    await db.rahal_outbox.update_one({"_id": item["_id"]}, {"$set": {"signature": sig}})
    await _deliver(item["_id"], url, raw, sig)
    fresh = await db.rahal_outbox.find_one({"_id": item["_id"]})
    return {"ok": True, "status": fresh.get("status"), "last_error": fresh.get("last_error")}


@router.post("/integrations/outbox/retry-all")
async def retry_all(payload: RetryIn, limit: int = 100, admin: dict = Depends(require_admin)):
    """Bounded, concurrent re-processing so the request always answers well inside the
    gateway timeout (a dead endpoint used to make 200 sequential deliveries time out)."""
    import asyncio
    from integration import _deliver, rahal_target_url, _meraaj_secret
    url = await rahal_target_url()
    if not url:
        raise HTTPException(400, "لم يتم ضبط عنوان Webhook الخاص برحال (RAHAL_WEBHOOK_URL)")
    items = await db.rahal_outbox.find({"status": {"$in": ["pending", "failed"]}}
                                       ).to_list(min(max(limit, 1), 300))
    sem = asyncio.Semaphore(10)

    async def one(item):
        async with sem:
            try:
                raw = json.dumps(item["payload"], ensure_ascii=False,
                                 separators=(",", ":")).encode("utf-8")
                sig = hmac.new(_meraaj_secret().encode(), raw, hashlib.sha256).hexdigest()
                await db.rahal_outbox.update_one({"_id": item["_id"]},
                                                 {"$set": {"signature": sig}})
                await _deliver(item["_id"], url, raw, sig)
                return True
            except Exception:
                return False

    results = await asyncio.gather(*[one(i) for i in items])
    done = sum(1 for r in results if r)
    await db.audit_log.insert_one({
        "entity": "integration", "entity_id": "batch", "action": "outbox_manual_retry_all",
        "actor": admin.get("email"), "actor_id": str(admin["_id"]),
        "reason": payload.reason.strip(), "meta": {"attempted": len(items)}, "at": now_iso()})
    delivered = await db.rahal_outbox.count_documents({"status": "delivered"})
    remaining = await db.rahal_outbox.count_documents({"status": {"$in": ["pending", "failed"]}})
    return {"attempted": len(items), "processed": done, "delivered_total": delivered,
            "still_undelivered": remaining}
