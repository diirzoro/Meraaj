"""Iteration 8 — Full E2E verification of the Meraaj side of the Rahaal Contract v2 link.

Covers: INBOUND real-signed v2 share (all fields), image reachability, share idempotency,
package.updated matching + event-id idempotency, partial-update non-blanking, matching
precedence (never by title), OUTBOUND outbox delivery to RAHAL_WEBHOOK_URL, non-office
sanitization. Signs with the CURRENT MERAAJ_SHARED_SECRET from /app/backend/.env.
"""
import hashlib
import hmac
import json
import os
import time
import uuid

import pytest
import requests
from bson import ObjectId
from dotenv import dotenv_values
from pymongo import MongoClient

from conftest import API, client

BE = dotenv_values("/app/backend/.env")
MERAAJ_SECRET = BE["MERAAJ_SHARED_SECRET"]
RAHAL_WEBHOOK_URL = BE.get("RAHAL_WEBHOOK_URL", "")
MONGO_URL = BE["MONGO_URL"]
DB_NAME = BE["DB_NAME"]

IMAGE_URL = "https://images.unsplash.com/photo-1519058082700-08a0b56da9b4?w=1200&q=80"
STAMP = uuid.uuid4().hex[:6].upper()
PKG_REF = f"E2E8-{STAMP}"
OFFICE_REF = f"RHL-E2E8-{STAMP}"

mdb = MongoClient(MONGO_URL)[DB_NAME]


def sign(raw: bytes) -> str:
    return hmac.new(MERAAJ_SECRET.encode(), raw, hashlib.sha256).hexdigest()


def post_signed(url: str, body: dict, header="X-Rahal-Signature"):
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    return requests.post(url, data=raw, headers={
        "Content-Type": "application/json",
        header: f"sha256={sign(raw)}",
    }, timeout=30)


def v2_body(**over):
    body = {
        "package_ref": PKG_REF,
        "office_ref": OFFICE_REF,
        "office_name": f"مكتب رحال E2E8 {STAMP}",
        "owner_name": "Rahaal Owner",
        "package_type": "umrah",
        "name": f"E2E8 برنامج عمرة {STAMP}",
        "description": "وصف البرنامج القادم من رحال",
        "departure_city": "بغداد",
        "start_date": "2026-11-01",
        "end_date": "2026-11-12",
        "currency": "SAR",
        "available_seats": 42,
        "room_pricing": [
            {"room_type": "double", "net": 1000, "commission": 150, "customer": 1300},
            {"room_type": "triple", "net": 900, "commission": 140, "customer": 1180},
            {"room_type": "quad", "net": 820, "commission": 130, "customer": 1050},
        ],
        "package_transports": [
            {"type": "bus", "company": "شركة النقل الأولى", "bus_type": "VIP 45", "seats": 45},
            {"type": "bus", "company": "شركة النقل الثانية", "bus_type": "Sleeper 30", "seats": 30},
        ],
        "hotels": [
            {"city": "مكة", "name": "فندق الصفوة", "nights": 5, "distance_m": 250},
            {"city": "المدينة", "name": "فندق الأنصار", "nights": 4, "distance_m": 400},
        ],
        "components": [
            {"name": "تأشيرة", "included": True},
            {"name": "إعاشة", "included": True},
            {"name": "زيارات", "included": False},
        ],
        "features": ["واي فاي", "مرشد ديني", "قريب من الحرم"],
        "images": [IMAGE_URL],
    }
    body.update(over)
    return body


@pytest.fixture(scope="module")
def office():
    email = f"test_e2e8_office_{STAMP}@qa-example.com".lower()
    r = requests.post(f"{API}/auth/register", json={
        "account_type": "office", "email": email, "password": "Test@1234",
        "phone": "0771111111", "governorate": "بغداد",
        "office_name": f"TEST_E2E8_OFFICE_{STAMP}", "owner_name": "QA Office Owner",
    })
    assert r.status_code == 200, f"office register failed {r.status_code}: {r.text[:300]}"
    d = r.json()
    return client(d["access_token"]), d["user"], d["access_token"]


@pytest.fixture(scope="module")
def individual():
    email = f"test_e2e8_indiv_{STAMP}@qa-example.com".lower()
    r = requests.post(f"{API}/auth/register", json={
        "account_type": "individual", "email": email, "password": "Test@1234",
        "phone": "0772222222", "governorate": "بغداد", "name": f"TEST_E2E8_IND_{STAMP}",
    })
    assert r.status_code == 200, f"individual register failed {r.status_code}: {r.text[:300]}"
    d = r.json()
    return client(d["access_token"]), d["user"]


@pytest.fixture(scope="module")
def shared_pkg_id():
    r = post_signed(f"{API}/integrations/rahal/packages/share", v2_body())
    assert r.status_code == 200, f"share failed {r.status_code}: {r.text[:400]}"
    pid = r.json()["meraaj_package_id"]
    assert isinstance(pid, str) and len(pid) == 24
    return pid


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    ids = [d["_id"] for d in mdb.packages.find({"rahal_ref": {"$regex": "^E2E8-"}}, {"_id": 1})]
    mdb.packages.delete_many({"rahal_ref": {"$regex": "^E2E8-"}})
    mdb.rahal_packages.delete_many({"rahal_ref": {"$regex": "^E2E8-"}})
    mdb.rahal_inbound_log.delete_many({"package_ref": {"$regex": "^E2E8-"}})
    mdb.users.delete_many({"rahal_office_ref": {"$regex": "^RHL-E2E8-"}})
    mdb.users.delete_many({"email": {"$regex": "^test_e2e8_"}})
    mdb.packages.delete_many({"title": {"$regex": "^TEST_E2E8"}})
    mdb.rahal_outbox.delete_many({"payload.title": {"$regex": "^TEST_E2E8"}})
    print(f"cleanup removed {len(ids)} inbound packages")


# ---------------- INBOUND SHARE (v2, real signature) ----------------
class TestInboundShare:
    def test_hmac_required(self):
        r = requests.post(f"{API}/integrations/rahal/packages/share",
                          data=json.dumps(v2_body()).encode(),
                          headers={"Content-Type": "application/json",
                                   "X-Rahal-Signature": "sha256=deadbeef"}, timeout=30)
        assert r.status_code == 401, r.text[:200]

    def test_all_v2_fields_stored_and_visible_to_office(self, shared_pkg_id, office):
        sess, _, _ = office
        r = sess.get(f"{API}/packages/{shared_pkg_id}")
        assert r.status_code == 200, r.text[:300]
        p = r.json()
        assert "_id" not in p
        # mapping
        assert p["type"] == "umrah"
        assert p["title"] == f"E2E8 برنامج عمرة {STAMP}"
        assert p["departure_date"] == "2026-11-01"
        assert p["return_date"] == "2026-11-12"
        assert p["currency"] == "SAR"
        assert p["description"] == "وصف البرنامج القادم من رحال"
        assert p["departure_city"] == "بغداد"
        assert p["available_seats"] == 42 and p["total_seats"] == 42
        assert p["rahal_ref"] == PKG_REF and p["source"] == "rahal"
        assert p["status"] == "listed"
        # room_pricing: all 3 rooms with net+commission+customer for an office
        rp = {r_["room_type"]: r_ for r_ in p["room_pricing"]}
        assert set(rp) == {"double", "triple", "quad"}, rp
        for rt, net, comm, cust in [("double", 1000, 150, 1300), ("triple", 900, 140, 1180),
                                    ("quad", 820, 130, 1050)]:
            assert rp[rt]["net"] == net and rp[rt]["commission"] == comm and rp[rt]["customer"] == cust
        # flat pricing derived from double
        assert p["net_cost_per_seat"] == 1000
        assert p["final_sale_price"] == 1300
        assert p["buyer_office_commission"] == 150
        # transports (2 buses)
        assert len(p["transports"]) == 2
        assert [t["company"] for t in p["transports"]] == ["شركة النقل الأولى", "شركة النقل الثانية"]
        assert all(t["type"] == "bus" for t in p["transports"])
        assert p["transport"] == "bus"
        # components / hotels / features / images
        assert len(p["components"]) == 3
        assert len(p["hotels"]) == 2
        assert {h["city"] for h in p["hotels"]} == {"مكة", "المدينة"}
        assert p["features"] == ["واي فاي", "مرشد ديني", "قريب من الحرم"]
        assert p["images"] == [IMAGE_URL]

    def test_stored_image_url_actually_loads(self, shared_pkg_id, office):
        sess, _, _ = office
        p = sess.get(f"{API}/packages/{shared_pkg_id}").json()
        assert p["images"], "no images stored"
        for url in p["images"]:
            r = requests.get(url, timeout=30, stream=True,
                             headers={"User-Agent": "Mozilla/5.0 (Meraaj-QA)"})
            assert r.status_code == 200, f"image {url} returned {r.status_code}"
            assert r.headers.get("Content-Type", "").startswith("image/"), r.headers.get("Content-Type")

    def test_share_idempotent_no_duplicate(self, shared_pkg_id):
        r = post_signed(f"{API}/integrations/rahal/packages/share", v2_body(name="E2E8 اسم محدث"))
        assert r.status_code == 200, r.text[:300]
        assert r.json()["meraaj_package_id"] == shared_pkg_id
        assert mdb.packages.count_documents({"rahal_ref": PKG_REF}) == 1
        doc = mdb.packages.find_one({"rahal_ref": PKG_REF})
        assert doc["title"] == "E2E8 اسم محدث"
        # restore original title for downstream tests
        post_signed(f"{API}/integrations/rahal/packages/share", v2_body())


# ---------------- package.updated webhook ----------------
class TestWebhookUpdated:
    def test_update_matches_by_ref_not_title(self, shared_pkg_id, office):
        sess, _, _ = office
        ev = {"id": f"evt-{STAMP}-1", "event": "package.updated",
              "data": v2_body(name=f"E2E8 محدث عبر Webhook {STAMP}", available_seats=30)}
        r = post_signed(f"{API}/integrations/rahal/webhooks", ev)
        assert r.status_code == 200, r.text[:300]
        b = r.json()
        assert b["handled"] is True and b["matched_count"] == 1, b
        assert mdb.packages.count_documents({"rahal_ref": PKG_REF}) == 1
        p = sess.get(f"{API}/packages/{shared_pkg_id}").json()
        assert p["title"] == f"E2E8 محدث عبر Webhook {STAMP}"
        assert p["available_seats"] == 30

    def test_event_id_idempotency(self, shared_pkg_id, office):
        sess, _, _ = office
        eid = f"evt-{STAMP}-idem"
        ev = {"id": eid, "event": "package.updated",
              "data": v2_body(name=f"E2E8 IDEM {STAMP}", available_seats=25)}
        r1 = post_signed(f"{API}/integrations/rahal/webhooks", ev)
        assert r1.status_code == 200 and r1.json()["handled"] is True
        assert r1.json().get("idempotent") is not True
        # second delivery with the SAME event id, mutated payload -> must NOT be applied
        ev2 = {"id": eid, "event": "package.updated",
               "data": v2_body(name="E2E8 SHOULD_NOT_APPLY", available_seats=1)}
        r2 = post_signed(f"{API}/integrations/rahal/webhooks", ev2)
        assert r2.status_code == 200, r2.text[:300]
        assert r2.json()["handled"] is True
        assert r2.json().get("idempotent") is True, r2.json()
        p = sess.get(f"{API}/packages/{shared_pkg_id}").json()
        assert p["title"] == f"E2E8 IDEM {STAMP}"
        assert p["available_seats"] == 25
        assert mdb.packages.count_documents({"rahal_ref": PKG_REF}) == 1

    def test_partial_update_does_not_blank_fields(self, shared_pkg_id, office):
        sess, _, _ = office
        before = sess.get(f"{API}/packages/{shared_pkg_id}").json()
        ev = {"id": f"evt-{STAMP}-partial", "event": "package.updated",
              "data": {"package_ref": PKG_REF, "name": f"E2E8 جزئي {STAMP}", "available_seats": 7}}
        r = post_signed(f"{API}/integrations/rahal/webhooks", ev)
        assert r.status_code == 200 and r.json()["matched_count"] == 1, r.text[:300]
        after = sess.get(f"{API}/packages/{shared_pkg_id}").json()
        assert after["title"] == f"E2E8 جزئي {STAMP}"
        assert after["available_seats"] == 7
        for f in ("description", "departure_city", "transport", "currency",
                  "departure_date", "return_date", "type"):
            assert after[f] == before[f], f"{f} changed/blanked: {before[f]!r} -> {after[f]!r}"
        for f in ("room_pricing", "transports", "components", "hotels", "features", "images"):
            assert after[f] == before[f], f"{f} wiped: {after[f]!r}"
        assert after["net_cost_per_seat"] == before["net_cost_per_seat"]
        assert after["buyer_office_commission"] == before["buyer_office_commission"]

    def test_wrong_title_correct_ref_updates_right_package(self, shared_pkg_id, office):
        sess, _, _ = office
        # create a decoy package with a colliding title via a second share
        decoy_ref = f"E2E8-DECOY-{STAMP}"
        d = post_signed(f"{API}/integrations/rahal/packages/share",
                        v2_body(package_ref=decoy_ref, name="E2E8 عنوان مضلل"))
        assert d.status_code == 200, d.text[:300]
        decoy_id = d.json()["meraaj_package_id"]
        assert decoy_id != shared_pkg_id
        ev = {"id": f"evt-{STAMP}-prec", "event": "package.updated",
              "data": {"package_ref": PKG_REF, "title": "E2E8 عنوان مضلل",
                       "name": "E2E8 عنوان مضلل", "available_seats": 11}}
        r = post_signed(f"{API}/integrations/rahal/webhooks", ev)
        assert r.status_code == 200 and r.json()["matched_count"] == 1, r.text[:300]
        target = sess.get(f"{API}/packages/{shared_pkg_id}").json()
        decoy = sess.get(f"{API}/packages/{decoy_id}").json()
        assert target["available_seats"] == 11
        assert decoy["available_seats"] == 42, "decoy (matched by title) was wrongly updated"

    def test_mirror_refreshed_after_update(self, shared_pkg_id):
        mirror = mdb.rahal_packages.find_one({"rahal_ref": PKG_REF})
        assert mirror is not None
        assert mirror["meraaj_package_id"] == shared_pkg_id
        assert len(mirror.get("room_pricing", [])) == 3
        assert len(mirror.get("transports", [])) == 2


class TestWebhookEdges:
    def test_unmatched_meraaj_package_id_should_not_be_acked_as_handled(self):
        ghost = "6a0000000000000000000000"
        ev = {"id": f"evt-{STAMP}-ghost", "event": "package.updated",
              "data": {"meraaj_package_id": ghost, "name": "ghost"}}
        r = post_signed(f"{API}/integrations/rahal/webhooks", ev)
        assert r.status_code == 200, r.text[:200]
        b = r.json()
        assert b["matched_count"] == 0, b
        assert b["handled"] is False, f"unmatched target ACKed as handled: {b}"

    def test_malformed_room_pricing_does_not_500(self):
        body = v2_body(package_ref=f"E2E8-BAD-{STAMP}", room_pricing={"double": 100})
        r = post_signed(f"{API}/integrations/rahal/packages/share", body)
        assert r.status_code in (200, 400, 422), f"unexpected {r.status_code}: {r.text[:200]}"
        assert r.status_code != 500

    def test_unknown_event_not_handled(self):
        ev = {"id": f"evt-{STAMP}-unknown", "event": "some.unknown.event",
              "data": {"package_ref": PKG_REF}}
        r = post_signed(f"{API}/integrations/rahal/webhooks", ev)
        assert r.status_code == 200
        assert r.json()["handled"] is False


# ---------------- Non-office sanitization ----------------
class TestSanitization:
    def test_individual_sees_customer_only(self, shared_pkg_id, individual):
        sess, _ = individual
        r = sess.get(f"{API}/packages/{shared_pkg_id}")
        assert r.status_code == 200, r.text[:300]
        p = r.json()
        assert "net_cost_per_seat" not in p
        assert "buyer_office_commission" not in p
        for row in p["room_pricing"]:
            assert set(row.keys()) == {"room_type", "customer"}, row

    def test_anonymous_sees_customer_only(self, shared_pkg_id):
        r = requests.get(f"{API}/packages/{shared_pkg_id}", timeout=30)
        assert r.status_code == 200, r.text[:300]
        p = r.json()
        assert "net_cost_per_seat" not in p and "buyer_office_commission" not in p
        for row in p["room_pricing"]:
            assert set(row.keys()) == {"room_type", "customer"}, row

    def test_market_list_sanitized_for_anonymous(self, shared_pkg_id):
        r = requests.get(f"{API}/packages", timeout=60)
        assert r.status_code == 200
        for p in r.json():
            assert "net_cost_per_seat" not in p
            for row in (p.get("room_pricing") or []):
                assert set(row.keys()) == {"room_type", "customer"}


# ---------------- OUTBOUND Meraaj -> Rahaal ----------------
class TestOutbound:
    def test_publish_enqueues_and_delivers(self, office):
        sess, user, _ = office
        title = f"TEST_E2E8_OUT_{STAMP}"
        body = {
            "type": "umrah", "title": title, "description": "outbound e2e",
            "departure_date": "2026-12-01", "return_date": "2026-12-10",
            "departure_city": "بغداد", "transport": "طيران",
            "hotels": [{"city": "مكة", "name": "فندق", "nights": 5, "distance_m": 300}],
            "images": [IMAGE_URL], "net_cost_per_seat": 900.0, "final_sale_price": 1200.0,
            "buyer_office_commission": 150.0, "currency": "SAR", "total_seats": 20,
        }
        r = sess.post(f"{API}/packages", json=body)
        assert r.status_code == 200, r.text[:400]
        pkg_id = r.json()["id"]
        time.sleep(6)  # allow the background outbox delivery to finish
        ev = mdb.rahal_outbox.find_one({"event": "package.published", "payload.package_ref": pkg_id})
        assert ev is not None, "package.published was NOT enqueued in db.rahal_outbox"
        assert ev["payload"]["title"] == title
        assert ev["payload"]["pricing"]["currency"] == "SAR"
        print(f"OUTBOUND package.published -> {RAHAL_WEBHOOK_URL} "
              f"status={ev.get('status')} http_status={ev.get('http_status')} "
              f"attempts={ev.get('attempts')} err={str(ev.get('last_error'))[:200]}")
        assert ev["attempts"] >= 1, "no delivery attempt was made (RAHAL_WEBHOOK_URL not used?)"
        assert ev.get("http_status") is not None, f"no HTTP response from Rahaal: {ev.get('last_error')}"
        # toggle -> deactivated, then -> activated
        t1 = sess.patch(f"{API}/packages/{pkg_id}/toggle")
        assert t1.status_code == 200 and t1.json()["status"] == "unlisted", t1.text[:200]
        t2 = sess.patch(f"{API}/packages/{pkg_id}/toggle")
        assert t2.status_code == 200 and t2.json()["status"] == "listed", t2.text[:200]
        time.sleep(5)
        for evt in ("package.deactivated", "package.activated"):
            d = mdb.rahal_outbox.find_one({"event": evt, "payload.package_ref": pkg_id})
            assert d is not None, f"{evt} was NOT enqueued"
            print(f"OUTBOUND {evt} status={d.get('status')} http_status={d.get('http_status')}")
        # cleanup
        mdb.packages.delete_one({"_id": ObjectId(pkg_id)})
        mdb.rahal_outbox.delete_many({"payload.package_ref": pkg_id})

    def test_meraaj_outbound_signature_is_valid(self):
        """Proves the 401 from Rahaal Test is a remote-secret mismatch, not a Meraaj signing bug:
        the exact same body+signature scheme is accepted by a receiver that holds MERAAJ_SHARED_SECRET."""
        body = {"event": "package.published", "package_ref": f"E2E8-SIGCHK-{STAMP}", "status": "listed"}
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        r = requests.post(f"{API}/meraaj/webhooks", data=raw, headers={
            "Content-Type": "application/json",
            "X-Meraaj-Signature": f"sha256={sign(raw)}"}, timeout=30)
        assert r.status_code == 200, f"local receiver rejected Meraaj signature: {r.status_code} {r.text[:200]}"
        assert r.json()["valid"] is True
        mdb.rahal_sim_inbox.delete_many({"package_ref": f"E2E8-SIGCHK-{STAMP}"})

    def test_rahal_webhook_url_configured(self):
        assert RAHAL_WEBHOOK_URL.startswith("https://"), RAHAL_WEBHOOK_URL
        assert len(MERAAJ_SECRET) == 64, f"MERAAJ_SHARED_SECRET len={len(MERAAJ_SECRET)}"
