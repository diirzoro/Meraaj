import asyncio
import os
import subprocess
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
API = subprocess.run(["bash", "-c", "grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d= -f2"],
                     capture_output=True, text=True).stdout.strip()


def login():
    r = subprocess.run(["curl", "-s", "-o", "/tmp/s", "-w", "%{http_code}", "-X", "POST",
                        f"{API}/api/auth/login", "-H", "Content-Type: application/json",
                        "-d", '{"email":"buyer@test.com","password":"Test@1234"}'],
                       capture_output=True, text=True)
    return r.stdout, open("/tmp/s").read()[:120]


async def main():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = c[os.environ["DB_NAME"]]
    u = await db.users.find_one({"email": "buyer@test.com"})
    await db.users.update_one({"_id": u["_id"]}, {"$set": {"status": "suspended"}})
    print("suspended ->", login())
    await db.users.update_one({"_id": u["_id"]}, {"$set": {"status": u.get("status", "active")}})
    await db.users.update_one({"_id": u["_id"]}, {"$set": {"status": "active"}})
    print("reactivated ->", login()[0])
    print("final status:", (await db.users.find_one({"_id": u["_id"]}, {"status": 1}))["status"])

asyncio.run(main())
