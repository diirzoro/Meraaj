"""Iteration-2 verification of money-safety guards (fixes 3-6)."""
import os
from datetime import datetime, timezone, timedelta

import pytest
import requests
from bson import ObjectId
from dotenv import dotenv_values
from pymongo import MongoClient

from conftest import API, new_office, fund_office, make_package, wallet_of

_env = dotenv_values("/app/backend/.env")
MONGO_URL = os.environ.get("MONGO_URL") or _env.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME") or _env.get("DB_NAME")
_mc = MongoClient(MONGO_URL)
_db = _mc[DB_NAME]


def book(buyer, pkg, seats=1):
    r = buyer.post(f"{API}/bookings", json={"package_id": pkg["id"], "registrants": [
        {"name": f"reg{i}", "passport_no": f"P{i}", "age": 30} for i in range(seats)]})
    assert r.status_code == 200, r.text[:300]
    return r.json()


# ---------- FIX 3: double cancel / double refund ----------
class TestFix3DoubleCancel:
    def test_replay_cancel_request_returns_400_no_refund(self, admin):
        seller, _, _ = new_office("f3s")
        buyer, _, _ = new_office("f3b")
        fund_office(admin, buyer, 10000)
        pkg = make_package(seller, total_seats=5)
        b = book(buyer, pkg)

        r1 = buyer.post(f"{API}/bookings/{b['id']}/cancel-request")
        assert r1.status_code == 200, r1.text[:300]
        bal_after_first = wallet_of(buyer)["available"]

        r2 = buyer.post(f"{API}/bookings/{b['id']}/cancel-request")
        assert r2.status_code == 400, f"replay cancel-request returned {r2.status_code}: {r2.text[:200]}"
        assert wallet_of(buyer)["available"] == bal_after_first, "balance changed on replayed cancel"

        # downstream negotiation endpoints must also refuse
        o = seller.post(f"{API}/bookings/{b['id']}/cancel-offer", json={"deduction": 0})
        assert o.status_code == 400, f"cancel-offer on cancelled booking: {o.status_code}"
        a = buyer.post(f"{API}/bookings/{b['id']}/cancel-accept")
        assert a.status_code == 400, f"cancel-accept on cancelled booking: {a.status_code}"
        assert wallet_of(buyer)["available"] == bal_after_first
        seats = requests.get(f"{API}/packages/{pkg['id']}").json()["available_seats"]
        assert seats == 5, f"seats over-released: {seats}"


# ---------- FIX 4: double dispute resolution ----------
class TestFix4DoubleResolve:
    @pytest.mark.parametrize("resolution", ["refund_buyer", "release_seller"])
    def test_second_resolve_returns_400_and_no_balance_change(self, admin, resolution):
        seller, _, _ = new_office("f4s")
        buyer, _, _ = new_office("f4b")
        fund_office(admin, buyer, 10000)
        pkg = make_package(seller, total_seats=3)
        b = book(buyer, pkg)
        seller.post(f"{API}/bookings/{b['id']}/issue-visas", json={"visas": [{"index": 0, "visa_no": "V1"}]})
        assert seller.post(f"{API}/bookings/{b['id']}/dispatch").status_code == 200
        assert buyer.post(f"{API}/bookings/{b['id']}/dispute", json={"reason": "خدمة سيئة"}).status_code == 200

        r1 = admin.post(f"{API}/admin/disputes/{b['id']}/resolve", json={"resolution": resolution})
        assert r1.status_code == 200, r1.text[:300]
        buyer_bal, seller_w = wallet_of(buyer)["available"], wallet_of(seller)

        r2 = admin.post(f"{API}/admin/disputes/{b['id']}/resolve", json={"resolution": resolution})
        assert r2.status_code == 400, f"replay resolve returned {r2.status_code}: {r2.text[:200]}"
        assert wallet_of(buyer)["available"] == buyer_bal
        assert wallet_of(seller) == seller_w


# ---------- FIX 5: duplicate dispute + 24h window ----------
class TestFix5DisputeGuards:
    def _green_booking(self, admin):
        seller, _, _ = new_office("f5s")
        buyer, _, _ = new_office("f5b")
        fund_office(admin, buyer, 10000)
        pkg = make_package(seller, total_seats=3)
        b = book(buyer, pkg)
        seller.post(f"{API}/bookings/{b['id']}/issue-visas", json={"visas": [{"index": 0, "visa_no": "V1"}]})
        assert seller.post(f"{API}/bookings/{b['id']}/dispatch").status_code == 200
        return seller, buyer, b

    def test_duplicate_dispute_rejected(self, admin):
        _, buyer, b = self._green_booking(admin)
        assert buyer.post(f"{API}/bookings/{b['id']}/dispute", json={"reason": "أول"}).status_code == 200
        r = buyer.post(f"{API}/bookings/{b['id']}/dispute", json={"reason": "ثاني"})
        assert r.status_code == 400, f"duplicate dispute allowed: {r.status_code} {r.text[:200]}"
        doc = _db.bookings.find_one({"_id": ObjectId(b["id"])})
        assert doc["dispute"]["reason"] == "أول", "original dispute overwritten"

    def test_dispute_after_24h_window_rejected(self, admin):
        _, buyer, b = self._green_booking(admin)
        old = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        _db.bookings.update_one({"_id": ObjectId(b["id"])}, {"$set": {"dispatched_at": old}})
        r = buyer.post(f"{API}/bookings/{b['id']}/dispute", json={"reason": "متأخر"})
        assert r.status_code == 400, f"dispute allowed after 24h: {r.status_code} {r.text[:200]}"


# ---------- FIX 6: malformed ObjectId ----------
class TestFix6MalformedIds:
    @pytest.mark.parametrize("path", [
        "/packages/not-a-valid-objectid",
        "/packages/123",
        "/bookings/not-a-valid-objectid/dispatch",
    ])
    def test_malformed_id_not_500(self, admin, path):
        method = requests.get if "dispatch" not in path else None
        if method:
            r = requests.get(f"{API}{path}")
        else:
            seller, _, _ = new_office("f6")
            r = seller.post(f"{API}{path}")
        assert r.status_code != 500, f"{path} -> 500: {r.text[:200]}"
        assert r.status_code in (400, 404, 422), f"{path} -> {r.status_code}"
