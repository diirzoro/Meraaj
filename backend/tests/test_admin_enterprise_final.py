"""FINAL Enterprise review suite (iteration_13).

Covers: the 5 previously failing cases, integrations diagnose, reconciliation preview + guards
(money safety), encrypted backups + restore guards, cron endpoints, staff separation sharing the
office wallet, Arabic PDF exports, and an end-to-end booking money regression.

Run serially:  cd /app/backend && python -m pytest tests/test_admin_enterprise_final.py -n 0
"""
import json
import os
import time
import uuid

import pytest
import requests
from dotenv import dotenv_values

from conftest import (API, client, new_office, fund_office, make_package, ADMIN_EMAIL,
                      ADMIN_PASSWORD, PLATFORM_PCT)

BACKEND_ENV = dotenv_values("/app/backend/.env")
CRON_SECRET = BACKEND_ENV.get("WEBHOOK_CRON_SECRET")
SELLER = ("seller@test.com", "Test@1234")
BUYER = ("buyer@test.com", "Test@1234")
STAFF_QA = ("staffqa@test.com", "Staff@1234")

REPORT_KEYS = None  # filled by the catalog test


def reg(i=0):
    return {"name": f"TEST_QA مسافر {i}", "passport_no": f"Q{uuid.uuid4().hex[:9].upper()}",
            "age": 30, "category": "adult", "phone": "0770000000",
            "nationality": "عراقي", "gender": "male", "passport_expiry": "2031-01-01"}


def login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password})
    return r


def tok(email, password):
    r = login(email, password)
    assert r.status_code == 200, f"login {email} -> {r.status_code} {r.text[:200]}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def adm():
    return client(tok(ADMIN_EMAIL, ADMIN_PASSWORD))


@pytest.fixture(scope="module")
def seller():
    return client(tok(*SELLER))


@pytest.fixture(scope="module")
def buyer():
    return client(tok(*BUYER))


def money_snapshot(a):
    """Global money fingerprint: wallet sums + ledger totals + txn count."""
    r = a.get(f"{API}/admin/reconciliation")
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    n = a.get(f"{API}/admin/ledger?limit=1").json()["total"]
    return {"wallets": d["wallets"], "ledger": d["ledger_totals"], "txn_count": n}


# ==================== A. Re-verification of the 5 previous failures ====================
class TestPreviousFailures:
    def test_outbox_manual_retry_no_importerror(self, adm):
        lst = adm.get(f"{API}/admin/integrations/outbox?limit=5")
        assert lst.status_code == 200, lst.text[:300]
        items = lst.json()
        if not items:
            pytest.skip("no undelivered outbox events")
        r = adm.post(f"{API}/admin/integrations/outbox/{items[0]['id']}/retry",
                     json={"reason": "TEST_QA إعادة إرسال يدوية"})
        assert r.status_code == 200, f"retry -> {r.status_code} {r.text[:300]}"
        body = r.json()
        assert body["ok"] is True
        assert body["status"] in ("pending", "failed", "delivered")
        # audit written
        au = adm.get(f"{API}/admin/audit?entity=integration&limit=10").json()
        assert any(x["action"] == "outbox_manual_retry" for x in au["items"]), au

    def test_retry_requires_reason(self, adm):
        items = adm.get(f"{API}/admin/integrations/outbox?limit=1").json()
        if not items:
            pytest.skip("no events")
        r = adm.post(f"{API}/admin/integrations/outbox/{items[0]['id']}/retry", json={"reason": "x"})
        assert r.status_code == 422, r.status_code

    def test_suspended_account_login_is_403(self, adm):
        s, user, _ = new_office("SUSP")
        uid = user["id"]
        r = adm.post(f"{API}/admin/users/{uid}/suspend", json={"suspend": True,
                                                              "reason": "TEST_QA suspend"})
        assert r.status_code == 200, r.text[:300]
        try:
            lr = login(user["email"], "Test@1234")
            assert lr.status_code == 403, f"suspended login -> {lr.status_code} {lr.text[:200]}"
        finally:
            adm.post(f"{API}/admin/users/{uid}/suspend", json={"suspend": False,
                                                              "reason": "TEST_QA restore"})

    def test_credit_search_bypasses_only_exposed(self, adm):
        base = adm.get(f"{API}/admin/credit?only_exposed=true&limit=50")
        assert base.status_code == 200, base.text[:300]
        r = adm.get(f"{API}/admin/credit?only_exposed=true&q=seller@test.com")
        assert r.status_code == 200, r.text[:300]
        items = r.json()["items"]
        assert any("seller@test.com" in (i.get("email") or "") for i in items), \
            "search must bypass only_exposed"

    def test_settings_merged_has_no_metadata(self, adm):
        r = adm.get(f"{API}/admin/settings")
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        for k in d["settings"]:
            assert not k.startswith("updated_"), f"metadata leaked into settings: {k}"
        assert "updated_at" in d and "updated_by" in d

    def test_adjust_guard_order_existing_entry_first(self, adm):
        """Existing-opening-entry check must fire before the zero-difference check."""
        rec = adm.get(f"{API}/admin/reconciliation/preview").json()
        adjusted = [i for i in rec["items"] if i["already_adjusted"]]
        target = adjusted[0] if adjusted else None
        if target:
            r = adm.post(f"{API}/admin/reconciliation/adjust",
                         json={"office_id": target["office_id"], "currency": target["currency"],
                               "reason": "TEST_QA guard order", "dry_run": True})
            assert r.status_code == 400, r.status_code
            assert "افتتاحي" in r.json().get("detail", ""), r.json()
        # zero-difference account must give the other message
        s, user, _ = new_office("ZERO")
        r2 = adm.post(f"{API}/admin/reconciliation/adjust",
                      json={"office_id": user["id"], "currency": "USD",
                            "reason": "TEST_QA zero diff", "dry_run": True})
        assert r2.status_code == 400, r2.status_code
        assert "فرق" in r2.json().get("detail", ""), r2.json()


# ==================== B. Integrations diagnose ====================
class TestDiagnose:
    def test_diagnose_classifies_all(self, adm):
        r = adm.get(f"{API}/admin/integrations/diagnose")
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        health = adm.get(f"{API}/admin/integrations/health").json()
        assert d["undelivered"] == health["outbox"]["undelivered"], (d["undelivered"], health)
        assert sum(g["count"] for g in d["groups"]) == d["undelivered"]
        for g in d["groups"]:
            assert g["cause"] in ("hmac", "not_found", "unknown_ref", "network", "pending", "other")
            assert g["owner"] in ("meraaj", "rahal", "shared")
            assert g["action"] and g["key"]
            assert isinstance(g["events"], dict) and g["events"]
        assert d["meraaj_side_fixable"] + d["rahal_side_fixable"] <= d["undelivered"]

    def test_diagnose_requires_admin(self, seller):
        assert seller.get(f"{API}/admin/integrations/diagnose").status_code == 403
        assert requests.get(f"{API}/admin/integrations/diagnose").status_code == 401


# ==================== C. Reconciliation preview + guards (MONEY SAFETY) ====================
class TestReconciliationGuards:
    def test_preview_lists_everything_no_cap(self, adm):
        before = money_snapshot(adm)
        r = adm.get(f"{API}/admin/reconciliation/preview")
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        full = adm.get(f"{API}/admin/reconciliation").json()
        assert d["count"] == full["mismatch_count"], (d["count"], full["mismatch_count"])
        assert d["count"] > 100, f"preview looks capped: {d['count']}"
        assert len(d["items"]) == d["count"]
        assert d["execution_enabled"] is False
        for it in d["items"][:20]:
            assert it["proposed_entry"] == it["difference"]
            assert isinstance(it["already_adjusted"], bool)
            assert it["entry_type"] == "opening_balance"
        assert set(d["totals"].keys()) == {"SAR", "USD"}
        assert money_snapshot(adm) == before, "preview must not write anything"

    def test_adjust_blocked_403_and_dry_run_works(self, adm):
        before = money_snapshot(adm)
        items = [i for i in adm.get(f"{API}/admin/reconciliation/preview").json()["items"]
                 if not i["already_adjusted"]]
        assert items, "no un-adjusted mismatch to test with"
        t = items[0]
        body = {"office_id": t["office_id"], "currency": t["currency"],
                "reason": "TEST_QA reconciliation gate"}
        r = adm.post(f"{API}/admin/reconciliation/adjust", json={**body, "dry_run": False})
        assert r.status_code == 403, f"adjust must be 403: {r.status_code} {r.text[:200]}"
        dry = adm.post(f"{API}/admin/reconciliation/adjust", json={**body, "dry_run": True})
        assert dry.status_code == 200, dry.text[:300]
        assert dry.json()["dry_run"] is True
        assert dry.json()["difference"] == t["difference"]
        assert money_snapshot(adm) == before, "MONEY DRIFT during adjust attempts"

    def test_adjust_all_blocked(self, adm):
        before = money_snapshot(adm)
        r = adm.post(f"{API}/admin/reconciliation/adjust-all",
                     json={"office_id": "-", "currency": "USD",
                           "reason": "TEST_QA bulk gate", "dry_run": False})
        assert r.status_code == 403, (
            f"adjust-all must be rejected with 403 while ALLOW_RECONCILIATION!=true, "
            f"got {r.status_code}: {r.text[:300]}")
        after = money_snapshot(adm)
        assert after == before, "MONEY DRIFT during adjust-all attempt"

    def test_adjust_all_dry_run(self, adm):
        before = money_snapshot(adm)
        r = adm.post(f"{API}/admin/reconciliation/adjust-all",
                     json={"office_id": "-", "currency": "USD",
                           "reason": "TEST_QA bulk dry", "dry_run": True})
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["dry_run"] is True and d["processed"] >= 1
        assert money_snapshot(adm) == before, "MONEY DRIFT during adjust-all dry-run"

    def test_no_opening_balance_txn_created_by_qa(self, adm):
        r = adm.get(f"{API}/admin/ledger?txn_type=opening_balance&q=TEST_QA")
        assert r.status_code == 200
        assert r.json()["total"] == 0, r.json()["items"][:3]


# ==================== D. Encrypted backups + restore guards ====================
class TestBackups:
    def test_run_backup_encrypted(self, adm):
        r = adm.post(f"{API}/admin/backups/run", json={"reason": "TEST_QA نسخة تحقق"})
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        assert d["result"] == "success", d
        assert d["encrypted"] is True, d
        assert d["file"].endswith(".enc"), d["file"]
        assert d["size"] > 10000, d["size"]
        assert d["by"] and d["reason"]
        assert os.path.exists(f"/app/backups/{d['file']}")
        au = adm.get(f"{API}/admin/audit?entity=backup&limit=5").json()["items"]
        assert any(x["action"] == "backup_run" for x in au), au

    def test_retention_seven_files(self, adm):
        files = [f for f in os.listdir("/app/backups") if f.startswith("meraaj-")]
        assert len(files) <= 7, files

    def test_list_backups_flags(self, adm):
        r = adm.get(f"{API}/admin/backups")
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["encrypted"] is True
        assert d["restore_enabled"] is False
        assert d["retention"] == 7
        assert d["items"] and d["items"][0]["result"] in ("success", "failed")
        assert all("_id" not in i for i in d["items"])

    def test_restore_blocked(self, adm):
        f = adm.get(f"{API}/admin/backups").json()["items"][0]["file"]
        r = adm.post(f"{API}/admin/backups/restore",
                     json={"file": f, "confirm_phrase": "أؤكد الاستعادة",
                           "reason": "TEST_QA restore drill"})
        assert r.status_code == 403, f"{r.status_code} {r.text[:200]}"
        r2 = adm.post(f"{API}/admin/backups/restore",
                      json={"file": f, "confirm_phrase": "wrong phrase",
                            "reason": "TEST_QA wrong phrase"})
        assert r2.status_code in (400, 403), r2.status_code

    @pytest.mark.parametrize("path,method", [
        ("/admin/backups", "get"), ("/admin/backups/run", "post"),
        ("/admin/backups/restore", "post")])
    def test_admin_only(self, seller, path, method):
        body = {"reason": "TEST_QA", "file": "x", "confirm_phrase": "y"}
        r = getattr(seller, method)(f"{API}{path}", json=body)
        assert r.status_code == 403, (path, r.status_code)
        r2 = getattr(requests, method)(f"{API}{path}", json=body)
        assert r2.status_code == 401, (path, r2.status_code)


# ==================== E. Cron endpoints ====================
class TestCron:
    def test_secret_configured(self):
        assert CRON_SECRET, "WEBHOOK_CRON_SECRET missing from backend/.env"

    @pytest.mark.parametrize("job", ["backup", "alerts"])
    def test_requires_bearer(self, job):
        r = requests.post(f"{API}/cron/{job}", json={"run_id": "x"})
        assert r.status_code == 401, r.status_code
        r2 = requests.post(f"{API}/cron/{job}", json={"run_id": "x"},
                           headers={"Authorization": "Bearer wrong"})
        assert r2.status_code == 401, r2.status_code

    @pytest.mark.parametrize("job", ["backup", "alerts"])
    def test_idempotent_per_run_id(self, job):
        rid = f"TEST_QA-{uuid.uuid4().hex[:8]}"
        h = {"Authorization": f"Bearer {CRON_SECRET}"}
        t0 = time.time()
        r = requests.post(f"{API}/cron/{job}", json={"run_id": rid}, headers=h)
        elapsed = time.time() - t0
        assert r.status_code == 200, r.text[:200]
        assert r.json().get("queued") == job, r.json()
        assert elapsed < 10, f"cron ack too slow: {elapsed:.1f}s"
        r2 = requests.post(f"{API}/cron/{job}", json={"run_id": rid}, headers=h)
        assert r2.status_code == 200 and r2.json().get("duplicate") is True, r2.json()

    def test_crons_yml_declares_jobs(self):
        txt = open("/app/.emergent/crons.yml").read()
        assert "daily-db-backup" in txt and "daily-alert-scan" in txt
        assert "/api/cron/backup" in txt and "/api/cron/alerts" in txt


# ==================== F. Staff separation sharing the office wallet (MONEY) ====================
@pytest.fixture(scope="module")
def office_id(seller):
    return seller.get(f"{API}/auth/me").json()["id"]


class TestStaffSeparation:
    created = {}

    def test_create_staff_record_and_account(self, adm, office_id):
        r = adm.post(f"{API}/admin/orgs/{office_id}/staff",
                     json={"name": "TEST_QA موظف", "job_title": "موظف حجوزات",
                           "phone": "0770000001", "roles": ["operations_officer"]})
        assert r.status_code == 200, r.text[:300]
        sid = r.json().get("id") or r.json().get("_id")
        assert sid, r.json()
        TestStaffSeparation.created["staff_id"] = sid
        email = f"test_qa_staff_{uuid.uuid4().hex[:6]}@qa-example.com"
        a = adm.post(f"{API}/admin/staff/{sid}/account",
                     json={"email": email, "password": "Staff@1234",
                           "roles": ["operations_officer"]})
        assert a.status_code == 200, a.text[:300]
        assert a.json()["shares_office_wallet"] is True
        TestStaffSeparation.created["email"] = email
        TestStaffSeparation.created["user_id"] = a.json()["user_id"]

    def test_staff_login_returns_office_identity(self, office_id):
        email = TestStaffSeparation.created["email"]
        st = client(tok(email, "Staff@1234"))
        me = st.get(f"{API}/auth/me")
        assert me.status_code == 200, me.text[:300]
        d = me.json()
        assert d["id"] == office_id, (d["id"], office_id)
        assert d.get("office_name")
        acting = d.get("_acting_staff")
        assert acting, d
        assert acting["email"] == email
        assert acting["roles"] == ["operations_officer"]
        assert acting["id"] == TestStaffSeparation.created["user_id"]
        assert acting["id"] != office_id
        # office wallet shared
        w_staff = st.get(f"{API}/wallet").json()
        TestStaffSeparation.created["staff_session"] = st
        TestStaffSeparation.created["wallet"] = w_staff

    def test_staff_user_document_has_no_wallet(self, adm, seller):
        st = TestStaffSeparation.created["staff_session"]
        assert st.get(f"{API}/wallet").json() == seller.get(f"{API}/wallet").json()

    def test_duplicate_email_rejected(self, adm, office_id):
        r = adm.post(f"{API}/admin/orgs/{office_id}/staff",
                     json={"name": "TEST_QA موظف٢", "roles": []})
        sid2 = r.json().get("id") or r.json().get("_id")
        TestStaffSeparation.created["staff_id2"] = sid2
        dup = adm.post(f"{API}/admin/staff/{sid2}/account",
                       json={"email": TestStaffSeparation.created["email"],
                             "password": "Staff@1234", "roles": []})
        assert dup.status_code == 400, dup.status_code

    def test_second_account_for_same_staff_rejected(self, adm):
        sid = TestStaffSeparation.created["staff_id"]
        r = adm.post(f"{API}/admin/staff/{sid}/account",
                     json={"email": f"test_qa_dup_{uuid.uuid4().hex[:6]}@qa-example.com",
                           "password": "Staff@1234", "roles": []})
        assert r.status_code == 400, r.status_code

    def test_staff_booking_debits_office_wallet_only(self, adm, seller, buyer, office_id):
        """The staff account of the BUYER office books; only the office wallet must move."""
        # create a staff login on the buyer office
        buyer_id = buyer.get(f"{API}/auth/me").json()["id"]
        r = adm.post(f"{API}/admin/orgs/{buyer_id}/staff",
                     json={"name": "TEST_QA موظف مشتري", "roles": ["operations_officer"]})
        sid = r.json().get("id") or r.json().get("_id")
        TestStaffSeparation.created["buyer_staff_id"] = sid
        email = f"test_qa_bstaff_{uuid.uuid4().hex[:6]}@qa-example.com"
        a = adm.post(f"{API}/admin/staff/{sid}/account",
                     json={"email": email, "password": "Staff@1234", "roles": ["operations_officer"]})
        assert a.status_code == 200, a.text[:300]
        TestStaffSeparation.created["buyer_staff_user"] = a.json()["user_id"]
        st = client(tok(email, "Staff@1234"))

        pkg = make_package(seller, currency="USD", total_seats=5, net_cost_per_seat=100.0,
                           final_sale_price=130.0, buyer_office_commission=20.0)
        pkg_id = pkg.get("id") or pkg.get("_id")
        before = buyer.get(f"{API}/wallet").json()
        seats = 1
        body = {"package_id": pkg_id, "registrants": [reg("staff")]}
        bk = st.post(f"{API}/bookings", json=body)
        assert bk.status_code == 200, f"staff booking failed {bk.status_code}: {bk.text[:300]}"
        bid = bk.json().get("id") or bk.json().get("_id")
        TestStaffSeparation.created["booking_id"] = bid
        after = buyer.get(f"{API}/wallet").json()
        assert after != before, "office wallet did not move on staff booking"
        # staff has no own wallet: office wallet == staff-visible wallet
        assert st.get(f"{API}/wallet").json() == after
        # booking appears in the office's list
        lst = buyer.get(f"{API}/bookings").json()
        ids = [b.get("id") or b.get("_id") for b in (lst if isinstance(lst, list) else lst.get("items", []))]
        assert bid in ids, "staff booking missing from office bookings"
        # no wallet key created on the staff user document
        led = adm.get(f"{API}/admin/ledger?office_id={TestStaffSeparation.created['buyer_staff_user']}")
        assert led.json()["total"] == 0, "ledger entries written against the staff user!"

    def test_disable_blocks_staff_login_only(self, adm, office_id):
        sid = TestStaffSeparation.created["staff_id"]
        r = adm.post(f"{API}/admin/staff/{sid}/account/disable", json={})
        assert r.status_code == 200, r.text[:300]
        lr = login(TestStaffSeparation.created["email"], "Staff@1234")
        assert lr.status_code == 403, f"disabled staff login -> {lr.status_code}"
        assert login(*SELLER).status_code == 200, "office login broken after staff disable"

    def test_rahal_sso_user_unaffected(self, adm):
        u = adm.get(f"{API}/admin/offices?q=rahal_office1@qa-example.com")
        assert u.status_code == 200, u.text[:300]
        items = u.json()["items"] if isinstance(u.json(), dict) else u.json()
        rahal = [i for i in items if i.get("email") == "rahal_office1@qa-example.com"]
        assert rahal, "rahal SSO office missing"
        assert len(rahal) == 1, "duplicate rahal user"
        assert not rahal[0].get("parent_office_id"), rahal[0]
        assert not rahal[0].get("is_staff_account")

    @classmethod
    def teardown_class(cls):
        a = client(tok(ADMIN_EMAIL, ADMIN_PASSWORD))
        for key in ("staff_id", "staff_id2", "buyer_staff_id"):
            sid = cls.created.get(key)
            if sid:
                a.delete(f"{API}/admin/staff/{sid}")


# ==================== G. Arabic RTL PDF ====================
class TestArabicPdf:
    def test_catalog_has_13_reports(self, adm):
        global REPORT_KEYS
        r = adm.get(f"{API}/admin/reports")
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        keys = list(d["reports"].keys()) if isinstance(d.get("reports"), dict) else \
            [x["key"] for x in d.get("reports", d.get("items", []))]
        REPORT_KEYS = keys
        assert len(keys) == 13, (len(keys), keys)

    def test_every_report_exports_pdf(self, adm):
        assert REPORT_KEYS, "catalog test must run first"
        failures = []
        for k in REPORT_KEYS:
            r = adm.post(f"{API}/admin/reports/export-pdf", json={"report": k})
            ok = (r.status_code == 200 and r.headers.get("content-type", "").startswith("application/pdf")
                  and r.content[:5] == b"%PDF-" and len(r.content) > 800)
            if not ok:
                failures.append((k, r.status_code, r.headers.get("content-type"),
                                 len(r.content), r.text[:120] if r.status_code != 200 else ""))
        assert not failures, failures

    def test_pdf_pagination_and_log(self, adm):
        r = adm.post(f"{API}/admin/reports/export-pdf", json={"report": REPORT_KEYS[0]})
        assert r.status_code == 200
        assert r.content.count(b"/Type /Page") >= 1 or b"/Count" in r.content
        assert b"/Type /Font" in r.content, "no embedded font -> Arabic would not render"

    def test_voucher_pdf(self, adm):
        led = adm.get(f"{API}/admin/ledger?limit=1").json()
        txn = led["items"][0]["id"]
        r = adm.get(f"{API}/admin/vouchers/{txn}/pdf")
        assert r.status_code == 200, r.text[:200]
        assert r.headers["content-type"].startswith("application/pdf")
        assert r.content[:5] == b"%PDF-" and len(r.content) > 800

    def test_bad_report_key(self, adm):
        r = adm.post(f"{API}/admin/reports/export-pdf", json={"report": "nope"})
        assert r.status_code == 400, r.status_code


# ==================== H. Booking money regression (buyer -> seller approve) ====================
class TestBookingMoneyRegression:
    def test_end_to_end_booking(self, adm, seller, buyer):
        pkg = make_package(seller, currency="USD", total_seats=4, net_cost_per_seat=100.0,
                           final_sale_price=130.0, buyer_office_commission=20.0)
        pkg_id = pkg.get("id") or pkg.get("_id")
        seats = 2
        b_before = buyer.get(f"{API}/wallet").json()
        s_before = seller.get(f"{API}/wallet").json()
        body = {"package_id": pkg_id, "registrants": [reg(i) for i in range(seats)]}
        bk = buyer.post(f"{API}/bookings", json=body)
        assert bk.status_code == 200, bk.text[:300]
        bid = bk.json().get("id") or bk.json().get("_id")
        b_after = buyer.get(f"{API}/wallet").json()
        debit = round(b_before["USD"]["available"] - b_after["USD"]["available"], 2)
        # B2B: buyer pays net + platform fee on the buyer commission
        expected = round(100.0 * seats + PLATFORM_PCT * 20.0 * seats, 2)
        assert debit == expected, (debit, expected)
        s_after = seller.get(f"{API}/wallet").json()
        escrow = round(s_after["USD"]["pending"] - s_before["USD"]["pending"], 2)
        assert escrow == round(100.0 * seats, 2), (escrow, s_before, s_after)
        # Non-Rahal packages are confirmed on creation (escrow already applied above);
        # the pending-approval path only exists for Rahal-sourced packages.
        bdet = buyer.get(f"{API}/bookings/{bid}").json()
        if bdet.get("approval_status") == "pending":
            ap = seller.post(f"{API}/bookings/{bid}/approve", json={})
            assert ap.status_code == 200, ap.text[:300]
            notes = buyer.get(f"{API}/notifications").json()
            arr = notes if isinstance(notes, list) else notes.get("items", [])
            assert any(bid in json.dumps(n, ensure_ascii=False) for n in arr[:20]), \
                "no buyer notification after approval"
        detail = adm.get(f"{API}/admin/bookings/{bid}/full")
        assert detail.status_code == 200, detail.text[:300]
        assert detail.json()["booking"]["seats"] == seats
        pkg_after = seller.get(f"{API}/packages/{pkg_id}").json()
        assert pkg_after["available_seats"] == 4 - seats, pkg_after["available_seats"]

    def test_seller_approve_path_rahal_only(self, seller):
        """Approve on a confirmed non-Rahal booking must be refused, not silently accepted."""
        lst = seller.get(f"{API}/bookings").json()
        arr = lst if isinstance(lst, list) else lst.get("items", [])
        target = next((b for b in arr if not b.get("approval_status")), None)
        if not target:
            pytest.skip("no legacy booking")
        r = seller.post(f"{API}/bookings/{target.get('id')}/approve", json={})
        assert r.status_code in (400, 404), r.status_code
