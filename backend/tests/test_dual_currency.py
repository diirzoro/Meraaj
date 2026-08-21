"""Dual-currency (SAR/USD) wallet engine tests — NEW contract (June 2026 refactor).

Covers: wallet shape, currency-preserving top-ups, native-currency bookings/escrow,
cross-currency shortfall at fixed 3.77, blue & yellow cancellation, P2P transfer,
withdrawal, marketer commission per currency, dispute resolution, admin dashboard
per-currency liquidity/revenue, and money conservation.
"""
import uuid
import pytest
import requests

from conftest import API, client, make_package, PLATFORM_PCT, CANCEL_FEE_PCT

RATE = 3.77
MARKETER_PCT = 0.20


# ---------- helpers ----------
def register_office(prefix="DC"):
    email = f"test_{prefix}_{uuid.uuid4().hex[:8]}@qa-example.com".lower()
    r = requests.post(f"{API}/auth/register", json={
        "account_type": "office", "email": email, "password": "Test@1234",
        "office_name": f"TEST_{prefix}", "owner_name": "QA", "phone": "0770000000",
        "governorate": "بغداد", "address": "شارع الاختبار",
    })
    assert r.status_code == 200, f"office register failed {r.status_code}: {r.text[:300]}"
    d = r.json()
    return client(d["access_token"]), d["user"], email


def register_individual(prefix="IND"):
    email = f"test_{prefix}_{uuid.uuid4().hex[:8]}@qa-example.com".lower()
    r = requests.post(f"{API}/auth/register", json={
        "account_type": "individual", "email": email, "password": "Test@1234",
        "name": f"TEST_{prefix}", "phone": "0770000001", "governorate": "بغداد",
    })
    assert r.status_code == 200, f"individual register failed {r.status_code}: {r.text[:300]}"
    d = r.json()
    return client(d["access_token"]), d["user"], email


def fund(admin_s, session, amount, currency):
    r = session.post(f"{API}/wallet/topups", json={
        "amount": amount, "currency": currency, "method": "bank", "receipt_url": "http://x/r.png"})
    assert r.status_code == 200, r.text[:300]
    tid = r.json()["id"]
    assert r.json()["currency"] == currency
    r2 = admin_s.post(f"{API}/admin/topups/{tid}/review", json={"approve": True})
    assert r2.status_code == 200, r2.text[:300]


def wallet(session):
    r = session.get(f"{API}/wallet")
    assert r.status_code == 200, r.text[:300]
    w = r.json()
    assert set(w.keys()) >= {"SAR", "USD"}, f"unexpected wallet shape: {w}"
    return w


def av(w, c):
    return round(w[c]["available"], 2)


def pend(w, c):
    return round(w[c]["pending"], 2)


def book(session, pkg_id, seats=1, ref=None):
    regs = [{"name": f"QA {i}", "passport_no": f"P{uuid.uuid4().hex[:7]}", "age": 30} for i in range(seats)]
    body = {"package_id": pkg_id, "registrants": regs}
    if ref:
        body["ref"] = ref
    return session.post(f"{API}/bookings", json=body)


@pytest.fixture(scope="module")
def sellers_and_admin():
    r = requests.post(f"{API}/auth/login", json={"email": "abuzay84@gmail.com", "password": "Meraaj@2026"})
    assert r.status_code == 200, f"admin login failed: {r.text[:200]}"
    admin_s = client(r.json()["access_token"])
    seller_s, seller_u, _ = register_office("SELL")
    return admin_s, seller_s, seller_u


class TestDualCurrencyWallet:
    """New wallet shape + currency-preserving top-ups"""

    def test_fresh_wallet_shape(self, sellers_and_admin):
        buyer_s, _, _ = register_office("SHAPE")
        w = wallet(buyer_s)
        for c in ("SAR", "USD"):
            assert set(w[c].keys()) == {"available", "pending", "total"}, w
            assert w[c]["available"] == 0 and w[c]["pending"] == 0 and w[c]["total"] == 0

    def test_topup_keeps_currency(self, sellers_and_admin):
        admin_s, _, _ = sellers_and_admin
        buyer_s, _, _ = register_office("TOPUP")
        fund(admin_s, buyer_s, 5000, "SAR")
        w = wallet(buyer_s)
        assert av(w, "SAR") == 5000.0, w
        assert av(w, "USD") == 0.0, w
        fund(admin_s, buyer_s, 1200, "USD")
        w = wallet(buyer_s)
        assert av(w, "SAR") == 5000.0 and av(w, "USD") == 1200.0, w
        assert w["SAR"]["total"] == 5000.0 and w["USD"]["total"] == 1200.0


class TestSarBooking:
    """SAR-priced program: native debit, native escrow, blue cancel"""

    def test_sar_booking_deducts_only_sar(self, sellers_and_admin):
        admin_s, seller_s, _ = sellers_and_admin
        buyer_s, _, _ = register_office("SARB")
        fund(admin_s, buyer_s, 10000, "SAR")
        fund(admin_s, buyer_s, 500, "USD")
        pkg = make_package(seller_s, currency="SAR", net_cost_per_seat=1000.0,
                           final_sale_price=1500.0, buyer_office_commission=200.0)
        sw0 = wallet(seller_s)
        r = book(buyer_s, pkg["id"], seats=2)
        assert r.status_code == 200, r.text[:300]
        b = r.json()
        fee = round(400 * PLATFORM_PCT, 2)  # 10% of buyer commission total
        assert b["currency"] == "SAR"
        assert b["net_cost_total"] == 2000.0
        assert b["platform_fee"] == fee
        assert b["amount_charged"] == round(2000 + fee, 2)
        assert b["debit_split"] == {"SAR": round(2000 + fee, 2), "USD": 0.0}, b["debit_split"]
        bw = wallet(buyer_s)
        assert av(bw, "SAR") == round(10000 - 2000 - fee, 2), bw
        assert av(bw, "USD") == 500.0, "USD balance must be untouched"
        sw = wallet(seller_s)
        assert pend(sw, "SAR") == round(pend(sw0, "SAR") + 2000, 2), sw
        assert pend(sw, "USD") == pend(sw0, "USD")

    def test_blue_cancel_refunds_in_program_currency(self, sellers_and_admin):
        admin_s, seller_s, _ = sellers_and_admin
        buyer_s, _, _ = register_office("BLUEC")
        fund(admin_s, buyer_s, 8000, "SAR")
        pkg = make_package(seller_s, currency="SAR", net_cost_per_seat=1000.0,
                           final_sale_price=1500.0, buyer_office_commission=200.0)
        sw0 = wallet(seller_s)
        r = book(buyer_s, pkg["id"], seats=1)
        assert r.status_code == 200, r.text[:300]
        b = r.json()
        rc = buyer_s.post(f"{API}/bookings/{b['id']}/cancel-request")
        assert rc.status_code == 200, rc.text[:300]
        data = rc.json()
        admin_fee = round(1000 * CANCEL_FEE_PCT, 2)
        assert data["admin_fee"] == admin_fee
        assert data["refund"] == round(b["amount_charged"] - admin_fee, 2)
        bw = wallet(buyer_s)
        assert av(bw, "SAR") == round(8000 - admin_fee, 2), bw
        assert av(bw, "USD") == 0.0
        sw = wallet(seller_s)
        assert pend(sw, "SAR") == pend(sw0, "SAR"), "seller escrow must be reversed"


class TestCrossCurrencyShortfall:
    """USD program paid partly from SAR at the fixed 3.77 rate"""

    def test_usd_shortfall_covered_from_sar(self, sellers_and_admin):
        admin_s, seller_s, _ = sellers_and_admin
        buyer_s, _, _ = register_office("XCUR")
        fund(admin_s, buyer_s, 500, "USD")
        fund(admin_s, buyer_s, 10000, "SAR")
        pkg = make_package(seller_s, currency="USD", net_cost_per_seat=1000.0,
                           final_sale_price=1300.0, buyer_office_commission=200.0)
        sw0 = wallet(seller_s)
        r = book(buyer_s, pkg["id"], seats=1)
        assert r.status_code == 200, r.text[:300]
        b = r.json()
        fee = round(200 * PLATFORM_PCT, 2)
        required = round(1000 + fee, 2)
        shortfall = round(required - 500, 2)
        sar_debit = round(shortfall * RATE, 2)
        assert b["currency"] == "USD"
        assert b["debit_split"]["USD"] == 500.0, b["debit_split"]
        assert b["debit_split"]["SAR"] == pytest.approx(sar_debit, abs=0.02), b["debit_split"]
        bw = wallet(buyer_s)
        assert av(bw, "USD") == 0.0, bw
        assert av(bw, "SAR") == pytest.approx(round(10000 - sar_debit, 2), abs=0.02), bw
        sw = wallet(seller_s)
        assert pend(sw, "USD") == round(pend(sw0, "USD") + 1000, 2), "escrow must be USD"

    def test_insufficient_total_funds_rejected(self, sellers_and_admin):
        admin_s, seller_s, _ = sellers_and_admin
        buyer_s, _, _ = register_office("POOR")
        fund(admin_s, buyer_s, 100, "USD")
        fund(admin_s, buyer_s, 100, "SAR")
        pkg = make_package(seller_s, currency="USD", net_cost_per_seat=1000.0,
                           final_sale_price=1300.0, buyer_office_commission=200.0)
        r = book(buyer_s, pkg["id"], seats=1)
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:200]}"
        w = wallet(buyer_s)
        assert av(w, "USD") == 100.0 and av(w, "SAR") == 100.0, "no partial debit allowed"


class TestSettlementGuard:
    def test_settle_blocked_before_grace(self, sellers_and_admin):
        admin_s, seller_s, _ = sellers_and_admin
        buyer_s, _, _ = register_office("SETL")
        fund(admin_s, buyer_s, 5000, "SAR")
        pkg = make_package(seller_s, currency="SAR", net_cost_per_seat=1000.0,
                           final_sale_price=1500.0, buyer_office_commission=200.0)
        b = book(buyer_s, pkg["id"], seats=1).json()
        # settle before dispatch
        r0 = seller_s.post(f"{API}/bookings/{b['id']}/settle")
        assert r0.status_code == 400, r0.text[:200]
        rv = seller_s.post(f"{API}/bookings/{b['id']}/issue-visas",
                           json={"visas": [{"index": 0, "visa_no": "V-123"}]})
        assert rv.status_code == 200, rv.text[:300]
        rd = seller_s.post(f"{API}/bookings/{b['id']}/dispatch")
        assert rd.status_code == 200, rd.text[:300]
        r = seller_s.post(f"{API}/bookings/{b['id']}/settle")
        assert r.status_code == 400, f"grace guard missing: {r.status_code} {r.text[:200]}"
        sw = wallet(seller_s)
        assert sw["SAR"]["pending"] >= 1000, "escrow must remain pending before grace"


class TestYellowCancellation:
    def test_yellow_flow_settles_in_program_currency(self, sellers_and_admin):
        admin_s, seller_s, _ = sellers_and_admin
        buyer_s, _, _ = register_office("YELW")
        fund(admin_s, buyer_s, 6000, "SAR")
        pkg = make_package(seller_s, currency="SAR", net_cost_per_seat=1000.0,
                           final_sale_price=1500.0, buyer_office_commission=200.0)
        sw0 = wallet(seller_s)
        b = book(buyer_s, pkg["id"], seats=1).json()
        fee = b["platform_fee"]
        rv = seller_s.post(f"{API}/bookings/{b['id']}/issue-visas",
                           json={"visas": [{"index": 0, "visa_no": "V-999"}]})
        assert rv.status_code == 200, rv.text[:300]
        r1 = buyer_s.post(f"{API}/bookings/{b['id']}/cancel-request")
        assert r1.status_code == 200 and r1.json()["cancellation"] == "awaiting_seller", r1.text[:300]
        deduction = 300.0
        r2 = seller_s.post(f"{API}/bookings/{b['id']}/cancel-offer", json={"deduction": deduction})
        assert r2.status_code == 200, r2.text[:300]
        r3 = buyer_s.post(f"{API}/bookings/{b['id']}/cancel-accept")
        assert r3.status_code == 200, r3.text[:300]
        d = r3.json()
        cut = round(deduction * PLATFORM_PCT, 2)
        assert d["seller_keeps"] == round(deduction - cut, 2)
        assert d["refund"] == round(1000 - deduction + fee, 2)
        bw = wallet(buyer_s)
        assert av(bw, "SAR") == round(6000 - b["amount_charged"] + d["refund"], 2), bw
        assert av(bw, "USD") == 0.0 and bw["USD"]["total"] == 0.0, "USD bucket must be untouched"
        sw = wallet(seller_s)
        assert pend(sw, "SAR") == pend(sw0, "SAR"), "escrow must be released"
        assert av(sw, "SAR") == round(av(sw0, "SAR") + d["seller_keeps"], 2), sw
        # money conservation in SAR terms: buyer_out == seller_keeps + platform (cut + admin) ...
        buyer_out = round(b["amount_charged"] - d["refund"], 2)
        assert buyer_out == round(d["seller_keeps"] + cut, 2), (
            f"value leak: buyer paid {buyer_out}, seller+platform got {d['seller_keeps'] + cut}")


class TestP2PAndWithdrawal:
    def test_transfer_currency_aware(self, sellers_and_admin):
        admin_s, _, _ = sellers_and_admin
        a_s, _, _ = register_office("TRFA")
        b_s, _, b_email = register_office("TRFB")
        fund(admin_s, a_s, 3000, "SAR")
        # insufficient in USD even though SAR is funded
        r_bad = a_s.post(f"{API}/wallet/transfers",
                         json={"to_email": b_email, "amount": 100, "currency": "USD", "note": "x"})
        assert r_bad.status_code == 400, f"expected 400 for USD transfer w/o USD funds: {r_bad.status_code}"
        r = a_s.post(f"{API}/wallet/transfers",
                     json={"to_email": b_email, "amount": 1000, "currency": "SAR", "note": "TEST"})
        assert r.status_code == 200, r.text[:300]
        tr = r.json()
        assert tr["currency"] == "SAR"
        ra = admin_s.post(f"{API}/admin/transfers/{tr['id']}/review", json={"approve": True})
        assert ra.status_code == 200, ra.text[:300]
        wa, wb = wallet(a_s), wallet(b_s)
        assert av(wa, "SAR") == 2000.0 and av(wa, "USD") == 0.0, wa
        assert av(wb, "SAR") == 1000.0 and av(wb, "USD") == 0.0, wb

    def test_withdrawal_currency_aware(self, sellers_and_admin):
        admin_s, _, _ = sellers_and_admin
        s, _, _ = register_office("WDR")
        fund(admin_s, s, 2000, "SAR")
        r_bad = s.post(f"{API}/wallet/withdrawals",
                       json={"amount": 50, "currency": "USD", "method": "bank", "details": "acct"})
        assert r_bad.status_code == 400, f"expected 400 for USD withdrawal: {r_bad.status_code}"
        r = s.post(f"{API}/wallet/withdrawals",
                   json={"amount": 700, "currency": "SAR", "method": "bank", "details": "acct"})
        assert r.status_code == 200, r.text[:300]
        wd = r.json()
        assert wd["currency"] == "SAR"
        ra = admin_s.post(f"{API}/admin/withdrawals/{wd['id']}/review", json={"approve": True})
        assert ra.status_code == 200, ra.text[:300]
        w = wallet(s)
        assert av(w, "SAR") == 1300.0 and av(w, "USD") == 0.0, w


class TestMarketerCommission:
    def test_marketer_commission_in_program_currency(self, sellers_and_admin):
        admin_s, seller_s, _ = sellers_and_admin
        mk_s, _, _ = register_individual("MKTR")
        rm = mk_s.post(f"{API}/individual/become-marketer")
        assert rm.status_code == 200, rm.text[:300]
        code = rm.json()["affiliate_code"]
        buyer_s, _, _ = register_individual("B2C")
        fund(admin_s, buyer_s, 9000, "SAR")
        pkg = make_package(seller_s, currency="SAR", net_cost_per_seat=1000.0,
                           final_sale_price=1500.0, buyer_office_commission=200.0)
        r = book(buyer_s, pkg["id"], seats=1, ref=code)
        assert r.status_code == 200, r.text[:300]
        b = r.json()
        margin = 500.0
        expected_comm = round(margin * MARKETER_PCT, 2)
        assert b["currency"] == "SAR"
        assert b["amount_charged"] == 1500.0, b
        assert b["marketer_commission"] == expected_comm, b
        assert b["platform_profit"] == round(margin - expected_comm, 2), b
        mw = wallet(mk_s)
        assert pend(mw, "SAR") == expected_comm, mw
        assert pend(mw, "USD") == 0.0 and av(mw, "USD") == 0.0, mw
        aff = mk_s.get(f"{API}/individual/affiliate")
        assert aff.status_code == 200, aff.text[:300]
        te = aff.json()["total_earned"]
        assert isinstance(te, dict) and set(te.keys()) == {"SAR", "USD"}, te
        assert te["SAR"] == expected_comm and te["USD"] == 0.0, te


class TestDisputeCurrencyAware:
    def test_dispute_refund_buyer_in_program_currency(self, sellers_and_admin):
        admin_s, seller_s, _ = sellers_and_admin
        buyer_s, _, _ = register_office("DISP")
        fund(admin_s, buyer_s, 5000, "SAR")
        pkg = make_package(seller_s, currency="SAR", net_cost_per_seat=1000.0,
                           final_sale_price=1500.0, buyer_office_commission=200.0)
        sw0 = wallet(seller_s)
        b = book(buyer_s, pkg["id"], seats=1).json()
        seller_s.post(f"{API}/bookings/{b['id']}/issue-visas",
                      json={"visas": [{"index": 0, "visa_no": "V-777"}]})
        rd = seller_s.post(f"{API}/bookings/{b['id']}/dispatch")
        assert rd.status_code == 200, rd.text[:300]
        rdis = buyer_s.post(f"{API}/bookings/{b['id']}/dispute", json={"reason": "TEST dispute"})
        assert rdis.status_code == 200, rdis.text[:300]
        rr = admin_s.post(f"{API}/admin/disputes/{b['id']}/resolve", json={"resolution": "refund_buyer"})
        assert rr.status_code == 200, rr.text[:300]
        bw = wallet(buyer_s)
        assert av(bw, "SAR") == 5000.0, f"buyer must be made whole in SAR: {bw}"
        assert av(bw, "USD") == 0.0
        sw = wallet(seller_s)
        assert pend(sw, "SAR") == pend(sw0, "SAR"), sw


class TestAdminDashboardPerCurrency:
    def test_dashboard_split_per_currency(self, sellers_and_admin):
        admin_s, _, _ = sellers_and_admin
        r = admin_s.get(f"{API}/admin/dashboard")
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert "liquidity" in d and set(d["liquidity"].keys()) == {"SAR", "USD"}, d.get("liquidity")
        for c in ("SAR", "USD"):
            assert set(d["liquidity"][c].keys()) == {"available", "pending", "total"}
        assert isinstance(d["platform_revenue"], dict), d["platform_revenue"]
        assert set(d["platform_revenue"].keys()) == {"SAR", "USD"}, d["platform_revenue"]
        assert "total_system_balance" not in d, "obsolete merged field still present"

    def test_liquidity_moves_with_currency_of_topup(self, sellers_and_admin):
        admin_s, _, _ = sellers_and_admin
        before = admin_s.get(f"{API}/admin/dashboard").json()["liquidity"]
        s, _, _ = register_office("LIQ")
        fund(admin_s, s, 1000, "SAR")
        after = admin_s.get(f"{API}/admin/dashboard").json()["liquidity"]
        assert after["SAR"]["available"] == pytest.approx(before["SAR"]["available"] + 1000, abs=0.05)
        assert after["USD"]["available"] == pytest.approx(before["USD"]["available"], abs=0.05)


class TestMoneyConservation:
    def test_no_negative_balances_and_value_conserved(self, sellers_and_admin):
        """Cross-currency booking then blue cancel: total value (in SAR terms @3.77) preserved
        minus the 2% admin fee, and no bucket goes negative."""
        admin_s, seller_s, _ = sellers_and_admin
        buyer_s, _, _ = register_office("CONS")
        fund(admin_s, buyer_s, 400, "USD")
        fund(admin_s, buyer_s, 8000, "SAR")

        def value_sar(w):
            return round(w["SAR"]["available"] + w["SAR"]["pending"]
                         + (w["USD"]["available"] + w["USD"]["pending"]) * RATE, 2)

        v0 = value_sar(wallet(buyer_s))
        pkg = make_package(seller_s, currency="USD", net_cost_per_seat=800.0,
                           final_sale_price=1000.0, buyer_office_commission=150.0)
        r = book(buyer_s, pkg["id"], seats=1)
        assert r.status_code == 200, r.text[:300]
        b = r.json()
        w1 = wallet(buyer_s)
        for c in ("SAR", "USD"):
            for k in ("available", "pending", "total"):
                assert w1[c][k] >= -0.01, f"negative balance {c}.{k}={w1[c][k]}"
        v1 = value_sar(w1)
        assert v1 == pytest.approx(round(v0 - b["amount_charged"] * RATE, 2), abs=1.0), (v0, v1)
        rc = buyer_s.post(f"{API}/bookings/{b['id']}/cancel-request")
        assert rc.status_code == 200, rc.text[:300]
        admin_fee = rc.json()["admin_fee"]
        v2 = value_sar(wallet(buyer_s))
        assert v2 == pytest.approx(round(v0 - admin_fee * RATE, 2), abs=1.0), (v0, v2, admin_fee)
