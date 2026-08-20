"""Edge-case / abuse tests for cancellation state guards (double refund risk)."""
import requests
from conftest import API, new_office, fund_office, make_package, wallet_of


class TestCancelStateGuards:
    def test_double_refund_on_cancelled_booking(self, admin):
        seller, _, _ = new_office("dr_s")
        buyer, _, _ = new_office("dr_b")
        fund_office(admin, buyer, 10000)
        pkg = make_package(seller, total_seats=5)
        b = buyer.post(f"{API}/bookings", json={"package_id": pkg["id"], "registrants": [
            {"name": "a", "passport_no": "p1", "age": 30}]}).json()
        charged = b["amount_charged"]
        # first (blue) cancellation -> refund
        r1 = buyer.post(f"{API}/bookings/{b['id']}/cancel-request")
        assert r1.status_code == 200
        after_first = wallet_of(buyer)["available"]

        # attempt to run the yellow cancellation flow again on an already cancelled booking
        r2 = buyer.post(f"{API}/bookings/{b['id']}/cancel-request")
        print("second cancel-request:", r2.status_code, r2.text[:120])
        if r2.status_code == 200:
            o = seller.post(f"{API}/bookings/{b['id']}/cancel-offer", json={"deduction": 0})
            print("cancel-offer:", o.status_code, o.text[:120])
            a = buyer.post(f"{API}/bookings/{b['id']}/cancel-accept")
            print("cancel-accept:", a.status_code, a.text[:200])
            after_second = wallet_of(buyer)["available"]
            print("buyer available before/after replay:", after_first, after_second)
            seats = requests.get(f"{API}/packages/{pkg['id']}").json()["available_seats"]
            print("seats now:", seats, "(expected 5)")
            assert after_second == after_first, (
                f"DOUBLE REFUND: buyer credited again {after_second - after_first} on cancelled booking")
            assert seats == 5, f"seats over-released: {seats}"
        assert after_first < 10000 + charged

    def test_double_dispatch_and_double_settle_guards(self, admin):
        seller, _, _ = new_office("dd_s")
        buyer, _, _ = new_office("dd_b")
        fund_office(admin, buyer, 10000)
        pkg = make_package(seller, total_seats=3)
        b = buyer.post(f"{API}/bookings", json={"package_id": pkg["id"], "registrants": [
            {"name": "a", "passport_no": "p1", "age": 30}]}).json()
        seller.post(f"{API}/bookings/{b['id']}/issue-visas", json={"visas": [{"index": 0, "visa_no": "V"}]})
        assert seller.post(f"{API}/bookings/{b['id']}/dispatch").status_code == 200
        assert seller.post(f"{API}/bookings/{b['id']}/dispatch").status_code == 400
        assert seller.post(f"{API}/bookings/{b['id']}/issue-visas",
                           json={"visas": [{"index": 0, "visa_no": "V2"}]}).status_code == 400
        # duplicate dispute open
        assert buyer.post(f"{API}/bookings/{b['id']}/dispute", json={"reason": "x"}).status_code == 200
        r = buyer.post(f"{API}/bookings/{b['id']}/dispute", json={"reason": "y"})
        assert r.status_code == 400, f"duplicate dispute allowed on open dispute: {r.status_code}"

    def test_double_dispute_resolution(self, admin):
        seller, _, _ = new_office("ddr_s")
        buyer, _, _ = new_office("ddr_b")
        fund_office(admin, buyer, 10000)
        pkg = make_package(seller, total_seats=3)
        b = buyer.post(f"{API}/bookings", json={"package_id": pkg["id"], "registrants": [
            {"name": "a", "passport_no": "p1", "age": 30}]}).json()
        seller.post(f"{API}/bookings/{b['id']}/issue-visas", json={"visas": [{"index": 0, "visa_no": "V"}]})
        seller.post(f"{API}/bookings/{b['id']}/dispatch")
        buyer.post(f"{API}/bookings/{b['id']}/dispute", json={"reason": "x"})
        assert admin.post(f"{API}/admin/disputes/{b['id']}/resolve",
                          json={"resolution": "refund_buyer"}).status_code == 200
        bal = wallet_of(buyer)["available"]
        r = admin.post(f"{API}/admin/disputes/{b['id']}/resolve", json={"resolution": "refund_buyer"})
        print("re-resolve:", r.status_code, r.text[:150], "balance:", bal, "->", wallet_of(buyer)["available"])
        assert wallet_of(buyer)["available"] == bal, "DOUBLE PAYOUT: dispute resolved twice credits buyer again"
