"""B2C layer (individual / marketer) tests — iteration 3."""
import uuid
import requests
import pytest
from conftest import API, client, new_office, fund_office, make_package, wallet_of, PLATFORM_PCT, CANCEL_FEE_PCT

MARKETER_PCT = 0.20


# ---------- helpers ----------
def new_individual(prefix="IND"):
    email = f"test_{prefix}_{uuid.uuid4().hex[:8]}@qa-example.com".lower()
    payload = {
        "account_type": "individual", "email": email, "password": "Test@1234",
        "name": f"TEST_فرد_{prefix}", "phone": "0771111111", "governorate": "بغداد",
    }
    r = requests.post(f"{API}/auth/register", json=payload)
    assert r.status_code == 200, f"individual register failed {r.status_code}: {r.text[:300]}"
    d = r.json()
    return client(d["access_token"]), d["user"], d["access_token"]


def platform_revenue(admin_session):
    r = admin_session.get(f"{API}/admin/dashboard")
    assert r.status_code == 200, r.text[:300]
    return r.json()["platform_revenue"]


def revenue_for_booking(booking_id):
    """Sum platform_revenue rows for one booking (parallel-safe, unlike the global total)."""
    from pymongo import MongoClient
    from dotenv import dotenv_values
    env = dotenv_values("/app/backend/.env")
    cli = MongoClient(env["MONGO_URL"])
    rows = list(cli[env["DB_NAME"]].platform_revenue.find({"ref": booking_id}))
    cli.close()
    return round(sum(r["amount"] for r in rows), 2), rows


# ---------- registration ----------
class TestSmartRegistration:
    def test_register_individual(self):
        sess, user, _ = new_individual()
        assert user["role"] == "individual"
        assert user["is_marketer"] is False
        assert user["affiliate_code"] is None
        assert "password_hash" not in user and "_id" not in user
        me = sess.get(f"{API}/auth/me")
        assert me.status_code == 200
        assert me.json()["role"] == "individual"
        assert me.json()["office_name"] == user["office_name"]  # display name

    def test_register_individual_missing_name_400(self):
        r = requests.post(f"{API}/auth/register", json={
            "account_type": "individual",
            "email": f"test_noname_{uuid.uuid4().hex[:6]}@qa-example.com",
            "password": "Test@1234", "phone": "077", "governorate": "بغداد"})
        assert r.status_code == 400, r.text[:200]

    def test_register_office_missing_office_name_400(self):
        r = requests.post(f"{API}/auth/register", json={
            "account_type": "office",
            "email": f"test_noofc_{uuid.uuid4().hex[:6]}@qa-example.com",
            "password": "Test@1234", "phone": "077", "governorate": "بغداد"})
        assert r.status_code == 400, r.text[:200]

    def test_register_office_with_license(self):
        email = f"test_lic_{uuid.uuid4().hex[:8]}@qa-example.com"
        r = requests.post(f"{API}/auth/register", json={
            "account_type": "office", "email": email, "password": "Test@1234",
            "office_name": "TEST_OFC_LIC", "owner_name": "QA", "phone": "0770",
            "governorate": "بغداد", "address": "شارع", "commercial_license": "LIC-123"})
        assert r.status_code == 200, r.text[:300]
        u = r.json()["user"]
        assert u["role"] == "office"
        assert u["commercial_license"] == "LIC-123"


# ---------- pricing visibility ----------
class TestPricingVisibility:
    def test_pricing_stripped_for_individual_and_guest_shown_for_office(self, admin):
        seller, _, _ = new_office("PVSELL")
        pkg = make_package(seller)
        ind, _, _ = new_individual("PVIND")

        # office sees full pricing
        r = seller.get(f"{API}/packages/{pkg['id']}")
        assert r.status_code == 200
        assert r.json()["net_cost_per_seat"] == 1000.0
        assert r.json()["buyer_office_commission"] == 200.0

        # individual: stripped, final price present
        r2 = ind.get(f"{API}/packages/{pkg['id']}")
        assert r2.status_code == 200
        d = r2.json()
        assert "net_cost_per_seat" not in d, "net cost leaked to individual"
        assert "buyer_office_commission" not in d, "office commission leaked to individual"
        assert d["final_sale_price"] == 1300.0

        # guest: stripped
        r3 = requests.get(f"{API}/packages/{pkg['id']}")
        assert r3.status_code == 200
        assert "net_cost_per_seat" not in r3.json()

        # list endpoint too
        lst = ind.get(f"{API}/packages").json()
        assert all("net_cost_per_seat" not in p for p in lst)
        lst_o = seller.get(f"{API}/packages").json()
        assert all("net_cost_per_seat" in p for p in lst_o)


# ---------- authorization ----------
class TestIndividualAuthorization:
    def test_individual_cannot_create_or_list_own_packages(self):
        ind, _, _ = new_individual("AUTH")
        r = ind.post(f"{API}/packages", json={
            "type": "umrah", "title": "TEST_hack", "departure_date": "2026-09-01",
            "return_date": "2026-09-10", "net_cost_per_seat": 1.0, "final_sale_price": 2.0,
            "buyer_office_commission": 1.0, "total_seats": 1})
        assert r.status_code == 403, f"individual created a package! {r.status_code}"
        assert r.json()["detail"]
        assert ind.get(f"{API}/packages/mine").status_code == 403

    def test_office_cannot_become_marketer(self):
        ofc, _, _ = new_office("NOTMKT")
        assert ofc.post(f"{API}/individual/become-marketer").status_code == 403
        assert ofc.get(f"{API}/individual/affiliate").status_code == 403

    def test_individual_blocked_from_admin(self):
        ind, _, _ = new_individual("NOADM")
        assert ind.get(f"{API}/admin/dashboard").status_code == 403


# ---------- marketer ----------
class TestMarketer:
    def test_become_marketer_idempotent_and_affiliate_link(self):
        ind, _, _ = new_individual("MKT")
        r = ind.post(f"{API}/individual/become-marketer")
        assert r.status_code == 200, r.text[:300]
        code = r.json()["affiliate_code"]
        assert r.json()["is_marketer"] is True
        assert isinstance(code, str) and len(code) == 8

        r2 = ind.post(f"{API}/individual/become-marketer")
        assert r2.json()["affiliate_code"] == code, "code regenerated on second activation"

        aff = ind.get(f"{API}/individual/affiliate")
        assert aff.status_code == 200
        a = aff.json()
        assert a["affiliate_code"] == code
        assert a["link"] and a["link"].endswith(f"/?ref={code}")
        assert a["total_earned"] == 0
        assert a["transactions"] == []


# ---------- individual wallet ----------
class TestIndividualWallet:
    def test_wallet_and_topup_flow(self, admin):
        ind, _, _ = new_individual("WAL")
        w = wallet_of(ind)
        assert w == {"total": 0.0, "pending": 0.0, "available": 0.0}
        fund_office(admin, ind, 500)
        w2 = wallet_of(ind)
        assert w2["available"] == 500 and w2["total"] == 500
        txns = ind.get(f"{API}/wallet/transactions").json()
        assert any(t["type"] == "topup" and t["amount"] == 500 for t in txns)
        tp = ind.get(f"{API}/wallet/topups").json()
        assert tp[0]["status"] == "approved"

    def test_insufficient_balance_booking_blocked(self, admin):
        seller, _, _ = new_office("INSSELL")
        pkg = make_package(seller)
        ind, _, _ = new_individual("INS")
        fund_office(admin, ind, 100)
        r = ind.post(f"{API}/bookings", json={"package_id": pkg["id"], "registrants": [
            {"name": "A", "passport_no": "P1", "age": 30}]})
        assert r.status_code == 400
        assert wallet_of(ind)["available"] == 100


# ---------- B2C booking money math ----------
class TestB2CBooking:
    def test_individual_booking_charges_retail_and_splits_margin(self, admin):
        seller, _, _ = new_office("B2CSELL")
        pkg = make_package(seller)  # net 1000, final 1300, comm 200
        ind, _, _ = new_individual("B2CBUY")
        fund_office(admin, ind, 3000)
        rev_before = platform_revenue(admin)

        r = ind.post(f"{API}/bookings", json={"package_id": pkg["id"], "registrants": [
            {"name": "A", "passport_no": "P1", "age": 30},
            {"name": "B", "passport_no": "P2", "age": 25}]})
        assert r.status_code == 200, r.text[:300]
        b = r.json()
        assert b["buyer_type"] == "individual"
        assert b["amount_charged"] == 2600.0        # 1300 * 2
        assert b["net_cost_total"] == 2000.0
        assert b["platform_fee"] == 0.0
        assert b["marketer_id"] is None
        assert b["marketer_commission"] == 0.0
        assert b["platform_profit"] == 600.0        # margin 300*2
        assert b["status"] == "blue"

        assert wallet_of(ind)["available"] == 400.0
        sw = wallet_of(seller)
        assert sw["pending"] == 2000.0 and sw["total"] == 2000.0
        assert platform_revenue(admin) >= rev_before
        assert revenue_for_booking(b["id"])[0] == 600.0

        # visible in my bookings
        mine = ind.get(f"{API}/bookings?role=buyer").json()
        assert any(x["id"] == b["id"] for x in mine)
        # seats decremented
        assert seller.get(f"{API}/packages/{pkg['id']}").json()["available_seats"] == 8

    def test_affiliate_ref_credits_marketer(self, admin):
        seller, _, _ = new_office("AFFSELL")
        pkg = make_package(seller)
        mkt, mkt_user, _ = new_individual("AFFMKT")
        code = mkt.post(f"{API}/individual/become-marketer").json()["affiliate_code"]
        buyer, _, _ = new_individual("AFFBUY")
        fund_office(admin, buyer, 2000)
        rev_before = platform_revenue(admin)

        r = buyer.post(f"{API}/bookings", json={
            "package_id": pkg["id"], "ref": code,
            "registrants": [{"name": "A", "passport_no": "P1", "age": 30}]})
        assert r.status_code == 200, r.text[:300]
        b = r.json()
        margin = 300.0
        assert b["marketer_commission"] == round(margin * MARKETER_PCT, 2) == 60.0
        assert b["platform_profit"] == 240.0
        assert b["amount_charged"] == 1300.0

        mw = wallet_of(mkt)
        # FIX A: commission is escrowed in PENDING until the seller settles
        assert mw["pending"] == 60.0 and mw["available"] == 0.0 and mw["total"] == 60.0, mw
        aff = mkt.get(f"{API}/individual/affiliate").json()
        assert aff["total_earned"] == 60.0
        assert len(aff["transactions"]) == 1
        assert platform_revenue(admin) >= rev_before
        assert revenue_for_booking(b["id"])[0] == 240.0

    def test_bad_ref_ignored(self, admin):
        seller, _, _ = new_office("BADREFS")
        pkg = make_package(seller)
        buyer, _, _ = new_individual("BADREF")
        fund_office(admin, buyer, 1500)
        r = buyer.post(f"{API}/bookings", json={
            "package_id": pkg["id"], "ref": "NOSUCHCODE",
            "registrants": [{"name": "A", "passport_no": "P1", "age": 30}]})
        assert r.status_code == 200, r.text[:300]
        assert r.json()["marketer_id"] is None
        assert r.json()["platform_profit"] == 300.0


# ---------- B2C cancellation reversal ----------
class TestB2CCancellation:
    def test_blue_cancel_reverses_margin_and_marketer(self, admin):
        seller, _, _ = new_office("CANSELL")
        pkg = make_package(seller)
        mkt, _, _ = new_individual("CANMKT")
        code = mkt.post(f"{API}/individual/become-marketer").json()["affiliate_code"]
        buyer, _, _ = new_individual("CANBUY")
        fund_office(admin, buyer, 1500)
        rev_before = platform_revenue(admin)

        b = buyer.post(f"{API}/bookings", json={
            "package_id": pkg["id"], "ref": code,
            "registrants": [{"name": "A", "passport_no": "P1", "age": 30}]}).json()
        assert wallet_of(mkt)["pending"] == 60.0

        c = buyer.post(f"{API}/bookings/{b['id']}/cancel-request")
        assert c.status_code == 200, c.text[:300]
        admin_fee = round(1000 * CANCEL_FEE_PCT, 2)
        expected_refund = round(1300 - admin_fee, 2)
        assert c.json()["refund"] == expected_refund
        # buyer refunded
        assert wallet_of(buyer)["available"] == round(1500 - 1300 + expected_refund, 2)
        # seller escrow released back
        assert wallet_of(seller)["pending"] == 0.0
        # marketer pending commission reversed (no money created)
        mw = wallet_of(mkt)
        assert mw["available"] == 0.0 and mw["pending"] == 0.0 and mw["total"] == 0.0, mw
        # platform revenue for THIS booking = profit +240, reversal -240, admin fee kept (FIX D)
        total, rows = revenue_for_booking(b["id"])
        assert total == round(1000 * CANCEL_FEE_PCT, 2), f"unexpected revenue rows: {rows}"
        assert len(rows) == 3, rows
        # seats restored
        assert seller.get(f"{API}/packages/{pkg['id']}").json()["available_seats"] == 10
        # double cancel blocked
        assert buyer.post(f"{API}/bookings/{b['id']}/cancel-request").status_code == 400

    def test_yellow_cancel_blocked_for_individual(self, admin):
        seller, _, _ = new_office("YELSELL")
        pkg = make_package(seller)
        buyer, _, _ = new_individual("YELBUY")
        fund_office(admin, buyer, 1500)
        b = buyer.post(f"{API}/bookings", json={"package_id": pkg["id"], "registrants": [
            {"name": "A", "passport_no": "P1", "age": 30}]}).json()
        v = seller.post(f"{API}/bookings/{b['id']}/issue-visas",
                        json={"visas": [{"index": 0, "visa_no": "V-1"}]})
        assert v.status_code == 200 and v.json()["status"] == "yellow"
        c = buyer.post(f"{API}/bookings/{b['id']}/cancel-request")
        assert c.status_code == 400, f"individual yellow cancellation allowed! {c.status_code}"
        assert "التأشيرات" in c.json()["detail"]


# ---------- admin metrics ----------
class TestAdminMetrics:
    def test_dashboard_new_metrics(self, admin):
        d = admin.get(f"{API}/admin/dashboard")
        assert d.status_code == 200
        j = d.json()
        for k in ("platform_revenue", "individuals_count", "marketers_count"):
            assert k in j, f"missing metric {k}"
        before = j
        ind, _, _ = new_individual("METRIC")
        ind.post(f"{API}/individual/become-marketer")
        after = admin.get(f"{API}/admin/dashboard").json()
        assert after["individuals_count"] >= before["individuals_count"] + 1
        assert after["marketers_count"] >= before["marketers_count"] + 1


# ---------- B2B regression ----------
class TestB2BRegression:
    def test_office_booking_lifecycle_and_fees(self, admin):
        seller, _, _ = new_office("REGSELL")
        buyer, _, _ = new_office("REGBUY")
        pkg = make_package(seller)
        fund_office(admin, buyer, 2000)
        r = buyer.post(f"{API}/bookings", json={"package_id": pkg["id"], "registrants": [
            {"name": "A", "passport_no": "P1", "age": 30}]})
        assert r.status_code == 200, r.text[:300]
        b = r.json()
        expected_fee = round(200 * PLATFORM_PCT, 2)
        assert b["platform_fee"] == expected_fee
        assert b["amount_charged"] == round(1000 + expected_fee, 2)
        assert b["platform_profit"] == 0.0 and b["marketer_commission"] == 0.0
        assert wallet_of(buyer)["available"] == round(2000 - 1000 - expected_fee, 2)
        assert wallet_of(seller)["pending"] == 1000.0

        # visas mandatory for all registrants
        assert seller.post(f"{API}/bookings/{b['id']}/issue-visas",
                           json={"visas": [{"index": 0, "visa_no": ""}]}).status_code == 400
        assert seller.post(f"{API}/bookings/{b['id']}/issue-visas",
                           json={"visas": [{"index": 0, "visa_no": "V1"}]}).status_code == 200
        # dispatch then settle blocked <24h
        assert seller.post(f"{API}/bookings/{b['id']}/dispatch").json()["status"] == "green"
        s = seller.post(f"{API}/bookings/{b['id']}/settle")
        assert s.status_code == 400 and "السماح" in s.json()["detail"]
        # cancellation after dispatch blocked
        assert buyer.post(f"{API}/bookings/{b['id']}/cancel-request").status_code == 400

    def test_office_blue_cancel_refund(self, admin):
        seller, _, _ = new_office("BCSELL")
        buyer, _, _ = new_office("BCBUY")
        pkg = make_package(seller)
        fund_office(admin, buyer, 2000)
        b = buyer.post(f"{API}/bookings", json={"package_id": pkg["id"], "registrants": [
            {"name": "A", "passport_no": "P1", "age": 30}]}).json()
        c = buyer.post(f"{API}/bookings/{b['id']}/cancel-request")
        assert c.status_code == 200, c.text[:300]
        admin_fee = round(1000 * CANCEL_FEE_PCT, 2)
        assert c.json()["refund"] == round(b["amount_charged"] - admin_fee, 2)
        assert wallet_of(seller)["pending"] == 0.0
