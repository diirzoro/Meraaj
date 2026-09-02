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
    return serialize(docs)


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
            "http_status": status, "latency_ms": ms, "response_body": text,
            "transport_error": err, "verdict": verdict, "owner": owner,
            "sent_body": body, "checked_at": now_iso()}


@router.get("/integrations/outbox/{item_id}")
async def outbox_detail(item_id: str, admin: dict = Depends(require_admin)):
    """Exact failure reason for ONE event: payload actually sent, signature, every attempt
    with its HTTP status, the classified cause and a reproducible curl command."""
    item = await db.rahal_outbox.find_one({"_id": oid(item_id)})
    if not item:
        raise HTTPException(404, "الحدث غير موجود")
    from integration import rahal_target_url, _meraaj_secret
    url = item.get("url") or await rahal_target_url()
    raw = json.dumps(item["payload"], ensure_ascii=False, separators=(",", ":"))
    sig = hmac.new(_meraaj_secret().encode(), raw.encode("utf-8"), hashlib.sha256).hexdigest()
    d = serialize(item)
    d["url"] = url
    d["signed_body"] = raw
    d["current_signature"] = sig
    d["attempt_history"] = item.get("attempt_history") or []
    d["curl"] = (f"curl -i -X POST '{url}' -H 'Content-Type: application/json' "
                 f"-H 'X-Meraaj-Signature: {sig}' -d '{raw[:1200]}'")
    audit_rows = await db.audit_log.find({"entity": "integration", "entity_id": item_id}
                                        ).sort("at", -1).to_list(20)
    d["audit"] = serialize(audit_rows)
    return d


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
