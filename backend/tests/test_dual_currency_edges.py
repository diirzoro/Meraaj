"""Dual-currency edge cases & money-safety probes (validation gaps, exploits)."""
import pytest
import requests

from conftest import API, client, make_package, PLATFORM_PCT, CANCEL_FEE_PCT
from test_dual_currency import (register_office, fund, wallet, av, pend, book, RATE)


@pytest.fixture(scope="module")
def env():
    r = requests.post(f"{API}/auth/login", json={"email": "abuzay84@gmail.com", "password": "Meraaj@2026"})
    assert r.status_code == 200
    admin_s = client(r.json()["access_token"])
    seller_s, _, _ = register_office("EDGESELL")
    return admin_s, seller_s


class TestCurrencyValidation:
    def test_topup_unknown_currency(self, env):
        admin_s, _ = env
        s, _, _ = register_office("EURTOP")
        r = s.post(f"{API}/wallet/topups", json={"amount": 100, "currency": "EUR",
                                                 "method": "bank", "receipt_url": "http://x/r.png"})
        assert r.status_code in (400, 422), (
            f"unknown currency accepted (coerced to {r.json().get('currency')}) — expected validation error")

    def test_transfer_unknown_currency(self, env):
        admin_s, _ = env
        a, _, _ = register_office("EURTA")
        b, _, b_email = register_office("EURTB")
        fund(admin_s, a, 100, "USD")
        r = a.post(f"{API}/wallet/transfers", json={"to_email": b_email, "amount": 50,
                                                    "currency": "EUR", "note": "x"})
        assert r.status_code in (400, 422), (
            f"unknown currency accepted on transfer (coerced to {r.json().get('currency')})")

    def test_package_unknown_currency(self, env):
        _, seller_s = env
        r = seller_s.post(f"{API}/packages", json={
            "type": "umrah", "title": "TEST_EUR_PKG", "departure_date": "2026-09-01",
            "return_date": "2026-09-10", "net_cost_per_seat": 100.0, "final_sale_price": 150.0,
            "buyer_office_commission": 20.0, "currency": "EUR", "total_seats": 5})
        assert r.status_code in (400, 422), (
            "package created with unsupported currency EUR — bookings will silently treat it as USD")


class TestYellowDeductionValidation:
    def test_deduction_greater_than_net_creates_money(self, env):
        admin_s, seller_s = env
        buyer_s, _, _ = register_office("YOVER")
        fund(admin_s, buyer_s, 6000, "SAR")
        pkg = make_package(seller_s, currency="SAR", net_cost_per_seat=1000.0,
                           final_sale_price=1500.0, buyer_office_commission=200.0)
        sw0 = wallet(seller_s)
        b = book(buyer_s, pkg["id"], seats=1).json()
        seller_s.post(f"{API}/bookings/{b['id']}/issue-visas",
                      json={"visas": [{"index": 0, "visa_no": "V-1"}]})
        buyer_s.post(f"{API}/bookings/{b['id']}/cancel-request")
        r2 = seller_s.post(f"{API}/bookings/{b['id']}/cancel-offer", json={"deduction": 5000.0})
        # deduction must not exceed the escrowed net cost
        if r2.status_code in (400, 422):
            return
        r3 = buyer_s.post(f"{API}/bookings/{b['id']}/cancel-accept")
        if r3.status_code in (400, 422):
            return
        sw = wallet(seller_s)
        gained = round(av(sw, "SAR") - av(sw0, "SAR"), 2)
        assert gained <= b["net_cost_total"] + 0.01, (
            f"seller credited {gained} SAR from an escrow of only {b['net_cost_total']} — money created")

    def test_negative_deduction_rejected(self, env):
        admin_s, seller_s = env
        buyer_s, _, _ = register_office("YNEG")
        fund(admin_s, buyer_s, 6000, "SAR")
        pkg = make_package(seller_s, currency="SAR", net_cost_per_seat=1000.0,
                           final_sale_price=1500.0, buyer_office_commission=200.0)
        b = book(buyer_s, pkg["id"], seats=1).json()
        seller_s.post(f"{API}/bookings/{b['id']}/issue-visas",
                      json={"visas": [{"index": 0, "visa_no": "V-2"}]})
        buyer_s.post(f"{API}/bookings/{b['id']}/cancel-request")
        r2 = seller_s.post(f"{API}/bookings/{b['id']}/cancel-offer", json={"deduction": -1000.0})
        if r2.status_code in (400, 422):
            return
        r3 = buyer_s.post(f"{API}/bookings/{b['id']}/cancel-accept")
        if r3.status_code in (400, 422):
            return
        bw = wallet(buyer_s)
        assert av(bw, "SAR") <= 6000.01, (
            f"buyer ended with {av(bw, 'SAR')} SAR after paying and cancelling — negative deduction created money")


class TestCrossCurrencyCancelConversion:
    def test_book_then_cancel_converts_currency(self, env):
        """SAR-only buyer books a USD program (full shortfall) then blue-cancels: the refund
        lands in USD, effectively converting SAR->USD at the fixed rate for a 2% fee."""
        admin_s, seller_s = env
        buyer_s, _, _ = register_office("CONV")
        fund(admin_s, buyer_s, 8000, "SAR")
        pkg = make_package(seller_s, currency="USD", net_cost_per_seat=1000.0,
                           final_sale_price=1300.0, buyer_office_commission=200.0)
        b = book(buyer_s, pkg["id"], seats=1)
        assert b.status_code == 200, b.text[:300]
        b = b.json()
        assert b["debit_split"]["USD"] == 0.0 and b["debit_split"]["SAR"] > 0
        rc = buyer_s.post(f"{API}/bookings/{b['id']}/cancel-request")
        assert rc.status_code == 200, rc.text[:300]
        w = wallet(buyer_s)
        usd_gained = av(w, "USD")
        print(f"SAR debited: {b['debit_split']['SAR']}, USD refunded: {usd_gained}")
        # informational: flag the implicit FX round-trip
        assert usd_gained > 0, "refund should be in the program currency (USD)"
        assert av(w, "SAR") == pytest.approx(round(8000 - b["debit_split"]["SAR"], 2), abs=0.02)


class TestDoubleCancelGuards:
    def test_second_cancel_request_rejected(self, env):
        admin_s, seller_s = env
        buyer_s, _, _ = register_office("DBLC")
        fund(admin_s, buyer_s, 6000, "SAR")
        pkg = make_package(seller_s, currency="SAR", net_cost_per_seat=1000.0,
                           final_sale_price=1500.0, buyer_office_commission=200.0)
        b = book(buyer_s, pkg["id"], seats=1).json()
        r1 = buyer_s.post(f"{API}/bookings/{b['id']}/cancel-request")
        assert r1.status_code == 200, r1.text[:300]
        w1 = wallet(buyer_s)
        r2 = buyer_s.post(f"{API}/bookings/{b['id']}/cancel-request")
        assert r2.status_code == 400, f"double refund allowed! {r2.status_code} {r2.text[:200]}"
        w2 = wallet(buyer_s)
        assert av(w2, "SAR") == av(w1, "SAR"), "balance changed on rejected duplicate cancel"
