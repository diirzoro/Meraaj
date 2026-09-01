"""Probe: is a FROZEN office actually blocked from booking when its wallet is funded?"""
import sys
sys.path.insert(0, "/app/backend/tests")
from conftest import API, new_office, make_package  # noqa: E402
from test_admin_enterprise_b2 import login, fund, book, avail  # noqa: E402

admin = login("abuzay84@gmail.com", "Meraaj@2026")
seller = login("seller@test.com", "Test@1234")
pkg = make_package(seller, currency="SAR")

s, u, _ = new_office("FRZPROBE")
fund(admin, s, 5000, "SAR")
r = admin.post(f"{API}/admin/credit/{u['id']}/freeze",
               json={"currency": "SAR", "frozen": True, "reason": "اختبار التجميد مع رصيد كافٍ"})
print("freeze:", r.status_code, r.text[:120])
rb = book(s, pkg["id"])
print("booking by FROZEN but funded office ->", rb.status_code, rb.text[:180])
print("wallet after:", avail(s, "SAR"))
# also check the exposed office id 6a874bfef5d41cc3c4bb2f19
d = admin.get(f"{API}/admin/credit", params={"only_exposed": False}).json()
row = [x for x in d["items"] if x["office_id"] == "6a874bfef5d41cc3c4bb2f19"]
print("leftover frozen office:", row[:1])
# cleanup
admin.post(f"{API}/admin/credit/{u['id']}/freeze",
           json={"currency": "SAR", "frozen": False, "reason": "تنظيف بعد الاختبار"})
