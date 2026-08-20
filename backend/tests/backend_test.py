"""Meraaj Network backend regression suite.

Covers: auth/security, packages/market, booking lifecycle (blue->yellow->green),
settlement grace, cancellations, disputes, wallet (topup/transfer/withdraw),
admin finance + offices, Rahal integration.
"""
import hmac
import hashlib
import json
import uuid

import requests
import pytest
from pymongo import MongoClient
from dotenv import dotenv_values

from conftest import (API, ADMIN_EMAIL, ADMIN_PASSWORD, RAHAL_SECRET, PLATFORM_PCT,
                      CANCEL_FEE_PCT, client, new_office, fund_office, make_package, wallet_of)


# ---------------- Auth & security ----------------
class TestAuthSecurity:
    def test_health(self):
        r = requests.get(f"{API}/")
        assert r.status_code == 200
        assert "Meraaj" in r.json()["message"]

    def test_admin_login_sets_httponly_cookie_and_token(self):
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert data["user"]["role"] == "super_admin"
        assert "password_hash" not in data["user"]
        assert "_id" not in data["user"] and isinstance(data["user"]["id"], str)
        assert isinstance(data["access_token"], str) and len(data["access_token"]) > 20
        cookie_header = r.headers.get("set-cookie", "").lower()
        assert "access_token=" in cookie_header
        assert "httponly" in cookie_header
        assert "samesite=none" in cookie_header
        assert "secure" in cookie_header

    def test_bcrypt_hash_format(self):
        env = dotenv_values("/app/backend/.env")
        mc = MongoClient(env["MONGO_URL"])
        user = mc[env["DB_NAME"]].users.find_one({"email": ADMIN_EMAIL})
        assert user is not None, "admin not seeded"
        assert user["password_hash"].startswith("$2b$"), user["password_hash"][:10]
        mc.close()

    def test_login_wrong_password_401(self):
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong-pass"})
        assert r.status_code == 401
        assert "detail" in r.json()

    def test_brute_force_lockout_after_5_failures(self):
        email = f"test_bf_{uuid.uuid4().hex[:6]}@qa-example.com"
        requests.post(f"{API}/auth/register", json={
            "email": email, "password": "Test@1234", "office_name": "TEST_BF",
            "owner_name": "x", "phone": "1", "governorate": "بغداد", "address": "a"})
        codes = []
        for _ in range(6):
            codes.append(requests.post(f"{API}/auth/login",
                                       json={"email": email, "password": "bad"}).status_code)
        assert codes[-1] in (423, 429), f"no lockout after 5 failed logins; codes={codes}"

    def test_me_requires_auth(self):
        assert requests.get(f"{API}/auth/me").status_code == 401
        assert requests.get(f"{API}/auth/me", headers={"Authorization": "Bearer junk"}).status_code == 401

    def test_register_validation_and_duplicate(self):
        s, user, token = new_office("reg")
        me = s.get(f"{API}/auth/me")
        assert me.status_code == 200
        assert me.json()["email"] == user["email"]
        assert me.json()["role"] == "office"
        assert me.json()["wallet"] == {"total": 0.0, "pending": 0.0, "available": 0.0}
        dup = requests.post(f"{API}/auth/register", json={
            "email": user["email"], "password": "Test@1234", "office_name": "x",
            "owner_name": "y", "phone": "1", "governorate": "بغداد", "address": "a"})
        assert dup.status_code == 400
        short = requests.post(f"{API}/auth/register", json={
            "email": f"test_short_{uuid.uuid4().hex[:6]}@qa-example.com", "password": "123",
            "office_name": "x", "owner_name": "y", "phone": "1", "governorate": "g", "address": "a"})
        assert short.status_code == 422
        missing = requests.post(f"{API}/auth/register", json={"email": "a@b.co", "password": "Test@1234"})
        assert missing.status_code == 422

    def test_role_separation(self, admin):
        # admin cannot use office endpoints
        assert admin.get(f"{API}/wallet").status_code == 403
        s, _, _ = new_office("role")
        # office cannot use admin endpoints
        assert s.get(f"{API}/admin/dashboard").status_code == 403

    def test_logout_clears_cookie(self):
        r = requests.post(f"{API}/auth/logout")
        assert r.status_code == 200
        assert "access_token=" in r.headers.get("set-cookie", "")


# ---------------- Packages / market ----------------
class TestPackages:
    def test_create_list_filter_search_toggle(self, admin):
        seller, suser, _ = new_office("pkgseller")
        pkg = make_package(seller, type="umrah", title=f"TEST_عمرة_{uuid.uuid4().hex[:6]}")
        assert pkg["available_seats"] == pkg["total_seats"] == 10
        assert pkg["status"] == "listed"
        assert pkg["seller_id"] == suser["id"]
        assert "_id" not in pkg
        # GET single
        g = requests.get(f"{API}/packages/{pkg['id']}")
        assert g.status_code == 200 and g.json()["title"] == pkg["title"]
        # list
        lst = requests.get(f"{API}/packages").json()
        assert any(p["id"] == pkg["id"] for p in lst)
        # type filter
        tour = make_package(seller, type="tourism", title=f"TEST_سياحة_{uuid.uuid4().hex[:6]}")
        ids = [p["id"] for p in requests.get(f"{API}/packages", params={"type": "tourism"}).json()]
        assert tour["id"] in ids and pkg["id"] not in ids
        # search
        found = requests.get(f"{API}/packages", params={"q": pkg["title"]}).json()
        assert [p["id"] for p in found] == [pkg["id"]]
        # mine
        mine = seller.get(f"{API}/packages/mine")
        assert mine.status_code == 200 and len(mine.json()) == 2
        # toggle
        t = seller.patch(f"{API}/packages/{pkg['id']}/toggle")
        assert t.status_code == 200 and t.json()["status"] == "unlisted"
        assert pkg["id"] not in [p["id"] for p in requests.get(f"{API}/packages").json()]
        seller.patch(f"{API}/packages/{pkg['id']}/toggle")

    def test_package_not_found_and_bad_id(self):
        assert requests.get(f"{API}/packages/64b7f9f9f9f9f9f9f9f9f9f9").status_code == 404
        r = requests.get(f"{API}/packages/not-an-objectid")
        assert r.status_code in (400, 404, 422), f"malformed id returned {r.status_code}"

    def test_other_office_cannot_toggle(self):
        seller, _, _ = new_office("s1")
        other, _, _ = new_office("s2")
        pkg = make_package(seller)
        assert other.patch(f"{API}/packages/{pkg['id']}/toggle").status_code == 404

    def test_create_package_requires_office(self, admin):
        assert admin.post(f"{API}/packages", json={"type": "umrah"}).status_code in (403, 422)


# ---------------- Booking happy path: blue -> yellow -> green ----------------
class TestBookingLifecycle:
    def test_full_lifecycle(self, admin):
        seller, suser, _ = new_office("lcseller")
        buyer, buser, _ = new_office("lcbuyer")
        fund_office(admin, buyer, 50000)
        assert wallet_of(buyer)["available"] == 50000

        pkg = make_package(seller)
        seats = 2
        net_total = pkg["net_cost_per_seat"] * seats
        commission_total = pkg["buyer_office_commission"] * seats
        fee = round(commission_total * PLATFORM_PCT, 2)
        required = round(net_total + fee, 2)

        regs = [{"name": f"مسجل {i}", "passport_no": f"A{i}00{i}", "age": 30 + i} for i in range(seats)]
        r = buyer.post(f"{API}/bookings", json={"package_id": pkg["id"], "registrants": regs})
        assert r.status_code == 200, r.text[:300]
        b = r.json()
        assert b["status"] == "blue"
        assert b["amount_charged"] == required
        assert b["platform_fee"] == fee
        assert b["net_cost_total"] == net_total
        assert all(x["visa_no"] is None for x in b["registrants"])

        # wallets
        bw = wallet_of(buyer)
        assert bw["available"] == 50000 - required
        assert bw["total"] == 50000 - required
        sw = wallet_of(seller)
        assert sw["pending"] == net_total and sw["available"] == 0 and sw["total"] == net_total
        # seats decremented
        assert requests.get(f"{API}/packages/{pkg['id']}").json()["available_seats"] == 10 - seats
        # transactions logged
        txns = buyer.get(f"{API}/wallet/transactions").json()
        assert any(t["type"] == "booking_debit" and t["amount"] == -required for t in txns)

        # buyer / seller listing
        assert b["id"] in [x["id"] for x in buyer.get(f"{API}/bookings", params={"role": "buyer"}).json()]
        assert b["id"] in [x["id"] for x in seller.get(f"{API}/bookings", params={"role": "seller"}).json()]
        assert buyer.get(f"{API}/bookings", params={"role": "seller"}).json() == []

        # visa validation: partial -> 400 and status stays blue
        bad = seller.post(f"{API}/bookings/{b['id']}/issue-visas",
                          json={"visas": [{"index": 0, "visa_no": "V1"}]})
        assert bad.status_code == 400, bad.text[:300]
        assert seller.get(f"{API}/bookings/{b['id']}").json()["status"] == "blue"
        assert seller.get(f"{API}/bookings/{b['id']}").json()["registrants"][0]["visa_no"] is None, \
            "partial visa data persisted despite rejected transition"
        # empty visa_no rejected
        assert seller.post(f"{API}/bookings/{b['id']}/issue-visas", json={"visas": [
            {"index": 0, "visa_no": "V1"}, {"index": 1, "visa_no": ""}]}).status_code == 400

        # dispatch before yellow blocked
        assert seller.post(f"{API}/bookings/{b['id']}/dispatch").status_code == 400
        # buyer cannot issue visas
        assert buyer.post(f"{API}/bookings/{b['id']}/issue-visas", json={"visas": [
            {"index": 0, "visa_no": "V1"}, {"index": 1, "visa_no": "V2"}]}).status_code == 404

        ok = seller.post(f"{API}/bookings/{b['id']}/issue-visas", json={"visas": [
            {"index": 0, "visa_no": "V-100", "visa_file": "http://x/v1.pdf"},
            {"index": 1, "visa_no": "V-101"}]})
        assert ok.status_code == 200 and ok.json()["status"] == "yellow"
        fetched = seller.get(f"{API}/bookings/{b['id']}").json()
        assert fetched["status"] == "yellow"
        assert [x["visa_no"] for x in fetched["registrants"]] == ["V-100", "V-101"]

        # settle while yellow blocked
        assert seller.post(f"{API}/bookings/{b['id']}/settle").status_code == 400

        d = seller.post(f"{API}/bookings/{b['id']}/dispatch")
        assert d.status_code == 200 and d.json()["status"] == "green"
        assert d.json()["grace_hours"] == 24
        assert seller.get(f"{API}/bookings/{b['id']}").json()["dispatched_at"] is not None

        # settle before 24h blocked
        s = seller.post(f"{API}/bookings/{b['id']}/settle")
        assert s.status_code == 400
        assert "24" in s.json()["detail"], s.json()
        # escrow untouched
        assert wallet_of(seller)["pending"] == net_total
        # cancel after dispatch blocked
        c = buyer.post(f"{API}/bookings/{b['id']}/cancel-request")
        assert c.status_code == 400 and "التفويج" in c.json()["detail"]

    def test_booking_guards(self, admin):
        seller, _, _ = new_office("gseller")
        buyer, _, _ = new_office("gbuyer")
        pkg = make_package(seller, total_seats=2)
        # own package
        r = seller.post(f"{API}/bookings", json={"package_id": pkg["id"], "registrants": [
            {"name": "a", "passport_no": "p", "age": 20}]})
        assert r.status_code == 400
        # no registrants
        assert buyer.post(f"{API}/bookings", json={"package_id": pkg["id"], "registrants": []}).status_code == 400
        # not enough seats
        regs = [{"name": f"n{i}", "passport_no": f"p{i}", "age": 20} for i in range(3)]
        assert buyer.post(f"{API}/bookings", json={"package_id": pkg["id"], "registrants": regs}).status_code == 400
        # insufficient balance (buyer has 0)
        r = buyer.post(f"{API}/bookings", json={"package_id": pkg["id"], "registrants": [
            {"name": "a", "passport_no": "p", "age": 20}]})
        assert r.status_code == 400 and "الرصيد" in r.json()["detail"]
        # unlisted package
        fund_office(admin, buyer, 5000)
        seller.patch(f"{API}/packages/{pkg['id']}/toggle")
        r = buyer.post(f"{API}/bookings", json={"package_id": pkg["id"], "registrants": [
            {"name": "a", "passport_no": "p", "age": 20}]})
        assert r.status_code == 404

    def test_third_party_cannot_read_booking(self, admin):
        seller, _, _ = new_office("t3s")
        buyer, _, _ = new_office("t3b")
        stranger, _, _ = new_office("t3x")
        fund_office(admin, buyer, 5000)
        pkg = make_package(seller)
        b = buyer.post(f"{API}/bookings", json={"package_id": pkg["id"], "registrants": [
            {"name": "a", "passport_no": "p", "age": 20}]}).json()
        assert stranger.get(f"{API}/bookings/{b['id']}").status_code == 404


# ---------------- Cancellations ----------------
class TestCancellations:
    def test_blue_cancel_refund_and_seat_release(self, admin):
        seller, _, _ = new_office("cbs")
        buyer, _, _ = new_office("cbb")
        fund_office(admin, buyer, 10000)
        pkg = make_package(seller, total_seats=5)
        regs = [{"name": "a", "passport_no": "p1", "age": 30}, {"name": "b", "passport_no": "p2", "age": 31}]
        b = buyer.post(f"{API}/bookings", json={"package_id": pkg["id"], "registrants": regs}).json()
        charged = b["amount_charged"]
        net = b["net_cost_total"]
        r = buyer.post(f"{API}/bookings/{b['id']}/cancel-request")
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert data["status"] == "cancelled"
        expected_fee = round(net * CANCEL_FEE_PCT, 2)
        assert data["admin_fee"] == expected_fee
        assert data["refund"] == round(charged - expected_fee, 2)
        bw = wallet_of(buyer)
        assert bw["available"] == round(10000 - charged + data["refund"], 2)
        sw = wallet_of(seller)
        assert sw["pending"] == 0 and sw["total"] == 0
        assert requests.get(f"{API}/packages/{pkg['id']}").json()["available_seats"] == 5
        # double cancel guard
        r2 = buyer.post(f"{API}/bookings/{b['id']}/cancel-request")
        assert r2.status_code == 400, f"cancelled booking cancelled again: {r2.status_code} {r2.text[:200]}"

    def test_yellow_cancel_flow(self, admin):
        seller, _, _ = new_office("cys")
        buyer, _, _ = new_office("cyb")
        fund_office(admin, buyer, 10000)
        pkg = make_package(seller, total_seats=4)
        b = buyer.post(f"{API}/bookings", json={"package_id": pkg["id"], "registrants": [
            {"name": "a", "passport_no": "p1", "age": 30}]}).json()
        charged, net, fee = b["amount_charged"], b["net_cost_total"], b["platform_fee"]
        assert seller.post(f"{API}/bookings/{b['id']}/issue-visas",
                           json={"visas": [{"index": 0, "visa_no": "V-1"}]}).status_code == 200
        # offer before request
        assert seller.post(f"{API}/bookings/{b['id']}/cancel-offer", json={"deduction": 100}).status_code == 400
        r = buyer.post(f"{API}/bookings/{b['id']}/cancel-request")
        assert r.status_code == 200 and r.json()["cancellation"] == "awaiting_seller"
        # accept before offer
        assert buyer.post(f"{API}/bookings/{b['id']}/cancel-accept").status_code == 400
        deduction = 300.0
        o = seller.post(f"{API}/bookings/{b['id']}/cancel-offer", json={"deduction": deduction})
        assert o.status_code == 200 and o.json()["stage"] == "awaiting_buyer"
        a = buyer.post(f"{API}/bookings/{b['id']}/cancel-accept")
        assert a.status_code == 200, a.text[:300]
        res = a.json()
        platform_cut = round(deduction * PLATFORM_PCT, 2)
        assert res["seller_keeps"] == round(deduction - platform_cut, 2)
        assert res["refund"] == round(net - deduction + fee, 2)
        sw = wallet_of(seller)
        assert sw["pending"] == 0
        assert sw["available"] == res["seller_keeps"]
        bw = wallet_of(buyer)
        assert bw["available"] == round(10000 - charged + res["refund"], 2)
        assert requests.get(f"{API}/packages/{pkg['id']}").json()["available_seats"] == 4
        assert buyer.get(f"{API}/bookings/{b['id']}").json()["status"] == "cancelled"


# ---------------- Disputes ----------------
class TestDisputes:
    def _green_booking(self, admin):
        seller, _, _ = new_office("dis_s")
        buyer, _, _ = new_office("dis_b")
        fund_office(admin, buyer, 10000)
        pkg = make_package(seller, total_seats=3)
        b = buyer.post(f"{API}/bookings", json={"package_id": pkg["id"], "registrants": [
            {"name": "a", "passport_no": "p1", "age": 30}]}).json()
        seller.post(f"{API}/bookings/{b['id']}/issue-visas", json={"visas": [{"index": 0, "visa_no": "V-9"}]})
        seller.post(f"{API}/bookings/{b['id']}/dispatch")
        return seller, buyer, pkg, b

    def test_dispute_blocks_settlement_and_release_seller(self, admin):
        seller, buyer, pkg, b = self._green_booking(admin)
        d = buyer.post(f"{API}/bookings/{b['id']}/dispute", json={"reason": "لم يتم التفويج فعلياً"})
        assert d.status_code == 200 and d.json()["dispute"]["status"] == "open"
        # seller cannot open dispute
        assert seller.post(f"{API}/bookings/{b['id']}/dispute", json={"reason": "x"}).status_code == 404
        # appears in admin disputes
        lst = admin.get(f"{API}/admin/disputes")
        assert lst.status_code == 200
        assert b["id"] in [x["id"] for x in lst.json()]
        assert admin.get(f"{API}/admin/dashboard").json()["open_disputes"] >= 1
        # resolve release_seller
        net, fee = b["net_cost_total"], b["platform_fee"]
        r = admin.post(f"{API}/admin/disputes/{b['id']}/resolve", json={"resolution": "release_seller"})
        assert r.status_code == 200, r.text[:300]
        sw = wallet_of(seller)
        assert sw["pending"] == 0
        assert sw["available"] == round(net - fee, 2)
        assert admin.post(f"{API}/admin/disputes/{b['id']}/resolve",
                          json={"resolution": "bogus"}).status_code == 400

    def test_dispute_refund_buyer(self, admin):
        seller, buyer, pkg, b = self._green_booking(admin)
        buyer.post(f"{API}/bookings/{b['id']}/dispute", json={"reason": "مشكلة"})
        r = admin.post(f"{API}/admin/disputes/{b['id']}/resolve", json={"resolution": "refund_buyer"})
        assert r.status_code == 200, r.text[:300]
        refund = round(b["net_cost_total"] + b["platform_fee"], 2)
        bw = wallet_of(buyer)
        assert bw["available"] == round(10000 - b["amount_charged"] + refund, 2)
        assert wallet_of(seller)["pending"] == 0
        assert buyer.get(f"{API}/bookings/{b['id']}").json()["status"] == "cancelled"
        assert requests.get(f"{API}/packages/{pkg['id']}").json()["available_seats"] == 3

    def test_dispute_not_allowed_on_blue(self, admin):
        seller, _, _ = new_office("dnb_s")
        buyer, _, _ = new_office("dnb_b")
        fund_office(admin, buyer, 5000)
        pkg = make_package(seller)
        b = buyer.post(f"{API}/bookings", json={"package_id": pkg["id"], "registrants": [
            {"name": "a", "passport_no": "p", "age": 20}]}).json()
        assert buyer.post(f"{API}/bookings/{b['id']}/dispute", json={"reason": "x"}).status_code == 400


# ---------------- Wallet: topups / transfers / withdrawals ----------------
class TestWalletFlows:
    def test_topup_approve_and_reject(self, admin):
        office, _, _ = new_office("tp")
        r = office.post(f"{API}/wallet/topups", json={"amount": 1000, "method": "bank",
                                                     "receipt_url": "http://x/a.png"})
        assert r.status_code == 200 and r.json()["status"] == "pending"
        tid = r.json()["id"]
        assert tid in [x["id"] for x in admin.get(f"{API}/admin/topups").json()]
        assert admin.post(f"{API}/admin/topups/{tid}/review", json={"approve": True}).status_code == 200
        assert wallet_of(office)["available"] == 1000
        # double review blocked
        assert admin.post(f"{API}/admin/topups/{tid}/review", json={"approve": True}).status_code == 404
        # reject path
        r2 = office.post(f"{API}/wallet/topups", json={"amount": 500, "method": "bank",
                                                      "receipt_url": "http://x/b.png"})
        tid2 = r2.json()["id"]
        assert admin.post(f"{API}/admin/topups/{tid2}/review", json={"approve": False}).status_code == 200
        assert wallet_of(office)["available"] == 1000
        assert office.get(f"{API}/wallet/topups").json()[0]["status"] in ("rejected", "approved")
        # invalid amount
        assert office.post(f"{API}/wallet/topups", json={"amount": -5, "method": "bank",
                                                        "receipt_url": "u"}).status_code == 422

    def test_p2p_transfer_requires_approval(self, admin):
        a, auser, _ = new_office("p2pa")
        b, buser, _ = new_office("p2pb")
        fund_office(admin, a, 2000)
        # unknown recipient
        assert a.post(f"{API}/wallet/transfers", json={"to_email": "nobody@none-example.com",
                                                      "amount": 10}).status_code == 404
        # self transfer
        assert a.post(f"{API}/wallet/transfers", json={"to_email": auser["email"],
                                                      "amount": 10}).status_code == 400
        # insufficient
        assert a.post(f"{API}/wallet/transfers", json={"to_email": buser["email"],
                                                      "amount": 999999}).status_code == 400
        r = a.post(f"{API}/wallet/transfers", json={"to_email": buser["email"], "amount": 500,
                                                   "note": "TEST"})
        assert r.status_code == 200 and r.json()["status"] == "pending"
        tid = r.json()["id"]
        # balances unchanged before approval
        assert wallet_of(a)["available"] == 2000 and wallet_of(b)["available"] == 0
        assert tid in [x["id"] for x in admin.get(f"{API}/admin/transfers").json()]
        assert admin.post(f"{API}/admin/transfers/{tid}/review", json={"approve": True}).status_code == 200
        assert wallet_of(a)["available"] == 1500
        assert wallet_of(b)["available"] == 500
        assert any(t["type"] == "p2p_in" for t in b.get(f"{API}/wallet/transactions").json())
        # reject path leaves balances
        r2 = a.post(f"{API}/wallet/transfers", json={"to_email": buser["email"], "amount": 100})
        admin.post(f"{API}/admin/transfers/{r2.json()['id']}/review", json={"approve": False})
        assert wallet_of(a)["available"] == 1500

    def test_withdrawal_requires_approval(self, admin):
        office, _, _ = new_office("wd")
        fund_office(admin, office, 1000)
        assert office.post(f"{API}/wallet/withdrawals", json={"amount": 5000, "method": "bank",
                                                             "details": "x"}).status_code == 400
        r = office.post(f"{API}/wallet/withdrawals", json={"amount": 400, "method": "bank",
                                                          "details": "IBAN TEST"})
        assert r.status_code == 200 and r.json()["status"] == "pending"
        wid = r.json()["id"]
        assert wallet_of(office)["available"] == 1000
        assert wid in [x["id"] for x in admin.get(f"{API}/admin/withdrawals").json()]
        assert admin.post(f"{API}/admin/withdrawals/{wid}/review", json={"approve": True}).status_code == 200
        assert wallet_of(office)["available"] == 600
        assert office.get(f"{API}/wallet/withdrawals").json()[0]["status"] == "approved"


# ---------------- Admin: dashboard & office status ----------------
class TestAdmin:
    def test_dashboard_fields(self, admin):
        r = admin.get(f"{API}/admin/dashboard")
        assert r.status_code == 200
        d = r.json()
        for k in ["total_system_balance", "total_available", "total_pending", "offices_count",
                  "packages_count", "bookings_count", "pending_topups", "pending_transfers",
                  "pending_withdrawals", "open_disputes"]:
            assert k in d, f"missing {k}"
        assert isinstance(d["offices_count"], int) and d["offices_count"] > 0
        assert d["total_system_balance"] >= 0

    def test_suspend_blocks_office_then_activate(self, admin):
        office, ouser, _ = new_office("susp")
        offices = admin.get(f"{API}/admin/offices")
        assert offices.status_code == 200
        assert ouser["id"] in [o["id"] for o in offices.json()]
        assert all("password_hash" not in o for o in offices.json())
        assert admin.patch(f"{API}/admin/offices/{ouser['id']}/status",
                           json={"status": "bogus"}).status_code == 400
        assert admin.patch(f"{API}/admin/offices/{ouser['id']}/status",
                           json={"status": "suspended"}).status_code == 200
        assert office.get(f"{API}/wallet").status_code == 403
        assert office.post(f"{API}/packages", json={
            "type": "umrah", "title": "x", "departure_date": "d", "return_date": "d",
            "net_cost_per_seat": 1, "final_sale_price": 2, "buyer_office_commission": 1,
            "total_seats": 1}).status_code == 403
        assert admin.patch(f"{API}/admin/offices/{ouser['id']}/status",
                           json={"status": "active"}).status_code == 200
        assert office.get(f"{API}/wallet").status_code == 200

    def test_admin_endpoints_require_auth(self):
        for path in ["/admin/dashboard", "/admin/offices", "/admin/topups", "/admin/transfers",
                     "/admin/withdrawals", "/admin/disputes"]:
            assert requests.get(f"{API}{path}").status_code == 401, path


# ---------------- Rahal integration ----------------
class TestRahalIntegration:
    def test_status(self):
        r = requests.get(f"{API}/integrations/rahal/status")
        assert r.status_code == 200
        assert r.json()["status"] == "ready"
        assert r.json()["integration"] == "rahal"

    def test_share_requires_key_and_upserts(self):
        ref = f"TEST_RAHAL_{uuid.uuid4().hex[:8]}"
        body = {"package_ref": ref, "title": "TEST_باكج رحال", "type": "umrah",
                "departure_date": "2026-10-01", "return_date": "2026-10-08",
                "available_seats": 12,
                "pricing": {"net_cost_per_seat": 900, "final_sale_price": 1200,
                            "buyer_office_commission": 150, "currency": "USD"}}
        assert requests.post(f"{API}/integrations/rahal/packages/share", json=body).status_code == 401
        assert requests.post(f"{API}/integrations/rahal/packages/share", json=body,
                             headers={"X-Rahal-Api-Key": "wrong"}).status_code == 401
        r = requests.post(f"{API}/integrations/rahal/packages/share", json=body,
                          headers={"X-Rahal-Api-Key": RAHAL_SECRET})
        assert r.status_code == 200, r.text[:300]
        pid = r.json()["meraaj_package_id"]
        assert r.json()["status"] == "listed"
        pkg = requests.get(f"{API}/packages/{pid}").json()
        assert pkg["source"] == "rahal" and pkg["available_seats"] == 12
        assert pkg["net_cost_per_seat"] == 900
        # upsert same ref
        body["available_seats"] = 7
        r2 = requests.post(f"{API}/integrations/rahal/packages/share", json=body,
                           headers={"X-Rahal-Api-Key": RAHAL_SECRET})
        assert r2.json()["meraaj_package_id"] == pid
        assert requests.get(f"{API}/packages/{pid}").json()["available_seats"] == 7
        return pid, ref

    def test_webhook_hmac(self):
        pid, ref = self.test_share_requires_key_and_upserts()
        payload = json.dumps({"event": "inventory.updated", "package_ref": ref,
                              "available_seats": 3}).encode()
        # bad signature
        assert requests.post(f"{API}/integrations/rahal/webhooks", data=payload,
                             headers={"Content-Type": "application/json",
                                      "X-Rahal-Signature": "sha256=deadbeef"}).status_code == 401
        assert requests.post(f"{API}/integrations/rahal/webhooks", data=payload,
                             headers={"Content-Type": "application/json"}).status_code == 401
        sig = hmac.new(RAHAL_SECRET.encode(), payload, hashlib.sha256).hexdigest()
        r = requests.post(f"{API}/integrations/rahal/webhooks", data=payload,
                          headers={"Content-Type": "application/json",
                                   "X-Rahal-Signature": f"sha256={sig}"})
        assert r.status_code == 200 and r.json()["received"] is True
        assert requests.get(f"{API}/packages/{pid}").json()["available_seats"] == 3
        # deactivate
        p2 = json.dumps({"event": "package.deactivated", "package_ref": ref}).encode()
        sig2 = hmac.new(RAHAL_SECRET.encode(), p2, hashlib.sha256).hexdigest()
        assert requests.post(f"{API}/integrations/rahal/webhooks", data=p2,
                             headers={"Content-Type": "application/json",
                                      "X-Rahal-Signature": f"sha256={sig2}"}).status_code == 200
        assert requests.get(f"{API}/packages/{pid}").json()["status"] == "unlisted"
