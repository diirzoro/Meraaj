"""Batch 2 Enterprise Admin — Commission Engine, Credit Control, Unified Ledger,
Vouchers/Reconciliation, 6-stage withdrawal cycle + protected-path regressions.

Run serially:  pytest tests/test_admin_enterprise_b2.py -n 0
(Commission rules are GLOBAL state, so parallel classes would race.)
"""
import base64
import hashlib
import hmac
import json
import time
import uuid

import pytest
import requests

from conftest import API, client, new_office, make_package, RAHAL_SECRET, PLATFORM_PCT

SELLER = ("seller@test.com", "Test@1234")
BUYER = ("buyer@test.com", "Test@1234")


# ---------------- helpers ----------------
def login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"login {email} failed {r.status_code}: {r.text[:200]}"
    return client(r.json()["access_token"])


def fund(admin_s, office_s, amount, currency="SAR"):
    r = office_s.post(f"{API}/wallet/topups", json={
        "amount": amount, "method": "bank", "receipt_url": "http://x/r.png",
        "currency": currency})
    assert r.status_code == 200, r.text[:300]
    tid = r.json()["id"]
    r2 = admin_s.post(f"{API}/admin/topups/{tid}/review", json={"approve": True})
    assert r2.status_code == 200, r2.text[:300]


def avail(session, currency="SAR"):
    r = session.get(f"{API}/wallet")
    assert r.status_code == 200, r.text[:200]
    w = r.json()
    bal = w.get("wallet", w)
    return float(((bal.get(currency) or {}).get("available")) or 0)


def registrant(i=0):
    return {"name": f"TEST مسافر {i}", "passport_no": f"T{uuid.uuid4().hex[:9].upper()}",
            "age": 30, "category": "adult", "phone": "0770000000",
            "nationality": "عراقي", "gender": "male"}


def book(buyer_s, pkg_id, seats=1):
    return buyer_s.post(f"{API}/bookings", json={
        "package_id": pkg_id, "registrants": [registrant(i) for i in range(seats)]})


@pytest.fixture(scope="module")
def admin_s():
    return login("abuzay84@gmail.com", "Meraaj@2026")


@pytest.fixture(scope="module")
def seller_s():
    return login(*SELLER)


@pytest.fixture(scope="module")
def office_s():
    return login(*BUYER)


@pytest.fixture(scope="module")
def anon():
    return client()


@pytest.fixture(scope="module")
def sar_pkg(seller_s):
    # net 1000, sale 1300, buyer commission 200 per seat, SAR
    return make_package(seller_s, currency="SAR")


@pytest.fixture(scope="module")
def usd_pkg(seller_s):
    return make_package(seller_s, currency="USD")


# ================= AUTHORIZATION =================
class TestAuthorizationB2:
    ENDPOINTS = [
        ("GET", "/admin/commission-rules"), ("POST", "/admin/commission-rules"),
        ("POST", "/admin/commission-rules/preview"), ("GET", "/admin/commission-events"),
        ("GET", "/admin/credit"), ("POST", "/admin/credit/000000000000000000000000"),
        ("POST", "/admin/credit/000000000000000000000000/freeze"),
        ("GET", "/admin/credit-events"),
        ("GET", "/admin/ledger"), ("GET", "/admin/ledger/export"),
        ("GET", "/admin/vouchers/000000000000000000000000"),
        ("GET", "/admin/reconciliation"),
        ("GET", "/admin/withdrawals/queue"),
        ("POST", "/admin/withdrawals/000000000000000000000000/stage"),
        ("POST", "/admin/withdrawals/000000000000000000000000/receipt"),
        ("GET", "/admin/withdrawals/000000000000000000000000/detail"),
        ("POST", "/admin/bookings/000000000000000000000000/commission-override"),
        ("PATCH", "/admin/commission-rules/000000000000000000000000"),
        ("DELETE", "/admin/commission-rules/000000000000000000000000"),
    ]

    def test_anonymous_blocked(self, anon):
        bad = []
        for m, p in self.ENDPOINTS:
            r = anon.request(m, f"{API}{p}", json={})
            if r.status_code not in (401, 403):
                bad.append((m, p, r.status_code))
        assert not bad, f"anon not blocked: {bad}"

    def test_office_token_blocked(self, office_s):
        bad = []
        for m, p in self.ENDPOINTS:
            r = office_s.request(m, f"{API}{p}", json={})
            if r.status_code not in (401, 403):
                bad.append((m, p, r.status_code))
        assert not bad, f"office not blocked: {bad}"


# ================= COMMISSION ENGINE =================
class TestCommissionEngine:
    state = {}

    def test_00_no_active_rules_precondition(self, admin_s):
        r = admin_s.get(f"{API}/admin/commission-rules")
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert abs(data["default_pct"] - PLATFORM_PCT) < 1e-9
        actives = [x for x in data["rules"] if x.get("active")]
        assert not actives, f"pre-existing active rules would break default test: {actives}"

    def test_01_default_commission_preserved(self, admin_s, sar_pkg):
        s, user, _ = new_office("B2CMD")
        fund(admin_s, s, 5000, "SAR")
        self.state["buyer"] = s
        self.state["buyer_id"] = user["id"] if "id" in user else user.get("_id")
        r = book(s, sar_pkg["id"])
        assert r.status_code == 200, r.text[:400]
        b = r.json()
        assert b["platform_fee"] == round(200 * PLATFORM_PCT, 2), b["platform_fee"]
        assert b["amount_charged"] == round(1000 + 200 * PLATFORM_PCT, 2)
        snap = b.get("commission_snapshot")
        assert snap, "commission_snapshot missing"
        assert snap["source"] == "default"
        assert snap["rule_name"] == "القاعدة الافتراضية (10%)"
        assert snap["rule_id"] is None
        assert b.get("credit_used") == 0
        self.state["default_booking"] = b["id"]

    def test_02_create_rule_validation(self, admin_s):
        base = {"name": "TEST_قاعدة", "mode": "percent", "value": 1.5,
                "charge_side": "buyer", "scope": {"buyer_type": "office", "currency": "SAR"}}
        r = admin_s.post(f"{API}/admin/commission-rules", json=base)
        assert r.status_code == 400, f"percent>1 accepted: {r.status_code} {r.text[:200]}"
        r = admin_s.post(f"{API}/admin/commission-rules",
                         json={**base, "value": 0.05, "mode": "bogus"})
        assert r.status_code == 400, f"bad mode accepted: {r.status_code}"
        r = admin_s.post(f"{API}/admin/commission-rules",
                         json={**base, "value": 0.05, "charge_side": "bogus"})
        assert r.status_code == 400, f"bad charge_side accepted: {r.status_code}"

    def test_03_create_rule_and_apply(self, admin_s, sar_pkg, usd_pkg):
        r = admin_s.post(f"{API}/admin/commission-rules", json={
            "name": "TEST_SAR_5PCT", "mode": "percent", "value": 0.05,
            "charge_side": "buyer", "priority": 10,
            "scope": {"buyer_type": "office", "currency": "SAR"}})
        assert r.status_code == 200, r.text[:300]
        rule = r.json()
        assert "_id" not in rule
        self.state["rule_id"] = rule["id"]

        s = self.state["buyer"]
        rb = book(s, sar_pkg["id"])
        assert rb.status_code == 200, rb.text[:400]
        b = rb.json()
        assert b["platform_fee"] == 10.0, f"expected 5% => 10.0 got {b['platform_fee']}"
        snap = b["commission_snapshot"]
        assert snap["source"] == "rule"
        assert snap["rule_id"] == self.state["rule_id"]
        assert snap["rule_name"] == "TEST_SAR_5PCT"
        assert snap["value"] == 0.05
        self.state["rule_booking"] = b["id"]

        # scope isolation: USD booking still 10%
        s2, _, _ = new_office("B2USD")
        fund(admin_s, s2, 5000, "USD")
        ru = book(s2, usd_pkg["id"])
        assert ru.status_code == 200, ru.text[:400]
        bu = ru.json()
        assert bu["platform_fee"] == round(200 * PLATFORM_PCT, 2), bu["platform_fee"]
        assert bu["commission_snapshot"]["source"] == "default"

    def test_04_priority_higher_wins(self, admin_s, sar_pkg):
        r = admin_s.post(f"{API}/admin/commission-rules", json={
            "name": "TEST_SAR_8PCT_HIPRI", "mode": "percent", "value": 0.08,
            "charge_side": "buyer", "priority": 99,
            "scope": {"buyer_type": "office", "currency": "SAR"}})
        assert r.status_code == 200, r.text[:300]
        self.state["rule2_id"] = r.json()["id"]
        rb = book(self.state["buyer"], sar_pkg["id"])
        assert rb.status_code == 200, rb.text[:400]
        b = rb.json()
        assert b["platform_fee"] == 16.0, f"priority rule not applied: {b['platform_fee']}"
        assert b["commission_snapshot"]["rule_id"] == self.state["rule2_id"]

    def test_05_preview(self, admin_s):
        r = admin_s.post(f"{API}/admin/commission-rules/preview", json={
            "buyer_type": "office", "currency": "SAR", "base_amount": 1000, "seats": 1})
        assert r.status_code == 200, r.text[:300]
        assert r.json()["amount"] == 80.0, r.json()
        r2 = admin_s.post(f"{API}/admin/commission-rules/preview", json={
            "buyer_type": "office", "currency": "USD", "base_amount": 1000})
        assert r2.json()["amount"] == round(1000 * PLATFORM_PCT, 2)

    def test_06_historic_immutability(self, admin_s):
        rid = self.state["rule_id"]
        r = admin_s.patch(f"{API}/admin/commission-rules/{rid}", json={
            "name": "TEST_SAR_5PCT_EDITED", "mode": "percent", "value": 0.30,
            "charge_side": "buyer", "priority": 10,
            "scope": {"buyer_type": "office", "currency": "SAR"}})
        assert r.status_code == 200, r.text[:300]
        rb = admin_s.get(f"{API}/admin/bookings/{self.state['rule_booking']}/full")
        assert rb.status_code == 200, rb.text[:300]
        b = rb.json()["booking"]
        assert b["platform_fee"] == 10.0, "historic platform_fee changed!"
        assert b["commission_snapshot"]["value"] == 0.05, "historic snapshot mutated!"
        assert b["commission_snapshot"]["rule_name"] == "TEST_SAR_5PCT"

    def test_07_delete_deactivates(self, admin_s):
        for key in ("rule_id", "rule2_id"):
            rid = self.state.get(key)
            if not rid:
                continue
            r = admin_s.delete(f"{API}/admin/commission-rules/{rid}")
            assert r.status_code == 200, r.text[:300]
        docs = admin_s.get(f"{API}/admin/commission-rules").json()["rules"]
        byid = {d["id"]: d for d in docs}
        for key in ("rule_id", "rule2_id"):
            rid = self.state.get(key)
            assert rid in byid, "rule hard-deleted instead of deactivated"
            assert byid[rid]["active"] is False

    def test_08_events_recorded(self, admin_s):
        r = admin_s.get(f"{API}/admin/commission-events",
                        params={"rule_id": self.state["rule_id"]})
        assert r.status_code == 200, r.text[:300]
        actions = {e["action"] for e in r.json()}
        assert {"created", "updated", "deactivated"} <= actions, actions
        assert all(e.get("by") for e in r.json())

    def test_09_default_restored_after_deactivation(self, admin_s, sar_pkg):
        rb = book(self.state["buyer"], sar_pkg["id"])
        assert rb.status_code == 200, rb.text[:400]
        b = rb.json()
        assert b["platform_fee"] == round(200 * PLATFORM_PCT, 2)
        assert b["commission_snapshot"]["source"] == "default"


# ================= MANUAL OVERRIDE =================
class TestCommissionOverride:
    state = {}

    @pytest.fixture(scope="class", autouse=True)
    def setup(self, admin_s, seller_s):
        pkg = make_package(seller_s, currency="SAR")
        s, user, _ = new_office("B2OVR")
        fund(admin_s, s, 3000, "SAR")
        r = book(s, pkg["id"])
        assert r.status_code == 200, r.text[:400]
        self.state["buyer_s"] = s
        self.state["booking"] = r.json()["id"]
        self.state["fee"] = r.json()["platform_fee"]

    def test_override_applies_and_moves_money(self, admin_s):
        bal_before = avail(self.state["buyer_s"], "SAR")
        bid = self.state["booking"]
        r = admin_s.post(f"{API}/admin/bookings/{bid}/commission-override", json={
            "new_platform_fee": 50.0, "reason": "تعديل اختباري للعمولة"})
        assert r.status_code == 200, r.text[:400]
        data = r.json()
        delta = round(50.0 - self.state["fee"], 2)
        assert data["delta"] == delta
        bal_after = avail(self.state["buyer_s"], "SAR")
        assert abs((bal_before - delta) - bal_after) < 0.02, (bal_before, bal_after, delta)

        full = admin_s.get(f"{API}/admin/bookings/{bid}/full").json()
        assert full["booking"]["platform_fee"] == 50.0
        assert full["booking"]["amount_charged"] == round(1000 + self.state["fee"] + delta, 2)
        types = [t["type"] for t in full["transactions"]]
        assert "commission_adjustment" in types, types
        adj = [t for t in full["transactions"] if t["type"] == "commission_adjustment"]
        assert adj[0]["amount"] == -delta
        events = [e for e in full["timeline"] if e["event"] == "commission_override"]
        assert events, "no audit entry"
        assert events[0]["reason"] == "تعديل اختباري للعمولة"

    def test_override_short_reason_rejected(self, admin_s):
        r = admin_s.post(f"{API}/admin/bookings/{self.state['booking']}/commission-override",
                         json={"new_platform_fee": 60.0, "reason": "x"})
        assert r.status_code in (400, 422), r.status_code

    def test_override_no_diff_rejected(self, admin_s):
        r = admin_s.post(f"{API}/admin/bookings/{self.state['booking']}/commission-override",
                         json={"new_platform_fee": 50.0, "reason": "نفس القيمة تماماً"})
        assert r.status_code == 400, r.status_code

    def test_override_insufficient_balance_rejected(self, admin_s):
        bal = avail(self.state["buyer_s"], "SAR")
        r = admin_s.post(f"{API}/admin/bookings/{self.state['booking']}/commission-override",
                         json={"new_platform_fee": 50.0 + bal + 5000,
                               "reason": "زيادة تتجاوز الرصيد"})
        assert r.status_code == 400, f"{r.status_code} {r.text[:200]}"
        assert abs(avail(self.state["buyer_s"], "SAR") - bal) < 0.01, "wallet moved on rejection"

    def test_override_b2c_rejected(self, admin_s):
        r = admin_s.get(f"{API}/admin/bookings", params={"limit": 200})
        items = r.json().get("items", r.json()) if isinstance(r.json(), dict) else r.json()
        b2c = [b for b in items if b.get("buyer_type") == "individual"]
        if not b2c:
            pytest.skip("no B2C booking available")
        rr = admin_s.post(f"{API}/admin/bookings/{b2c[0]['id']}/commission-override",
                          json={"new_platform_fee": 5.0, "reason": "اختبار حجز أفراد"})
        assert rr.status_code == 400, f"B2C override allowed: {rr.status_code}"

    def test_override_cancelled_or_settled_rejected(self, admin_s):
        r = admin_s.get(f"{API}/admin/bookings", params={"limit": 200, "status": "cancelled"})
        payload = r.json()
        items = payload.get("items", payload) if isinstance(payload, dict) else payload
        target = next((b for b in items if b.get("status") == "cancelled"
                       or b.get("settled")), None)
        if not target:
            pytest.skip("no cancelled/settled booking available")
        rr = admin_s.post(f"{API}/admin/bookings/{target['id']}/commission-override",
                          json={"new_platform_fee": 1.0, "reason": "اختبار حجز مسوّى"})
        assert rr.status_code == 400, f"settled/cancelled override allowed: {rr.status_code}"


# ================= CREDIT CONTROL =================
class TestCreditControl:
    state = {}

    @pytest.fixture(scope="class", autouse=True)
    def setup(self, admin_s, seller_s):
        pkg = make_package(seller_s, currency="SAR")
        s, user, _ = new_office("B2CRD")
        self.state["pkg"] = pkg["id"]
        self.state["s"] = s
        self.state["id"] = user["id"]
        yield
        # cleanup: clear debt then reset limit to 0
        bal = avail(s, "SAR")
        if bal < 0:
            fund(admin_s, s, round(-bal + 10, 2), "SAR")
        admin_s.post(f"{API}/admin/credit/{user['id']}", json={
            "currency": "SAR", "limit": 0, "reason": "إعادة الضبط بعد الاختبار"})

    def test_01_no_limit_rejects_and_no_negative(self):
        r = book(self.state["s"], self.state["pkg"])
        assert r.status_code == 400, r.status_code
        assert "الرصيد المتاح غير كافٍ" in r.text, r.text[:300]
        assert avail(self.state["s"], "SAR") == 0

    def test_02_set_limit(self, admin_s):
        r = admin_s.post(f"{API}/admin/credit/{self.state['id']}", json={
            "currency": "SAR", "limit": 2000, "reason": "سقف اختباري"})
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        body = r.json()
        assert "_id" not in body
        assert body["limit"] == 2000

    def test_03_booking_within_limit_succeeds(self):
        r = book(self.state["s"], self.state["pkg"])
        assert r.status_code == 200, r.text[:400]
        b = r.json()
        assert b["credit_used"] == b["amount_charged"], b
        assert avail(self.state["s"], "SAR") == -b["amount_charged"]
        self.state["debt"] = b["amount_charged"]

    def test_04_credit_list_exposure(self, admin_s):
        r = admin_s.get(f"{API}/admin/credit", params={"q": "B2CRD", "only_exposed": True})
        assert r.status_code == 200, r.text[:300]
        rows = [x for x in r.json()["items"] if x["office_id"] == self.state["id"]]
        assert rows, "office missing from credit list"
        c = rows[0]["currencies"]["SAR"]
        assert c["limit"] == 2000
        assert c["used"] == self.state["debt"]
        assert c["headroom"] == round(2000 - self.state["debt"], 2)
        util = round(self.state["debt"] / 2000 * 100, 1)
        assert c["utilization"] == util
        expected = "critical" if util >= 100 else "high" if util >= 90 else "warning" if util >= 70 else "ok"
        assert c["alert"] == expected, (c["alert"], util)
        assert r.json()["totals"]["SAR"]["limit"] >= 2000

    def test_05_beyond_limit_rejected(self):
        bal = avail(self.state["s"], "SAR")
        r = book(self.state["s"], self.state["pkg"])
        assert r.status_code == 400, r.status_code
        assert "تجاوز الحد المتاح" in r.text, r.text[:300]
        assert avail(self.state["s"], "SAR") == bal

    def test_06_lower_limit_below_debt_rejected(self, admin_s):
        r = admin_s.post(f"{API}/admin/credit/{self.state['id']}", json={
            "currency": "SAR", "limit": 10, "reason": "تخفيض غير مسموح"})
        assert r.status_code == 400, f"{r.status_code} {r.text[:200]}"

    def test_07_freeze_blocks_booking(self, admin_s):
        r = admin_s.post(f"{API}/admin/credit/{self.state['id']}/freeze", json={
            "currency": "SAR", "frozen": True, "reason": "تجميد اختباري"})
        assert r.status_code == 200, r.text[:300]
        rb = book(self.state["s"], self.state["pkg"])
        assert rb.status_code == 400
        assert "مجمّد" in rb.text, rb.text[:300]
        r2 = admin_s.post(f"{API}/admin/credit/{self.state['id']}/freeze", json={
            "currency": "SAR", "frozen": False, "reason": "فك التجميد"})
        assert r2.status_code == 200

    def test_08_topup_reduces_debt(self, admin_s):
        fund(admin_s, self.state["s"], 1500, "SAR")
        bal = avail(self.state["s"], "SAR")
        assert abs(bal - (1500 - self.state["debt"])) < 0.02, bal
        r = admin_s.get(f"{API}/admin/credit", params={"q": "B2CRD"})
        row = [x for x in r.json()["items"] if x["office_id"] == self.state["id"]][0]
        assert row["currencies"]["SAR"]["used"] == 0
        assert row["currencies"]["SAR"]["headroom"] == 2000

    def test_09_credit_events_audited(self, admin_s):
        r = admin_s.get(f"{API}/admin/credit/{self.state['id']}/events")
        assert r.status_code == 200, r.text[:300]
        evs = r.json()
        actions = {e["action"] for e in evs}
        assert {"limit_changed", "frozen", "unfrozen"} <= actions, actions
        assert all(e.get("reason") and e.get("by") for e in evs)
        assert any(e["by"] == "abuzay84@gmail.com" for e in evs)
        r2 = admin_s.get(f"{API}/admin/credit-events")
        assert r2.status_code == 200 and isinstance(r2.json(), list)


# ================= LEDGER / VOUCHERS / RECONCILIATION =================
class TestLedger:
    def test_ledger_basic(self, admin_s):
        r = admin_s.get(f"{API}/admin/ledger", params={"limit": 20})
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["total"] > 100, d["total"]
        assert len(d["items"]) == 20
        it = d["items"][0]
        for k in ("office_name", "type_label", "amount", "currency", "id"):
            assert k in it, (k, it)
        assert "_id" not in it
        assert set(d["net"].keys()) == {"SAR", "USD"}
        assert round(d["inflow"]["SAR"] + d["outflow"]["SAR"], 2) == d["net"]["SAR"]

    def test_pagination(self, admin_s):
        p1 = admin_s.get(f"{API}/admin/ledger", params={"limit": 10, "page": 1}).json()
        p2 = admin_s.get(f"{API}/admin/ledger", params={"limit": 10, "page": 2}).json()
        assert {i["id"] for i in p1["items"]}.isdisjoint({i["id"] for i in p2["items"]})
        assert p1["total"] == p2["total"]

    def test_filters(self, admin_s):
        allp = admin_s.get(f"{API}/admin/ledger", params={"limit": 1}).json()
        sar = admin_s.get(f"{API}/admin/ledger", params={"limit": 5, "currency": "SAR"}).json()
        assert all(i["currency"] == "SAR" for i in sar["items"])
        assert sar["total"] < allp["total"]
        assert sar["inflow"]["USD"] == 0 and sar["outflow"]["USD"] == 0

        t = admin_s.get(f"{API}/admin/ledger", params={"limit": 5, "txn_type": "topup"}).json()
        assert all(i["type"] == "topup" for i in t["items"])
        assert t["total"] < allp["total"]

        oid_ = sar["items"][0]["office_id"]
        o = admin_s.get(f"{API}/admin/ledger", params={"limit": 50, "office_id": oid_}).json()
        assert all(i["office_id"] == oid_ for i in o["items"])
        assert o["total"] <= allp["total"]

        q = admin_s.get(f"{API}/admin/ledger", params={"limit": 5, "q": "حجز"}).json()
        assert q["total"] > 0 and q["total"] < allp["total"]

        dt = admin_s.get(f"{API}/admin/ledger", params={
            "limit": 5, "date_from": "2020-01-01", "date_to": "2020-01-02"}).json()
        assert dt["total"] == 0, dt["total"]

    def test_export_csv(self, admin_s):
        r = admin_s.get(f"{API}/admin/ledger/export", params={"currency": "SAR",
                                                             "txn_type": "topup"})
        assert r.status_code == 200, r.text[:200]
        assert "text/csv" in r.headers.get("content-type", "")
        assert "attachment" in r.headers.get("content-disposition", "")
        body = r.content.decode("utf-8")
        assert body.startswith("\ufeff"), "missing UTF-8 BOM"
        lines = [x for x in body.splitlines() if x.strip()]
        assert "العملة" in lines[0]
        n = admin_s.get(f"{API}/admin/ledger", params={
            "limit": 1, "currency": "SAR", "txn_type": "topup"}).json()["total"]
        assert len(lines) - 1 == min(n, 20000), (len(lines) - 1, n)

    def test_voucher_kinds(self, admin_s):
        items = admin_s.get(f"{API}/admin/ledger", params={"limit": 200}).json()["items"]
        pos = next(i for i in items if i["amount"] > 0 and i["type"] not in ("p2p_in", "p2p_out"))
        neg = next(i for i in items if i["amount"] < 0 and i["type"] not in ("p2p_in", "p2p_out"))
        r = admin_s.get(f"{API}/admin/vouchers/{pos['id']}").json()
        assert r["kind_label"] == "سند قبض" and r["kind"] == "receipt"
        assert r["voucher_no"].startswith("MRJ-") and r["amount"] == abs(pos["amount"])
        assert r["party"]["name"]
        r2 = admin_s.get(f"{API}/admin/vouchers/{neg['id']}").json()
        assert r2["kind_label"] == "سند صرف"
        p2p = next((i for i in items if i["type"] in ("p2p_in", "p2p_out")), None)
        if p2p:
            r3 = admin_s.get(f"{API}/admin/vouchers/{p2p['id']}").json()
            assert r3["kind_label"] == "سند تحويل"
        bad = admin_s.get(f"{API}/admin/vouchers/000000000000000000000000")
        assert bad.status_code == 404

    def test_reconciliation(self, admin_s):
        r = admin_s.get(f"{API}/admin/reconciliation")
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        for c in ("SAR", "USD"):
            assert set(d["wallets"][c]) == {"available", "pending", "total"}
            assert isinstance(d["ledger_totals"][c], float)
            assert c in d["platform_revenue"]
        assert isinstance(d["mismatch_count"], int)
        assert len(d["mismatches"]) <= 100
        if d["mismatches"]:
            m = d["mismatches"][0]
            assert round(m["wallet_total"] - m["ledger_total"], 2) == m["difference"]
            assert abs(m["difference"]) > 0.5
            diffs = [abs(x["difference"]) for x in d["mismatches"]]
            assert diffs == sorted(diffs, reverse=True)
        assert d["generated_at"]


# ================= WITHDRAWALS 6-STAGE =================
class TestWithdrawalStages:
    state = {}

    @pytest.fixture(scope="class", autouse=True)
    def setup(self, admin_s):
        s, user, _ = new_office("B2WDR")
        fund(admin_s, s, 500, "SAR")
        r = s.post(f"{API}/wallet/withdrawals", json={
            "amount": 100, "currency": "SAR", "method": "bank",
            "details": "بنك الاختبار - IBAN123"})
        assert r.status_code == 200, r.text[:400]
        self.state["s"] = s
        self.state["wid"] = r.json()["id"]

    def test_01_queue_shape_and_legacy_mapping(self, admin_s):
        r = admin_s.get(f"{API}/admin/withdrawals/queue")
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["stages"][0] == "requested" and d["stages"][-1] == "closed"
        assert len(d["stages"]) == 7
        mine = [x for x in d["items"] if x["id"] == self.state["wid"]]
        assert mine, "new withdrawal not in queue"
        assert mine[0]["stage"] == "requested" and mine[0]["stage_index"] == 0
        assert mine[0]["stage_label"] == "طلب البائع"
        legacy = [x for x in d["items"] if x["status"] == "approved"]
        assert all(x["stage"] in d["stages"] for x in d["items"])
        if legacy:
            assert all(isinstance(x["stage_index"], int) for x in legacy)
        assert set(d["totals"]) == {"SAR", "USD"}

    def test_02_invalid_and_guarded_stages(self, admin_s):
        wid = self.state["wid"]
        r = admin_s.post(f"{API}/admin/withdrawals/{wid}/stage", json={"stage": "bogus"})
        assert r.status_code == 400
        r = admin_s.post(f"{API}/admin/withdrawals/{wid}/stage", json={"stage": "executed"})
        assert r.status_code == 400 and "اعتماد" in r.text, r.text[:200]
        r = admin_s.post(f"{API}/admin/withdrawals/{wid}/stage",
                         json={"stage": "receipt_uploaded"})
        assert r.status_code == 400 and "إيصال" in r.text, r.text[:200]

    def test_03_forward_stages_no_money_movement(self, admin_s):
        wid = self.state["wid"]
        before = avail(self.state["s"], "SAR")
        for st in ("under_review", "approved_internal", "sent_to_accounting"):
            r = admin_s.post(f"{API}/admin/withdrawals/{wid}/stage",
                             json={"stage": st, "note": f"TEST {st}"})
            assert r.status_code == 200, f"{st}: {r.status_code} {r.text[:200]}"
            assert r.json()["stage"] == st
            assert r.json()["history_entry"]["by"] == "abuzay84@gmail.com"
        after = avail(self.state["s"], "SAR")
        assert before == after, f"stage change moved money {before} -> {after}"
        d = admin_s.get(f"{API}/admin/withdrawals/{wid}/detail").json()
        assert d["stage"] == "sent_to_accounting"
        hist = [h["stage"] for h in d.get("stage_history", [])]
        assert hist == ["under_review", "approved_internal", "sent_to_accounting"], hist
        assert d["office"]["email"]

    def test_04_backwards_rejected(self, admin_s):
        r = admin_s.post(f"{API}/admin/withdrawals/{self.state['wid']}/stage",
                         json={"stage": "under_review"})
        assert r.status_code == 400 and "الرجوع" in r.text, r.text[:200]

    def test_05_review_debits_then_executed_allowed(self, admin_s):
        wid = self.state["wid"]
        before = avail(self.state["s"], "SAR")
        r = admin_s.post(f"{API}/admin/withdrawals/{wid}/review", json={"approve": True})
        assert r.status_code == 200, r.text[:300]
        after = avail(self.state["s"], "SAR")
        assert abs((before - 100) - after) < 0.01, (before, after)
        r2 = admin_s.post(f"{API}/admin/withdrawals/{wid}/stage", json={"stage": "executed"})
        assert r2.status_code == 200, r2.text[:300]
        assert abs(avail(self.state["s"], "SAR") - after) < 0.01, "executed stage moved money"

    def test_06_receipt_then_close(self, admin_s):
        wid = self.state["wid"]
        before = avail(self.state["s"], "SAR")
        r = admin_s.post(f"{API}/admin/withdrawals/{wid}/receipt", json={
            "receipt_url": "http://x/receipt.png", "reference": "BANKREF-TEST-1"})
        assert r.status_code == 200, r.text[:300]
        d = admin_s.get(f"{API}/admin/withdrawals/{wid}/detail").json()
        assert d["receipt_url"] == "http://x/receipt.png"
        assert d["bank_reference"] == "BANKREF-TEST-1"
        for st in ("receipt_uploaded", "closed"):
            rr = admin_s.post(f"{API}/admin/withdrawals/{wid}/stage", json={"stage": st})
            assert rr.status_code == 200, f"{st}: {rr.text[:200]}"
        assert abs(avail(self.state["s"], "SAR") - before) < 0.01, "receipt/close moved money"
        d2 = admin_s.get(f"{API}/admin/withdrawals/{wid}/detail").json()
        assert d2["stage"] == "closed" and d2["stage_label"] == "إغلاق الطلب"

    def test_07_short_receipt_url_rejected(self, admin_s):
        r = admin_s.post(f"{API}/admin/withdrawals/{self.state['wid']}/receipt",
                         json={"receipt_url": "ab"})
        assert r.status_code in (400, 422), r.status_code

    def test_08_unknown_ids_404(self, admin_s):
        miss = "000000000000000000000000"
        assert admin_s.get(f"{API}/admin/withdrawals/{miss}/detail").status_code == 404
        assert admin_s.post(f"{API}/admin/withdrawals/{miss}/stage",
                            json={"stage": "under_review"}).status_code == 404
        assert admin_s.post(f"{API}/admin/withdrawals/{miss}/receipt",
                            json={"receipt_url": "http://x/y.png"}).status_code == 404


# ================= REGRESSIONS (protected paths) =================
def _rahal_token(office_ref, email, name):
    payload = {"iss": "rahaal-erp", "aud": "meraaj-network", "office_ref": office_ref,
               "email": email, "office_name": name, "exp": int(time.time()) + 600}
    raw = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    sig = hmac.new(RAHAL_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()
    return f"{raw}.{sig}"


class TestRegression:
    def test_rahal_sso_no_duplicate(self):
        tok = _rahal_token("RHL-OFF-77001", "rahal_office1@qa-example.com", "مكتب رحال 1")
        r = requests.post(f"{API}/integrations/rahal/sso", json={"token": tok})
        assert r.status_code == 200, r.text[:300]
        assert r.json().get("access_token")
        r2 = requests.post(f"{API}/integrations/rahal/sso", json={"token": tok})
        assert r2.status_code == 200
        assert r2.json()["user"]["id"] == r.json()["user"]["id"], "duplicate office created"

    def test_inbound_webhook_hmac(self):
        body = json.dumps({"type": "rahal.ping", "data": {}}).encode()
        sig = hmac.new(RAHAL_SECRET.encode(), body, hashlib.sha256).hexdigest()
        ok = requests.post(f"{API}/integrations/rahal/webhooks", data=body,
                           headers={"Content-Type": "application/json",
                                    "X-Rahal-Signature": sig})
        assert ok.status_code in (200, 202), f"{ok.status_code} {ok.text[:200]}"
        bad = requests.post(f"{API}/integrations/rahal/webhooks", data=body,
                            headers={"Content-Type": "application/json",
                                     "X-Rahal-Signature": "deadbeef"})
        assert bad.status_code == 401, bad.status_code

    def test_office_login_market_wallet(self, office_s):
        assert office_s.get(f"{API}/wallet").status_code == 200
        r = office_s.get(f"{API}/packages")
        assert r.status_code == 200
        assert isinstance(r.json(), (list, dict))

    def test_booking_lifecycle_intact(self, admin_s, seller_s):
        pkg = make_package(seller_s, currency="SAR")
        s, _, _ = new_office("B2LFC")
        fund(admin_s, s, 3000, "SAR")
        r = book(s, pkg["id"])
        assert r.status_code == 200, r.text[:400]
        bid = r.json()["id"]
        lst = seller_s.get(f"{API}/bookings", params={"role": "seller"})
        assert lst.status_code == 200
        rr = seller_s.post(f"{API}/bookings/{bid}/dispatch", json={})
        assert rr.status_code in (200, 400, 404), rr.status_code
        full = admin_s.get(f"{API}/admin/bookings/{bid}/full")
        assert full.status_code == 200
        assert full.json()["booking"]["status"] in ("blue", "green", "yellow", "dispatched")

    def test_admin_pages_load(self, admin_s):
        for path in ("/admin/analytics", "/admin/bookings", "/admin/cancellations",
                     "/admin/topups", "/admin/transfers", "/admin/withdrawals"):
            r = admin_s.get(f"{API}{path}")
            assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:150]}"
