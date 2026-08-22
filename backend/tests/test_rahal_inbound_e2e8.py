"""Iteration 8 — ONLY the two remaining inbound Rahaal -> Meraaj tests.

TEST 1: POST /api/integrations/rahal/packages/share with a FULL Contract v2 body,
        signed HMAC-SHA256 with the SHARED secret (MERAAJ_SHARED_SECRET).
TEST 2: POST /api/integrations/rahal/webhooks event=package.updated partial delta
        (no-blank, no-duplicate, match by ref/id not name, idempotency, 401 on bad sig).
"""
import hashlib
import hmac
import json
import os
import time
import uuid

import pytest
import requests
from dotenv import dotenv_values

fe = dotenv_values("/app/frontend/.env")
be = dotenv_values("/app/backend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or fe.get("REACT_APP_BACKEND_URL")).rstrip("/")
SECRET = os.environ.get("MERAAJ_SHARED_SECRET") or be.get("MERAAJ_SHARED_SECRET")
assert SECRET, "MERAAJ_SHARED_SECRET missing"

SHARE = f"{BASE_URL}/api/integrations/rahal/packages/share"
HOOK = f"{BASE_URL}/api/integrations/rahal/webhooks"
IMAGE_URL = "https://images.unsplash.com/photo-1519677100203-a0e668c92439?w=1200&q=70"
IMAGE_URL_2 = "https://images.unsplash.com/photo-1564769625905-50e93615e769?w=1200&q=70"

REF = f"TEST-E2E8-{uuid.uuid4().hex[:8].upper()}"
OFFICE_REF = f"TEST-RHL-OFF-{uuid.uuid4().hex[:6].upper()}"

state = {}


def sign(raw: bytes) -> str:
    return "sha256=" + hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()


def post_signed(url, body, sig_header="X-Rahal-Signature", bad=False):
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    sig = sign(raw) if not bad else "sha256=" + "0" * 64
    return requests.post(url, data=raw, headers={
        "Content-Type": "application/json", sig_header: sig}, timeout=45)


def full_v2_body():
    return {
        "package_ref": REF,
        "office_ref": OFFICE_REF,
        "office_name": "مكتب رحال للاختبار E2E8",
        "owner_name": "مالك رحال",
        "package_type": "umrah",
        "name": "TEST_E2E8 برنامج عمرة رمضان الشامل",
        "description": "برنامج عمرة شامل 10 ليالٍ مع إقامة فندقية ونقل بري.",
        "departure_city": "صنعاء",
        "start_date": "2026-09-01",
        "end_date": "2026-09-11",
        "currency": "SAR",
        "available_seats": 44,
        "room_pricing": [
            {"room_type": "double", "net": 1000, "commission": 100, "customer": 1200},
            {"room_type": "triple", "net": 900, "commission": 90, "customer": 1080},
            {"room_type": "quad", "net": 800, "commission": 80, "customer": 960},
        ],
        "package_transports": [
            {"type": "bus", "company": "شركة النقل الأولى", "bus_type": "VIP", "seats": 24},
            {"type": "bus", "company": "شركة النقل الثانية", "bus_type": "عادي", "seats": 20},
        ],
        "hotels": [
            {"city": "مكة", "name": "فندق أجياد مكة", "nights": 6, "distance_m": 400},
            {"city": "المدينة", "name": "فندق دار الهجرة", "nights": 4, "distance_m": 250},
        ],
        "components": [
            {"name": "تأشيرة", "included": True},
            {"name": "وجبات إفطار", "included": True},
            {"name": "زيارات", "included": False},
        ],
        "features": ["واي فاي", "مرشد ديني", "تأمين صحي"],
        "image_url": [IMAGE_URL, IMAGE_URL_2],
    }


@pytest.fixture(scope="module")
def office_client():
    """Fresh OFFICE account (sees net + commission)."""
    s = requests.Session()
    email = f"test_e2e8_office_{uuid.uuid4().hex[:6]}@qa-example.com"
    r = s.post(f"{BASE_URL}/api/auth/register", json={
        "account_type": "office", "email": email, "password": "Test@1234",
        "phone": "770000111", "governorate": "صنعاء",
        "office_name": "TEST_E2E8 Office", "owner_name": "QA Owner"}, timeout=30)
    assert r.status_code == 200, r.text[:400]
    tok = r.json()["access_token"]
    s.headers.update({"Authorization": f"Bearer {tok}"})
    state["office_email"] = email
    state["office_token"] = tok
    yield s


# ---------------- TEST 1 — SHARE (full Contract v2) ----------------
class TestShareFullV2:
    def test_01_share_accepted_and_returns_ids(self):
        r = post_signed(SHARE, full_v2_body())
        assert r.status_code == 200, f"{r.status_code} {r.text[:500]}"
        d = r.json()
        assert d.get("remote_id"), d
        assert d.get("meraaj_package_id") == d["remote_id"]
        assert d.get("status") == "listed"
        state["pkg_id"] = d["remote_id"]

    def test_02_office_get_package_maps_all_v2_fields(self, office_client):
        pid = state["pkg_id"]
        r = office_client.get(f"{BASE_URL}/api/packages/{pid}", timeout=30)
        assert r.status_code == 200, r.text[:400]
        p = r.json()
        assert "_id" not in p, "MongoDB _id leaked in response"
        # package_type -> type
        assert p["type"] == "umrah"
        assert p["title"] == "TEST_E2E8 برنامج عمرة رمضان الشامل"
        # dates mapped
        assert p["departure_date"] == "2026-09-01"
        assert p["return_date"] == "2026-09-11"
        assert p["currency"] == "SAR"
        assert p["available_seats"] == 44 and p["total_seats"] == 44
        assert p["rahal_ref"] == REF and p["source"] == "rahal"
        # 3 room types with full office pricing
        rp = {r_["room_type"]: r_ for r_ in p["room_pricing"]}
        assert len(p["room_pricing"]) == 3, p["room_pricing"]
        assert set(rp) == {"double", "triple", "quad"}
        for rt, net, comm, cust in [("double", 1000, 100, 1200), ("triple", 900, 90, 1080),
                                    ("quad", 800, 80, 960)]:
            assert rp[rt]["net"] == net and rp[rt]["commission"] == comm and rp[rt]["customer"] == cust, rp[rt]
        # flat backward-compat pricing derived from double
        assert p["net_cost_per_seat"] == 1000 and p["final_sale_price"] == 1200
        assert p["buyer_office_commission"] == 100
        # transports / hotels / components / features / images
        assert len(p["transports"]) == 2, p["transports"]
        assert len(p["hotels"]) == 2, p["hotels"]
        assert len(p["components"]) == 3, p["components"]
        assert len(p["features"]) == 3
        assert p["images"] == [IMAGE_URL, IMAGE_URL_2]
        assert p["transport"], "flat transport string not derived"

    def test_03_stored_image_url_is_reachable_200(self, office_client):
        p = office_client.get(f"{BASE_URL}/api/packages/{state['pkg_id']}", timeout=30).json()
        for u in p["images"]:
            resp = requests.get(u, timeout=30)
            assert resp.status_code == 200, f"image {u} -> {resp.status_code}"
            assert resp.headers.get("content-type", "").startswith("image/"), resp.headers

    def test_04_non_office_pricing_is_stripped(self):
        r = requests.get(f"{BASE_URL}/api/packages/{state['pkg_id']}", timeout=30)
        assert r.status_code == 200
        p = r.json()
        assert "net_cost_per_seat" not in p and "buyer_office_commission" not in p
        assert all("net" not in x and "commission" not in x for x in p["room_pricing"])

    def test_05_bad_signature_share_401(self):
        r = post_signed(SHARE, {**full_v2_body(), "package_ref": REF + "-BAD"}, bad=True)
        assert r.status_code == 401, f"{r.status_code} {r.text[:300]}"


# ---------------- TEST 2 — package.updated webhook ----------------
class TestPackageUpdatedWebhook:
    def test_10_partial_update_by_ref_no_blank_no_duplicate(self, office_client):
        before = office_client.get(f"{BASE_URL}/api/packages/{state['pkg_id']}", timeout=30).json()
        ev_id = f"evt-{uuid.uuid4().hex[:10]}"
        state["ev_id"] = ev_id
        body = {
            "id": ev_id,
            "event": "package.updated",
            "data": {
                "package_ref": REF,
                "name": "TEST_E2E8 برنامج عمرة معدّل (اسم جديد)",
                "room_pricing": [
                    {"room_type": "double", "net": 1050, "commission": 120, "customer": 1300},
                    {"room_type": "triple", "net": 900, "commission": 90, "customer": 1080},
                    {"room_type": "quad", "net": 800, "commission": 80, "customer": 960},
                ],
                "available_seats": 30,
            },
        }
        r = post_signed(HOOK, body)
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        assert d["handled"] is True and d["matched_count"] == 1, d
        after = office_client.get(f"{BASE_URL}/api/packages/{state['pkg_id']}", timeout=30).json()
        # (c) matched by rahal_ref even though the name changed -> SAME record
        assert after["title"] == "TEST_E2E8 برنامج عمرة معدّل (اسم جديد)"
        assert after["available_seats"] == 30 and after["total_seats"] == 30
        rp = {x["room_type"]: x for x in after["room_pricing"]}
        assert rp["double"]["customer"] == 1300 and rp["double"]["net"] == 1050
        assert len(after["room_pricing"]) == 3
        # (b) untouched fields NOT blanked
        for f in ("description", "departure_city", "transport", "currency",
                  "departure_date", "return_date", "type"):
            assert after[f] == before[f], f"{f} changed/blanked: {before[f]!r} -> {after[f]!r}"
        for f in ("hotels", "components", "features", "images", "transports"):
            assert after[f] == before[f], f"{f} blanked: {after[f]!r}"

    def test_11_no_duplicate_package_for_ref(self, office_client):
        r = office_client.get(f"{BASE_URL}/api/packages", timeout=30)
        assert r.status_code == 200
        same = [p for p in r.json() if p.get("rahal_ref") == REF]
        assert len(same) == 1, f"expected 1 package for ref, got {len(same)}"

    def test_12_idempotency_same_event_id(self, office_client):
        body = {
            "id": state["ev_id"], "event": "package.updated",
            "data": {"package_ref": REF, "available_seats": 999},
        }
        r = post_signed(HOOK, body)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d.get("idempotent") is True, d
        after = office_client.get(f"{BASE_URL}/api/packages/{state['pkg_id']}", timeout=30).json()
        assert after["available_seats"] == 30, "idempotent replay applied a second effect"

    def test_13_update_matching_by_meraaj_package_id(self, office_client):
        body = {
            "id": f"evt-{uuid.uuid4().hex[:10]}", "event": "package.updated",
            "meraaj_package_id": state["pkg_id"],
            "data": {"meraaj_package_id": state["pkg_id"], "available_seats": 25,
                     "name": "TEST_E2E8 مطابقة بالمعرّف"},
        }
        r = post_signed(HOOK, body)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["matched_count"] == 1, r.json()
        after = office_client.get(f"{BASE_URL}/api/packages/{state['pkg_id']}", timeout=30).json()
        assert after["available_seats"] == 25
        assert after["title"] == "TEST_E2E8 مطابقة بالمعرّف"
        assert len(after["room_pricing"]) == 3 and after["hotels"]

    def test_14_webhook_bad_signature_401(self):
        r = post_signed(HOOK, {"id": f"evt-{uuid.uuid4().hex[:6]}", "event": "package.updated",
                               "data": {"package_ref": REF, "available_seats": 1}}, bad=True)
        assert r.status_code == 401, f"{r.status_code} {r.text[:300]}"

    def test_15_reshare_same_ref_does_not_duplicate(self, office_client):
        r = post_signed(SHARE, full_v2_body())
        assert r.status_code == 200
        assert r.json()["remote_id"] == state["pkg_id"], "re-share created a NEW package"


def test_99_cleanup():
    """Remove TEST_ data created by this suite (packages, mirror, logs, office users)."""
    import asyncio
    import sys
    sys.path.insert(0, "/app/backend")
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    from db import db

    async def run():
        await db.packages.delete_many({"rahal_ref": {"$regex": "^TEST-E2E8-"}})
        await db.rahal_packages.delete_many({"rahal_ref": {"$regex": "^TEST-E2E8-"}})
        await db.rahal_inbound_log.delete_many({"package_ref": {"$regex": "^TEST-E2E8-"}})
        await db.users.delete_many({"rahal_office_ref": {"$regex": "^TEST-RHL-OFF-"}})
        await db.users.delete_many({"email": {"$regex": "^test_e2e8_office_"}})
        left = await db.packages.count_documents({"rahal_ref": REF})
        assert left == 0
    asyncio.get_event_loop().run_until_complete(run()) if False else asyncio.run(run())
