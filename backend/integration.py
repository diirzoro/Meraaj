"""Rahal integration layer — server-to-server endpoints & webhooks.

These endpoints are ready to receive data from Rahal once their dev team is done.
They authenticate with a shared API key (X-Rahal-Api-Key) and verify HMAC signatures.
Currently active and functional (no external Rahal calls are mocked into the UI).
"""
import os
import hmac
import hashlib
import json
import asyncio
import jwt
import httpx
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Request, Header, Depends
from db import db, serialize, oid, now_iso
from security import create_access_token, require_admin

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
                "X-Meraaj-Signature": f"sha256={sig}",
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


async def notify_rahal(event: str, payload: dict):
    """Persist the event to an outbox (never lost) then deliver in the background."""
    body = {"event": event, **payload, "occurred_at": now_iso()}
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
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
        raw = json.dumps(d["payload"], ensure_ascii=False).encode("utf-8")
        await _deliver(d["_id"], url, raw, d["signature"])
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
            net = base.get("net", 0)
        if sale is None:
            cust = base.get("customer", 0)
            sale = cust.get("adult", 0) if isinstance(cust, dict) else cust
        if comm is None:
            comm = base.get("commission", 0)
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
    if has("images", "image_url"):
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
        "source": "rahal",
        "rahal_ref": ref_v,
        "rahal_office_ref": office_ref,
        "seller_id": str(seller["_id"]) if seller else None,
        "seller_office_name": seller["office_name"] if seller else (body.get("office_name") or "مكتب رحال"),
    }
    if existing:
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
            "images": mapped["images"],
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
    return {"remote_id": pkg_id, "meraaj_package_id": pkg_id, "status": "listed",
            "market_url": f"{os.environ.get('FRONTEND_URL','')}/market/{pkg_id}"}


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
        r = await db.packages.update_one(match, {"$set": {"status": "unlisted"}})
        matched_count = r.matched_count
    elif etype == "package.activated" and match:
        r = await db.packages.update_one(match, {"$set": {"status": "listed"}})
        matched_count = r.matched_count
    elif etype == "package.updated" and match:
        # Same v2 Adapter as /share, but only touch fields present in the delta (no blanking)
        updates = _adapt_partial(data)
        raw_status = str(event.get("status", data.get("status", ""))).lower()
        if event.get("active") is False or raw_status in ("inactive", "deleted", "disabled", "cancelled", "removed"):
            updates["status"] = "unlisted"
        elif event.get("active") is True or raw_status in ("active", "listed"):
            updates["status"] = "listed"
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


class SSOInput(BaseModel):
    token: str


@router.post("/sso")
async def rahal_sso(payload: SSOInput):
    """Signed-JWT SSO handoff from Rahal. Token is HS256-signed with the shared secret
    and carries the office identity. Auto-provisions/links a Meraaj office account and
    returns a Meraaj session token used inside the embedded iframe."""
    try:
        claims = jwt.decode(payload.token, _shared_secret(), algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="انتهت صلاحية رمز الدخول من رحال")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="رمز دخول غير صالح من رحال")

    office_ref = claims.get("office_ref")
    email = (claims.get("email") or "").lower()
    if not office_ref or not email:
        raise HTTPException(status_code=400, detail="بيانات المكتب ناقصة في رمز الدخول")

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
            "wallet": _empty_wallet(),
            "created_at": now_iso(),
        }
        res = await db.users.insert_one(doc)
        doc["_id"] = res.inserted_id
        user = doc
    elif not user.get("rahal_office_ref"):
        await db.users.update_one({"_id": user["_id"]}, {"$set": {"rahal_office_ref": office_ref}})

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
