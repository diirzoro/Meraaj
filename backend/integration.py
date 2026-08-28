"""Rahal integration layer — server-to-server endpoints & webhooks.

These endpoints are ready to receive data from Rahal once their dev team is done.
They authenticate with a shared API key (X-Rahal-Api-Key) and verify HMAC signatures.
Currently active and functional (no external Rahal calls are mocked into the UI).
"""
import os
import hmac
import hashlib
import json
import time
import base64
import asyncio
import httpx
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Request, Header, Depends
from db import db, serialize, oid, now_iso, adjust_wallet, log_txn, log_platform_revenue, audit
from security import create_access_token, require_admin, RAHAL_PERMISSIONS

def _empty_wallet():
    from db import empty_wallet
    return empty_wallet()

router = APIRouter(prefix="/api/integrations/rahal", tags=["rahal-integration"])
# Simulated Rahal receiver (soft-launch on the same environment). In production this
# lives inside Rahal at POST /api/meraaj/webhooks and verifies X-Meraaj-Signature.
sim_router = APIRouter(prefix="/api/meraaj", tags=["rahal-sim-receiver"])


def _shared_secret() -> str:
    return os.environ["RAHAL_SHARED_SECRET"]


def _check_api_key(key: str):
    if key != _shared_secret():
        raise HTTPException(status_code=401, detail="Invalid Rahal API key")


def _verify_hmac(raw_body: bytes, signature: str) -> bool:
    """Verify an inbound HMAC-SHA256 signature from Rahal. Accepts MERAAJ_SHARED_SECRET
    (the agreed inbound key) and falls back to RAHAL_SHARED_SECRET for backward compat."""
    if not signature:
        return False
    provided = signature.replace("sha256=", "")
    for secret in (_meraaj_secret(), _shared_secret()):
        expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
        if hmac.compare_digest(expected, provided):
            return True
    return False


# ---------- Outbound: Meraaj -> Rahal (reliable outbox + HMAC) ----------
def _meraaj_secret() -> str:
    return os.environ.get("MERAAJ_SHARED_SECRET", _shared_secret())


def _rahal_webhook_url() -> str:
    return os.environ.get("RAHAL_WEBHOOK_URL", "").strip()


async def _deliver(outbox_id, url: str, raw: bytes, sig: str):
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(url, content=raw, headers={
                "Content-Type": "application/json",
                # Rahaal's meraajVerify() compares the header verbatim to the raw hex digest
                # (it does NOT strip a "sha256=" prefix), so send the bare lowercase hex.
                "X-Meraaj-Signature": sig,
            })
        ok = 200 <= r.status_code < 300
        await db.rahal_outbox.update_one({"_id": outbox_id}, {
            "$set": {"status": "delivered" if ok else "failed",
                     "http_status": r.status_code,
                     "last_error": None if ok else r.text[:500],
                     "delivered_at": now_iso() if ok else None},
            "$inc": {"attempts": 1}})
    except Exception as e:
        await db.rahal_outbox.update_one({"_id": outbox_id}, {
            "$set": {"status": "failed", "last_error": str(e)[:500]},
            "$inc": {"attempts": 1}})


async def notify_rahal(event: str, payload: dict, *, envelope: dict = None):
    """Persist the event to an outbox (never lost) then deliver in the background.
    When `envelope` is provided it is sent VERBATIM as the signed body (Rahaal v2
    {id,type,timestamp,data} contract); otherwise the legacy flat {event, ...payload}
    shape is used. Serialization / HMAC / _deliver / outbox are unchanged."""
    body = envelope if envelope is not None else {"event": event, **payload, "occurred_at": now_iso()}
    # Compact separators to byte-match Node's JSON.stringify (no spaces) so the HMAC
    # signature verifies on the Rahal side (fixes 401 Invalid HMAC signature).
    raw = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    sig = hmac.new(_meraaj_secret().encode(), raw, hashlib.sha256).hexdigest()
    res = await db.rahal_outbox.insert_one({
        "event": event, "payload": body, "signature": sig,
        "status": "pending", "attempts": 0, "last_error": None, "created_at": now_iso(),
    })
    url = _rahal_webhook_url()
    if url:
        asyncio.create_task(_deliver(res.inserted_id, url, raw, sig))


@router.get("/outbox")
async def list_outbox(status: str = "all", admin: dict = Depends(require_admin)):
    q = {} if status == "all" else {"status": status}
    docs = await db.rahal_outbox.find(q).sort("created_at", -1).to_list(300)
    return serialize(docs)


@router.post("/outbox/retry")
async def retry_outbox(admin: dict = Depends(require_admin)):
    url = _rahal_webhook_url()
    if not url:
        raise HTTPException(400, "لم يتم ضبط عنوان Webhook الخاص برحال (RAHAL_WEBHOOK_URL)")
    pending = await db.rahal_outbox.find({"status": {"$in": ["pending", "failed"]}}).to_list(300)
    for d in pending:
        # Re-serialize with the SAME compact separators used at signing time AND recompute the
        # signature with the CURRENT secret, so the retried bytes byte-match the signed bytes
        # (fixes invalid_signature — incl. events queued before an HMAC secret rotation).
        raw = json.dumps(d["payload"], ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        sig = hmac.new(_meraaj_secret().encode(), raw, hashlib.sha256).hexdigest()
        await db.rahal_outbox.update_one({"_id": d["_id"]}, {"$set": {"signature": sig}})
        await _deliver(d["_id"], url, raw, sig)
    return {"retried": len(pending)}


@router.post("/_sink")
async def _selftest_sink(request: Request, x_meraaj_signature: str = Header(default="")):
    """Internal self-test receiver that verifies X-Meraaj-Signature exactly like Rahal must."""
    raw = await request.body()
    expected = hmac.new(_meraaj_secret().encode(), raw, hashlib.sha256).hexdigest()
    valid = hmac.compare_digest(expected, x_meraaj_signature.replace("sha256=", ""))
    await db.rahal_sink.insert_one({"valid": valid, "body": json.loads(raw), "received_at": now_iso()})
    if not valid:
        raise HTTPException(401, "invalid signature")
    return {"received": True, "valid": valid}


@sim_router.post("/webhooks")
async def simulated_rahal_receiver(request: Request, x_meraaj_signature: str = Header(default="")):
    """Simulated Rahal inbound receiver for the soft launch. Verifies HMAC exactly as
    Rahal must, records the event, and acknowledges (this is what proves overbooking sync)."""
    raw = await request.body()
    expected = hmac.new(_meraaj_secret().encode(), raw, hashlib.sha256).hexdigest()
    valid = hmac.compare_digest(expected, x_meraaj_signature.replace("sha256=", ""))
    body = json.loads(raw)
    await db.rahal_sim_inbox.insert_one({
        "valid": valid, "event": body.get("event"),
        "package_ref": body.get("package_ref"), "body": body, "received_at": now_iso(),
    })
    if not valid:
        raise HTTPException(401, "invalid signature")
    return {"received": True, "valid": valid, "action": "seats_synced"}


@sim_router.get("/inbox")
async def simulated_rahal_inbox(admin: dict = Depends(require_admin)):
    docs = await db.rahal_sim_inbox.find().sort("received_at", -1).to_list(100)
    return serialize(docs)


def _base_room(room_pricing):
    """Pick a base room (double preferred) to derive flat pricing for backward-compatible booking math."""
    if not room_pricing:
        return None
    for r in room_pricing:
        if str(r.get("room_type", "")).lower() in ("double", "twin", "ثنائية"):
            return r
    return room_pricing[0]


def _adapt_package(body: dict) -> dict:
    """Normalize Rahal Contract v2 OR the legacy payload into Meraaj's canonical package fields.
    v2 fields: package_type, name, start_date/end_date, room_pricing[], package_transports[],
    components[], image_url; legacy: type, title, departure_date/return_date, pricing{...}, images[]."""
    pricing = body.get("pricing") or {}
    room_pricing = body.get("room_pricing") or []
    if not isinstance(room_pricing, list):
        room_pricing = []
    transports = body.get("package_transports") or body.get("transports") or []
    if not isinstance(transports, list):
        transports = []
    components = body.get("components") or body.get("package_components") or []
    if not isinstance(components, list):
        components = []
    images = body.get("images") or []
    if not images and body.get("image_url"):
        iu = body["image_url"]
        images = iu if isinstance(iu, list) else [iu]
    base = _base_room(room_pricing)
    net = pricing.get("net_cost_per_seat")
    sale = pricing.get("final_sale_price")
    comm = pricing.get("buyer_office_commission")
    if base is not None:
        if net is None:
            bn = base.get("net")
            net = (bn.get("adult") if isinstance(bn, dict) else bn) or 0
        if sale is None:
            cust = base.get("customer", 0)
            sale = cust.get("adult", 0) if isinstance(cust, dict) else cust
        if comm is None:
            bc = base.get("commission")
            comm = (bc.get("adult") if isinstance(bc, dict) else bc) or 0
    currency = pricing.get("currency") or body.get("currency") or "USD"
    currency = "SAR" if currency == "SAR" else "USD"
    seats = body.get("available_seats")
    if seats is None:
        seats = body.get("total_seats", 0)
    transport_str = body.get("transport") or ""
    if not transport_str and transports:
        f = transports[0]
        transport_str = f.get("type") or f.get("bus_type") or f.get("company") or f.get("name") or "نقل بري"
    return {
        "type": body.get("type") or body.get("package_type") or "umrah",
        "title": body.get("title") or body.get("name") or "",
        "description": body.get("description", ""),
        "departure_date": body.get("departure_date") or body.get("start_date") or "",
        "return_date": body.get("return_date") or body.get("end_date") or "",
        "departure_city": body.get("departure_city", ""),
        "transport": transport_str,
        "transports": transports,
        "components": components,
        "room_pricing": room_pricing,
        "hotels": body.get("hotels") or [],
        "images": images,
        "features": body.get("features") or [],
        "net_cost_per_seat": net or 0,
        "final_sale_price": sale or 0,
        "buyer_office_commission": comm or 0,
        "currency": currency,
        "total_seats": seats or 0,
    }


def _adapt_partial(data: dict) -> dict:
    """Build a package.updated $set from ONLY the fields actually present in the v2 delta,
    so a partial update never blanks previously-stored fields (description/city/transport…)."""
    m = _adapt_package(data)
    has = lambda *ks: any(k in data for k in ks)
    upd = {}
    if has("type", "package_type"):
        upd["type"] = m["type"]
    if has("title", "name") and m["title"]:
        upd["title"] = m["title"]
    if "description" in data:
        upd["description"] = m["description"]
    if has("departure_date", "start_date"):
        upd["departure_date"] = m["departure_date"]
    if has("return_date", "end_date"):
        upd["return_date"] = m["return_date"]
    if "departure_city" in data:
        upd["departure_city"] = m["departure_city"]
    if has("transport", "package_transports", "transports"):
        upd["transport"] = m["transport"]
        upd["transports"] = m["transports"]
    if has("components", "package_components"):
        upd["components"] = m["components"]
    if has("hotels"):
        upd["hotels"] = m["hotels"]
    if has("features"):
        upd["features"] = m["features"]
    if has("images", "image_url") and m["images"]:
        upd["images"] = m["images"]
    if has("room_pricing") or "pricing" in data:
        upd["net_cost_per_seat"] = m["net_cost_per_seat"]
        upd["final_sale_price"] = m["final_sale_price"]
        upd["buyer_office_commission"] = m["buyer_office_commission"]
        if has("room_pricing"):
            upd["room_pricing"] = m["room_pricing"]
    if has("currency") or "pricing" in data:
        upd["currency"] = m["currency"]
    if has("available_seats", "total_seats"):
        upd["available_seats"] = m["total_seats"]
        upd["total_seats"] = m["total_seats"]
    return upd


def _price_warnings(mapped: dict, ref: str):
    """Data-quality warnings for incoming Rahal pricing (logged, never blocks)."""
    warns = []
    rooms = mapped.get("room_pricing") or []
    if not rooms:
        warns.append("لا توجد أسعار غرف (room_pricing فارغ)")
    for r in rooms:
        rt = r.get("room_type", "?")
        cust = r.get("customer")
        adult_missing = cust is None or (isinstance(cust, dict) and cust.get("adult") is None)
        if adult_missing:
            warns.append(f"غرفة {rt}: سعر البالغ للعميل مفقود")
        if isinstance(cust, dict):
            if cust.get("child") is None:
                warns.append(f"غرفة {rt}: سعر الطفل مفقود")
            if cust.get("infant") is None:
                warns.append(f"غرفة {rt}: سعر الرضيع مفقود")
        if r.get("net") is None:
            warns.append(f"غرفة {rt}: الصافي (net) مفقود")
        if r.get("commission") is None:
            warns.append(f"غرفة {rt}: العمولة (commission) مفقودة")
    return warns


@router.post("/packages/share")
async def share_package(request: Request,
                        x_rahal_api_key: str = Header(default=""),
                        x_rahal_signature: str = Header(default=""),
                        x_meraaj_signature: str = Header(default="")):
    raw = await request.body()
    sig = x_rahal_signature or x_meraaj_signature
    # Authorize via HMAC (MERAAJ_SHARED_SECRET) OR the legacy shared API key
    authorized = (x_rahal_api_key and x_rahal_api_key == _shared_secret()) or _verify_hmac(raw, sig)
    if not authorized:
        raise HTTPException(status_code=401, detail="Invalid Rahal credentials (API key or HMAC signature)")
    try:
        body = json.loads(raw)
    except (ValueError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="Malformed JSON body")
    ref_v = body.get("package_ref") or body.get("rahal_ref")
    if not ref_v:
        raise HTTPException(status_code=400, detail="package_ref مطلوب")
    office_ref = body.get("office_ref")
    mapped = _adapt_package(body)
    # Resolve (or auto-provision) the seller office linked to this Rahal office_ref
    seller = await db.users.find_one({"rahal_office_ref": office_ref}) if office_ref else None
    if not seller:
        seller_doc = {
            "email": f"{(office_ref or 'rahal').lower()}@rahal.local",
            "password_hash": None,
            "role": "office",
            "office_name": body.get("office_name") or f"مكتب رحال {office_ref or ''}".strip(),
            "owner_name": body.get("owner_name") or "",
            "phone": "", "governorate": "", "address": "", "commercial_license": "",
            "status": "active", "source": "rahal", "rahal_office_ref": office_ref,
            "wallet": _empty_wallet(),
            "created_at": now_iso(),
        }
        try:
            res_s = await db.users.insert_one(seller_doc)
            seller_doc["_id"] = res_s.inserted_id
            seller = seller_doc
        except Exception:
            seller = await db.users.find_one({"rahal_office_ref": office_ref})
    # Matching precedence: meraaj_package_id -> rahal_ref (never by title/name)
    mid = body.get("meraaj_package_id") or body.get("remote_id")
    existing = None
    if mid:
        try:
            existing = await db.packages.find_one({"_id": oid(mid)})
        except Exception:
            existing = None
    if not existing:
        existing = await db.packages.find_one({"rahal_ref": ref_v})
    doc = {
        **mapped,
        "available_seats": mapped["total_seats"],
        "status": "listed",
        "is_active": True,
        "source": "rahal",
        "rahal_ref": ref_v,
        "rahal_office_ref": office_ref,
        "seller_id": str(seller["_id"]) if seller else None,
        "seller_office_name": seller["office_name"] if seller else (body.get("office_name") or "مكتب رحال"),
    }
    if existing:
        # Never overwrite a previously-stored valid images[] with an empty incoming array.
        if not doc["images"] and existing.get("images"):
            doc["images"] = existing["images"]
        await db.packages.update_one({"_id": existing["_id"]}, {"$set": doc})
        pkg_id = str(existing["_id"])
    else:
        doc["created_at"] = now_iso()
        res = await db.packages.insert_one(doc)
        pkg_id = str(res.inserted_id)
    # Source-of-truth mirror of the exact inbound payload (dedicated Rahal collection)
    await db.rahal_packages.update_one(
        {"rahal_ref": ref_v},
        {"$set": {
            "rahal_ref": ref_v,
            "office_ref": office_ref,
            "payload": body,
            "images": doc["images"],
            "features": mapped["features"],
            "room_pricing": mapped["room_pricing"],
            "transports": mapped["transports"],
            "components": mapped["components"],
            "meraaj_package_id": pkg_id,
            "status": "listed",
            "updated_at": now_iso(),
        }, "$setOnInsert": {"created_at": now_iso()}},
        upsert=True,
    )
    # Data-quality audit: log a warning when incoming prices are incomplete (never blocks)
    warns = _price_warnings(mapped, ref_v)
    await db.rahal_packages.update_one({"rahal_ref": ref_v}, {"$set": {"price_warnings": warns}})
    if warns:
        await db.rahal_inbound_log.insert_one({
            "event": "data.warning", "event_id": None, "rahal_ref": ref_v,
            "meraaj_package_id": pkg_id, "warnings": warns, "handled": True,
            "created_at": now_iso(),
        })
    return {"remote_id": pkg_id, "meraaj_package_id": pkg_id, "status": "listed",
            "price_warnings": warns,
            "market_url": f"{os.environ.get('FRONTEND_URL','')}/market/{pkg_id}"}


async def apply_approval_financials(b):
    """Establish DEFERRED effects at seller approval: seller escrow (pending) + platform
    revenue + marketer commission. Does NOT release to seller available (settlement does)."""
    cur = b.get("currency", "USD")
    net_total = b.get("net_cost_total", 0) or 0
    bid = str(b["_id"])
    await adjust_wallet(oid(b["seller_id"]), cur, pending=net_total, total=net_total)
    await log_txn(b["seller_id"], "booking_escrow", net_total, f"إيراد معلق (قبول): {b.get('package_title','')}", bid, currency=cur)
    if b.get("buyer_type") == "office" and b.get("platform_fee"):
        await log_platform_revenue(b["platform_fee"], f"عمولة منصة (قبول): {b.get('package_title','')}", bid, currency=cur)
    if b.get("buyer_type") != "office":
        if b.get("marketer_id") and (b.get("marketer_commission", 0) or 0) > 0:
            await adjust_wallet(oid(b["marketer_id"]), cur, pending=b["marketer_commission"], total=b["marketer_commission"])
            await log_txn(b["marketer_id"], "marketer_commission", b["marketer_commission"], f"عمولة تسويق (قبول): {b.get('package_title','')}", bid, currency=cur)
        if b.get("platform_profit"):
            await log_platform_revenue(b["platform_profit"], f"أرباح المنصة (قبول): {b.get('package_title','')}", bid, currency=cur)


async def refund_and_release(b):
    """Idempotent unwind of a HELD (pre-approval) booking: reverse the EXACT debit split
    (per-currency, no leak), release seats, free passport reservations. No seller escrow
    existed yet, so nothing to reverse there."""
    cur = b.get("currency", "USD")
    bid = str(b["_id"])
    split = b.get("debit_split") or {cur: b.get("amount_charged", 0) or 0}
    for c, amt in split.items():
        if amt:
            await adjust_wallet(oid(b["buyer_id"]), c, available=amt, total=amt)
    await log_txn(b["buyer_id"], "hold_release", b.get("amount_charged", 0) or 0,
                  f"فك حجز المبلغ: {b.get('package_title','')}", bid, currency=cur)
    await db.packages.update_one({"_id": oid(b["package_id"])}, {"$inc": {"available_seats": b.get("seats", 0)}})
    await db.trip_passports.delete_many({"booking_id": bid})


async def _handle_booking_decision(etype, booking_ref, reason):
    """Apply Rahal's approve/reject. Atomic state-claim => idempotent + race-safe."""
    if not booking_ref:
        return {"handled": False, "matched_count": 0}
    try:
        bid = oid(booking_ref)
    except HTTPException:
        return {"handled": False, "matched_count": 0}
    if etype == "booking.approved":
        b = await db.bookings.find_one_and_update(
            {"_id": bid, "approval_status": "pending"},
            {"$set": {"approval_status": "approved", "approved_at": now_iso()}})
        if not b:
            return {"handled": True, "matched_count": 0, "idempotent": True}
        await apply_approval_financials(b)
        await audit(str(bid), "seller_approved", "rahal_owner")
        return {"handled": True, "matched_count": 1}
    b = await db.bookings.find_one_and_update(
        {"_id": bid, "approval_status": "pending"},
        {"$set": {"approval_status": "rejected", "status": "cancelled",
                  "rejected_at": now_iso(), "rejection_reason": reason,
                  "cancellation_status": "none",
                  "cancellation": {"type": "seller_rejected", "reason": reason}}})
    if not b:
        return {"handled": True, "matched_count": 0, "idempotent": True}
    await refund_and_release(b)
    await audit(str(bid), "seller_rejected", "rahal_owner", reason=reason)
    return {"handled": True, "matched_count": 1}



@router.post("/webhooks")
async def rahal_webhook(request: Request, x_rahal_signature: str = Header(default="")):
    raw = await request.body()
    if not _verify_hmac(raw, x_rahal_signature):
        raise HTTPException(status_code=401, detail="Invalid signature")
    try:
        event = json.loads(raw)
    except (ValueError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="Malformed JSON body")
    data = event.get("data") if isinstance(event.get("data"), dict) else event
    # Rahal sends the envelope as {id, type, timestamp, data}; older payloads use "event".
    etype = event.get("event") or event.get("type")
    ref = event.get("package_ref") or data.get("package_ref") or data.get("rahal_ref")
    event_id = event.get("id") or event.get("event_id")
    # Idempotency: a webhook carrying the same event id is applied at most once
    if event_id:
        prior = await db.rahal_inbound_log.find_one({"event_id": event_id, "handled": True})
        if prior:
            return {"received": True, "event": etype, "handled": True,
                    "matched_count": prior.get("matched_count", 0), "idempotent": True}
    log_res = await db.rahal_inbound_log.insert_one({
        "event": etype, "event_id": event_id, "package_ref": ref, "body": event,
        "handled": False, "matched_count": 0, "received_at": now_iso(),
    })
    # --- Booking approval/rejection from Rahal (match by booking_ref = bookings._id) ---
    if etype in ("booking.approved", "booking.rejected"):
        bref = data.get("booking_ref") or data.get("meraaj_booking_id") or event.get("booking_ref")
        reason = data.get("reason") or data.get("rejection_reason") or event.get("reason")
        res = await _handle_booking_decision(etype, bref, reason)
        await db.rahal_inbound_log.update_one({"_id": log_res.inserted_id},
            {"$set": {"handled": res.get("handled", False), "matched_count": res.get("matched_count", 0)}})
        return {"received": True, "event": etype, **res}
    # --- Rahal owner's cancellation POSITION (evidence/executed costs only — no money moves) ---
    if etype == "booking.cancellation.position":
        bref = data.get("booking_ref") or event.get("booking_ref")
        matched = 0
        if bref:
            try:
                r = await db.bookings.update_one({"_id": oid(bref)},
                    {"$set": {"cancellation_position": data, "cancellation_position_at": now_iso()},
                     "$push": {"cancellation_positions": data}})
                matched = r.matched_count
            except HTTPException:
                matched = 0
            if matched:
                await audit(bref, "rahal_position", "rahal_owner", reason=data.get("position"),
                            meta={"actual_costs_total": data.get("actual_costs_total")})
            await _store_evidence(bref, data)
        await db.rahal_inbound_log.update_one({"_id": log_res.inserted_id},
            {"$set": {"handled": matched > 0, "matched_count": matched}})
        return {"received": True, "event": etype, "handled": matched > 0, "matched_count": matched}
    # --- Office verification status from Rahal (Rahal = source of truth) ---
    if etype == "office.verification_updated":
        oref = data.get("office_ref") or data.get("tenant_id") or event.get("office_ref")
        status_v = data.get("verification_status") or data.get("status")
        reason_v = data.get("verification_reason") or data.get("reason") or ""
        allowed = {"unverified", "pending_review", "verified", "rejected"}
        matched = 0
        if oref and status_v in allowed:
            r = await db.users.update_one({"rahal_office_ref": oref}, {"$set": {
                "verification_status": status_v, "verification_reason": reason_v,
                "verified_at": now_iso() if status_v == "verified" else None,
                "updated_at": now_iso()}})
            matched = r.matched_count
        await db.rahal_inbound_log.update_one({"_id": log_res.inserted_id},
            {"$set": {"handled": matched > 0, "matched_count": matched}})
        return {"received": True, "event": etype, "handled": matched > 0, "matched_count": matched}
    # --- Cancellation evidence files from Rahal (NO financial effect) ---
    if etype == "booking.cancellation.evidence":
        bref = data.get("booking_ref") or event.get("booking_ref")
        n = await _store_evidence(bref, data)
        await db.rahal_inbound_log.update_one({"_id": log_res.inserted_id},
            {"$set": {"handled": n > 0, "matched_count": n}})
        return {"received": True, "event": etype, "handled": n > 0, "matched_count": n}
    # Matching precedence: meraaj_package_id -> rahal_ref (never by name)
    mid = event.get("meraaj_package_id") or data.get("meraaj_package_id")
    match = None
    if mid:
        try:
            match = {"_id": oid(mid)}
        except Exception:
            match = None
    if match is None and ref:
        match = {"rahal_ref": ref}
    recognized = True
    matched_count = 0
    if etype == "inventory.updated" and match:
        r = await db.packages.update_one(match, {"$set": {"available_seats": data.get("available_seats", event.get("available_seats", 0))}})
        matched_count = r.matched_count
    elif etype in ("package.deactivated", "package.deleted", "package.removed", "package.disabled") and match:
        r = await db.packages.update_one(match, {"$set": {"status": "unlisted", "is_active": False}})
        matched_count = r.matched_count
    elif etype == "package.activated" and match:
        r = await db.packages.update_one(match, {"$set": {"status": "listed", "is_active": True}})
        matched_count = r.matched_count
    elif etype == "package.updated" and match:
        # Same v2 Adapter as /share, but only touch fields present in the delta (no blanking)
        updates = _adapt_partial(data)
        active_flag = event.get("active")
        if active_flag is None:
            active_flag = data.get("active")
        raw_status = str(event.get("status", data.get("status", ""))).lower()
        if active_flag is False or raw_status in ("inactive", "deleted", "disabled", "cancelled", "removed"):
            updates["status"] = "unlisted"
            updates["is_active"] = False
        else:
            # Rahal emits NO package.activated and sends NO status field on re-open;
            # a package.updated for a known package implicitly means active -> re-list it.
            updates["status"] = "listed"
            updates["is_active"] = True
        if updates:
            r = await db.packages.update_one(match, {"$set": updates})
            matched_count = r.matched_count
        # Keep the source-of-truth mirror authoritative after an update
        if matched_count:
            pkgdoc = await db.packages.find_one(match)
            rref = (pkgdoc or {}).get("rahal_ref") or ref
            if rref:
                await db.rahal_packages.update_one({"rahal_ref": rref}, {"$set": {
                    "payload": data,
                    "room_pricing": (pkgdoc or {}).get("room_pricing", []),
                    "transports": (pkgdoc or {}).get("transports", []),
                    "components": (pkgdoc or {}).get("components", []),
                    "images": (pkgdoc or {}).get("images", []),
                    "features": (pkgdoc or {}).get("features", []),
                    "updated_at": now_iso(),
                }})
    else:
        recognized = False
    # handled = event recognized AND (targeted event actually matched a package)
    handled = recognized and (matched_count > 0 if match else True)
    # Keep the dedicated Rahal mirror collection in sync for deactivate/delete/activate
    if ref and etype in ("package.deactivated", "package.deleted", "package.removed",
                         "package.disabled", "package.activated"):
        mirror_status = "listed" if etype == "package.activated" else "unlisted"
        await db.rahal_packages.update_one({"rahal_ref": ref},
                                           {"$set": {"status": mirror_status, "updated_at": now_iso()}})
    await db.rahal_inbound_log.update_one(
        {"_id": log_res.inserted_id},
        {"$set": {"handled": handled, "matched_count": matched_count}})
    return {"received": True, "event": etype, "handled": handled, "matched_count": matched_count}


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def verify_rahal_sso_token(token: str) -> dict:
    """Rahal SSO token = base64url(JSON) + '.' + HMAC-SHA256-hex(base64url). NOT a JWT.
    Verifies the signature constant-time with the shared secret, then iss/aud/exp."""
    if not token or token.count(".") != 1:
        raise HTTPException(status_code=401, detail="رمز دخول رحّال غير صالح")
    payload_b64, sig = token.split(".")
    expected = hmac.new(_shared_secret().encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, (sig or "").strip().lower()):
        raise HTTPException(status_code=401, detail="توقيع رمز الدخول من رحّال غير صالح")
    try:
        claims = json.loads(_b64url_decode(payload_b64))
    except Exception:
        raise HTTPException(status_code=401, detail="حمولة رمز الدخول غير صالحة")
    if not isinstance(claims, dict):
        raise HTTPException(status_code=401, detail="حمولة رمز الدخول غير صالحة")
    if claims.get("iss") != "rahaal-erp" or claims.get("aud") != "meraaj-network":
        raise HTTPException(status_code=401, detail="جهة الإصدار أو الجمهور غير صحيحة في رمز الدخول")
    exp = claims.get("exp")
    try:
        if exp is None or int(time.time()) > int(exp):
            raise HTTPException(status_code=401, detail="انتهت صلاحية رمز الدخول")
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="صلاحية رمز الدخول غير صالحة")
    return claims


async def _remote_verify(token: str):
    """Optional LIVE verification against Rahal (POST /api/meraaj/sso/verify). Authoritative
    for permissions/identity when reachable; falls back to local claims when not configured."""
    url = os.environ.get("RAHAL_SSO_VERIFY_URL", "").strip()
    if not url:
        base = os.environ.get("RAHAL_BASE_URL", "").strip()
        url = base.rstrip("/") + "/api/meraaj/sso/verify" if base else ""
    if not url:
        return None
    try:
        async with httpx.AsyncClient(timeout=5) as h:
            r = await h.post(url, json={"token": token})
        if r.status_code == 200:
            body = r.json()
            if isinstance(body, dict) and isinstance(body.get("data"), dict):
                return body["data"]
            return body if isinstance(body, dict) else None
    except Exception:
        return None
    return None


async def _store_evidence(booking_ref, data):
    """Persist cancellation evidence file references from Rahal. NO financial effect."""
    if not booking_ref:
        return 0
    items = data.get("evidence") or data.get("evidences") or data.get("documents") or []
    if not isinstance(items, list):
        items = []
    if isinstance(data.get("file_ref"), str):
        items = items + [data]
    count = 0
    for it in items:
        if not isinstance(it, dict):
            continue
        await db.cancellation_evidence.insert_one({
            "booking_id": str(booking_ref),
            "file_ref": it.get("file_ref") or it.get("id"),
            "doc_type": (it.get("type") or it.get("doc_type") or "other"),
            "metadata": it.get("metadata") or {},
            "download_ref": it.get("download_ref") or it.get("signed_url") or it.get("url"),
            "source": "rahal", "created_at": now_iso(),
        })
        count += 1
    return count


def _norm_perms(raw):
    """Normalize an incoming permission set (list OR {perm: true} map) to the allowed set."""
    if isinstance(raw, dict):
        raw = [k for k, v in raw.items() if v]
    if not isinstance(raw, list):
        return []
    return sorted({str(p) for p in raw if str(p) in RAHAL_PERMISSIONS})


@router.post("/offices/link")
async def link_office(request: Request,
                      x_rahal_api_key: str = Header(default=""),
                      x_rahal_signature: str = Header(default=""),
                      x_meraaj_signature: str = Header(default="")):
    """Inbound account-link from Rahal (HMAC-signed). Idempotently create OR link a Meraaj
    office to a Rahal office_ref and store the office permissions. Never creates a duplicate
    for the same office_ref/email."""
    raw = await request.body()
    sig = x_rahal_signature or x_meraaj_signature
    authorized = (x_rahal_api_key and x_rahal_api_key == _shared_secret()) or _verify_hmac(raw, sig)
    if not authorized:
        raise HTTPException(status_code=401, detail="Invalid Rahal credentials (API key or HMAC signature)")
    try:
        body = json.loads(raw)
    except (ValueError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="Malformed JSON body")
    office_ref = body.get("office_ref") or body.get("office_id")
    if not office_ref:
        raise HTTPException(status_code=400, detail="office_ref مطلوب")
    email = (body.get("email") or f"{str(office_ref).lower()}@rahal.local").lower()
    perms = _norm_perms(body.get("permissions"))
    user_ref = body.get("user_ref") or body.get("rahal_user_id")

    set_fields = {
        "source": "rahal", "rahal_office_ref": office_ref,
        "rahal_permissions": perms, "status": "active", "updated_at": now_iso(),
    }
    for k in ("office_name", "owner_name", "phone", "governorate", "address", "commercial_license"):
        if body.get(k) is not None:
            set_fields[k] = body.get(k)
    if user_ref is not None:
        set_fields["rahal_user_ref"] = user_ref

    existing = await db.users.find_one({"$or": [{"rahal_office_ref": office_ref}, {"email": email}]})
    if existing:
        await db.users.update_one({"_id": existing["_id"]}, {"$set": set_fields})
        return {"ok": True, "office_id": str(existing["_id"]), "action": "updated",
                "permissions": perms, "rahal_office_ref": office_ref}
    doc = {
        "email": email, "password_hash": None, "role": "office",
        "office_name": body.get("office_name") or f"مكتب رحال {office_ref}".strip(),
        "owner_name": body.get("owner_name") or "",
        "phone": body.get("phone") or "", "governorate": body.get("governorate") or "",
        "address": body.get("address") or "", "commercial_license": body.get("commercial_license") or "",
        "wallet": _empty_wallet(), "created_at": now_iso(),
        **set_fields,
    }
    try:
        res = await db.users.insert_one(doc)
        office_id = str(res.inserted_id)
    except Exception:
        again = await db.users.find_one({"rahal_office_ref": office_ref})
        if not again:
            raise
        await db.users.update_one({"_id": again["_id"]}, {"$set": set_fields})
        office_id = str(again["_id"])
    return {"ok": True, "office_id": office_id, "action": "created",
            "permissions": perms, "rahal_office_ref": office_ref}


class SSOInput(BaseModel):
    token: str


@router.post("/sso")
async def rahal_sso(payload: SSOInput):
    """Signed-JWT SSO handoff from Rahal. Token is HS256-signed with the shared secret
    and carries the office identity. Auto-provisions/links a Meraaj office account and
    returns a Meraaj session token used inside the embedded iframe."""
    claims = verify_rahal_sso_token(payload.token)

    office_ref = claims.get("tenant_id") or claims.get("office_ref") or claims.get("office_id")
    email = (claims.get("email") or "").lower()
    if not office_ref or not email:
        raise HTTPException(status_code=400, detail="بيانات المكتب ناقصة في رمز الدخول")

    # Live verification with Rahal wins for permissions/identity when reachable.
    live = await _remote_verify(payload.token)
    src = live if isinstance(live, dict) else claims
    perms = _norm_perms(src.get("permissions"))
    has_perms = src.get("permissions") is not None
    rahal_role = src.get("role") or claims.get("role")
    user_ref = (src.get("user_ref") or claims.get("user_ref")
                or src.get("meraaj_office_id") or claims.get("meraaj_office_id"))

    user = await db.users.find_one({"$or": [{"rahal_office_ref": office_ref}, {"email": email}]})
    if not user:
        doc = {
            "email": email,
            "password_hash": None,
            "role": "office",
            "office_name": claims.get("office_name") or claims.get("name") or "مكتب رحال",
            "owner_name": claims.get("owner_name") or claims.get("name") or "",
            "phone": claims.get("phone") or "",
            "governorate": claims.get("governorate") or "",
            "address": claims.get("address") or "",
            "commercial_license": claims.get("commercial_license") or "",
            "status": "active",
            "source": "rahal",
            "rahal_office_ref": office_ref,
            "rahal_permissions": perms if has_perms else None,
            "rahal_user_ref": user_ref,
            "rahal_role": rahal_role,
            "wallet": _empty_wallet(),
            "created_at": now_iso(),
        }
        res = await db.users.insert_one(doc)
        doc["_id"] = res.inserted_id
        user = doc
    else:
        upd = {}
        if not user.get("rahal_office_ref"):
            upd["rahal_office_ref"] = office_ref
            upd["source"] = "rahal"
        if has_perms:
            upd["rahal_permissions"] = perms   # refresh permissions from Rahal on every login
        if user_ref is not None and not user.get("rahal_user_ref"):
            upd["rahal_user_ref"] = user_ref
        if rahal_role:
            upd["rahal_role"] = rahal_role
        if upd:
            await db.users.update_one({"_id": user["_id"]}, {"$set": upd})
            user = await db.users.find_one({"_id": user["_id"]})

    token = create_access_token(str(user["_id"]), user["email"], user.get("role", "office"))
    return {"access_token": token, "user": serialize(user)}


@router.get("/status")
async def integration_status():
    """Public status endpoint to confirm the integration layer is live."""
    return {
        "integration": "rahal",
        "status": "ready",
        "endpoints": {
            "share": "/api/integrations/rahal/packages/share",
            "webhooks": "/api/integrations/rahal/webhooks",
        },
        "receives": ["package_type", "name/title", "start_date/end_date", "currency",
                     "room_pricing[]", "package_transports[]", "components[]", "hotels[]",
                     "features[]", "image_url/images[]", "pricing (flat, backward-compat)"],
        "contract": "rahal_v2 (with legacy flat fallback)",
        "auth": "HMAC-SHA256 via MERAAJ_SHARED_SECRET (X-Rahal-Signature / X-Meraaj-Signature); legacy X-Rahal-Api-Key also accepted",
        "webhook_events": ["package.deactivated", "package.deleted", "package.removed",
                           "package.disabled", "package.activated", "package.updated", "inventory.updated"],
    }
