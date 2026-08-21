"""Rahal inbound webhook sync tests (bug fix verification).

Covers: package.deactivated/deleted/removed/disabled -> unlisted, package.activated -> listed,
package.updated status normalization, inventory.updated, signature enforcement,
rahal_inbound_log diagnosability, and the end-to-end share -> market -> delete flow.
"""
import hmac
import hashlib
import json
import uuid

import pytest
import requests
from pymongo import MongoClient
from dotenv import dotenv_values

from conftest import API, RAHAL_SECRET

backend_env = dotenv_values("/app/backend/.env")
MONGO_URL = backend_env.get("MONGO_URL")
DB_NAME = backend_env.get("DB_NAME")

WEBHOOK = f"{API}/integrations/rahal/webhooks"
SHARE = f"{API}/integrations/rahal/packages/share"


@pytest.fixture(scope="module")
def mongo():
    if not MONGO_URL or not DB_NAME:
        pytest.fail("MONGO_URL/DB_NAME missing from /app/backend/.env")
    c = MongoClient(MONGO_URL)
    yield c[DB_NAME]
    c.close()


def sign(raw: bytes) -> str:
    return "sha256=" + hmac.new(RAHAL_SECRET.encode(), raw, hashlib.sha256).hexdigest()


def post_webhook(body: dict, signature=None):
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    sig = sign(raw) if signature is None else signature
    headers = {"Content-Type": "application/json"}
    if sig != "__omit__":
        headers["X-Rahal-Signature"] = sig
    return requests.post(WEBHOOK, data=raw, headers=headers)


def share_pkg(ref, **over):
    body = {
        "package_ref": ref,
        "office_ref": "RHL-OFF-QA-TEST",
        "office_name": "TEST_مكتب رحال QA",
        "type": "umrah",
        "title": f"TEST_رحال_{ref}",
        "available_seats": 12,
        "pricing": {"net_cost_per_seat": 900, "final_sale_price": 1200,
                    "buyer_office_commission": 150, "currency": "USD"},
    }
    body.update(over)
    return requests.post(SHARE, json=body, headers={"X-Rahal-Api-Key": RAHAL_SECRET})


def market_refs():
    r = requests.get(f"{API}/packages")
    assert r.status_code == 200, r.text[:300]
    return {p.get("rahal_ref") for p in r.json()}


def db_status(mongo, ref):
    d = mongo.packages.find_one({"rahal_ref": ref})
    return d["status"] if d else None


@pytest.fixture
def pkg(mongo, request):
    """Create a fresh shared rahal package; cleaned up afterwards."""
    ref = f"TEST-QA-{uuid.uuid4().hex[:10]}"
    r = share_pkg(ref)
    assert r.status_code == 200, f"share failed {r.status_code}: {r.text[:300]}"
    assert r.json()["status"] == "listed"
    yield ref
    mongo.packages.delete_many({"rahal_ref": ref})
    mongo.rahal_inbound_log.delete_many({"package_ref": ref})


# ---------- deactivation / deletion events must unlist ----------
@pytest.mark.parametrize("event", ["package.deactivated", "package.deleted",
                                  "package.removed", "package.disabled"])
def test_disable_events_unlist_package(mongo, pkg, event):
    assert db_status(mongo, pkg) == "listed"
    assert pkg in market_refs(), "package not visible in market before webhook"

    r = post_webhook({"event": event, "package_ref": pkg, "occurred_at": "2026-07-01T00:00:00Z"})
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    assert data["received"] is True
    assert data["event"] == event
    assert data["handled"] is True

    assert db_status(mongo, pkg) == "unlisted", f"{event} did not unlist package"
    assert pkg not in market_refs(), f"{event}: package still visible in GET /api/packages"

    log = mongo.rahal_inbound_log.find_one({"package_ref": pkg, "event": event})
    assert log is not None, "webhook not recorded in rahal_inbound_log"
    assert log["handled"] is True


# ---------- reactivation ----------
def test_activated_relists_package(mongo, pkg):
    post_webhook({"event": "package.deleted", "package_ref": pkg, "occurred_at": "x"})
    assert db_status(mongo, pkg) == "unlisted"
    r = post_webhook({"event": "package.activated", "package_ref": pkg, "occurred_at": "x"})
    assert r.status_code == 200 and r.json()["handled"] is True
    assert db_status(mongo, pkg) == "listed"
    assert pkg in market_refs()


# ---------- package.updated status normalization ----------
@pytest.mark.parametrize("payload_extra,expected", [
    ({"active": False}, "unlisted"),
    ({"status": "inactive"}, "unlisted"),
    ({"status": "deleted"}, "unlisted"),
    ({"status": "disabled"}, "unlisted"),
    ({"status": "cancelled"}, "unlisted"),
    ({"status": "removed"}, "unlisted"),
    ({"active": True}, "listed"),
    ({"status": "active"}, "listed"),
    ({"status": "listed"}, "listed"),
])
def test_updated_status_normalization(mongo, pkg, payload_extra, expected):
    body = {"event": "package.updated", "package_ref": pkg, "occurred_at": "x"}
    body.update(payload_extra)
    r = post_webhook(body)
    assert r.status_code == 200 and r.json()["handled"] is True
    assert db_status(mongo, pkg) == expected, f"{payload_extra} -> expected {expected}"
    in_market = pkg in market_refs()
    assert in_market == (expected == "listed")


def test_updated_other_fields_do_not_corrupt_status(mongo, pkg):
    r = post_webhook({"event": "package.updated", "package_ref": pkg,
                      "title": "TEST_عنوان محدث", "occurred_at": "x"})
    assert r.status_code == 200 and r.json()["handled"] is True
    doc = mongo.packages.find_one({"rahal_ref": pkg})
    assert doc["title"] == "TEST_عنوان محدث"
    assert doc["status"] == "listed", "internal status corrupted by field-only update"
    assert pkg in market_refs()


def test_updated_unknown_foreign_status_does_not_leak(mongo, pkg):
    """A foreign status value we do not recognise must never be copied verbatim."""
    r = post_webhook({"event": "package.updated", "package_ref": pkg,
                      "status": "SOME_RAHAL_STATE", "occurred_at": "x"})
    assert r.status_code == 200
    assert db_status(mongo, pkg) in ("listed", "unlisted"), "foreign status leaked into DB"


# ---------- inventory ----------
def test_inventory_updated(mongo, pkg):
    r = post_webhook({"event": "inventory.updated", "package_ref": pkg,
                      "available_seats": 3, "occurred_at": "x"})
    assert r.status_code == 200 and r.json()["handled"] is True
    doc = mongo.packages.find_one({"rahal_ref": pkg})
    assert doc["available_seats"] == 3
    api = [p for p in requests.get(f"{API}/packages").json() if p.get("rahal_ref") == pkg]
    assert api and api[0]["available_seats"] == 3


# ---------- signature enforcement ----------
def test_missing_signature_rejected(mongo, pkg):
    r = post_webhook({"event": "package.deleted", "package_ref": pkg, "occurred_at": "x"},
                     signature="__omit__")
    assert r.status_code == 401, f"expected 401, got {r.status_code}"
    assert db_status(mongo, pkg) == "listed", "unsigned webhook mutated the package"


def test_invalid_signature_rejected(mongo, pkg):
    r = post_webhook({"event": "package.deleted", "package_ref": pkg, "occurred_at": "x"},
                     signature="sha256=" + "0" * 64)
    assert r.status_code == 401
    assert db_status(mongo, pkg) == "listed"


def test_tampered_body_rejected(mongo, pkg):
    raw = json.dumps({"event": "package.deleted", "package_ref": pkg}).encode()
    sig = sign(raw)
    tampered = json.dumps({"event": "package.deleted", "package_ref": pkg, "x": 1}).encode()
    r = requests.post(WEBHOOK, data=tampered,
                      headers={"Content-Type": "application/json", "X-Rahal-Signature": sig})
    assert r.status_code == 401
    assert db_status(mongo, pkg) == "listed"


# ---------- unknown events & logging ----------
def test_unknown_event_logged_unhandled(mongo, pkg):
    r = post_webhook({"event": "package.somethingelse", "package_ref": pkg, "occurred_at": "x"})
    assert r.status_code == 200
    assert r.json()["handled"] is False
    log = mongo.rahal_inbound_log.find_one({"package_ref": pkg, "event": "package.somethingelse"})
    assert log is not None
    assert log["handled"] is False
    assert db_status(mongo, pkg) == "listed"


def test_unknown_ref_handled_gracefully(mongo):
    ref = f"TEST-QA-NOEXIST-{uuid.uuid4().hex[:8]}"
    r = post_webhook({"event": "package.deleted", "package_ref": ref, "occurred_at": "x"})
    assert r.status_code == 200
    mongo.rahal_inbound_log.delete_many({"package_ref": ref})


# ---------- end-to-end ----------
def test_end_to_end_share_then_delete(mongo):
    ref = f"TEST-QA-E2E-{uuid.uuid4().hex[:8]}"
    try:
        r = share_pkg(ref)
        assert r.status_code == 200, r.text[:300]
        pkg_id = r.json()["meraaj_package_id"]
        assert pkg_id

        listing = [p for p in requests.get(f"{API}/packages").json() if p.get("rahal_ref") == ref]
        assert listing, "shared package not in market"
        assert listing[0]["status"] == "listed"
        assert "net_cost_per_seat" not in listing[0] or listing[0].get("net_cost_per_seat") in (None, 0), \
            "net cost leaked to anonymous market viewer"

        r2 = post_webhook({"event": "package.deleted", "package_ref": ref,
                           "occurred_at": "2026-07-01T00:00:00Z"})
        assert r2.status_code == 200 and r2.json()["handled"] is True
        assert db_status(mongo, ref) == "unlisted"
        assert ref not in market_refs(), "deleted package still in market"
    finally:
        mongo.packages.delete_many({"rahal_ref": ref})
        mongo.rahal_inbound_log.delete_many({"package_ref": ref})


def test_share_requires_api_key():
    ref = f"TEST-QA-NOKEY-{uuid.uuid4().hex[:8]}"
    r = requests.post(SHARE, json={"package_ref": ref, "title": "x"},
                      headers={"X-Rahal-Api-Key": "wrong"})
    assert r.status_code == 401
