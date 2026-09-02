"""Cleanup of iteration_13 QA artifacts (staff logins/records, suspension flags)."""
import os
from dotenv import dotenv_values
from pymongo import MongoClient

env = dotenv_values("/app/backend/.env")
cli = MongoClient(env["MONGO_URL"])
db = cli[env["DB_NAME"]]

# 1) staff LOGIN user documents created by this QA round (keep staffqa@test.com drill account)
q = {"email": {"$regex": "^test_qa_(ui_)?(b)?staff|^test_qa_dup", "$options": "i"}}
print("staff users to remove:", [u["email"] for u in db.users.find(q, {"email": 1})])
ids = [str(u["_id"]) for u in db.users.find(q, {"_id": 1})]
print("delete users:", db.users.delete_many(q).deleted_count)
print("delete user_roles:", db.user_roles.delete_many({"user_id": {"$in": ids}}).deleted_count)

# 2) staff RECORDS created by QA (name prefixed TEST_QA)
print("delete office_staff:", db.office_staff.delete_many(
    {"name": {"$regex": "TEST_QA"}}).deleted_count)

# 3) no account may stay suspended / force-logged-out because of QA
susp = list(db.users.find({"status": "suspended"}, {"email": 1}))
print("still suspended:", [u["email"] for u in susp])
print("force_logout flags set:",
      [u.get("email") for u in db.users.find({"force_logout_at": {"$ne": None}}, {"email": 1})])

# 4) credit limits must stay at 0 / active
print("credit_limits non-zero:", list(db.credit_limits.find(
    {"$or": [{"limit": {"$gt": 0}}, {"status": {"$ne": "active"}}]},
    {"office_id": 1, "limit": 1, "status": 1, "_id": 0})))

# 5) no reconciliation opening entries written
print("opening_balance txns:", db.transactions.count_documents({"type": "opening_balance"}))

# 6) settings must not carry QA sections beyond defaults
s = db.settings.find_one({"_id": "system"}) or {}
print("settings keys:", sorted(k for k in s if k != "_id"))
print("backups files:", len([f for f in os.listdir("/app/backups") if f.startswith("meraaj-")]))
print("2FA docs:", db.admin_2fa.count_documents({}) if "admin_2fa" in db.list_collection_names() else "n/a")
