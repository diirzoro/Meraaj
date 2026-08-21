"""One-off migration: convert single-USD wallets into dual-currency wallets.

Old:  wallet = {total, pending, available}                 (USD)
New:  wallet = {SAR:{...}, USD:{available,pending,total}}   (old balance -> USD bucket)

Also backfills `currency` on legacy topups/transfers/withdrawals/transactions/platform_revenue
and on legacy bookings (defaults to USD, since the base was USD before).
Idempotent: skips wallets already migrated.
"""
import os
import asyncio
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent / ".env")
from motor.motor_asyncio import AsyncIOMotorClient

client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]


def _zero():
    return {"available": 0.0, "pending": 0.0, "total": 0.0}


async def migrate_wallets():
    n = 0
    async for u in db.users.find({}):
        w = u.get("wallet") or {}
        if isinstance(w.get("USD"), dict) and isinstance(w.get("SAR"), dict):
            continue  # already migrated
        usd = {
            "available": round(float(w.get("available", 0.0)), 2),
            "pending": round(float(w.get("pending", 0.0)), 2),
            "total": round(float(w.get("total", 0.0)), 2),
        }
        await db.users.update_one({"_id": u["_id"]},
                                  {"$set": {"wallet": {"SAR": _zero(), "USD": usd}}})
        n += 1
    return n


async def backfill_currency():
    counts = {}
    for coll in ("topups", "transfers", "withdrawals", "transactions", "platform_revenue", "bookings"):
        res = await db[coll].update_many({"currency": {"$exists": False}}, {"$set": {"currency": "USD"}})
        counts[coll] = res.modified_count
    return counts


async def main():
    migrated = await migrate_wallets()
    filled = await backfill_currency()
    print(f"Wallets migrated: {migrated}")
    print(f"Currency backfilled: {filled}")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
