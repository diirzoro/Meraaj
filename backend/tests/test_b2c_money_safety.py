"""Money-safety tests for the B2C layer — iteration 4 (asserts the FIXED behaviour)."""
import requests
import pytest
from conftest import (API, new_office, fund_office, make_package, wallet_of,
                      CANCEL_FEE_PCT, PLATFORM_PCT)
from test_b2c_individual import new_individual, revenue_for_booking

MARKETER_PCT = 0.20


def txn_sum(session, type_filter=None):
    r = session.get(f"{API}/wallet/transactions")
    assert r.status_code == 200, r.text[:200]
    rows = r.json()
    if type_filter:
        rows = [t for t in rows if t["type"] in type_filter]
    return round(sum(t["amount"] for t in rows), 2), rows


class TestFixAMarketerEscrow:
    """FIX A: marketer commission goes to PENDING (not spendable) and can never overdraw."""

    def test_commission_lands_in_pending_only(self, admin):
        seller, _, _ = new_office("ESCSELL")
        pkg = make_package(seller)                      # net 1000, sale 1300 -> margin 300
        mkt, _, _ = new_individual("ESCMKT")
        code = mkt.post(f"{API}/individual/become-marketer").json()["affiliate_code"]
        buyer, _, _ = new_individual("ESCBUY")
        fund_office(admin, buyer, 1500)
        b = buyer.post(f"{API}/bookings", json={
            "package_id": pkg["id"], "ref": code,
            "registrants": [{"name": "A", "passport_no": "P1", "age": 30}]})
        assert b.status_code == 200, b.text[:300]
        j = b.json()
        assert j["marketer_commission"] == 60.0
        assert j["platform_profit"] == 240.0
        w = wallet_of(mkt)
        assert w["pending"] == 60.0, w
        assert w["available"] == 0.0, w
        assert w["total"] == 60.0, w
        # buyer charged full retail
        assert wallet_of(buyer)["available"] == 200.0
        # ledger reconciles with wallet total
        total, rows = txn_sum(mkt)
        assert total == 60.0, rows
        assert any(t["type"] == "marketer_commission" for t in rows), rows

    def test_pending_commission_not_spendable(self, admin):
        seller, _, _ = new_office("SPSELL")
        pkg = make_package(seller)
        cheap = make_package(seller, net_cost_per_seat=50.0, final_sale_price=60.0,
                             buyer_office_commission=10.0)
        mkt, _, _ = new_individual("SPMKT")
        code = mkt.post(f"{API}/individual/become-marketer").json()["affiliate_code"]
        buyer, _, _ = new_individual("SPBUY")
        fund_office(admin, buyer, 1500)
        buyer.post(f"{API}/bookings", json={
            "package_id": pkg["id"], "ref": code,
            "registrants": [{"name": "A", "passport_no": "P1", "age": 30}]})
        assert wallet_of(mkt)["pending"] == 60.0
        # marketer has 0 available -> cannot spend the pending commission
        r = mkt.post(f"{API}/bookings", json={"package_id": cheap["id"], "registrants": [
            {"name": "M", "passport_no": "P9", "age": 40}]})
        assert r.status_code == 400, r.text[:300]
        assert wallet_of(mkt)["available"] == 0.0

    def test_no_negative_wallet_after_spend_then_blue_cancel(self, admin):
        """Marketer funds own wallet, spends it, then the ref booking is cancelled."""
        seller, _, _ = new_office("NEGSELL")
        pkg = make_package(seller)
        cheap = make_package(seller, net_cost_per_seat=50.0, final_sale_price=60.0,
                             buyer_office_commission=10.0)
        mkt, _, _ = new_individual("NEGMKT")
        code = mkt.post(f"{API}/individual/become-marketer").json()["affiliate_code"]
        fund_office(admin, mkt, 100)
        buyer, _, _ = new_individual("NEGBUY")
        fund_office(admin, buyer, 1500)
        b = buyer.post(f"{API}/bookings", json={
            "package_id": pkg["id"], "ref": code,
            "registrants": [{"name": "A", "passport_no": "P1", "age": 30}]}).json()
        assert wallet_of(mkt)["pending"] == 60.0
        # marketer spends own funds (60 retail on the cheap package)
        r2 = mkt.post(f"{API}/bookings", json={"package_id": cheap["id"], "registrants": [
            {"name": "M", "passport_no": "P9", "age": 40}]})
        assert r2.status_code == 200, r2.text[:300]
        assert wallet_of(mkt)["available"] == 40.0
        # buyer cancels (blue) -> pending commission reversed, no overdraft
        c = buyer.post(f"{API}/bookings/{b['id']}/cancel-request")
        assert c.status_code == 200, c.text[:300]
        w = wallet_of(mkt)
        assert w["available"] >= 0, f"negative available: {w}"
        assert w["pending"] == 0.0, w
        assert w["available"] == 40.0, w
        # FIX B: reversal written to the ledger and wallet reconciles
        total, rows = txn_sum(mkt, {"marketer_commission", "marketer_commission_reversal"})
        assert total == 0.0, rows
        assert any(t["type"] == "marketer_commission_reversal" and t["amount"] == -60.0
                   for t in rows), rows

    def test_commission_released_on_settle(self, admin):
        """pending -> available only via settle (blocked before the 24h grace)."""
        seller, _, _ = new_office("RELSELL")
        pkg = make_package(seller)
        mkt, _, _ = new_individual("RELMKT")
        code = mkt.post(f"{API}/individual/become-marketer").json()["affiliate_code"]
        buyer, _, _ = new_individual("RELBUY")
        fund_office(admin, buyer, 1500)
        b = buyer.post(f"{API}/bookings", json={
            "package_id": pkg["id"], "ref": code,
            "registrants": [{"name": "A", "passport_no": "P1", "age": 30}]}).json()
        seller.post(f"{API}/bookings/{b['id']}/issue-visas",
                    json={"visas": [{"index": 0, "visa_no": "V1"}]})
        seller.post(f"{API}/bookings/{b['id']}/dispatch")
        s = seller.post(f"{API}/bookings/{b['id']}/settle")
        assert s.status_code == 400, f"settle allowed inside grace: {s.status_code} {s.text[:200]}"
        # commission still pending because settle was blocked
        w = wallet_of(mkt)
        assert w["pending"] == 60.0 and w["available"] == 0.0, w


class TestFixCNoSelfReferral:
    def test_marketer_no_ref_earns_nothing(self, admin):
        seller, _, _ = new_office("NRSELL")
        pkg = make_package(seller)
        ind, _, _ = new_individual("NOREF")
        ind.post(f"{API}/individual/become-marketer")
        fund_office(admin, ind, 1500)
        j = ind.post(f"{API}/bookings", json={"package_id": pkg["id"], "registrants": [
            {"name": "A", "passport_no": "P1", "age": 30}]}).json()
        assert j["marketer_id"] is None, j
        assert j["marketer_commission"] == 0.0
        assert j["platform_profit"] == 300.0
        w = wallet_of(ind)
        assert w["available"] == 200.0 and w["pending"] == 0.0, w
        rev, rows = revenue_for_booking(j["id"])
        assert rev == 300.0, rows

    def test_marketer_own_code_earns_nothing(self, admin):
        seller, _, _ = new_office("OCSELL")
        pkg = make_package(seller)
        ind, _, _ = new_individual("OWNCODE")
        code = ind.post(f"{API}/individual/become-marketer").json()["affiliate_code"]
        fund_office(admin, ind, 1500)
        j = ind.post(f"{API}/bookings", json={"package_id": pkg["id"], "ref": code,
                     "registrants": [{"name": "A", "passport_no": "P1", "age": 30}]}).json()
        assert j["marketer_id"] is None, j
        assert j["marketer_commission"] == 0.0
        assert wallet_of(ind)["pending"] == 0.0

    def test_different_marketer_ref_earns_commission(self, admin):
        seller, _, _ = new_office("DMSELL")
        pkg = make_package(seller)
        other, _, _ = new_individual("DMMKT")
        code = other.post(f"{API}/individual/become-marketer").json()["affiliate_code"]
        buyer, _, _ = new_individual("DMBUY")
        buyer.post(f"{API}/individual/become-marketer")   # buyer is also a marketer
        fund_office(admin, buyer, 1500)
        j = buyer.post(f"{API}/bookings", json={"package_id": pkg["id"], "ref": code,
                       "registrants": [{"name": "A", "passport_no": "P1", "age": 30}]}).json()
        assert j["marketer_commission"] == 60.0
        assert wallet_of(other)["pending"] == 60.0
        assert wallet_of(buyer)["pending"] == 0.0


class TestFixDCancellationFeesRecorded:
    def test_blue_cancel_admin_fee_in_platform_revenue(self, admin):
        seller, _, _ = new_office("FEESELL")
        pkg = make_package(seller)
        buyer, _, _ = new_individual("FEEBUY")
        fund_office(admin, buyer, 1500)
        b = buyer.post(f"{API}/bookings", json={"package_id": pkg["id"], "registrants": [
            {"name": "A", "passport_no": "P1", "age": 30}]}).json()
        admin_fee = round(1000 * CANCEL_FEE_PCT, 2)
        c = buyer.post(f"{API}/bookings/{b['id']}/cancel-request").json()
        assert c["admin_fee"] == admin_fee
        rev, rows = revenue_for_booking(b["id"])
        # booking profit 300 logged, then reversed (-300), plus the admin fee retained
        assert any(r["amount"] == admin_fee for r in rows), rows
        assert rev == admin_fee, rows
        assert wallet_of(buyer)["available"] == round(1500 - admin_fee, 2)
        assert wallet_of(seller)["total"] == 0.0

    def test_yellow_cancel_platform_cut_in_platform_revenue(self, admin):
        seller, _, _ = new_office("YCSELL")
        pkg = make_package(seller)
        buyer, _, _ = new_office("YCBUY")
        fund_office(admin, buyer, 2000)
        b = buyer.post(f"{API}/bookings", json={"package_id": pkg["id"], "registrants": [
            {"name": "A", "passport_no": "P1", "age": 30}]}).json()
        assert b["platform_fee"] == 20.0
        seller.post(f"{API}/bookings/{b['id']}/issue-visas",
                    json={"visas": [{"index": 0, "visa_no": "V1"}]})
        buyer.post(f"{API}/bookings/{b['id']}/cancel-request")
        seller.post(f"{API}/bookings/{b['id']}/cancel-offer", json={"deduction": 200})
        acc = buyer.post(f"{API}/bookings/{b['id']}/cancel-accept")
        assert acc.status_code == 200, acc.text[:300]
        cut = round(200 * PLATFORM_PCT, 2)
        assert acc.json()["seller_keeps"] == round(200 - cut, 2)
        rev, rows = revenue_for_booking(b["id"])
        assert any(r["amount"] == cut for r in rows), rows
        assert rev == cut, rows


class TestFixEIndividualP2PRecipient:
    def test_individual_can_receive_transfer(self, admin):
        ofc, _, _ = new_office("P2PSRC")
        fund_office(admin, ofc, 100)
        ind, ind_user, _ = new_individual("P2PDST")
        r = ofc.post(f"{API}/wallet/transfers", json={"to_email": ind_user["email"],
                                                     "amount": 10, "note": "t"})
        assert r.status_code == 200, r.text[:300]
        tr = r.json()
        assert tr["status"] == "pending"
        assert tr["to_office_id"]
        # funds move only after admin approval
        assert wallet_of(ind)["available"] == 0.0
        a = admin.post(f"{API}/admin/transfers/{tr['id']}/review", json={"approve": True})
        assert a.status_code == 200, a.text[:300]
        assert wallet_of(ind)["available"] == 10.0
        assert wallet_of(ofc)["available"] == 90.0
        # idempotency
        again = admin.post(f"{API}/admin/transfers/{tr['id']}/review", json={"approve": True})
        # backend returns 404 for an already-reviewed transfer (idempotent, no double credit)
        assert again.status_code in (400, 404), again.text[:200]
        assert wallet_of(ind)["available"] == 10.0

    def test_transfer_to_unknown_email_404(self, admin):
        ofc, _, _ = new_office("P2PNONE")
        fund_office(admin, ofc, 50)
        r = ofc.post(f"{API}/wallet/transfers", json={"to_email": "nobody_qa@qa-example.com",
                                                     "amount": 5})
        assert r.status_code == 404, r.text[:200]


class TestRoleGuards:
    def test_individual_seller_endpoints_blocked(self, admin):
        seller, _, _ = new_office("SELLB")
        pkg = make_package(seller)
        ind, _, _ = new_individual("INDSELL")
        fund_office(admin, ind, 1500)
        b = ind.post(f"{API}/bookings", json={"package_id": pkg["id"], "registrants": [
            {"name": "A", "passport_no": "P1", "age": 30}]}).json()
        for path in ("issue-visas", "dispatch", "settle"):
            body = {"visas": [{"index": 0, "visa_no": "X"}]} if path == "issue-visas" else {}
            r = ind.post(f"{API}/bookings/{b['id']}/{path}", json=body)
            assert r.status_code == 403, f"{path} allowed for individual: {r.status_code}"


class TestVisaFilePreservation:
    def test_visa_file_kept_and_second_submit_blocked(self, admin):
        seller, _, _ = new_office("VFSELL")
        pkg = make_package(seller)
        buyer, _, _ = new_office("VFBUY")
        fund_office(admin, buyer, 2500)
        b = buyer.post(f"{API}/bookings", json={"package_id": pkg["id"], "registrants": [
            {"name": "A", "passport_no": "P1", "age": 30},
            {"name": "B", "passport_no": "P2", "age": 31}]}).json()
        # partial submit must not flip status
        partial = seller.post(f"{API}/bookings/{b['id']}/issue-visas",
                              json={"visas": [{"index": 0, "visa_no": "V1", "visa_file": "http://x/v1.pdf"}]})
        assert partial.status_code == 400, partial.text[:200]
        assert seller.get(f"{API}/bookings/{b['id']}").json()["status"] == "blue"
        ok = seller.post(f"{API}/bookings/{b['id']}/issue-visas", json={"visas": [
            {"index": 0, "visa_no": "V1", "visa_file": "http://x/v1.pdf"},
            {"index": 1, "visa_no": "V2"}]})
        assert ok.status_code == 200, ok.text[:300]
        regs = seller.get(f"{API}/bookings/{b['id']}").json()["registrants"]
        assert regs[0]["visa_file"] == "http://x/v1.pdf"
        assert regs[1]["visa_no"] == "V2"
        # re-submit omitting visa_file is rejected (already yellow) and data untouched
        again = seller.post(f"{API}/bookings/{b['id']}/issue-visas",
                            json={"visas": [{"index": 0, "visa_no": "V1"}]})
        assert again.status_code == 400, again.text[:200]
        assert seller.get(f"{API}/bookings/{b['id']}").json()["registrants"][0]["visa_file"] == "http://x/v1.pdf"
