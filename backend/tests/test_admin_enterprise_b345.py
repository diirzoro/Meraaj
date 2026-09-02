"""Batches 3–5 — Enterprise admin verification (integration health, reconciliation, programs,
travelers/docs, RBAC, maker-checker, sessions/2FA, notifications, reports, audit, settings,
health, backup) + Batch 1/2 fix verification + money-safety regressions.

Run SERIALLY:  cd /app/backend && python -m pytest tests/test_admin_enterprise_b345.py -n 0
"""
import base64
import time
import uuid

import pytest
import requests
from bson import ObjectId
from dotenv import dotenv_values
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError

from conftest import API, client, new_office, fund_office, make_package

BE = dotenv_values("/app/backend/.env")
mdb = MongoClient(BE["MONGO_URL"])[BE["DB_NAME"]]

ADMIN = ("abuzay84@gmail.com", "Meraaj@2026")
CHECKER = ("qa.checker@qa-example.com", "Checker@2026")
BUYER = ("buyer@test.com", "Test@1234")

STAGES = ["requested", "under_review", "approved_internal", "sent_to_accounting",
          "executed", "closed"]

TINY_PNG = base64.b64encode(base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8AAAwAB/AF/9p8AAAAASUVORK5CYII="
)).decode()


def login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=60)
    assert r.status_code == 200, f"login {email} failed {r.status_code}: {r.text[:200]}"
    return client(r.json()["access_token"]), r.json()["access_token"], r.json()["user"]


def registrant(i=0):
    return {"name": f"TEST مسافر {i}", "passport_no": f"T{uuid.uuid4().hex[:9].upper()}",
            "age": 30, "category": "adult", "phone": "0770000000",
            "nationality": "عراقي", "gender": "male", "passport_expiry": "2031-01-01"}


@pytest.fixture(scope="module")
def admin_s():
    return login(*ADMIN)[0]


@pytest.fixture(scope="module")
def checker_s():
    return login(*CHECKER)[0]


@pytest.fixture(scope="module")
def office_s():
    return login(*BUYER)[0]


@pytest.fixture(scope="module")
def anon():
    return client()


# =============================================================================
# AUTHORIZATION on every new endpoint
# =============================================================================
GET_ENDPOINTS = [
    "/admin/integrations/health", "/admin/integrations/outbox", "/admin/programs",
    "/admin/travelers", "/admin/documents", "/admin/passport-alerts", "/admin/rbac/catalog",
    "/admin/rbac/users", "/admin/approvals", "/admin/sessions", "/admin/login-history",
    "/admin/reports", "/admin/audit", "/admin/anomalies", "/admin/settings",
    "/admin/system/health", "/admin/backups", "/admin/orgs", "/admin/tasks",
    "/admin/notification-templates", "/admin/notification-log",
]
POST_ENDPOINTS = [
    ("/admin/integrations/outbox/retry-all", {"reason": "قياس"}),
    ("/admin/notifications/scan", {}),
    ("/admin/reports/run", {"report": "sales"}),
    ("/admin/reports/export", {"report": "sales"}),
    ("/admin/settings", {"section": "locale", "values": {}, "reason": "قياس"}),
    ("/admin/rbac/dual-control", {"required": {}, "reason": "قياس"}),
    ("/admin/approvals", {"operation": "credit.edit", "target": "x", "reason": "قياس"}),
    ("/admin/reconciliation/adjust", {"office_id": "x", "currency": "SAR", "reason": "قياس1"}),
    ("/admin/backups/run", {"reason": "قياس"}),
    ("/admin/backups/restore", {"file": "x", "confirm_phrase": "y", "reason": "قياس1"}),
]


class TestAuthorization:
    @pytest.mark.parametrize("path", GET_ENDPOINTS)
    def test_get_anonymous_401(self, anon, path):
        assert anon.get(f"{API}{path}", timeout=120).status_code == 401, path

    @pytest.mark.parametrize("path", GET_ENDPOINTS)
    def test_get_office_403(self, office_s, path):
        assert office_s.get(f"{API}{path}", timeout=120).status_code == 403, path

    @pytest.mark.parametrize("path,body", POST_ENDPOINTS)
    def test_post_guards(self, anon, office_s, path, body):
        assert anon.post(f"{API}{path}", json=body, timeout=120).status_code == 401, f"anon {path}"
        assert office_s.post(f"{API}{path}", json=body, timeout=120).status_code == 403, f"office {path}"

    def test_notifications_are_per_user(self, office_s, anon):
        r = office_s.get(f"{API}/notifications")
        assert r.status_code == 200, r.text[:200]
        assert "items" in r.json() and "unread" in r.json()
        assert anon.get(f"{API}/notifications").status_code == 401


# =============================================================================
# BATCH 1/2 FIX VERIFICATION
# =============================================================================
class TestBatch12Fixes:
    def test_analytics_counts_check_and_awaiting_seller(self, admin_s):
        r = admin_s.get(f"{API}/admin/analytics", timeout=180)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        cc = d.get("counts_check")
        assert cc, "counts_check missing"
        assert cc["bookings_count"] == cc["status_sum"], cc
        assert cc["matches"] is True, cc
        ba = d["bookings_by_approval"]
        assert "awaiting_seller" in ba
        # awaiting_seller must include legacy new bookings (status=blue, no approval_status)
        legacy = mdb.bookings.count_documents(
            {"status": "blue", "approval_status": {"$in": [None, "", "pending"]}})
        pending = mdb.bookings.count_documents({"approval_status": "pending"})
        assert ba["awaiting_seller"] >= max(legacy, pending), (ba["awaiting_seller"], legacy, pending)
        assert ba["awaiting_seller"] > 0

    def test_credit_office_only_and_pagination(self, admin_s):
        r = admin_s.get(f"{API}/admin/credit", params={"page": 1, "limit": 5}, timeout=180)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["page"] == 1 and d["limit"] == 5
        assert len(d["items"]) <= 5
        assert d["total"] > 5
        assert all(i["role"] == "office" for i in d["items"]), "non-office row returned"
        p2 = admin_s.get(f"{API}/admin/credit", params={"page": 2, "limit": 5}, timeout=180).json()
        assert p2["items"] and p2["items"][0]["office_id"] != d["items"][0]["office_id"]

    def test_credit_search_bypasses_only_exposed(self, admin_s):
        base = admin_s.get(f"{API}/admin/credit", params={"limit": 200}, timeout=180).json()
        target = base["items"][0]
        r = admin_s.get(f"{API}/admin/credit",
                        params={"q": target["name"], "only_exposed": "true", "limit": 50},
                        timeout=180)
        assert r.status_code == 200, r.text[:300]
        names = [i["name"] for i in r.json()["items"]]
        assert target["name"] in names, "search result filtered out by only_exposed"

    def test_credit_limit_unique_index(self, admin_s):
        idx = mdb.credit_limits.index_information()
        uniq = [k for k, v in idx.items()
                if v.get("unique") and {f[0] for f in v["key"]} == {"office_id", "currency"}]
        assert uniq, f"no unique office_id+currency index: {idx}"
        row = mdb.credit_limits.find_one({})
        if row:
            with pytest.raises(DuplicateKeyError):
                mdb.credit_limits.insert_one({"office_id": row["office_id"],
                                              "currency": row["currency"], "limit": 1})

    def test_default_commission_rules_seeded(self, admin_s):
        r = admin_s.get(f"{API}/admin/commission-rules", timeout=120)
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert body["default_pct"] == 0.10, body["default_pct"]
        items = body["rules"]
        default = [x for x in items if x["name"] == "عمولة المنصة الأساسية — المكاتب"]
        assert default, [x.get("name") for x in items]
        d = default[0]
        assert d["active"] is True, d
        assert float(d["value"]) == 0.10, d
        assert d["mode"] == "percent" and d["scope"]["buyer_type"] == "office", d
        b2c = [x for x in items if x["scope"]["buyer_type"] == "individual"
               and x["active"] is False]
        assert b2c, "no inactive B2C rule seeded"


# =============================================================================
# INTEGRATION HEALTH (Batch 3)
# =============================================================================
class TestIntegrationHealth:
    def test_health_groups_failures(self, admin_s):
        r = admin_s.get(f"{API}/admin/integrations/health", timeout=180)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        ob = d["outbox"]
        assert ob["undelivered"] == mdb.rahal_outbox.count_documents(
            {"status": {"$in": ["pending", "failed"]}})
        assert ob["undelivered"] > 0
        assert ob["failure_groups"], "no failure groups"
        assert sum(g["count"] for g in ob["failure_groups"]) > 0
        assert any(g.get("last_error") for g in ob["failure_groups"]), "no real failure reasons"
        assert "total" in d["inbound"] and isinstance(d["inbound"]["recent"], list)
        assert all("_id" not in x for x in d["inbound"]["recent"])

    def test_outbox_list(self, admin_s):
        r = admin_s.get(f"{API}/admin/integrations/outbox", params={"limit": 10}, timeout=180)
        assert r.status_code == 200, r.text[:300]
        items = r.json()
        assert isinstance(items, list) and items
        assert all(i["status"] in ("pending", "failed") for i in items)
        assert all("_id" not in i and "id" in i for i in items)

    def test_retry_requires_reason_and_audits(self, admin_s):
        item = admin_s.get(f"{API}/admin/integrations/outbox", params={"limit": 1}).json()[0]
        bad = admin_s.post(f"{API}/admin/integrations/outbox/{item['id']}/retry", json={})
        assert bad.status_code == 422, bad.status_code
        before = mdb.audit_log.count_documents({"action": "outbox_manual_retry"})
        r = admin_s.post(f"{API}/admin/integrations/outbox/{item['id']}/retry",
                         json={"reason": "TEST_QA إعادة محاولة"}, timeout=180)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["status"] in ("pending", "failed", "delivered")
        assert mdb.audit_log.count_documents({"action": "outbox_manual_retry"}) == before + 1
        assert mdb.audit_log.find_one({"action": "outbox_manual_retry"},
                                      sort=[("at", -1)])["reason"] == "TEST_QA إعادة محاولة"

    def test_retry_unknown_id_404(self, admin_s):
        r = admin_s.post(f"{API}/admin/integrations/outbox/{ObjectId()}/retry",
                         json={"reason": "TEST_QA"})
        assert r.status_code == 404, r.status_code

    def test_retry_all(self, admin_s):
        assert admin_s.post(f"{API}/admin/integrations/outbox/retry-all",
                            json={}).status_code == 422
        t0 = time.time()
        try:
            r = admin_s.post(f"{API}/admin/integrations/outbox/retry-all",
                             json={"reason": "TEST_QA إعادة الكل"}, timeout=280)
        except requests.exceptions.ReadTimeout:
            pytest.fail("retry-all did not respond within 280s (blocking sequential deliveries)")
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["attempted"] > 0 and "still_undelivered" in d
        print(f"retry-all attempted={d['attempted']} in {round(time.time()-t0,1)}s")


# =============================================================================
# DOCUMENTED RECONCILIATION (Batch 3) — money safety
# =============================================================================
class TestReconciliation:
    @pytest.fixture(scope="class")
    def mismatch(self, admin_s):
        r = admin_s.get(f"{API}/admin/reconciliation", timeout=240)
        assert r.status_code == 200, r.text[:300]
        ms = [m for m in r.json()["mismatches"]
              if not mdb.transactions.find_one({"office_id": m["office_id"],
                                                "currency": m["currency"],
                                                "type": "opening_balance"})]
        if not ms:
            pytest.skip("no reconciliation mismatch available")
        return ms[0]

    @staticmethod
    def _wallets():
        return {str(u["_id"]): u.get("wallet")
                for u in mdb.users.find({}, {"wallet": 1})}

    def test_dry_run_writes_nothing(self, admin_s, mismatch):
        before_w = self._wallets()
        before_txn = mdb.transactions.count_documents({})
        r = admin_s.post(f"{API}/admin/reconciliation/adjust",
                         json={"office_id": mismatch["office_id"], "currency": mismatch["currency"],
                               "reason": "TEST_QA فحص جاف", "dry_run": True}, timeout=120)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["dry_run"] is True
        assert round(d["wallet_total"] - d["ledger_total"], 2) == d["difference"]
        assert mdb.transactions.count_documents({}) == before_txn, "dry_run wrote a transaction"
        assert self._wallets() == before_w, "dry_run touched a wallet"

    def test_real_entry_is_ledger_only_and_single(self, admin_s, mismatch):
        """UPDATED (iteration_13): real execution is now gated behind ALLOW_RECONCILIATION=true
        (explicit client approval). While the gate is off the endpoint must refuse with 403 and
        write nothing at all."""
        before_w = self._wallets()
        before_txn = mdb.transactions.count_documents({})
        r = admin_s.post(f"{API}/admin/reconciliation/adjust",
                         json={"office_id": mismatch["office_id"], "currency": mismatch["currency"],
                               "reason": "TEST_QA قيد افتتاحي موثّق"}, timeout=120)
        assert r.status_code == 403, f"{r.status_code} {r.text[:200]}"
        assert "ALLOW_RECONCILIATION" in r.json()["detail"]
        assert mdb.transactions.count_documents({}) == before_txn, "gated call wrote a transaction"
        assert self._wallets() == before_w, "gated call touched a wallet"

    def test_adjust_all_dry_run(self, admin_s):
        before_txn = mdb.transactions.count_documents({})
        r = admin_s.post(f"{API}/admin/reconciliation/adjust-all",
                         json={"office_id": "-", "currency": "SAR",
                               "reason": "TEST_QA فحص جاف شامل", "dry_run": True}, timeout=280)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["dry_run"] is True and d["processed"] >= 0
        assert mdb.transactions.count_documents({}) == before_txn, "adjust-all dry_run wrote data"

    def test_bad_currency(self, admin_s):
        # UPDATED (iteration_13): the ALLOW_RECONCILIATION gate is the outermost guard,
        # so a real call returns 403; currency validation is still enforced on dry-run.
        r = admin_s.post(f"{API}/admin/reconciliation/adjust",
                         json={"office_id": str(ObjectId()), "currency": "EUR",
                               "reason": "TEST_QA عملة"})
        assert r.status_code == 403, r.status_code
        d = admin_s.post(f"{API}/admin/reconciliation/adjust",
                         json={"office_id": str(ObjectId()), "currency": "EUR",
                               "reason": "TEST_QA عملة", "dry_run": True})
        assert d.status_code == 400, d.status_code


# =============================================================================
# WITHDRAWAL 6-STAGE CYCLE (money safety)
# =============================================================================
class TestWithdrawalStages:
    @pytest.fixture(scope="class")
    def wd(self, admin_s):
        s, user, _ = new_office("WD")
        fund_office(admin_s, s, 500)
        r = s.post(f"{API}/wallet/withdrawals",
                   json={"amount": 100, "currency": "SAR", "method": "bank",
                         "details": "TEST_QA bank"})
        assert r.status_code == 200, r.text[:300]
        return {"session": s, "id": r.json()["id"], "office_id": user["id"]}

    @staticmethod
    def _bal(office_id):
        u = mdb.users.find_one({"_id": ObjectId(office_id)}, {"wallet": 1})
        return u["wallet"]

    def test_stage_catalog_is_six_with_arabic_labels(self, admin_s):
        q = admin_s.get(f"{API}/admin/withdrawals/queue", timeout=180)
        assert q.status_code == 200, q.text[:300]
        d = q.json()
        assert d["stages"] == STAGES, d["stages"]
        assert len(d["stage_labels"]) == 6
        for i, st in enumerate(STAGES, start=1):
            assert d["stage_labels"][st].startswith("١٢٣٤٥٦"[i - 1]), d["stage_labels"][st]

    def test_forward_stages_never_move_money(self, admin_s, wd):
        before = self._bal(wd["office_id"])
        for st in ("under_review", "approved_internal", "sent_to_accounting"):
            r = admin_s.post(f"{API}/admin/withdrawals/{wd['id']}/stage",
                             json={"stage": st, "note": "TEST_QA"})
            assert r.status_code == 200, r.text[:300]
            assert r.json()["stage"] == st
        assert self._bal(wd["office_id"]) == before, "stage change moved money"

    def test_cannot_go_backwards(self, admin_s, wd):
        r = admin_s.post(f"{API}/admin/withdrawals/{wd['id']}/stage",
                         json={"stage": "requested"})
        assert r.status_code == 400, r.status_code

    def test_executed_blocked_before_financial_approval(self, admin_s, wd):
        r = admin_s.post(f"{API}/admin/withdrawals/{wd['id']}/stage", json={"stage": "executed"})
        assert r.status_code == 400, r.status_code
        assert "اعتماد" in r.json()["detail"]

    def test_closed_blocked_before_receipt(self, admin_s, wd):
        rv = admin_s.post(f"{API}/admin/withdrawals/{wd['id']}/review", json={"approve": True})
        assert rv.status_code == 200, rv.text[:300]
        ex = admin_s.post(f"{API}/admin/withdrawals/{wd['id']}/stage", json={"stage": "executed"})
        assert ex.status_code == 200, ex.text[:300]
        after_exec = self._bal(wd["office_id"])
        cl = admin_s.post(f"{API}/admin/withdrawals/{wd['id']}/stage", json={"stage": "closed"})
        assert cl.status_code == 400, cl.status_code
        assert "إيصال" in cl.json()["detail"]
        rc = admin_s.post(f"{API}/admin/withdrawals/{wd['id']}/receipt",
                          json={"receipt_url": "https://x.test/receipt.png", "reference": "TESTREF1"})
        assert rc.status_code == 200, rc.text[:300]
        cl2 = admin_s.post(f"{API}/admin/withdrawals/{wd['id']}/stage", json={"stage": "closed"})
        assert cl2.status_code == 200, cl2.text[:300]
        assert self._bal(wd["office_id"]) == after_exec, "closing moved money"
        det = admin_s.get(f"{API}/admin/withdrawals/{wd['id']}/detail").json()
        assert det["stage"] == "closed"
        hist = [h["stage"] for h in det.get("stage_history", [])]
        assert hist[:3] == ["under_review", "approved_internal", "sent_to_accounting"], hist
        assert "closed" in hist

    def test_invalid_stage_rejected(self, admin_s, wd):
        r = admin_s.post(f"{API}/admin/withdrawals/{wd['id']}/stage", json={"stage": "whatever"})
        assert r.status_code == 400, r.status_code


# =============================================================================
# E2E booking + commission + notifications + documents
# =============================================================================
def fund_currency(admin_s, office_s, amount, currency):
    r = office_s.post(f"{API}/wallet/topups",
                      json={"amount": amount, "currency": currency, "method": "bank",
                            "receipt_url": "http://x/r.png"})
    assert r.status_code == 200, r.text[:300]
    tid = r.json()["id"]
    assert admin_s.post(f"{API}/admin/topups/{tid}/review",
                        json={"approve": True}).status_code == 200


@pytest.fixture(scope="module")
def e2e(admin_s):
    seller_s, seller, _ = new_office("E2ESELL")
    buyer_s, buyer, _ = new_office("E2EBUY")
    fund_currency(admin_s, buyer_s, 5000, "USD")
    pkg = make_package(seller_s, net_cost_per_seat=1000.0, final_sale_price=1300.0,
                       buyer_office_commission=200.0, currency="USD", total_seats=10)
    # The seller review lifecycle (approval_status pending) only applies to Rahal-sourced
    # programs, so mark this TEST program as Rahal-linked to exercise approve/reject.
    ref = f"TEST-QA-{uuid.uuid4().hex[:6].upper()}"
    mdb.packages.update_one({"_id": ObjectId(pkg["id"])},
                            {"$set": {"source": "rahal", "rahal_ref": ref}})
    return {"seller_s": seller_s, "seller": seller, "buyer_s": buyer_s, "buyer": buyer,
            "pkg": pkg, "rahal_ref": ref}


class TestBookingLifecycleAndNotify:
    def test_booking_charges_net_plus_10pct_with_snapshot(self, admin_s, e2e):
        r = e2e["buyer_s"].post(f"{API}/bookings",
                                json={"package_id": e2e["pkg"]["id"],
                                      "registrants": [registrant(0)]})
        assert r.status_code == 200, r.text[:400]
        bid = r.json()["id"]
        e2e["booking_id"] = bid
        full = admin_s.get(f"{API}/admin/bookings/{bid}/full")
        assert full.status_code == 200, full.text[:300]
        b = full.json()["booking"]
        # B2B: office pays program net + the platform commission (10% of the buyer-office
        # commission base 200) => 1000 + 20 = 1020
        assert round(float(b["amount_charged"]), 2) == 1020.0, b["amount_charged"]
        assert b.get("commission_snapshot"), "commission_snapshot missing"
        snap = b["commission_snapshot"]
        assert round(float(snap["amount"]), 2) == 20.0, snap
        assert snap.get("rule_name") or snap.get("mode"), snap
        assert b.get("approval_status") == "pending", b.get("approval_status")

    def test_seller_approve_moves_money_and_notifies_buyer(self, admin_s, e2e):
        bid = e2e["booking_id"]
        seats_before = e2e["seller_s"].get(f"{API}/packages/{e2e['pkg']['id']}").json()
        r = e2e["seller_s"].post(f"{API}/bookings/{bid}/approve", json={})
        assert r.status_code == 200, r.text[:400]
        full = admin_s.get(f"{API}/admin/bookings/{bid}/full").json()
        b = full["booking"]
        # seats are reserved at request time; approval must not move them again
        assert b["status"] == "blue", b["status"]
        assert b.get("approval_status") == "approved", b.get("approval_status")
        pkg_after = e2e["seller_s"].get(f"{API}/packages/{e2e['pkg']['id']}").json()
        assert int(pkg_after["available_seats"]) == int(seats_before["available_seats"])
        assert int(pkg_after["available_seats"]) == 9, pkg_after["available_seats"]
        # escrow: seller pending holds the net
        sw = mdb.users.find_one({"_id": ObjectId(e2e["seller"]["id"])}, {"wallet": 1})["wallet"]
        assert round(float(sw["USD"]["pending"]), 2) >= 1000.0, sw["USD"]
        # notification for the buyer
        time.sleep(1)
        notes = e2e["buyer_s"].get(f"{API}/notifications").json()["items"]
        assert any(n["kind"] == "booking_approved" for n in notes), [n["kind"] for n in notes]
        assert all("_id" not in n for n in notes)

    def test_reject_notifies_buyer(self, admin_s, e2e):
        r = e2e["buyer_s"].post(f"{API}/bookings",
                                json={"package_id": e2e["pkg"]["id"],
                                      "registrants": [registrant(1)]})
        assert r.status_code == 200, r.text[:300]
        bid2 = r.json()["id"]
        rr = e2e["seller_s"].post(f"{API}/bookings/{bid2}/reject",
                                  json={"reason": "TEST_QA مقاعد غير متاحة"})
        assert rr.status_code == 200, rr.text[:400]
        time.sleep(1)
        notes = e2e["buyer_s"].get(f"{API}/notifications").json()["items"]
        assert any(n["kind"] == "booking_rejected" for n in notes), [n["kind"] for n in notes]

    def test_mark_notification_read(self, e2e):
        notes = e2e["buyer_s"].get(f"{API}/notifications").json()["items"]
        nid = notes[0]["id"]
        assert e2e["buyer_s"].post(f"{API}/notifications/{nid}/read", json={}).status_code == 200
        again = e2e["buyer_s"].get(f"{API}/notifications").json()["items"]
        assert [n for n in again if n["id"] == nid][0]["read"] is True


class TestDocumentLimits:
    def test_oversized_file_rejected(self, e2e):
        blob = base64.b64encode(b"x" * (11 * 1024 * 1024)).decode()
        r = e2e["buyer_s"].post(f"{API}/bookings/{e2e['booking_id']}/documents",
                                json={"registrant_index": 0, "doc_type": "passport",
                                      "filename": "big.pdf", "content_base64": blob},
                                timeout=240)
        assert r.status_code == 400, r.status_code
        assert "10" in r.json()["detail"], r.json()

    def test_batch_limit_rejected(self, e2e):
        r = e2e["buyer_s"].post(f"{API}/bookings/{e2e['booking_id']}/documents",
                                json={"registrant_index": 0, "doc_type": "passport",
                                      "filename": "s.png", "content_base64": TINY_PNG,
                                      "batch_total_bytes": 21 * 1024 * 1024})
        assert r.status_code == 400 and "20" in r.json()["detail"], r.text[:200]

    def test_small_upload_then_admin_delete_requires_reason(self, admin_s, e2e):
        r = e2e["buyer_s"].post(f"{API}/bookings/{e2e['booking_id']}/documents",
                                json={"registrant_index": 0, "doc_type": "passport",
                                      "filename": "ok.png", "content_base64": TINY_PNG,
                                      "passport_no": "T123456789",
                                      "batch_total_bytes": 1024})
        assert r.status_code == 200, r.text[:300]
        doc_id = r.json().get("id") or r.json().get("doc", {}).get("id")
        assert doc_id, r.json()
        short = admin_s.post(f"{API}/admin/documents/{doc_id}/delete", json={"reason": "abc"})
        assert short.status_code == 422, short.status_code
        ok = admin_s.post(f"{API}/admin/documents/{doc_id}/delete",
                          json={"reason": "TEST_QA حذف مستند تجريبي"})
        assert ok.status_code == 200, ok.text[:300]
        assert mdb.audit_log.count_documents({"action": "document_deleted",
                                              "entity_id": doc_id}) == 1
        assert mdb.booking_events.count_documents(
            {"booking_id": e2e["booking_id"], "event": "document_deleted_by_admin"}) >= 1
        assert admin_s.post(f"{API}/admin/documents/{doc_id}/delete",
                            json={"reason": "TEST_QA مرة ثانية"}).status_code == 404


# =============================================================================
# PROGRAMS & SEATS (Batch 3)
# =============================================================================
class TestPrograms:
    def test_list_filters_and_seats(self, admin_s, e2e):
        r = admin_s.get(f"{API}/admin/programs", params={"q": e2e["pkg"]["title"]}, timeout=180)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["total"] >= 1
        row = [x for x in d["items"] if x["id"] == e2e["pkg"]["id"]][0]
        assert row["sold_seats"] == 1, row
        assert row["allocated_seats"] == 10
        assert row["remaining_seats"] == 9
        assert row["availability"] == "available"
        assert "price_mismatch" in row and "is_expired" in row
        assert all("_id" not in x for x in d["items"])

    def test_list_pagination_and_currency_filter(self, admin_s):
        p1 = admin_s.get(f"{API}/admin/programs", params={"page": 1, "limit": 5}, timeout=180).json()
        assert len(p1["items"]) <= 5 and p1["total"] > 5
        p2 = admin_s.get(f"{API}/admin/programs", params={"page": 2, "limit": 5}, timeout=180).json()
        assert p1["items"][0]["id"] != p2["items"][0]["id"]
        usd = admin_s.get(f"{API}/admin/programs", params={"currency": "USD", "limit": 20},
                          timeout=180).json()
        assert all(i["currency"] == "USD" for i in usd["items"])
        exp = admin_s.get(f"{API}/admin/programs", params={"expired": "true", "limit": 20},
                          timeout=180).json()
        assert all(i["is_expired"] for i in exp["items"])
        rahal = admin_s.get(f"{API}/admin/programs", params={"source": "rahal", "limit": 20},
                            timeout=180).json()
        assert all(i.get("source") == "rahal" for i in rahal["items"])

    def test_detail_has_events_and_bookings(self, admin_s, e2e):
        r = admin_s.get(f"{API}/admin/programs/{e2e['pkg']['id']}", timeout=120)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["package"]["id"] == e2e["pkg"]["id"]
        assert d["package"]["sold_seats"] == 1
        assert isinstance(d["events"], list) and isinstance(d["bookings"], list)
        assert len(d["bookings"]) >= 1
        assert admin_s.get(f"{API}/admin/programs/{ObjectId()}").status_code == 404

    def test_patch_requires_reason_and_rejects_unknown_fields(self, admin_s, e2e):
        pid = e2e["pkg"]["id"]
        assert admin_s.patch(f"{API}/admin/programs/{pid}",
                             json={"changes": {"title": "x"}}).status_code == 422
        bad = admin_s.patch(f"{API}/admin/programs/{pid}",
                            json={"changes": {"seller_id": "hack", "status": "listed"},
                                  "reason": "TEST_QA"})
        assert bad.status_code == 400, bad.status_code
        assert "غير قابلة للتعديل" in bad.json()["detail"]
        empty = admin_s.patch(f"{API}/admin/programs/{pid}",
                              json={"changes": {}, "reason": "TEST_QA"})
        assert empty.status_code == 400

    def test_patch_cannot_reduce_seats_below_sold(self, admin_s, e2e):
        r = admin_s.patch(f"{API}/admin/programs/{e2e['pkg']['id']}",
                          json={"changes": {"total_seats": 0}, "reason": "TEST_QA تقليل"})
        assert r.status_code == 400, r.status_code
        assert "المباعة" in r.json()["detail"]

    def test_patch_applies_and_logs_event(self, admin_s, e2e):
        pid = e2e["pkg"]["id"]
        new_title = e2e["pkg"]["title"] + " مُعدّل"
        r = admin_s.patch(f"{API}/admin/programs/{pid}",
                          json={"changes": {"title": new_title, "total_seats": 12},
                                "reason": "TEST_QA تعديل إداري"})
        assert r.status_code == 200, r.text[:300]
        d = r.json()["package"]
        assert d["title"] == new_title
        assert d["allocated_seats"] == 12 and d["remaining_seats"] == 11
        ev = mdb.package_events.find_one({"package_id": pid, "action": "admin_edit"},
                                         sort=[("at", -1)])
        assert ev and ev["reason"] == "TEST_QA تعديل إداري"
        assert ev["after"]["title"] == new_title and ev["before"]["title"] != new_title

    def test_state_transitions(self, admin_s, e2e):
        pid = e2e["pkg"]["id"]
        assert admin_s.post(f"{API}/admin/programs/{pid}/state",
                            json={"state": "banana", "reason": "TEST_QA"}).status_code == 400
        assert admin_s.post(f"{API}/admin/programs/{pid}/state",
                            json={"state": "unlisted"}).status_code == 422
        for st, active in (("unlisted", False), ("archived", False), ("listed", True)):
            r = admin_s.post(f"{API}/admin/programs/{pid}/state",
                             json={"state": st, "reason": f"TEST_QA {st}"})
            assert r.status_code == 200, r.text[:300]
            p = mdb.packages.find_one({"_id": ObjectId(pid)})
            assert p["status"] == st and bool(p.get("is_active")) is active
            assert mdb.package_events.count_documents({"package_id": pid,
                                                       "action": f"state_{st}"}) >= 1

    def test_extend_and_images(self, admin_s, e2e):
        pid = e2e["pkg"]["id"]
        assert admin_s.post(f"{API}/admin/programs/{pid}/extend",
                            json={"reason": "TEST_QA بلا تواريخ"}).status_code == 400
        r = admin_s.post(f"{API}/admin/programs/{pid}/extend",
                         json={"departure_date": "2026-12-01", "return_date": "2026-12-10",
                               "authorization_expires_at": "2026-11-20",
                               "reason": "TEST_QA تمديد"})
        assert r.status_code == 200, r.text[:300]
        p = mdb.packages.find_one({"_id": ObjectId(pid)})
        assert p["departure_date"] == "2026-12-01"
        assert p["authorization_expires_at"] == "2026-11-20"
        ri = admin_s.post(f"{API}/admin/programs/{pid}/images",
                          json={"images": ["https://x.test/1.jpg", "https://x.test/2.jpg"]})
        assert ri.status_code == 200 and len(ri.json()["images"]) == 2
        rd = admin_s.post(f"{API}/admin/programs/{pid}/images", json={"images": []})
        assert rd.status_code == 200 and rd.json()["images"] == []
        evs = admin_s.get(f"{API}/admin/programs/{pid}/events").json()
        actions = [e["action"] for e in evs]
        for a in ("admin_edit", "state_listed", "extend_dates", "images_updated"):
            assert a in actions, actions


# =============================================================================
# TRAVELERS & DOCUMENTS (Batch 3)
# =============================================================================
class TestTravelers:
    def test_travelers_list(self, admin_s):
        r = admin_s.get(f"{API}/admin/travelers", params={"limit": 20}, timeout=240)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["total"] > 0 and len(d["items"]) <= 20
        st = d["stats"]
        for k in ("travelers", "with_missing_docs", "expired_passports",
                  "expiring_passports", "duplicates"):
            assert k in st
        assert d["limits"] == {"per_file_mb": 10, "per_batch_mb": 20}
        it = d["items"][0]
        for k in ("name", "passport_no", "missing_documents", "passport_status", "is_duplicate"):
            assert k in it, it.keys()
        assert it["passport_status"]["level"] in ("ok", "warning", "expired", "unknown")

    def test_travelers_filters(self, admin_s):
        miss = admin_s.get(f"{API}/admin/travelers",
                           params={"missing_only": "true", "limit": 10}, timeout=240).json()
        assert all(i["missing_documents"] for i in miss["items"])
        pi = admin_s.get(f"{API}/admin/travelers",
                         params={"passport_issue": "true", "limit": 10}, timeout=240).json()
        assert all(i["passport_status"]["level"] in ("expired", "warning", "unknown")
                   for i in pi["items"])
        dup = admin_s.get(f"{API}/admin/travelers",
                          params={"duplicates_only": "true", "limit": 10}, timeout=240).json()
        assert all(i["is_duplicate"] for i in dup["items"])
        p2 = admin_s.get(f"{API}/admin/travelers", params={"page": 2, "limit": 5},
                         timeout=240).json()
        assert p2["page"] == 2

    def test_documents_and_passport_alerts(self, admin_s):
        r = admin_s.get(f"{API}/admin/documents", params={"limit": 10}, timeout=180)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert "items" in d and "doc_labels" in d and "total" in d
        assert all("_id" not in x for x in d["items"])
        pa = admin_s.get(f"{API}/admin/passport-alerts", params={"days": 365}, timeout=240)
        assert pa.status_code == 200, pa.text[:300]
        assert pa.json()["threshold_days"] == 365
        assert isinstance(pa.json()["items"], list)


# =============================================================================
# RBAC (Batch 4)
# =============================================================================
class TestRBAC:
    def test_catalog(self, admin_s):
        d = admin_s.get(f"{API}/admin/rbac/catalog").json()
        assert len(d["permissions"]) == 21, len(d["permissions"])
        assert len(d["roles"]) == 12, len(d["roles"])
        assert d["roles"]["super_admin"]["perms"] == ["*"]
        assert len(d["dual_control"]) >= 7
        assert isinstance(d["settings"], dict)

    def test_super_admin_resolves_star(self, admin_s):
        me = admin_s.get(f"{API}/admin/my-permissions").json()
        assert me["role"] == "super_admin" and me["permissions"] == ["*"]

    def test_rbac_users_listing(self, admin_s):
        d = admin_s.get(f"{API}/admin/rbac/users", params={"q": "buyer@test.com"}).json()
        assert d["total"] >= 1
        u = d["items"][0]
        for k in ("enterprise_roles", "permissions", "is_rahal"):
            assert k in u
        assert "password_hash" not in u

    def test_assign_roles(self, admin_s):
        s, user, _ = new_office("RBAC")
        uid = user["id"]
        bad = admin_s.post(f"{API}/admin/rbac/users/{uid}/roles",
                           json={"roles": ["nope"], "reason": "TEST_QA"})
        assert bad.status_code == 400 and "غير معروفة" in bad.json()["detail"]
        assert admin_s.post(f"{API}/admin/rbac/users/{uid}/roles",
                            json={"roles": ["accountant"]}).status_code == 422
        assert admin_s.post(f"{API}/admin/rbac/users/{ObjectId()}/roles",
                            json={"roles": ["accountant"], "reason": "TEST_QA"}).status_code == 404
        r = admin_s.post(f"{API}/admin/rbac/users/{uid}/roles",
                         json={"roles": ["accountant", "branch_manager"],
                               "reason": "TEST_QA إسناد أدوار"})
        assert r.status_code == 200, r.text[:300]
        perms = r.json()["permissions"]
        assert "orders.view" in perms and "reports.view" in perms and "data.export" in perms
        assert mdb.audit_log.count_documents({"action": "roles_assigned", "entity_id": uid}) == 1
        # existing office behaviour unchanged
        assert s.get(f"{API}/packages").status_code == 200
        assert s.get(f"{API}/bookings", params={"role": "buyer"}).status_code == 200
        assert s.get(f"{API}/wallet").status_code == 200
        assert s.get(f"{API}/admin/rbac/catalog").status_code == 403
        mdb.user_roles.delete_many({"user_id": uid})
        mdb.audit_log.delete_many({"action": "roles_assigned", "entity_id": uid})

    def test_dual_control_settings(self, admin_s):
        before = admin_s.get(f"{API}/admin/rbac/catalog").json()["settings"]
        bad = admin_s.post(f"{API}/admin/rbac/dual-control",
                           json={"required": {"nope.op": True}, "reason": "TEST_QA"})
        assert bad.status_code == 400, bad.status_code
        r = admin_s.post(f"{API}/admin/rbac/dual-control",
                         json={"required": {"credit.edit": True}, "reason": "TEST_QA مزدوج"})
        assert r.status_code == 200 and r.json()["required"]["credit.edit"] is True
        assert admin_s.get(f"{API}/admin/rbac/catalog").json()["settings"]["credit.edit"] is True
        # restore
        admin_s.post(f"{API}/admin/rbac/dual-control",
                     json={"required": before, "reason": "TEST_QA استرجاع"})
        mdb.audit_log.delete_many({"action": "dual_control_updated", "reason":
                                   {"$in": ["TEST_QA مزدوج", "TEST_QA استرجاع"]}})


class TestMakerChecker:
    def test_maker_cannot_check(self, admin_s, checker_s):
        bad = admin_s.post(f"{API}/admin/approvals",
                           json={"operation": "orders.view", "target": "x", "reason": "TEST_QA"})
        assert bad.status_code == 400, bad.status_code
        r = admin_s.post(f"{API}/admin/approvals",
                         json={"operation": "credit.edit", "target": "office:123",
                               "payload": {"limit": 100}, "reason": "TEST_QA موافقة مزدوجة"})
        assert r.status_code == 200, r.text[:300]
        aid = r.json()["id"]
        assert r.json()["status"] == "pending" and r.json()["maker"] == ADMIN[0]
        self_dec = admin_s.post(f"{API}/admin/approvals/{aid}/decide", json={"approve": True})
        assert self_dec.status_code == 403, self_dec.status_code
        assert "لا يمكن لمنشئ العملية اعتمادها" in self_dec.json()["detail"]
        ok = checker_s.post(f"{API}/admin/approvals/{aid}/decide",
                            json={"approve": True, "note": "TEST_QA اعتماد"})
        assert ok.status_code == 200 and ok.json()["status"] == "approved"
        again = checker_s.post(f"{API}/admin/approvals/{aid}/decide", json={"approve": True})
        assert again.status_code == 400, again.status_code
        assert mdb.audit_log.count_documents({"entity": "approval", "entity_id": aid,
                                              "action": "approval_approved"}) == 1
        lst = admin_s.get(f"{API}/admin/approvals", params={"status": "approved"}).json()
        assert any(x["id"] == aid for x in lst)
        mdb.approvals.delete_one({"_id": ObjectId(aid)})
        mdb.audit_log.delete_many({"entity": "approval", "entity_id": aid})

    def test_reject_path(self, admin_s, checker_s):
        r = admin_s.post(f"{API}/admin/approvals",
                         json={"operation": "funds.release", "target": "b:1",
                               "reason": "TEST_QA رفض"})
        aid = r.json()["id"]
        d = checker_s.post(f"{API}/admin/approvals/{aid}/decide",
                           json={"approve": False, "note": "TEST_QA غير مبرر"})
        assert d.status_code == 200 and d.json()["status"] == "rejected"
        assert mdb.audit_log.count_documents({"entity_id": aid,
                                              "action": "approval_rejected"}) == 1
        mdb.approvals.delete_one({"_id": ObjectId(aid)})
        mdb.audit_log.delete_many({"entity": "approval", "entity_id": aid})


class TestSessionsAndAccountControl:
    def test_sessions_recorded_with_ip_and_ua(self, admin_s):
        s, user, token = new_office("SESS")
        requests.post(f"{API}/auth/login", json={"email": user["email"], "password": "Test@1234"},
                      headers={"User-Agent": "QA-Playwright-Probe"})
        d = admin_s.get(f"{API}/admin/sessions", params={"limit": 200}).json()
        mine = [x for x in d if x.get("email") == user["email"]]
        assert mine, "login not recorded as a session"
        assert "ip" in mine[0] and "user_agent" in mine[0]
        assert any(x.get("user_agent") == "QA-Playwright-Probe" for x in mine)
        assert all("_id" not in x for x in d)

    def test_login_history(self, admin_s):
        requests.post(f"{API}/auth/login",
                      json={"email": "nosuch_qa_user@qa-example.com", "password": "bad"})
        d = admin_s.get(f"{API}/admin/login-history",
                        params={"email": "nosuch_qa_user@qa-example.com"}).json()
        assert d["failed_attempts"], d
        assert d["failed_attempts"][0]["count"] >= 1
        mdb.login_attempts.delete_many({"email": "nosuch_qa_user@qa-example.com"})
        full = admin_s.get(f"{API}/admin/login-history").json()
        assert "sessions" in full and "failed_attempts" in full

    def test_force_logout_invalidates_existing_token(self, admin_s):
        s, user, _ = new_office("FORCE")
        s, token, _ = login(user["email"], "Test@1234")
        assert s.get(f"{API}/auth/me").status_code == 200
        assert admin_s.post(f"{API}/admin/users/{user['id']}/force-logout",
                            json={}).status_code == 422
        r = admin_s.post(f"{API}/admin/users/{user['id']}/force-logout",
                         json={"reason": "TEST_QA إنهاء الجلسة"})
        assert r.status_code == 200, r.text[:300]
        time.sleep(1)
        old = s.get(f"{API}/auth/me")
        assert old.status_code == 401, old.status_code
        assert "تم إنهاء الجلسة من الإدارة" in old.text, old.text[:200]
        s2, _, _ = login(user["email"], "Test@1234")
        assert s2.get(f"{API}/auth/me").status_code == 200, "fresh login blocked after force-logout"
        assert mdb.sessions.count_documents({"user_id": user["id"], "revoked": True}) >= 1
        mdb.users.update_one({"_id": ObjectId(user["id"])}, {"$set": {"force_logout_at": None}})

    def test_suspend_and_super_admin_protection(self, admin_s):
        s, user, _ = new_office("SUSP")
        admin_id = str(mdb.users.find_one({"email": ADMIN[0]})["_id"])
        prot = admin_s.post(f"{API}/admin/users/{admin_id}/suspend",
                            json={"suspend": True, "reason": "TEST_QA حماية"})
        assert prot.status_code == 400, prot.status_code
        assert "المدير العام" in prot.json()["detail"]
        assert mdb.users.find_one({"email": ADMIN[0]}).get("status") != "suspended"
        r = admin_s.post(f"{API}/admin/users/{user['id']}/suspend",
                         json={"suspend": True, "reason": "TEST_QA تعليق"})
        assert r.status_code == 200 and r.json()["status"] == "suspended"
        assert mdb.users.find_one({"_id": ObjectId(user["id"])})["status"] == "suspended"
        blocked = requests.post(f"{API}/auth/login",
                               json={"email": user["email"], "password": "Test@1234"})
        print(f"suspended-account login status={blocked.status_code} {blocked.text[:120]}")
        un = admin_s.post(f"{API}/admin/users/{user['id']}/suspend",
                          json={"suspend": False, "reason": "TEST_QA رفع التعليق"})
        assert un.status_code == 200 and un.json()["status"] == "active"
        mdb.users.update_one({"_id": ObjectId(user["id"])}, {"$set": {"force_logout_at": None}})
        assert blocked.status_code == 403, (
            "SUSPENDED account login must be rejected with 403 (status_code "
            f"{blocked.status_code})")

    def test_2fa_setup_and_verify(self, admin_s):
        import hashlib
        import hmac
        import struct
        r = admin_s.post(f"{API}/admin/2fa/setup", json={})
        assert r.status_code == 200, r.text[:300]
        secret = r.json()["secret"]
        assert r.json()["otpauth_url"].startswith("otpauth://totp/")
        assert admin_s.post(f"{API}/admin/2fa/verify",
                            json={"code": "000000"}).status_code == 400
        pad = secret + "=" * (-len(secret) % 8)
        key = base64.b32decode(pad, casefold=True)
        counter = int(time.time() // 30)
        digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
        off = digest[-1] & 0x0F
        code = f"{(struct.unpack('>I', digest[off:off+4])[0] & 0x7FFFFFFF) % 1000000:06d}"
        v = admin_s.post(f"{API}/admin/2fa/verify", json={"code": code})
        assert v.status_code == 200 and v.json()["enabled"] is True, v.text[:300]
        assert mdb.users.find_one({"email": ADMIN[0]})["twofa_enabled"] is True
        assert admin_s.get(f"{API}/admin/my-permissions").json()["twofa_enabled"] is True
        d = admin_s.post(f"{API}/admin/2fa/disable", json={"reason": "TEST_QA إيقاف"})
        assert d.status_code == 200 and d.json()["enabled"] is False
        assert requests.post(f"{API}/auth/login",
                            json={"email": ADMIN[0], "password": ADMIN[1]}).status_code == 200
        mdb.audit_log.delete_many({"action": {"$in": ["2fa_enabled", "2fa_disabled"]}})


# =============================================================================
# NOTIFICATIONS, TEMPLATES, TASKS (Batch 4)
# =============================================================================
class TestNotificationCenter:
    def test_scan_is_idempotent_same_day(self, admin_s):
        first = admin_s.post(f"{API}/admin/notifications/scan", json={}, timeout=280)
        assert first.status_code == 200, first.text[:300]
        second = admin_s.post(f"{API}/admin/notifications/scan", json={}, timeout=280)
        assert second.status_code == 200, second.text[:300]
        assert second.json()["total"] == 0, f"second scan created duplicates: {second.json()}"

    def test_templates_crud(self, admin_s):
        t = admin_s.get(f"{API}/admin/notification-templates").json()
        assert len(t["kinds"]) >= 10
        bad = admin_s.post(f"{API}/admin/notification-templates",
                           json={"kind": "nope", "title": "x"})
        assert bad.status_code == 400, bad.status_code
        r = admin_s.post(f"{API}/admin/notification-templates",
                         json={"kind": "escalation", "title": "TEST_QA قالب",
                               "body": "TEST_QA نص", "active": False})
        assert r.status_code == 200 and r.json()["title"] == "TEST_QA قالب"
        assert any(x["kind"] == "escalation"
                   for x in admin_s.get(f"{API}/admin/notification-templates").json()["items"])
        mdb.notification_templates.delete_many({"title": "TEST_QA قالب"})

    def test_notification_log_stats(self, admin_s):
        d = admin_s.get(f"{API}/admin/notification-log", params={"limit": 20}).json()
        assert isinstance(d["items"], list) and isinstance(d["stats"], dict)
        assert d["stats"].get("delivered", 0) > 0
        f = admin_s.get(f"{API}/admin/notification-log", params={"status": "delivered"}).json()
        assert all(i["status"] == "delivered" for i in f["items"])

    def test_tasks_center(self, admin_s):
        r = admin_s.get(f"{API}/admin/tasks", timeout=120)
        assert r.status_code == 200, r.text[:300]


# =============================================================================
# REPORTS CENTER (Batch 5)
# =============================================================================
REPORT_IDS = ["sales", "profit", "wallets", "credit", "programs", "travelers", "cancellations",
              "withdrawals", "offices", "users", "audit", "escrow", "fx"]


class TestReports:
    def test_catalog(self, admin_s):
        d = admin_s.get(f"{API}/admin/reports", timeout=120).json()
        assert len(d["reports"]) == 13, list(d["reports"])
        assert set(d["reports"]) == set(REPORT_IDS)
        assert isinstance(d["saved"], list)

    @pytest.mark.parametrize("rid", REPORT_IDS)
    def test_run_every_report(self, admin_s, rid):
        t0 = time.time()
        r = admin_s.post(f"{API}/admin/reports/run", json={"report": rid}, timeout=280)
        dt = round(time.time() - t0, 1)
        assert r.status_code == 200, f"{rid}: {r.status_code} {r.text[:300]}"
        d = r.json()
        assert d["report"] == rid and d["title"]
        assert isinstance(d["columns"], list) and d["columns"]
        assert isinstance(d["rows"], list)
        assert d["row_count"] >= len(d["rows"])
        if d["rows"]:
            assert len(d["rows"][0]) == len(d["columns"]), rid
        print(f"report {rid}: rows={d['row_count']} in {dt}s")
        if dt > 15:
            print(f"SLOW REPORT {rid} took {dt}s")

    def test_run_unknown_report(self, admin_s):
        assert admin_s.post(f"{API}/admin/reports/run",
                            json={"report": "nope"}).status_code == 400

    def test_export_csv_bom(self, admin_s):
        r = admin_s.post(f"{API}/admin/reports/export",
                         json={"report": "withdrawals"}, timeout=280)
        assert r.status_code == 200, r.text[:200]
        assert r.content.startswith(b"\xef\xbb\xbf"), r.content[:10]
        assert "text/csv" in r.headers["content-type"]
        assert "meraaj-withdrawals.csv" in r.headers.get("content-disposition", "")

    def test_filters_applied(self, admin_s):
        r = admin_s.post(f"{API}/admin/reports/run",
                         json={"report": "sales", "date_from": "2020-01-01",
                               "date_to": "2020-01-02"}, timeout=280).json()
        assert r["row_count"] == 0, r["row_count"]
        usd = admin_s.post(f"{API}/admin/reports/run",
                           json={"report": "sales", "currency": "USD"}, timeout=280).json()
        assert all(row[-1] == "USD" for row in usd["rows"])

    def test_save_report(self, admin_s):
        r = admin_s.post(f"{API}/admin/reports/save",
                         json={"name": "TEST_QA تقرير محفوظ", "report": "sales",
                               "filters": {"currency": "USD"}})
        assert r.status_code == 200, r.text[:300]
        sid = r.json()["id"]
        saved = admin_s.get(f"{API}/admin/reports").json()["saved"]
        assert any(x["id"] == sid and x["filters"]["currency"] == "USD" for x in saved)
        mdb.saved_reports.delete_one({"_id": ObjectId(sid)})


# =============================================================================
# AUDIT & ANOMALIES (Batch 5)
# =============================================================================
class TestAuditAnomalies:
    def test_audit_merges_sources(self, admin_s):
        d = admin_s.get(f"{API}/admin/audit", params={"limit": 200}, timeout=180).json()
        assert d["items"], d
        sources = {i["source"] for i in d["items"]}
        assert "audit_log" in sources
        assert len(sources) >= 2, sources
        ats = [str(i.get("at") or "") for i in d["items"]]
        assert ats == sorted(ats, reverse=True), "not chronological"
        assert any(i.get("before") is not None or i.get("after") is not None for i in d["items"])

    def test_audit_filters(self, admin_s):
        e = admin_s.get(f"{API}/admin/audit",
                        params={"entity": "booking", "limit": 50}, timeout=180).json()
        assert all(i["entity"] == "booking" for i in e["items"])
        a = admin_s.get(f"{API}/admin/audit",
                        params={"actor": ADMIN[0], "limit": 50}, timeout=180).json()
        offenders = [i for i in a["items"]
                     if ADMIN[0].lower() not in str(i.get("actor") or "").lower()]
        assert not offenders, ("actor filter is only applied to audit_log; merged sources "
                              f"leak through: {offenders[:3]}")
        q = admin_s.get(f"{API}/admin/audit",
                        params={"q": "TEST_QA", "limit": 50}, timeout=180).json()
        assert all("test_qa" in str(i).lower() for i in q["items"])

    def test_anomalies(self, admin_s):
        d = admin_s.get(f"{API}/admin/anomalies", timeout=240).json()
        assert d["total"] == len(d["items"])
        types = {i["type"] for i in d["items"]}
        assert "integration_burst" in types, types
        assert all(i["level"] in ("info", "warning", "critical") for i in d["items"])


# =============================================================================
# SETTINGS, SYSTEM HEALTH, BACKUP (Batch 5)
# =============================================================================
class TestSettingsHealthBackup:
    def test_settings_sections(self, admin_s):
        d = admin_s.get(f"{API}/admin/settings").json()
        s = d["settings"]
        expected = ["currencies", "commission", "order_flow", "reasons", "documents", "credit",
                    "funds_release", "numbering", "locale", "integrations", "feature_flags"]
        for k in expected:
            assert k in s, k
        leaked = [k for k in s if k not in expected]
        assert not leaked, f"non-section metadata leaked into settings: {leaked}"
        assert s["feature_flags"]["reports"] is True
        assert s["documents"]["per_file_mb"] == 10 and s["documents"]["per_batch_mb"] == 20

    def test_unknown_section_rejected(self, admin_s):
        r = admin_s.post(f"{API}/admin/settings",
                         json={"section": "nope", "values": {}, "reason": "TEST_QA"})
        assert r.status_code == 400 and "غير معروف" in r.json()["detail"]
        assert admin_s.post(f"{API}/admin/settings",
                            json={"section": "locale", "values": {}}).status_code == 422

    def test_settings_change_audited_and_restored(self, admin_s):
        before = admin_s.get(f"{API}/admin/settings").json()["settings"]["locale"]
        new = {**before, "timezone": "Asia/Baghdad"}
        r = admin_s.post(f"{API}/admin/settings",
                         json={"section": "locale", "values": new, "reason": "TEST_QA إعداد"})
        assert r.status_code == 200, r.text[:300]
        after = admin_s.get(f"{API}/admin/settings").json()["settings"]["locale"]
        assert after["timezone"] == "Asia/Baghdad"
        a = mdb.audit_log.find_one({"action": "settings_updated", "entity_id": "locale"},
                                   sort=[("at", -1)])
        assert a and a["before"] == before and a["after"] == new
        admin_s.post(f"{API}/admin/settings",
                     json={"section": "locale", "values": before, "reason": "TEST_QA استرجاع"})
        assert admin_s.get(f"{API}/admin/settings").json()["settings"]["locale"] == before
        mdb.audit_log.delete_many({"action": "settings_updated",
                                   "reason": {"$in": ["TEST_QA إعداد", "TEST_QA استرجاع"]}})
        mdb.settings.update_one({"_id": "system"}, {"$unset": {"locale": ""}})

    def test_system_health(self, admin_s):
        d = admin_s.get(f"{API}/admin/system/health", timeout=180).json()
        svc = {c["service"]: c for c in d["checks"]}
        assert svc["MongoDB"]["status"] == "ok"
        assert svc["Backend API"]["status"] == "ok"
        assert any("رحّال" in k for k in svc)
        assert any("القرص" in k for k in svc)
        assert any("النسخ" in k for k in svc)
        for c in ("users", "bookings", "packages", "transactions"):
            assert d["collections"][c] > 0, c

    def test_backup_run_and_retention(self, admin_s):
        assert admin_s.post(f"{API}/admin/backups/run", json={}).status_code == 422
        reason = f"TEST_QA نسخة اختبار {uuid.uuid4().hex[:6]}"
        r = admin_s.post(f"{API}/admin/backups/run", json={"reason": reason}, timeout=280)
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        assert d["result"] == "success" and d["size"] > 0 and d["file"]
        import os
        assert os.path.exists(f"/app/backups/{d['file']}")
        files = [f for f in os.listdir("/app/backups") if f.startswith("meraaj-")]
        assert len(files) <= 7, files
        lst = admin_s.get(f"{API}/admin/backups").json()
        assert lst["retention"] == 7 and "encrypted" in lst and "restore_enabled" in lst
        assert any(x["file"] == d["file"] for x in lst["items"])
        assert mdb.audit_log.count_documents({"action": "backup_run", "reason": reason}) == 1
        mdb.audit_log.delete_many({"action": "backup_run", "reason": reason})

    def test_restore_refused(self, admin_s):
        lst = admin_s.get(f"{API}/admin/backups").json()
        fname = (lst["items"][0]["file"] if lst["items"] else "x.gz") or "x.gz"
        r = admin_s.post(f"{API}/admin/backups/restore",
                         json={"file": fname, "confirm_phrase": "أؤكد الاستعادة",
                               "reason": "TEST_QA استعادة"})
        if lst["restore_enabled"]:
            pytest.fail("ALLOW_RESTORE is enabled in the preview environment")
        assert r.status_code == 403, r.status_code
        assert "ALLOW_RESTORE" in r.json()["detail"]
        bad = admin_s.post(f"{API}/admin/backups/restore",
                           json={"file": fname, "confirm_phrase": "نعم",
                                 "reason": "TEST_QA استعادة"})
        assert bad.status_code in (400, 403), bad.status_code


# =============================================================================
# REGRESSION — existing admin pages/APIs still load
# =============================================================================
class TestRegressionPages:
    @pytest.mark.parametrize("path", [
        "/admin/analytics", "/admin/bookings", "/admin/cancellations", "/admin/disputes",
        "/admin/offices", "/admin/topups", "/admin/transfers", "/admin/withdrawals",
        "/admin/ledger", "/admin/reconciliation", "/admin/commission-rules", "/admin/credit",
        "/admin/withdrawals/queue", "/admin/credit-events", "/admin/commission-events",
    ])
    def test_admin_endpoint_ok(self, admin_s, path):
        r = admin_s.get(f"{API}{path}", timeout=280)
        assert r.status_code == 200, f"{path}: {r.status_code} {r.text[:200]}"

    @pytest.mark.parametrize("path,params", [
        ("/packages", {}), ("/packages/mine", {}), ("/bookings", {"role": "buyer"}),
        ("/bookings", {"role": "seller"}), ("/wallet", {}), ("/wallet/transactions", {}),
        ("/wallet/withdrawals", {}), ("/notifications", {}),
    ])
    def test_office_endpoint_ok(self, office_s, path, params):
        r = office_s.get(f"{API}{path}", params=params, timeout=180)
        assert r.status_code == 200, f"{path}: {r.status_code} {r.text[:200]}"
