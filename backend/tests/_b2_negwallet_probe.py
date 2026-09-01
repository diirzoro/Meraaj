import sys
sys.path.insert(0, "/app/backend/tests")
from conftest import API  # noqa: E402
from test_admin_enterprise_b2 import login  # noqa: E402

admin = login("abuzay84@gmail.com", "Meraaj@2026")
r = admin.get(f"{API}/admin/ledger", params={
    "office_id": "6a874bfef5d41cc3c4bb2f19", "limit": 20})
d = r.json()
print("total txns:", d["total"], "inflow", d["inflow"], "outflow", d["outflow"])
for t in d["items"]:
    print(t["created_at"], t["type"], t["amount"], t["currency"], (t.get("description") or "")[:50])
