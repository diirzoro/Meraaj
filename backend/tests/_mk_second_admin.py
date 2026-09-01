"""One-off helper: create a SECOND super_admin for Maker-Checker testing."""
import asyncio
import os
import sys

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
from db import db, now_iso, empty_wallet  # noqa: E402
from security import hash_password  # noqa: E402

EMAIL = "qa.checker@qa-example.com"
PASSWORD = "Checker@2026"


async def main():
    u = await db.users.find_one({"email": EMAIL})
    if u:
        await db.users.update_one({"_id": u["_id"]}, {"$set": {
            "password_hash": hash_password(PASSWORD), "role": "super_admin",
            "status": "active", "force_logout_at": None}})
        print("updated", str(u["_id"]))
        return
    res = await db.users.insert_one({
        "email": EMAIL, "password_hash": hash_password(PASSWORD), "role": "super_admin",
        "office_name": "QA Checker (test)", "status": "active", "wallet": empty_wallet(),
        "created_at": now_iso()})
    print("created", str(res.inserted_id))


asyncio.run(main())
