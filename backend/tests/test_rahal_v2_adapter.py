"""Rahal Contract v2 Adapter tests — share, webhook update, idempotency, auth, sanitization."""
import os
import json
import time
import hmac
import hashlib
import uuid

import pytest
import requests
from dotenv import dotenv_values

fe = dotenv_values("/app/frontend/.env")
be = dotenv_values("/app/backend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or fe.get("REACT_APP_BACKEND_URL")).rstrip("/")
MERAAJ_SECRET = be.get("MERAAJ_SHARED_SECRET")
RAHAL_SECRET = be.get("RAHAL_SHARED_SECRET")
SHARE = f"{BASE_URL}/api/integrations/rahal/packages/share"
HOOK = f"{BASE_URL}/api/integrations/rahal/webhooks"

STAMP = uuid.uuid4().hex[:8]
V2_REF = f"V2-QA-{STAMP}"
LEGACY_REF = f"V2-QA-LEG-{STAMP}"
OFFICE_REF = f"RHL-V2-{STAMP}"


def sign(raw: bytes, secret=None):
    return "sha256=" + hmac.new((secret or MERAAJ_SECRET).encode(), raw, hashlib.sha256).hexdigest()


def post_signed(url, body, secret=None, headers=None):
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    h = {"Content-Type": "application/json", "X-Rahal-Signature": sign(raw, secret)}
    if headers:
        h.update(headers)
    return requests.post(url, data=raw, headers=h, timeout=30)


def v2_payload(**over):
    p = {
        "package_ref": V2_REF,
        "office_ref": OFFICE_REF,
        "office_name": "مكتب رحال v2",
        "package_type": "umrah",
        "name": "برنامج عمرة v2",
        "start_date": "2026-11-01",
        "end_date": "2026-11-10",
        "currency": "SAR",
        "room_pricing": [
            {"room_type": "double", "net": 3000, "commission": 300, "customer": 3600},
            {"room_type": "triple", "net": 2600, "commission": 250, "customer": 3100},
            {"room_type": "quad", "net": 2300, "commission": 200, "customer": 2800},
        ],
        "package_transports": [{"type": "bus", "company": "النقل الجماعي", "seats": 49, "route": "مكة-المدينة"}],
        "components": [{"name": "تأشيرة"}, {"name": "إعاشة"}],
        "hotels": [{"name": "فندق مكة", "city": "مكة", "nights": 5}],
        "features": ["طيران مباشر", "مرشد"],
        "image_url": ["https://img/x.jpg", "https://img/y.jpg"],
        "available_seats": 40,
    }
    p.update(over)
    return p


# ---------- fixtures ----------
@pytest.fixture(scope="module")
def office_client():
    s = requests.Session()
    email = f"TEST_office_{STAMP}@qa-v2.com"
    r = s.post(f"{BASE_URL}/api/auth/register", json={
        "account_type": "office", "email": email, "password": "Test@1234",
        "phone": f"0555{STAMP[:6]}", "governorate": "مكة", "office_name": "TEST office v2",
        "owner_name": "QA Owner"})
    assert r.status_code in (200, 201), r.text
    tok = r.json().get("access_token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def individual_client():
    s = requests.Session()
    email = f"TEST_indiv_{STAMP}@qa-v2.com"
    r = s.post(f"{BASE_URL}/api/auth/register", json={
        "account_type": "individual", "email": email, "password": "Test@1234",
        "phone": f"0566{STAMP[:6]}", "governorate": "مكة", "name": "QA Individual"})
    assert r.status_code in (200, 201), r.text
    tok = r.json().get("access_token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def shared_v2():
    r = post_signed(SHARE, v2_payload())
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("remote_id") and d.get("meraaj_package_id") == d["remote_id"]
    return d["meraaj_package_id"]


# ---------- SHARE v2 mapping ----------
class TestShareV2Mapping:
    def test_share_v2_maps_all_fields(self, shared_v2, office_client):
        g = office_client.get(f"{BASE_URL}/api/packages/{shared_v2}")
        assert g.status_code == 200, g.text
        p = g.json()
        assert "_id" not in p
        assert p["type"] == "umrah"
        assert p["title"] == "برنامج عمرة v2"
        assert p["departure_date"] == "2026-11-01"
        assert p["return_date"] == "2026-11-10"
        assert p["currency"] == "SAR"
        assert len(p["room_pricing"]) == 3
        base = [r for r in p["room_pricing"] if r["room_type"] == "double"][0]
        assert base == {"room_type": "double", "net": 3000, "commission": 300, "customer": 3600}
        assert len(p["transports"]) == 1 and p["transports"][0]["seats"] == 49
        assert p["transports"][0]["company"] == "النقل الجماعي"
        assert [c["name"] for c in p["components"]] == ["تأشيرة", "إعاشة"]
        assert p["hotels"][0]["name"] == "فندق مكة"
        assert p["features"] == ["طيران مباشر", "مرشد"]
        assert p["images"] == ["https://img/x.jpg", "https://img/y.jpg"]
        assert p["available_seats"] == 40

    def test_flat_pricing_derived_from_base_room(self, shared_v2, office_client):
        p = office_client.get(f"{BASE_URL}/api/packages/{shared_v2}").json()
        assert p["net_cost_per_seat"] == 3000
        assert p["final_sale_price"] == 3600
        assert p["buyer_office_commission"] == 300

    def test_legacy_flat_payload_no_regression(self, office_client):
        body = {
            "package_ref": LEGACY_REF, "office_ref": OFFICE_REF, "type": "tourism",
            "title": "TEST legacy flat", "departure_date": "2026-12-01", "return_date": "2026-12-05",
            "pricing": {"net_cost_per_seat": 900, "final_sale_price": 1200,
                        "buyer_office_commission": 100, "currency": "USD"},
            "available_seats": 12,
        }
        r = post_signed(SHARE, body)
        assert r.status_code == 200, r.text
        pid = r.json()["meraaj_package_id"]
        p = office_client.get(f"{BASE_URL}/api/packages/{pid}").json()
        assert p["type"] == "tourism"
        assert p["title"] == "TEST legacy flat"
        assert p["departure_date"] == "2026-12-01" and p["return_date"] == "2026-12-05"
        assert p["currency"] == "USD"
        assert (p["net_cost_per_seat"], p["final_sale_price"], p["buyer_office_commission"]) == (900, 1200, 100)
        assert p["available_seats"] == 12

    def test_image_url_string_accepted(self, office_client):
        ref = f"V2-QA-IMG-{STAMP}"
        r = post_signed(SHARE, v2_payload(package_ref=ref, image_url="https://img/only.jpg"))
        assert r.status_code == 200, r.text
        p = office_client.get(f"{BASE_URL}/api/packages/{r.json()['meraaj_package_id']}").json()
        assert p["images"] == ["https://img/only.jpg"]

    def test_share_same_ref_updates_not_duplicates(self, shared_v2):
        r = post_signed(SHARE, v2_payload(name="برنامج عمرة v2 معدل"))
        assert r.status_code == 200
        assert r.json()["meraaj_package_id"] == shared_v2


# ---------- Auth ----------
class TestAuth:
    def test_wrong_signature_401(self):
        raw = json.dumps(v2_payload(package_ref="V2-QA-BAD")).encode()
        r = requests.post(SHARE, data=raw, headers={
            "Content-Type": "application/json", "X-Rahal-Signature": "sha256=deadbeef"}, timeout=30)
        assert r.status_code == 401

    def test_no_signature_401(self):
        r = requests.post(SHARE, json=v2_payload(package_ref="V2-QA-BAD"), timeout=30)
        assert r.status_code == 401

    def test_meraaj_signature_header_accepted(self):
        body = v2_payload(package_ref=f"V2-QA-MS-{STAMP}")
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        r = requests.post(SHARE, data=raw, headers={
            "Content-Type": "application/json", "X-Meraaj-Signature": sign(raw)}, timeout=30)
        assert r.status_code == 200, r.text

    def test_legacy_api_key_accepted(self):
        r = requests.post(SHARE, json=v2_payload(package_ref=f"V2-QA-KEY-{STAMP}"),
                          headers={"X-Rahal-Api-Key": RAHAL_SECRET}, timeout=30)
        assert r.status_code == 200, r.text

    def test_malformed_json_valid_signature_400(self):
        raw = b'{"package_ref": "V2-QA-BROKEN",'
        r = requests.post(SHARE, data=raw, headers={
            "Content-Type": "application/json", "X-Rahal-Signature": sign(raw)}, timeout=30)
        assert r.status_code == 400, r.text

    def test_webhook_wrong_signature_401(self):
        raw = json.dumps({"event": "package.updated"}).encode()
        r = requests.post(HOOK, data=raw, headers={"X-Rahal-Signature": "sha256=bad"}, timeout=30)
        assert r.status_code == 401

    def test_webhook_malformed_json_400(self):
        raw = b'{"event":'
        r = requests.post(HOOK, data=raw, headers={
            "Content-Type": "application/json", "X-Rahal-Signature": sign(raw)}, timeout=30)
        assert r.status_code == 400


# ---------- package.updated via adapter ----------
class TestWebhookUpdate:
    def test_package_updated_v2_applies_full_adapter(self, shared_v2, office_client):
        evt = {
            "id": f"evt-upd-{STAMP}", "event": "package.updated",
            "data": v2_payload(
                name="برنامج عمرة v2 — عنوان جديد",
                package_type="tourism",
                start_date="2026-12-05", end_date="2026-12-15",
                room_pricing=[{"room_type": "double", "net": 4000, "commission": 400, "customer": 4800},
                              {"room_type": "triple", "net": 3500, "commission": 350, "customer": 4200}],
                package_transports=[{"type": "plane", "company": "طيران", "seats": 180}],
                components=[{"name": "تأشيرة"}, {"name": "نقل"}, {"name": "إعاشة"}],
                available_seats=25),
        }
        r = post_signed(HOOK, evt)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["handled"] is True and d["matched_count"] == 1
        p = office_client.get(f"{BASE_URL}/api/packages/{shared_v2}").json()
        assert p["title"] == "برنامج عمرة v2 — عنوان جديد"
        assert p["type"] == "tourism"
        assert p["departure_date"] == "2026-12-05" and p["return_date"] == "2026-12-15"
        assert len(p["room_pricing"]) == 2
        assert p["net_cost_per_seat"] == 4000 and p["final_sale_price"] == 4800
        assert p["transports"][0]["type"] == "plane"
        assert len(p["components"]) == 3
        assert p["available_seats"] == 25

    def test_update_by_rahal_ref_never_creates_duplicate(self, shared_v2, office_client):
        # title changed again with the same rahal_ref -> must update the same doc
        evt = {"id": f"evt-upd2-{STAMP}", "event": "package.updated",
               "package_ref": V2_REF,
               "data": v2_payload(name="عنوان مختلف تماماً")}
        r = post_signed(HOOK, evt)
        assert r.status_code == 200 and r.json()["matched_count"] == 1
        p = office_client.get(f"{BASE_URL}/api/packages/{shared_v2}").json()
        assert p["title"] == "عنوان مختلف تماماً"

    def test_update_by_meraaj_package_id(self, shared_v2, office_client):
        evt = {"id": f"evt-mid-{STAMP}", "event": "package.updated",
               "meraaj_package_id": shared_v2,
               "data": {"name": "عنوان بالمعرف", "package_type": "umrah"}}
        r = post_signed(HOOK, evt)
        assert r.status_code == 200, r.text
        assert r.json()["matched_count"] == 1
        p = office_client.get(f"{BASE_URL}/api/packages/{shared_v2}").json()
        assert p["title"] == "عنوان بالمعرف"

    def test_idempotency_same_event_id_applied_once(self, shared_v2, office_client):
        eid = f"evt-idem-{STAMP}"
        evt = {"id": eid, "event": "inventory.updated", "package_ref": V2_REF,
               "data": {"available_seats": 7}}
        r1 = post_signed(HOOK, evt)
        assert r1.status_code == 200 and r1.json()["handled"] is True
        # second delivery with a different payload but same event id must not apply
        evt2 = {"id": eid, "event": "inventory.updated", "package_ref": V2_REF,
                "data": {"available_seats": 99}}
        r2 = post_signed(HOOK, evt2)
        assert r2.status_code == 200
        assert r2.json().get("idempotent") is True
        assert r2.json()["handled"] is True
        p = office_client.get(f"{BASE_URL}/api/packages/{shared_v2}").json()
        assert p["available_seats"] == 7


# ---------- Sanitization ----------
class TestSanitization:
    def test_office_sees_full_room_pricing(self, shared_v2, office_client):
        p = office_client.get(f"{BASE_URL}/api/packages/{shared_v2}").json()
        assert "net_cost_per_seat" in p and "buyer_office_commission" in p
        for r in p["room_pricing"]:
            assert set(["room_type", "net", "commission", "customer"]).issubset(r.keys())

    def test_individual_sanitized(self, shared_v2, individual_client):
        r = individual_client.get(f"{BASE_URL}/api/packages/{shared_v2}")
        assert r.status_code == 200, r.text
        p = r.json()
        for k in ("net_cost_per_seat", "buyer_office_commission", "child_net_cost",
                  "child_commission", "infant_net_cost", "infant_commission"):
            assert k not in p, f"{k} leaked to individual"
        for rp in p["room_pricing"]:
            assert set(rp.keys()) == {"room_type", "customer"}, rp
        assert p["final_sale_price"] > 0

    def test_anonymous_sanitized(self, shared_v2):
        r = requests.get(f"{BASE_URL}/api/packages/{shared_v2}", timeout=30)
        assert r.status_code == 200, r.text
        p = r.json()
        assert "net_cost_per_seat" not in p and "buyer_office_commission" not in p
        for rp in p["room_pricing"]:
            assert set(rp.keys()) == {"room_type", "customer"}

    def test_market_list_sanitized_for_anonymous(self):
        r = requests.get(f"{BASE_URL}/api/packages", timeout=30)
        assert r.status_code == 200
        for p in r.json():
            assert "net_cost_per_seat" not in p
            for rp in (p.get("room_pricing") or []):
                assert set(rp.keys()) == {"room_type", "customer"}


# ---------- cleanup ----------
@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    import asyncio
    import sys
    sys.path.insert(0, "/app/backend")
    from motor.motor_asyncio import AsyncIOMotorClient

    async def _c():
        cl = AsyncIOMotorClient(be["MONGO_URL"])
        d = cl[be["DB_NAME"]]
        await d.packages.delete_many({"rahal_ref": {"$regex": f"V2-QA-.*{STAMP}"}})
        await d.packages.delete_many({"rahal_ref": {"$in": [V2_REF, LEGACY_REF]}})
        await d.rahal_packages.delete_many({"rahal_ref": {"$regex": f"V2-QA"}})
        await d.users.delete_many({"email": {"$regex": f"{STAMP}@qa-v2.com"}})
        await d.users.delete_many({"rahal_office_ref": OFFICE_REF})
        await d.rahal_inbound_log.delete_many({"event_id": {"$regex": STAMP}})
        cl.close()

    asyncio.get_event_loop().run_until_complete(_c())
