import asyncio
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
from db import db  # noqa: E402


async def main():
    print("active rules:", await db.commission_rules.count_documents({"active": True}))
    print("all rules:", await db.commission_rules.count_documents({}))
    async for l in db.credit_limits.find({}):
        print("limit:", l.get("office_id"), l.get("currency"), l.get("limit"), l.get("status"))
    neg = []
    async for u in db.users.find({"role": {"$in": ["office", "individual"]}},
                                 {"office_name": 1, "wallet": 1}):
        for c in ("SAR", "USD"):
            a = ((u.get("wallet") or {}).get(c) or {}).get("available", 0)
            if a and a < 0:
                neg.append((u.get("office_name"), c, a))
    print("negative wallets:", neg)

asyncio.run(main())
