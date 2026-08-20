import os
import time
import uuid
import requests
import pytest
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base.rstrip("/")
API = f"{BASE_URL}/api"

backend_env = dotenv_values("/app/backend/.env")
ADMIN_EMAIL = "abuzay84@gmail.com"
ADMIN_PASSWORD = "Meraaj@2026"
RAHAL_SECRET = backend_env.get("RAHAL_SHARED_SECRET", "rahal_meraaj_shared_secret_key_2026")
PLATFORM_PCT = float(backend_env.get("PLATFORM_COMMISSION_PCT", "0.10"))
CANCEL_FEE_PCT = float(backend_env.get("CANCEL_ADMIN_FEE_PCT", "0.02"))


def client(token=None):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="session")
def admin():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    if r.status_code != 200:
        pytest.fail(f"Admin login failed {r.status_code}: {r.text[:300]}")
    return client(r.json()["access_token"])


def new_office(prefix="TEST"):
    """Register a fresh office; returns (session, user_dict, token)."""
    email = f"test_{prefix}_{uuid.uuid4().hex[:8]}@qa-example.com".lower()
    payload = {
        "email": email, "password": "Test@1234", "office_name": f"TEST_{prefix}",
        "owner_name": "QA Owner", "phone": "0770000000",
        "governorate": "بغداد", "address": "شارع الاختبار",
    }
    r = requests.post(f"{API}/auth/register", json=payload)
    assert r.status_code == 200, f"register failed: {r.status_code} {r.text[:300]}"
    data = r.json()
    return client(data["access_token"]), data["user"], data["access_token"]


def fund_office(admin_session, office_session, amount):
    r = office_session.post(f"{API}/wallet/topups",
                            json={"amount": amount, "method": "bank", "receipt_url": "http://x/r.png"})
    assert r.status_code == 200, r.text[:300]
    tid = r.json()["id"]
    r2 = admin_session.post(f"{API}/admin/topups/{tid}/review", json={"approve": True})
    assert r2.status_code == 200, r2.text[:300]
    return tid


def make_package(seller_session, **over):
    body = {
        "type": "umrah", "title": f"TEST_باكج_{uuid.uuid4().hex[:6]}", "description": "اختبار",
        "departure_date": "2026-09-01", "return_date": "2026-09-10",
        "departure_city": "بغداد", "transport": "طيران",
        "hotels": [{"city": "مكة", "name": "فندق التجربة", "nights": 5, "distance_m": 300}],
        "images": [], "net_cost_per_seat": 1000.0, "final_sale_price": 1300.0,
        "buyer_office_commission": 200.0, "currency": "USD", "total_seats": 10,
    }
    body.update(over)
    r = seller_session.post(f"{API}/packages", json=body)
    assert r.status_code == 200, f"package create failed {r.status_code}: {r.text[:300]}"
    return r.json()


def wallet_of(session):
    r = session.get(f"{API}/wallet")
    assert r.status_code == 200, r.text[:300]
    return r.json()
