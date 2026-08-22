"""Seed a real v2 share + an office & individual account for the iteration-8 UI run."""
import hashlib, hmac, json, sys
import requests
from dotenv import dotenv_values

BE = dotenv_values("/app/backend/.env")
FE = dotenv_values("/app/frontend/.env")
API = FE["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
SECRET = BE["MERAAJ_SHARED_SECRET"]
IMAGE = "https://images.unsplash.com/photo-1519058082700-08a0b56da9b4?w=1200&q=80"
REF = "E2E8-UI-1"

body = {
    "package_ref": REF, "office_ref": "RHL-E2E8-UI", "office_name": "مكتب رحال UI",
    "package_type": "umrah", "name": "E2E8 برنامج واجهة رحال",
    "description": "وصف واجهة", "departure_city": "بغداد",
    "start_date": "2026-11-01", "end_date": "2026-11-12", "currency": "SAR",
    "available_seats": 42,
    "room_pricing": [
        {"room_type": "double", "net": 1000, "commission": 150, "customer": 1300},
        {"room_type": "triple", "net": 900, "commission": 140, "customer": 1180},
        {"room_type": "quad", "net": 820, "commission": 130, "customer": 1050}],
    "package_transports": [
        {"type": "bus", "company": "شركة النقل الأولى", "bus_type": "VIP 45", "seats": 45},
        {"type": "bus", "company": "شركة النقل الثانية", "bus_type": "Sleeper 30", "seats": 30}],
    "hotels": [{"city": "مكة", "name": "فندق الصفوة", "nights": 5, "distance_m": 250},
               {"city": "المدينة", "name": "فندق الأنصار", "nights": 4, "distance_m": 400}],
    "components": [{"name": "تأشيرة", "included": True}, {"name": "إعاشة", "included": True},
                   {"name": "زيارات", "included": False}],
    "features": ["واي فاي", "مرشد ديني", "قريب من الحرم"],
    "images": [IMAGE],
}
raw = json.dumps(body, ensure_ascii=False).encode()
sig = hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
r = requests.post(f"{API}/integrations/rahal/packages/share", data=raw, headers={
    "Content-Type": "application/json", "X-Rahal-Signature": f"sha256={sig}"})
print("share", r.status_code, r.text[:200])
pid = r.json()["meraaj_package_id"]

for acct, extra in (("office", {"office_name": "TEST_E2E8_UIOFF", "owner_name": "QA"}),
                    ("individual", {"name": "TEST_E2E8_UIIND"})):
    email = f"test_e2e8_ui_{acct}@qa-example.com"
    p = {"account_type": acct, "email": email, "password": "Test@1234",
         "phone": "0770000000", "governorate": "بغداد", **extra}
    rr = requests.post(f"{API}/auth/register", json=p)
    if rr.status_code != 200:
        rr = requests.post(f"{API}/auth/login", json={"email": email, "password": "Test@1234"})
    print(acct, email, rr.status_code)

print("PACKAGE_ID", pid)
print("URL", FE["REACT_APP_BACKEND_URL"] + "/market/" + pid)
