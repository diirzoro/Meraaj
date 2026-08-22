import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import dotenv_values
be = dotenv_values("/app/backend/.env")

async def main():
    cl = AsyncIOMotorClient(be["MONGO_URL"]); d = cl[be["DB_NAME"]]
    print("pkgs", (await d.packages.delete_many({"rahal_ref": {"$regex": "^V2-QA"}})).deleted_count)
    print("mirror", (await d.rahal_packages.delete_many({"rahal_ref": {"$regex": "^V2-QA"}})).deleted_count)
    print("users", (await d.users.delete_many({"email": {"$regex": "qa-v2.com$"}})).deleted_count)
    print("rahal offices", (await d.users.delete_many({"rahal_office_ref": {"$regex": "^RHL-V2"}})).deleted_count)
    cl.close()

asyncio.run(main())
