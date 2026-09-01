"""Seed a fresh pending withdrawal + a credit-exposed office for UI testing."""
import sys
sys.path.insert(0, "/app/backend/tests")
from conftest import API, new_office  # noqa: E402
from test_admin_enterprise_b2 import login, fund  # noqa: E402

admin = login("abuzay84@gmail.com", "Meraaj@2026")
s, u, _ = new_office("UIWDR")
fund(admin, s, 800, "SAR")
r = s.post(f"{API}/wallet/withdrawals", json={
    "amount": 120, "currency": "SAR", "method": "bank", "details": "بنك UI - IBAN999"})
print("withdrawal:", r.status_code, r.json().get("id"))
print("office:", u["id"], u["office_name"])
