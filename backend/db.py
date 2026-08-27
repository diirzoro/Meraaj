import os
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def oid(value) -> ObjectId:
    if isinstance(value, ObjectId):
        return value
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=404, detail="العنصر غير موجود")


def serialize(doc):
    """Convert a Mongo document (or list) into JSON-safe dict with id string."""
    if doc is None:
        return None
    if isinstance(doc, list):
        return [serialize(d) for d in doc]
    out = dict(doc)
    if "_id" in out:
        out["id"] = str(out.pop("_id"))
    for k, v in list(out.items()):
        if isinstance(v, ObjectId):
            out[k] = str(v)
    out.pop("password_hash", None)
    return out


SAR_PER_USD = float(os.environ.get("SAR_PER_USD", "3.77"))


from typing import Annotated
from pydantic import BeforeValidator

def _norm_ccy(v):
    s = str(v).strip().upper()
    if s not in ("SAR", "USD"):
        raise ValueError("العملة يجب أن تكون SAR أو USD")
    return s

# Strict currency field: normalizes case and rejects anything other than SAR/USD
CurrencyField = Annotated[str, BeforeValidator(_norm_ccy)]


def empty_wallet() -> dict:
    z = lambda: {"available": 0.0, "pending": 0.0, "total": 0.0}
    return {"SAR": z(), "USD": z()}


def other_ccy(ccy: str) -> str:
    return "USD" if ccy == "SAR" else "SAR"


def convert(amount, from_ccy: str, to_ccy: str) -> float:
    """Convert between SAR and USD at the fixed rate (used ONLY to cover a purchase shortfall)."""
    a = float(amount)
    if from_ccy == to_ccy:
        return round(a, 2)
    if from_ccy == "SAR":  # SAR -> USD
        return round(a / SAR_PER_USD, 2)
    return round(a * SAR_PER_USD, 2)  # USD -> SAR


def wallet_available(wallet: dict, ccy: str) -> float:
    return ((wallet or {}).get(ccy) or {}).get("available", 0.0)


def plan_debit(wallet: dict, ccy: str, required: float):
    """Plan a purchase debit: take from the program-currency balance first, then cover any
    shortfall from the other currency at the fixed rate. Returns {SAR:amt, USD:amt} in each
    native currency, or None if total funds are insufficient."""
    ccy = "SAR" if ccy == "SAR" else "USD"
    other = other_ccy(ccy)
    avail_prog = wallet_available(wallet, ccy)
    from_prog = min(avail_prog, required)
    shortfall = round(required - from_prog, 2)
    from_other = 0.0
    if shortfall > 0.005:
        from_other = convert(shortfall, ccy, other)
        if round(from_other - wallet_available(wallet, other), 2) > 0.005:
            return None
    return {ccy: round(from_prog, 2), other: round(from_other, 2)}


async def adjust_wallet(office_id, currency: str = "USD", *, available=0.0, pending=0.0, total=0.0):
    if available == 0 and pending == 0 and total == 0:
        return
    c = "SAR" if currency == "SAR" else "USD"
    await db.users.update_one(
        {"_id": oid(office_id)},
        {"$inc": {
            f"wallet.{c}.available": available,
            f"wallet.{c}.pending": pending,
            f"wallet.{c}.total": total,
        }},
    )


async def log_txn(office_id, txn_type: str, amount: float, description: str, ref: str = None,
                  currency: str = "USD", meta: dict = None):
    await db.transactions.insert_one({
        "office_id": str(office_id),
        "type": txn_type,
        "amount": amount,
        "currency": "SAR" if currency == "SAR" else "USD",
        "description": description,
        "ref": ref,
        "meta": meta or {},
        "created_at": now_iso(),
    })


def platform_pct() -> float:
    return float(os.environ.get("PLATFORM_COMMISSION_PCT", "0.10"))


def cancel_fee_pct() -> float:
    return float(os.environ.get("CANCEL_ADMIN_FEE_PCT", "0.02"))


def marketer_pct() -> float:
    return float(os.environ.get("MARKETER_COMMISSION_PCT", "0.20"))


async def log_platform_revenue(amount: float, description: str, ref: str = None, currency: str = "USD"):
    await db.platform_revenue.insert_one({
        "amount": amount,
        "currency": "SAR" if currency == "SAR" else "USD",
        "description": description,
        "ref": ref,
        "created_at": now_iso(),
    })



def approval_timeout_hours() -> float:
    return float(os.environ.get("APPROVAL_TIMEOUT_HOURS", "24"))


def iso_in_hours(hours: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


async def audit(booking_id, event: str, actor_type: str, *, actor_id=None, reason=None, meta=None):
    """Append-only booking audit trail entry (Enterprise timeline)."""
    await db.booking_events.insert_one({
        "booking_id": str(booking_id), "event": event, "actor_type": actor_type,
        "actor_id": actor_id, "reason": reason, "meta": meta or {}, "at": now_iso(),
    })
