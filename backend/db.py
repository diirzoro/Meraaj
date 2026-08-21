import os
from datetime import datetime, timezone
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


async def adjust_wallet(office_id, *, available=0.0, pending=0.0, total=0.0):
    if available == 0 and pending == 0 and total == 0:
        return
    await db.users.update_one(
        {"_id": oid(office_id)},
        {"$inc": {
            "wallet.available": available,
            "wallet.pending": pending,
            "wallet.total": total,
        }},
    )


async def log_txn(office_id, txn_type: str, amount: float, description: str, ref: str = None, meta: dict = None):
    await db.transactions.insert_one({
        "office_id": str(office_id),
        "type": txn_type,
        "amount": amount,
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


SAR_PER_USD = float(os.environ.get("SAR_PER_USD", "3.77"))


def to_usd(amount, currency: str) -> float:
    """Convert a native amount to the USD base used by all wallets."""
    if (currency or "USD") == "SAR":
        return round(float(amount) / SAR_PER_USD, 2)
    return round(float(amount), 2)


async def log_platform_revenue(amount: float, description: str, ref: str = None):
    await db.platform_revenue.insert_one({
        "amount": amount,
        "description": description,
        "ref": ref,
        "created_at": now_iso(),
    })
