"""Rahal integration layer — server-to-server endpoints & webhooks.

These endpoints are ready to receive data from Rahal once their dev team is done.
They authenticate with a shared API key (X-Rahal-Api-Key) and verify HMAC signatures.
Currently active and functional (no external Rahal calls are mocked into the UI).
"""
import os
import hmac
import hashlib
import json
from fastapi import APIRouter, HTTPException, Request, Header
from db import db, serialize, oid, now_iso

router = APIRouter(prefix="/api/integrations/rahal", tags=["rahal-integration"])


def _shared_secret() -> str:
    return os.environ["RAHAL_SHARED_SECRET"]


def _check_api_key(key: str):
    if key != _shared_secret():
        raise HTTPException(status_code=401, detail="Invalid Rahal API key")


def _verify_hmac(raw_body: bytes, signature: str) -> bool:
    if not signature:
        return False
    expected = hmac.new(_shared_secret().encode(), raw_body, hashlib.sha256).hexdigest()
    provided = signature.replace("sha256=", "")
    return hmac.compare_digest(expected, provided)


@router.post("/packages/share")
async def share_package(request: Request, x_rahal_api_key: str = Header(default="")):
    _check_api_key(x_rahal_api_key)
    body = await request.json()
    pricing = body.get("pricing", {})
    existing = await db.packages.find_one({"rahal_ref": body["package_ref"]})
    doc = {
        "type": body.get("type", "umrah"),
        "title": body["title"],
        "description": body.get("description", ""),
        "departure_date": body.get("departure_date", ""),
        "return_date": body.get("return_date", ""),
        "departure_city": body.get("departure_city", ""),
        "transport": body.get("transport", ""),
        "hotels": body.get("hotels", []),
        "images": body.get("images", []),
        "net_cost_per_seat": pricing.get("net_cost_per_seat", 0),
        "final_sale_price": pricing.get("final_sale_price", 0),
        "buyer_office_commission": pricing.get("buyer_office_commission", 0),
        "currency": pricing.get("currency", "USD"),
        "total_seats": body.get("available_seats", 0),
        "available_seats": body.get("available_seats", 0),
        "status": "listed",
        "source": "rahal",
        "rahal_ref": body["package_ref"],
        "rahal_office_ref": body.get("office_ref"),
    }
    if existing:
        await db.packages.update_one({"_id": existing["_id"]}, {"$set": doc})
        pkg_id = str(existing["_id"])
    else:
        doc["created_at"] = now_iso()
        res = await db.packages.insert_one(doc)
        pkg_id = str(res.inserted_id)
    return {"meraaj_package_id": pkg_id, "status": "listed",
            "market_url": f"{os.environ.get('FRONTEND_URL','')}/market/{pkg_id}"}


@router.post("/webhooks")
async def rahal_webhook(request: Request, x_rahal_signature: str = Header(default="")):
    raw = await request.body()
    if not _verify_hmac(raw, x_rahal_signature):
        raise HTTPException(status_code=401, detail="Invalid signature")
    event = json.loads(raw)
    etype = event.get("event")
    ref = event.get("package_ref")
    if etype == "inventory.updated" and ref:
        await db.packages.update_one({"rahal_ref": ref},
                                     {"$set": {"available_seats": event.get("available_seats", 0)}})
    elif etype == "package.deactivated" and ref:
        await db.packages.update_one({"rahal_ref": ref}, {"$set": {"status": "unlisted"}})
    elif etype == "package.updated" and ref:
        updates = {k: v for k, v in event.items() if k not in ("event", "event_id", "package_ref", "occurred_at")}
        if updates:
            await db.packages.update_one({"rahal_ref": ref}, {"$set": updates})
    return {"received": True, "event": etype}


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
        "auth": "X-Rahal-Api-Key + HMAC-SHA256 (X-Rahal-Signature)",
    }
