"""Seed a funded individual marketer (with a pending commission) for UI testing."""
import sys, requests
sys.path.insert(0, "/app/backend/tests")
from conftest import API, new_office, fund_office, make_package, client, ADMIN_EMAIL, ADMIN_PASSWORD, wallet_of
from test_b2c_individual import new_individual

admin = client(requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}).json()["access_token"])
seller, _, _ = new_office("UISELL")
pkg = make_package(seller)
mkt, mkt_user, _ = new_individual("UIMKT")
code = mkt.post(f"{API}/individual/become-marketer").json()["affiliate_code"]
fund_office(admin, mkt, 500)
buyer, _, _ = new_individual("UIBUY")
fund_office(admin, buyer, 1500)
b = buyer.post(f"{API}/bookings", json={"package_id": pkg["id"], "ref": code,
    "registrants": [{"name": "A", "passport_no": "P1", "age": 30}]}).json()
print("MARKETER_EMAIL", mkt_user["email"])
print("WALLET", wallet_of(mkt))
print("BOOKING_COMMISSION", b["marketer_commission"])
