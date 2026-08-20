"""B2B escrow money-conservation checks (dispute resolution & yellow cancellation)."""
import requests
from conftest import API, new_office, fund_office, make_package, wallet_of, PLATFORM_PCT


def _book(admin, seller, buyer, funds=5000):
    pkg = make_package(seller, total_seats=5)
    fund_office(admin, buyer, funds)
    r = buyer.post(f"{API}/bookings", json={"package_id": pkg["id"], "registrants": [
        {"name": "a", "passport_no": "p1", "age": 30}]})
    assert r.status_code == 200, r.text[:300]
    return pkg, r.json()


class TestEscrowConservation:
    def test_dispute_refund_buyer_is_money_neutral(self, admin):
        seller, _, _ = new_office("DSPS")
        buyer, _, _ = new_office("DSPB")
        pkg, b = _book(admin, seller, buyer)
        seller.post(f"{API}/bookings/{b['id']}/issue-visas", json={"visas": [{"index": 0, "visa_no": "V"}]})
        seller.post(f"{API}/bookings/{b['id']}/dispatch")
        buyer.post(f"{API}/bookings/{b['id']}/dispute", json={"reason": "قصور بالخدمة"})
        r = admin.post(f"{API}/admin/disputes/{b['id']}/resolve", json={"resolution": "refund_buyer"})
        assert r.status_code == 200, r.text[:300]
        sw = wallet_of(seller)
        assert sw == {"total": 0.0, "pending": 0.0, "available": 0.0}, f"seller wallet not neutral: {sw}"
        bw = wallet_of(buyer)
        assert bw["available"] == 5000.0, f"buyer not fully refunded: {bw}"

    def test_yellow_cancel_accept_conserves_money(self, admin):
        seller, _, _ = new_office("YCS")
        buyer, _, _ = new_office("YCB")
        pkg, b = _book(admin, seller, buyer)
        charged = b["amount_charged"]
        seller.post(f"{API}/bookings/{b['id']}/issue-visas", json={"visas": [{"index": 0, "visa_no": "V"}]})
        assert buyer.post(f"{API}/bookings/{b['id']}/cancel-request").status_code == 200
        assert seller.post(f"{API}/bookings/{b['id']}/cancel-offer", json={"deduction": 300}).status_code == 200
        a = buyer.post(f"{API}/bookings/{b['id']}/cancel-accept")
        assert a.status_code == 200, a.text[:300]
        platform_cut = round(300 * PLATFORM_PCT, 2)
        seller_keeps = round(300 - platform_cut, 2)
        sw = wallet_of(seller)
        assert sw["pending"] == 0.0, sw
        assert sw["available"] == seller_keeps, sw
        assert sw["total"] == seller_keeps, f"seller total inconsistent: {sw}"
        bw = wallet_of(buyer)
        expected_refund = round(1000 - 300 + b["platform_fee"], 2)
        assert bw["available"] == round(5000 - charged + expected_refund, 2), bw
        # nothing created: buyer loss + seller gain + platform cut must balance
        buyer_loss = round(5000 - bw["available"], 2)
        assert round(buyer_loss - seller_keeps - platform_cut, 2) == 0.0, \
            f"money not conserved: buyer_loss={buyer_loss} seller_keeps={seller_keeps} cut={platform_cut}"
        # seats restored
        assert requests.get(f"{API}/packages/{pkg['id']}").json()["available_seats"] == 5
