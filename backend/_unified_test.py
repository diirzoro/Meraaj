import json, hmac, hashlib, httpx
from dotenv import dotenv_values

env = dotenv_values("/app/backend/.env")
SECRET = env["MERAAJ_SHARED_SECRET"].encode()
API = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/")

def sign(raw): return "sha256=" + hmac.new(SECRET, raw, hashlib.sha256).hexdigest()
def post(path, body):
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    r = httpx.post(f"{API}{path}", content=raw,
                   headers={"Content-Type": "application/json", "X-Rahal-Signature": sign(raw)}, timeout=30)
    return r.status_code, (r.json() if r.headers.get("content-type","").startswith("application/json") else r.text)

REF = "RHL-UNIFIED-9100"
# NEW unified Rahal schema: net / commission / customer are ALL per-category objects
share = {
    "package_ref": REF, "office_ref": "RHL-OFF-UNI", "office_name": "مكتب رحال الموحّد",
    "package_type": "umrah", "name": "برنامج الهيكل الموحّد", "start_date": "2026-12-01", "end_date": "2026-12-10",
    "currency": "SAR", "available_seats": 30,
    "room_pricing": [
        {"room_type": "double",
         "net": {"adult": 1000, "child": 800, "infant": 400},
         "commission": {"adult": 200, "child": 150, "infant": 50},
         "customer": {"adult": 1500, "child": 1300, "infant": 700}},
        {"room_type": "quad",
         "net": {"adult": 700, "child": 550, "infant": 250},
         "commission": {"adult": 150, "child": 120, "infant": 40},
         "customer": {"adult": 1100, "child": 900, "infant": 300}},
    ],
}
sc, resp = post("/api/integrations/rahal/packages/share", share)
print("SHARE(unified objects):", sc)
pid = resp.get("meraaj_package_id")
g = httpx.get(f"{API}/api/packages/{pid}", timeout=30).json()
print("  stored net_cost_per_seat (scalar?):", g.get("net_cost_per_seat"), "| final_sale_price:", g.get("final_sale_price"))
print("  room_pricing preserved:", json.dumps(g.get("room_pricing"), ensure_ascii=False))

# Book QUAD with adult+child+infant as an individual (B2C) -> expect 1100+900+300 = 2300
TOK = httpx.post(f"{API}/api/auth/login", json={"email":"user1@qa-example.com","password":"Test@1234"}).json()["access_token"]
sc, b = httpx.post(f"{API}/api/bookings", headers={"Authorization":f"Bearer {TOK}"}, json={
    "package_id": pid, "room_type": "quad",
    "registrants": [
        {"name":"بالغ","passport_no":"A1","age":30,"category":"adult"},
        {"name":"طفل","passport_no":"C1","age":8,"category":"child"},
        {"name":"رضيع","passport_no":"I1","age":1,"category":"infant"},
    ]}, timeout=30).json() if True else (0,{})
sc2 = None
print("BOOK quad a+c+i -> amount_charged:", b.get("amount_charged"), "(expect 2300)", "| room_type:", b.get("room_type"), "| detail:", b.get("detail"))
print("PKG_ID", pid)
