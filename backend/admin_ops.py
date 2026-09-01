"""Batch 3 — operations & integrity center (Super Admin).
Additive: integration health + guarded retry, documented reconciliation adjustments
(ledger-only opening entries, never a direct balance edit), and data-integrity guards.
"""
from typing import Optional
import hashlib
import hmac
import json
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
    inbound_recent = serialize(await db.rahal_inbound_log.find({}).sort("at", -1).to_list(15))
    last_delivered = await db.rahal_outbox.find_one({"status": "delivered"}, sort=[("created_at", -1)])
    return {
        "outbox": {"total": total, "by_status": by_status,
                   "undelivered": by_status.get("pending", 0) + by_status.get("failed", 0),
                   "failure_groups": by_event,
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


@router.post("/integrations/outbox/{item_id}/retry")
async def retry_one(item_id: str, payload: RetryIn, admin: dict = Depends(require_admin)):
    """Manual re-processing of a failed integration event — requires a reason and is audited.
    Re-signs with the CURRENT secret using the same compact serialization as the dispatcher."""
    item = await db.rahal_outbox.find_one({"_id": oid(item_id)})
    if not item:
        raise HTTPException(404, "الحدث غير موجود")
    if item.get("status") == "delivered":
        raise HTTPException(400, "الحدث مُسلَّم بالفعل")
    from integration import _deliver, _rahal_webhook_url, _meraaj_secret
    url = _rahal_webhook_url()
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
async def retry_all(payload: RetryIn, admin: dict = Depends(require_admin)):
    from integration import _deliver, _rahal_webhook_url, _meraaj_secret
    url = _rahal_webhook_url()
    if not url:
        raise HTTPException(400, "لم يتم ضبط عنوان Webhook الخاص برحال (RAHAL_WEBHOOK_URL)")
    items = await db.rahal_outbox.find({"status": {"$in": ["pending", "failed"]}}).to_list(200)
    done = 0
    for item in items:
        try:
            raw = json.dumps(item["payload"], ensure_ascii=False,
                             separators=(",", ":")).encode("utf-8")
            sig = hmac.new(_meraaj_secret().encode(), raw, hashlib.sha256).hexdigest()
            await db.rahal_outbox.update_one({"_id": item["_id"]}, {"$set": {"signature": sig}})
            await _deliver(item["_id"], url, raw, sig)
            done += 1
        except Exception:
            continue
    await db.audit_log.insert_one({
        "entity": "integration", "entity_id": "batch", "action": "outbox_manual_retry_all",
        "actor": admin.get("email"), "actor_id": str(admin["_id"]),
        "reason": payload.reason.strip(), "meta": {"attempted": len(items)}, "at": now_iso()})
    delivered = await db.rahal_outbox.count_documents({"status": "delivered"})
    remaining = await db.rahal_outbox.count_documents({"status": {"$in": ["pending", "failed"]}})
    return {"attempted": len(items), "processed": done, "delivered_total": delivered,
            "still_undelivered": remaining}
