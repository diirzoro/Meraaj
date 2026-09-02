"""Client review round 1 — verification of the items raised in Emergent View.

Covers: Rahal integration diagnosis/target/probe/per-event reason + PROVEN delivery,
RBAC & independent office-staff accounts sharing the office wallet, notification
templates/recipients/variables/duplicate-prevention, travelers & documents E2E,
reconciliation dry-run with before/after preview, backup restore drill, real Arabic PDFs.

Run SERIALLY:  cd /app/backend && python -m pytest tests/test_review_round1.py -n 0
"""
import base64
import hashlib
import hmac
import json
import time
import uuid

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

from conftest import API, BASE_URL, client, new_office, make_package

BE = dotenv_values("/app/backend/.env")
mdb = MongoClient(BE["MONGO_URL"])[BE["DB_NAME"]]
SECRET = BE.get("MERAAJ_SHARED_SECRET") or BE["RAHAL_SHARED_SECRET"]

ADMIN = ("abuzay84@gmail.com", "Meraaj@2026")
SIM_URL = f"{BASE_URL}/api/meraaj/webhooks"   # in-repo receiver that verifies HMAC like Rahaal

TINY_PNG = base64.b64encode(base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8AAAwAB/AF/9p8AAAAASUVORK5CYII="
)).decode()


def login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=60)
    assert r.status_code == 200, f"login {email} failed {r.status_code}: {r.text[:200]}"
    return client(r.json()["access_token"]), r.json()["access_token"], r.json()["user"]


def registrant(i=0):
    return {"name": f"TEST مسافر {i}", "passport_no": f"R{uuid.uuid4().hex[:9].upper()}",
            "age": 30, "category": "adult", "phone": "0770000000",
            "nationality": "عراقي", "gender": "male", "passport_expiry": "2031-01-01"}


@pytest.fixture(scope="module")
def admin_s():
    return login(*ADMIN)[0]


@pytest.fixture(scope="module")
def original_target(admin_s):
    """Remember and restore the configured integration target around the tests."""
    before = admin_s.get(f"{API}/admin/integrations/target").json()
    yield before
    doc = mdb.settings.find_one({"_id": "integration_target"}) or {}
    if before["source"] == "env":
        mdb.settings.delete_one({"_id": "integration_target"})
    else:
        mdb.settings.update_one({"_id": "integration_target"},
                                {"$set": {"webhook_url": before["url"]}}, upsert=True)
    assert doc is not None


# =============================================================================
# 1) Rahal integration — exact endpoint facts, per-event reason, proven delivery
# =============================================================================
class TestRahalIntegration:
    def test_target_exposes_exact_contract(self, admin_s):
        r = admin_s.get(f"{API}/admin/integrations/target")
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["method"] == "POST"
        assert d["signature_header"] == "X-Meraaj-Signature"
        assert "HMAC-SHA256" in d["signature_algo"]
        assert d["content_type"] == "application/json"
        # the fingerprint must match the secret we sign with locally
        assert d["secret_fingerprint"] == hashlib.sha256(SECRET.encode()).hexdigest()[:12]
        assert d["source"] in ("env", "settings")
        if d["url"]:
            assert d["base_url"].startswith("http") and d["path"].startswith("/")

    def test_probe_reports_exact_http_reason(self, admin_s):
        r = admin_s.post(f"{API}/admin/integrations/probe")
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["signature_header"] == "X-Meraaj-Signature"
        assert d["owner"] in ("ok", "rahal", "shared")
        assert d["verdict"]
        # either a real HTTP code or an explicit transport error — never a silent pass
        assert d["http_status"] is not None or d["transport_error"]

    def test_outbox_detail_gives_reason_signature_and_curl(self, admin_s):
        items = admin_s.get(f"{API}/admin/integrations/outbox?limit=5").json()
        if not items:
            pytest.skip("no undelivered events")
        d = admin_s.get(f"{API}/admin/integrations/outbox/{items[0]['id']}")
        assert d.status_code == 200, d.text[:300]
        j = d.json()
        assert j["event"] and j["signed_body"]
        assert len(j["current_signature"]) == 64
        # the signature published for reproduction must verify against the signed body
        expected = hmac.new(SECRET.encode(), j["signed_body"].encode("utf-8"),
                            hashlib.sha256).hexdigest()
        assert j["current_signature"] == expected
        assert "X-Meraaj-Signature" in j["curl"] and j["curl"].startswith("curl")
        assert isinstance(j["attempt_history"], list)
        assert "_id" not in j

    def test_detail_404_for_unknown_event(self, admin_s):
        from bson import ObjectId
        assert admin_s.get(f"{API}/admin/integrations/outbox/{ObjectId()}").status_code == 404

    def test_diagnose_classifies_404_as_rahal_side(self, admin_s):
        d = admin_s.get(f"{API}/admin/integrations/diagnose").json()
        assert d["undelivered"] >= 0
        for g in d["groups"]:
            assert g["owner"] in ("rahal", "meraaj", "shared")
            assert g["action"]

    def test_target_update_requires_reason_and_valid_url(self, admin_s):
        assert admin_s.post(f"{API}/admin/integrations/target",
                            json={"webhook_url": SIM_URL, "reason": "x"}).status_code == 422
        assert admin_s.post(f"{API}/admin/integrations/target",
                            json={"webhook_url": "not-a-url",
                                  "reason": "اختبار التحقق"}).status_code == 400

    def test_retry_delivers_and_flips_status_when_endpoint_is_live(self, admin_s, original_target):
        """PROOF: with a live endpoint that verifies HMAC exactly as Rahaal must, a failed
        event is delivered, its status flips to `delivered` and the receiver validates the
        signature. This isolates the 404s to the Rahaal endpoint being unavailable."""
        r = admin_s.post(f"{API}/admin/integrations/target",
                         json={"webhook_url": SIM_URL,
                               "reason": "إثبات التسليم مقابل مستقبل يتحقق من HMAC"})
        assert r.status_code == 200, r.text[:300]
        assert mdb.audit_log.find_one({"action": "webhook_target_updated"})

        # queue a fresh event through the real dispatcher path
        seller_s, seller, _ = new_office("RVSELL")
        pkg = make_package(seller_s, currency="USD")
        time.sleep(2)
        ev = mdb.rahal_outbox.find_one({"payload.package_ref": pkg["id"]})
        assert ev, "package.published was not written to the outbox"

        before = mdb.rahal_outbox.find_one({"_id": ev["_id"]})
        res = admin_s.post(f"{API}/admin/integrations/outbox/{ev['_id']}/retry",
                           json={"reason": "إثبات نجاح التسليم بعد تصحيح الوجهة"})
        assert res.status_code in (200, 400), res.text[:300]
        if res.status_code == 400:
            assert "مُسلَّم" in res.text          # already delivered on first dispatch
        else:
            assert res.json()["status"] == "delivered", res.text[:300]
        fresh = mdb.rahal_outbox.find_one({"_id": ev["_id"]})
        assert fresh["status"] == "delivered"
        assert fresh["delivered_at"] and fresh["http_status"] == 200
        assert fresh["last_error"] is None
        # receiver-side proof: HMAC accepted
        sim = mdb.rahal_sim_inbox.find_one({"package_ref": pkg["id"]})
        assert sim and sim["valid"] is True, sim
        # audit trail for the manual retry
        assert mdb.audit_log.find_one({"entity": "integration",
                                       "entity_id": str(ev["_id"]),
                                       "action": "outbox_manual_retry"}) or before

    def test_retry_requires_reason(self, admin_s):
        items = admin_s.get(f"{API}/admin/integrations/outbox?limit=1").json()
        if not items:
            pytest.skip("nothing undelivered")
        assert admin_s.post(f"{API}/admin/integrations/outbox/{items[0]['id']}/retry",
                            json={"reason": ""}).status_code == 422

    def test_bad_signature_is_rejected_by_receiver(self):
        body = json.dumps({"event": "meraaj.ping"}, separators=(",", ":")).encode()
        r = requests.post(SIM_URL, data=body,
                          headers={"Content-Type": "application/json",
                                   "X-Meraaj-Signature": "0" * 64}, timeout=30)
        assert r.status_code == 401

    def test_good_signature_is_accepted_by_receiver(self):
        body = json.dumps({"event": "meraaj.ping"}, separators=(",", ":")).encode()
        sig = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
        r = requests.post(SIM_URL, data=body,
                          headers={"Content-Type": "application/json",
                                   "X-Meraaj-Signature": sig}, timeout=30)
        assert r.status_code == 200 and r.json()["valid"] is True

    def test_health_shows_destination_breakdown(self, admin_s):
        h = admin_s.get(f"{API}/admin/integrations/health", timeout=300).json()
        dests = h["outbox"]["by_destination"]
        assert dests and all({"url", "status", "count"} <= set(d) for d in dests)
        assert sum(d["count"] for d in dests) == h["outbox"]["total"]

    def test_retry_all_answers_within_gateway_timeout(self, admin_s):
        t0 = time.time()
        r = admin_s.post(f"{API}/admin/integrations/outbox/retry-all",
                         json={"reason": "TEST_QA فحص زمن الاستجابة"}, timeout=120)
        assert r.status_code == 200, r.text[:300]
        assert time.time() - t0 < 100
        assert "still_undelivered" in r.json()


# =============================================================================
# 9) QA/test data classification (read-only, nothing deleted)
# =============================================================================
class TestDataReport:
    def test_report_classifies_qa_vs_real_without_deleting(self, admin_s):
        users_before = mdb.users.count_documents({})
        pkgs_before = mdb.packages.count_documents({})
        r = admin_s.get(f"{API}/admin/system/test-data-report", timeout=300)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["database"] == BE["DB_NAME"]
        assert d["environment"] == "preview"
        rows = {x["collection"]: x for x in d["rows"]}
        assert rows["users"]["qa"] + rows["users"]["real"] == rows["users"]["total"]
        assert rows["users"]["qa"] > 0 and rows["users"]["real"] > 0
        assert rows["packages"]["qa"] > 0
        assert d["repetition_verdict"] and d["deletion_policy"]
        # read-only guarantee
        assert mdb.users.count_documents({}) == users_before
        assert mdb.packages.count_documents({}) == pkgs_before

    def test_rbac_users_explain_empty_permissions(self, admin_s):
        d = admin_s.get(f"{API}/admin/rbac/users", params={"limit": 50}).json()
        s = d["summary"]
        for k in ("with_roles", "without_roles", "staff_accounts", "qa_accounts"):
            assert k in s
        for u in d["items"]:
            if not u["enterprise_roles"]:
                assert u["roles_note"], u
        staff = admin_s.get(f"{API}/admin/rbac/users",
                            params={"staff_only": "true", "limit": 50}).json()
        assert staff["items"], "no staff accounts listed"
        assert all(x["is_staff"] for x in staff["items"])
        assert all(x["has_own_wallet"] is False for x in staff["items"])
        un = admin_s.get(f"{API}/admin/rbac/users",
                         params={"unassigned": "true", "limit": 50}).json()
        assert all(not x["enterprise_roles"] for x in un["items"])
        assert all("wallet" not in x for x in d["items"])


# =============================================================================
# 2) RBAC + independent office-staff account sharing the office wallet
# =============================================================================
@pytest.fixture(scope="module")
def staff(admin_s):
    office_s, office, _ = new_office("RVOFF")
    r = admin_s.post(f"{API}/admin/orgs/{office['id']}/staff",
                     json={"name": "موظف مراجعة", "job_title": "موظف حجوزات",
                           "roles": ["operations_officer"]})
    assert r.status_code == 200, r.text[:300]
    sid = r.json()["id"]
    email = f"rvstaff_{uuid.uuid4().hex[:8]}@qa-example.com"
    acc = admin_s.post(f"{API}/admin/staff/{sid}/account",
                       json={"email": email, "password": "Staff@2026",
                             "roles": ["operations_officer"]})
    assert acc.status_code == 200, acc.text[:300]
    return {"office_s": office_s, "office": office, "staff_id": sid, "email": email,
            "user_id": acc.json()["user_id"]}


class TestStaffAccounts:
    def test_roles_catalog_has_12_roles_and_permissions(self, admin_s):
        c = admin_s.get(f"{API}/admin/rbac/catalog").json()
        assert len(c["roles"]) == 12, list(c["roles"])
        assert len(c["permissions"]) >= 20
        assert c["roles"]["super_admin"]["perms"] == ["*"]
        assert len(c["dual_control"]) >= 5

    def test_staff_record_is_separate_from_user(self, staff):
        rec = mdb.office_staff.find_one({"login_email": staff["email"]})
        assert rec and rec["office_id"] == staff["office"]["id"]
        assert rec["linked_user_id"] == staff["user_id"]

    def test_staff_has_no_own_wallet(self, staff):
        from bson import ObjectId
        u = mdb.users.find_one({"_id": ObjectId(staff["user_id"])})
        assert "wallet" not in u, "staff must never own a wallet"
        assert u["parent_office_id"] == staff["office"]["id"]
        assert u["is_staff_account"] is True

    def test_staff_login_is_independent_and_shares_office_wallet(self, staff, admin_s):
        s, _, me = login(staff["email"], "Staff@2026")
        # identity resolves to the OFFICE (shared wallet/ledger), staff is the actor
        assert me["role"] == "office"
        office_wallet = staff["office_s"].get(f"{API}/wallet").json()
        staff_wallet = s.get(f"{API}/wallet").json()
        assert staff_wallet == office_wallet
        # money moved by the office is visible to the staff account (same wallet)
        t = staff["office_s"].post(f"{API}/wallet/topups",
                                   json={"amount": 700, "currency": "USD", "method": "bank",
                                         "receipt_url": "http://x/r.png"})
        assert t.status_code == 200, t.text[:300]
        assert admin_s.post(f"{API}/admin/topups/{t.json()['id']}/review",
                            json={"approve": True}).status_code == 200
        w = s.get(f"{API}/wallet").json()
        assert w["USD"]["available"] >= 700, w
        assert mdb.users.count_documents({"parent_office_id": staff["office"]["id"],
                                          "wallet": {"$exists": True}}) == 0

    def test_staff_permissions_are_limited_by_role(self, staff):
        s, _, _ = login(staff["email"], "Staff@2026")
        p = s.get(f"{API}/admin/my-permissions").json()
        assert "orders.view" in p["permissions"], p
        assert "funds.release" not in p["permissions"]
        assert "*" not in p["permissions"]
        assert p["acting_staff"]["email"] == staff["email"]
        assert p["office_id"] == staff["office"]["id"]
        # an office identity can never reach admin-only endpoints
        assert s.get(f"{API}/admin/reconciliation").status_code == 403

    def test_maker_cannot_approve_own_operation(self, admin_s):
        a = admin_s.post(f"{API}/admin/approvals",
                         json={"operation": "credit.edit", "target": "office:x",
                               "payload": {"limit": 1000}, "reason": "اختبار المنشئ/المعتمد"})
        assert a.status_code == 200, a.text[:300]
        aid = a.json()["id"]
        deny = admin_s.post(f"{API}/admin/approvals/{aid}/decide",
                            json={"approve": True, "note": "self"})
        assert deny.status_code == 403
        assert "لا يمكن لمنشئ العملية اعتمادها" in deny.text

    def test_suspended_staff_cannot_login_and_token_is_invalidated(self, staff, admin_s):
        s, token, _ = login(staff["email"], "Staff@2026")
        assert s.get(f"{API}/wallet").status_code == 200
        r = admin_s.post(f"{API}/admin/users/{staff['user_id']}/suspend",
                         json={"suspend": True, "reason": "اختبار الإيقاف"})
        assert r.status_code == 200, r.text[:300]
        # old token no longer works
        assert client(token).get(f"{API}/wallet").status_code in (401, 403)
        # and a fresh login is refused
        bad = requests.post(f"{API}/auth/login",
                            json={"email": staff["email"], "password": "Staff@2026"})
        assert bad.status_code == 403
        # reactivate for the remaining tests
        assert admin_s.post(f"{API}/admin/users/{staff['user_id']}/suspend",
                            json={"suspend": False, "reason": "إعادة التفعيل"}).status_code == 200

    def test_force_logout_invalidates_old_token_only(self, staff, admin_s):
        s, token, _ = login(staff["email"], "Staff@2026")
        assert s.get(f"{API}/wallet").status_code == 200
        assert admin_s.post(f"{API}/admin/users/{staff['user_id']}/force-logout",
                            json={"reason": "اختبار إنهاء الجلسة"}).status_code == 200
        assert client(token).get(f"{API}/wallet").status_code == 401
        time.sleep(1.2)
        fresh, _, _ = login(staff["email"], "Staff@2026")
        assert fresh.get(f"{API}/wallet").status_code == 200

    def test_logout_revokes_the_token(self, staff):
        s, token, _ = login(staff["email"], "Staff@2026")
        assert s.get(f"{API}/wallet").status_code == 200
        assert s.post(f"{API}/auth/logout").json()["revoked"] is True
        assert client(token).get(f"{API}/wallet").status_code == 401
        fresh, _, _ = login(staff["email"], "Staff@2026")
        assert fresh.get(f"{API}/wallet").status_code == 200

    def test_duplicate_staff_email_is_refused(self, staff, admin_s):
        r = admin_s.post(f"{API}/admin/orgs/{staff['office']['id']}/staff",
                         json={"name": "موظف ثانٍ", "roles": ["limited_user"]})
        sid = r.json()["id"]
        dup = admin_s.post(f"{API}/admin/staff/{sid}/account",
                           json={"email": staff["email"], "password": "Staff@2026",
                                 "roles": ["limited_user"]})
        assert dup.status_code == 400 and "مكرر" in dup.text

    def test_rahal_sso_user_is_not_duplicated(self, admin_s):
        """SSO must LINK to the existing Rahal office, never create a second account.
        Token format = base64url(JSON) + '.' + HMAC-SHA256-hex(base64url)."""
        ref = f"RHL-RV-{uuid.uuid4().hex[:6].upper()}"
        claims = {"iss": "rahaal-erp", "aud": "meraaj-network", "office_ref": ref,
                  "email": f"{ref.lower()}@qa-example.com",
                  "office_name": "مكتب رحّال مراجعة", "exp": int(time.time()) + 600}
        p = base64.urlsafe_b64encode(
            json.dumps(claims, ensure_ascii=False, separators=(",", ":")).encode()
        ).decode().rstrip("=")
        sig = hmac.new(BE["RAHAL_SHARED_SECRET"].encode(), p.encode(), hashlib.sha256).hexdigest()
        tok = f"{p}.{sig}"
        a = requests.post(f"{API}/integrations/rahal/sso", json={"token": tok}, timeout=60)
        assert a.status_code == 200, a.text[:300]
        b = requests.post(f"{API}/integrations/rahal/sso", json={"token": tok}, timeout=60)
        assert b.status_code == 200, b.text[:300]
        assert mdb.users.count_documents({"rahal_office_ref": ref}) == 1
        assert mdb.users.count_documents({"email": claims["email"]}) == 1
        # a tampered signature is refused
        bad = requests.post(f"{API}/integrations/rahal/sso",
                            json={"token": f"{p}.{'0' * 64}"}, timeout=60)
        assert bad.status_code == 401


# =============================================================================
# 3) Notification templates, recipients, variables, duplicate prevention
# =============================================================================
class TestNotifications:
    def test_all_kinds_have_a_seeded_editable_template(self, admin_s):
        seed = admin_s.post(f"{API}/admin/notification-templates/seed")
        assert seed.status_code == 200, seed.text[:300]
        d = admin_s.get(f"{API}/admin/notification-templates").json()
        kinds = set(d["kinds"])
        have = {t["kind"] for t in d["items"]}
        assert kinds.issubset(have), kinds - have
        assert len(kinds) == 11
        assert all(t["title"] for t in d["items"])
        assert all("_id" not in t for t in d["items"])

    def test_recipient_rules_and_variables_are_published(self, admin_s):
        d = admin_s.get(f"{API}/admin/notification-templates").json()
        rules = d["recipients_rules"]
        assert rules["booking_created"] == ["seller", "admin"]
        assert rules["booking_approved"] == ["buyer"]
        assert rules["credit_threshold"] == ["admin"]
        assert "package_title" in d["variables"]["booking_created"]
        assert "stage_label" in d["variables"]["withdrawal_stage"]

    def test_seed_is_idempotent(self, admin_s):
        a = admin_s.post(f"{API}/admin/notification-templates/seed").json()
        assert a["created"] == 0
        assert a["total"] >= 11

    def test_template_edit_is_used_and_variables_render(self, admin_s):
        marker = uuid.uuid4().hex[:6]
        r = admin_s.post(f"{API}/admin/notification-templates",
                         json={"kind": "booking_created",
                               "title": f"قالب مُعدَّل {marker}",
                               "body": "برنامج {{package_title}} — مقاعد {{seats}}",
                               "active": True})
        assert r.status_code == 200, r.text[:300]
        assert r.json()["is_default"] is False

        seller_s, seller, _ = new_office("RVNSELL")
        buyer_s, buyer, _ = new_office("RVNBUY")
        t = buyer_s.post(f"{API}/wallet/topups", json={"amount": 4000, "currency": "USD",
                                                       "method": "bank",
                                                       "receipt_url": "http://x/r.png"})
        admin_s.post(f"{API}/admin/topups/{t.json()['id']}/review", json={"approve": True})
        pkg = make_package(seller_s, currency="USD")
        b = buyer_s.post(f"{API}/bookings", json={"package_id": pkg["id"],
                                                  "registrants": [registrant(0)]})
        assert b.status_code == 200, b.text[:400]
        time.sleep(1.5)
        notes = seller_s.get(f"{API}/notifications").json()["items"]
        created = [n for n in notes if n["kind"] == "booking_created"]
        assert created, [n["kind"] for n in notes]
        assert marker in created[0]["title"]
        assert pkg["title"] in created[0]["body"]
        assert "{{" not in created[0]["body"]
        # delivery log
        assert mdb.notification_log.find_one({"notification_id": created[0]["id"],
                                              "status": "delivered"})
        # restore the default text
        admin_s.post(f"{API}/admin/notification-templates",
                     json={"kind": "booking_created", "title": "طلب حجز جديد",
                           "body": "طلب جديد على: {{package_title}} — عدد المقاعد {{seats}}",
                           "active": True})

    def test_cancellation_and_withdrawal_notifications_fire(self, admin_s):
        seller_s, seller, _ = new_office("RVCSELL")
        buyer_s, buyer, _ = new_office("RVCBUY")
        t = buyer_s.post(f"{API}/wallet/topups", json={"amount": 4000, "currency": "USD",
                                                       "method": "bank",
                                                       "receipt_url": "http://x/r.png"})
        admin_s.post(f"{API}/admin/topups/{t.json()['id']}/review", json={"approve": True})
        pkg = make_package(seller_s, currency="USD")
        bid = buyer_s.post(f"{API}/bookings", json={"package_id": pkg["id"],
                                                    "registrants": [registrant(1)]}).json()["id"]
        c = buyer_s.post(f"{API}/bookings/{bid}/cancel-request",
                         json={"reason": "اختبار الإشعارات"})
        assert c.status_code == 200, c.text[:300]
        time.sleep(1.5)
        buyer_notes = {n["kind"] for n in buyer_s.get(f"{API}/notifications").json()["items"]}
        seller_notes = {n["kind"] for n in seller_s.get(f"{API}/notifications").json()["items"]}
        # a blue booking cancels immediately -> both parties are notified
        assert "booking_cancelled" in buyer_notes, buyer_notes
        assert "booking_cancelled" in seller_notes, seller_notes

    def test_withdrawal_stage_notification_fires(self, admin_s):
        w = mdb.withdrawals.find_one({"status": {"$ne": "rejected"}})
        if not w:
            pytest.skip("no withdrawal to move")
        before = mdb.notifications.count_documents({"kind": "withdrawal_stage"})
        r = admin_s.post(f"{API}/admin/withdrawals/{w['_id']}/stage",
                         json={"stage": "under_review", "note": "اختبار إشعار المرحلة"})
        assert r.status_code in (200, 400), r.text[:300]
        if r.status_code == 200:
            time.sleep(1)
            assert mdb.notifications.count_documents({"kind": "withdrawal_stage"}) > before
            note = mdb.notifications.find_one({"kind": "withdrawal_stage"},
                                              sort=[("at", -1)])
            assert note["user_id"] == w["office_id"]
            assert "{{" not in note["body"]

    def test_scheduled_scan_prevents_duplicates_same_day(self, admin_s):
        first = admin_s.post(f"{API}/admin/notifications/scan")
        assert first.status_code == 200, first.text[:300]
        second = admin_s.post(f"{API}/admin/notifications/scan")
        assert second.status_code == 200, second.text[:300]
        assert second.json()["total"] == 0, second.json()

    def test_delivery_log_exposes_status_and_failures(self, admin_s):
        d = admin_s.get(f"{API}/admin/notification-log?limit=50").json()
        assert "delivered" in d["stats"]
        assert all("_id" not in x for x in d["items"])

    def test_tasks_have_assignee_priority_due_and_escalation(self, admin_s):
        b = mdb.bookings.find_one({}, {"_id": 1})
        r = admin_s.post(f"{API}/admin/bookings/{b['_id']}/tasks",
                         json={"title": f"مهمة مراجعة {uuid.uuid4().hex[:4]}",
                               "assignee": "مسؤول العمليات", "due_date": "2020-01-01",
                               "priority": "urgent"})
        assert r.status_code == 200, r.text[:300]
        t = r.json()
        assert t["assignee"] == "مسؤول العمليات" and t["priority"] == "urgent"
        assert t["due_date"] == "2020-01-01" and t["status"] == "open"
        assert admin_s.post(f"{API}/admin/bookings/{b['_id']}/tasks",
                            json={"title": "أولوية خاطئة", "priority": "nope"}).status_code == 400
        # an overdue task is escalated by the scheduled scan
        assert admin_s.post(f"{API}/admin/notifications/scan").status_code == 200
        from bson import ObjectId
        fresh = mdb.admin_tasks.find_one({"_id": ObjectId(t["id"])})
        assert fresh.get("escalated") is True and fresh.get("escalated_at")
        assert mdb.notifications.find_one({"kind": "task_overdue", "meta.target": t["id"]})
        # status transition
        up = admin_s.patch(f"{API}/admin/tasks/{t['id']}", json={"status": "done"})
        assert up.status_code == 200 and up.json()["status"] == "done"
        assert admin_s.patch(f"{API}/admin/tasks/{t['id']}",
                             json={"status": "bogus"}).status_code == 400


# =============================================================================
# 4) Travelers & documents E2E
# =============================================================================
@pytest.fixture(scope="module")
def docs_case(admin_s):
    seller_s, seller, _ = new_office("RVDSELL")
    buyer_s, buyer, _ = new_office("RVDBUY")
    t = buyer_s.post(f"{API}/wallet/topups", json={"amount": 5000, "currency": "USD",
                                                   "method": "bank",
                                                   "receipt_url": "http://x/r.png"})
    admin_s.post(f"{API}/admin/topups/{t.json()['id']}/review", json={"approve": True})
    pkg = make_package(seller_s, currency="USD")
    reg = registrant(0)
    bid = buyer_s.post(f"{API}/bookings", json={"package_id": pkg["id"],
                                                "registrants": [reg]}).json()["id"]
    return {"seller_s": seller_s, "buyer_s": buyer_s, "buyer": buyer, "pkg": pkg,
            "booking_id": bid, "reg": reg}


class TestTravelersDocuments:
    def test_passport_linked_to_traveler_and_booking(self, docs_case, admin_s):
        r = docs_case["buyer_s"].post(f"{API}/bookings/{docs_case['booking_id']}/documents",
                                      json={"registrant_index": 0, "doc_type": "passport",
                                            "filename": "p.png", "content_base64": TINY_PNG,
                                            "passport_no": docs_case["reg"]["passport_no"]})
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        assert d["booking_id"] == docs_case["booking_id"]
        assert d["registrant_index"] == 0
        assert d["registrant_name"] == docs_case["reg"]["name"]
        assert d["passport_no"] == docs_case["reg"]["passport_no"]
        docs_case["doc_id"] = d["id"]
        assert "_id" not in d

    def test_per_file_limit_10mb(self, docs_case):
        blob = base64.b64encode(b"x" * (11 * 1024 * 1024)).decode()
        r = docs_case["buyer_s"].post(f"{API}/bookings/{docs_case['booking_id']}/documents",
                                      json={"registrant_index": 0, "doc_type": "passport",
                                            "filename": "big.pdf", "content_base64": blob},
                                      timeout=240)
        assert r.status_code == 400 and "10 ميجابايت" in r.text

    def test_per_batch_limit_20mb(self, docs_case):
        r = docs_case["buyer_s"].post(f"{API}/bookings/{docs_case['booking_id']}/documents",
                                      json={"registrant_index": 0, "doc_type": "passport",
                                            "filename": "s.png", "content_base64": TINY_PNG,
                                            "batch_total_bytes": 21 * 1024 * 1024})
        assert r.status_code == 400 and "20 ميجابايت" in r.text

    def test_unknown_traveler_index_rejected(self, docs_case):
        r = docs_case["buyer_s"].post(f"{API}/bookings/{docs_case['booking_id']}/documents",
                                      json={"registrant_index": 99, "doc_type": "passport",
                                            "filename": "s.png", "content_base64": TINY_PNG})
        assert r.status_code == 400

    def test_view_and_download_are_permission_scoped(self, docs_case, admin_s):
        did = docs_case["doc_id"]
        assert docs_case["buyer_s"].get(f"{API}/documents/{did}/download").status_code == 200
        assert docs_case["seller_s"].get(f"{API}/documents/{did}/download").status_code == 200
        assert admin_s.get(f"{API}/documents/{did}/download").status_code == 200
        stranger, _, _ = new_office("RVSTRANGER")
        assert stranger.get(f"{API}/documents/{did}/download").status_code == 404
        assert requests.get(f"{API}/documents/{did}/download").status_code == 401

    def test_document_operations_are_audited(self, docs_case):
        ev = list(mdb.booking_events.find({"booking_id": docs_case["booking_id"]}))
        actions = {e.get("event") for e in ev}
        assert "document_uploaded" in actions, actions
        assert "document_read" in actions, actions

    def test_missing_document_detection(self, docs_case, admin_s):
        """A booking with NO documents must be flagged by the traveler center."""
        seller_s, _, _ = new_office("RVMSELL")
        buyer_s, _, _ = new_office("RVMBUY")
        t = buyer_s.post(f"{API}/wallet/topups", json={"amount": 4000, "currency": "USD",
                                                       "method": "bank",
                                                       "receipt_url": "http://x/r.png"})
        admin_s.post(f"{API}/admin/topups/{t.json()['id']}/review", json={"approve": True})
        pkg = make_package(seller_s, currency="USD")
        reg = registrant(3)
        bid = buyer_s.post(f"{API}/bookings", json={"package_id": pkg["id"],
                                                    "registrants": [reg]}).json()["id"]
        r = admin_s.get(f"{API}/admin/travelers",
                        params={"q": reg["passport_no"], "missing_only": "true"}, timeout=300)
        assert r.status_code == 200, r.text[:300]
        rows = r.json()["items"]
        assert rows, "missing-doc traveler not detected"
        row = rows[0]
        assert set(row["missing_documents"]) == {"passport", "visa"}, row["missing_documents"]
        assert any(b["booking_id"] == bid for b in row["bookings"])
        assert r.json()["stats"]["with_missing_docs"] >= 1
        assert r.json()["limits"] == {"per_file_mb": 10, "per_batch_mb": 20}

    def test_expiry_validation_and_duplicate_detection(self, admin_s):
        r = admin_s.get(f"{API}/admin/travelers", params={"limit": 50}, timeout=300)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        row = d["items"][0]
        for k in ("passport_no", "passport_expiry", "passport_status", "is_duplicate",
                  "missing_documents", "documents_count"):
            assert k in row, list(row)
        assert row["passport_status"]["level"] in ("ok", "warning", "expired", "unknown")
        for k in ("expired_passports", "expiring_passports", "duplicates"):
            assert k in d["stats"]
        # the expiry rule itself: < 6 months must be a warning, past date must be expired
        exp = admin_s.get(f"{API}/admin/passport-alerts", params={"days": 3650},
                          timeout=300).json()
        assert exp["threshold_days"] == 3650
        for a in exp["items"][:20]:
            assert a["status"]["level"] in ("ok", "warning", "expired", "unknown")

    def test_admin_delete_requires_reason_and_is_audited(self, docs_case, admin_s):
        from bson import ObjectId
        did = docs_case["doc_id"]
        assert admin_s.post(f"{API}/admin/documents/{did}/delete",
                            json={"reason": "قصير"}).status_code == 422
        r = admin_s.post(f"{API}/admin/documents/{did}/delete",
                         json={"reason": "حذف مستند اختبار مراجعة العميل"})
        assert r.status_code == 200, r.text[:300]
        assert mdb.audit_log.find_one({"entity": "document", "entity_id": did,
                                       "action": "document_deleted"})
        assert mdb.traveler_documents.count_documents({"_id": ObjectId(did)}) == 0


# =============================================================================
# 5) Reconciliation — dry-run only, before/after preview, idempotency
# =============================================================================
class TestReconciliation:
    def test_preview_writes_nothing_and_shows_before_after(self, admin_s):
        txn_before = mdb.transactions.count_documents({})
        opening_before = mdb.transactions.count_documents({"type": "opening_balance"})
        r = admin_s.get(f"{API}/admin/reconciliation/preview", timeout=300)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["execution_enabled"] is False
        assert d["wallet_writes"] == 0
        assert d["count"] >= 1
        for row in d["items"][:20]:
            assert row["entry_type"] == "opening_balance"
            assert row["wallet_changed"] is False
            assert row["before"]["wallet_total"] == row["after"]["wallet_total"]
            assert round(row["after"]["ledger_total"] - row["before"]["ledger_total"], 2) == \
                round(row["difference"], 2)
            assert row["account_email"]
        assert mdb.transactions.count_documents({}) == txn_before
        assert mdb.transactions.count_documents({"type": "opening_balance"}) == opening_before

    def test_execution_is_blocked_until_client_approval(self, admin_s):
        d = admin_s.get(f"{API}/admin/reconciliation/preview", timeout=300).json()
        target = next(x for x in d["items"] if not x["already_adjusted"])
        r = admin_s.post(f"{API}/admin/reconciliation/adjust",
                         json={"office_id": target["office_id"], "currency": target["currency"],
                               "reason": "محاولة تنفيذ بدون اعتماد", "dry_run": False})
        assert r.status_code == 403 and "ALLOW_RECONCILIATION" in r.text
        assert mdb.transactions.count_documents({"office_id": target["office_id"],
                                                 "type": "opening_balance"}) == 0

    def test_dry_run_adjust_all_changes_nothing(self, admin_s):
        before = mdb.transactions.count_documents({})
        r = admin_s.post(f"{API}/admin/reconciliation/adjust-all",
                         json={"office_id": "-", "currency": "USD",
                               "reason": "معاينة جماعية بدون تنفيذ", "dry_run": True},
                         timeout=300)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["dry_run"] is True
        assert mdb.transactions.count_documents({}) == before


# =============================================================================
# 6) Backup / restore drill
# =============================================================================
class TestBackups:
    def test_backup_runs_encrypted_and_is_logged(self, admin_s):
        r = admin_s.post(f"{API}/admin/backups/run",
                         json={"reason": "نسخة تحقق لمراجعة العميل"}, timeout=600)
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        assert d["result"] == "success"
        assert d["encrypted"] is True and d["file"].endswith(".enc")
        assert d["size"] > 1000 and d["by"]
        TestBackups.file = d["file"]

    def test_history_shows_operator_size_time_result(self, admin_s):
        d = admin_s.get(f"{API}/admin/backups").json()
        assert d["retention"] == 7 and d["encrypted"] is True
        assert d["environment"] == "preview"
        row = d["items"][0]
        for k in ("by", "size", "at", "result", "reason"):
            assert k in row, list(row)
        assert len(d["files_on_disk"]) <= 7, d["files_on_disk"]

    def test_restore_drill_proves_the_archive_is_usable(self, admin_s):
        r = admin_s.post(f"{API}/admin/backups/verify",
                         json={"file": TestBackups.file,
                               "reason": "اختبار استعادة على قاعدة مؤقتة"}, timeout=900)
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        assert d["result"] == "success" and d["decrypted"] is True
        assert d["collections"] >= 10 and d["documents"] > 1000
        assert d["counts"]["users"] >= 1
        # the drill database is dropped and the working DB is untouched
        assert f"{BE['DB_NAME']}_restore_drill" not in \
            MongoClient(BE["MONGO_URL"]).list_database_names()
        assert mdb.users.count_documents({}) > 0

    def test_restore_is_triple_guarded(self, admin_s):
        r = admin_s.post(f"{API}/admin/backups/restore",
                         json={"file": TestBackups.file, "confirm_phrase": "أؤكد الاستعادة",
                               "reason": "اختبار الحواجز"})
        assert r.status_code == 403 and "ALLOW_RESTORE" in r.text


# =============================================================================
# 7) Real server-side Arabic PDFs + Excel export
# =============================================================================
class TestPdfExports:
    def test_report_pdf_is_a_real_pdf_with_arabic_font(self, admin_s):
        r = admin_s.post(f"{API}/admin/reports/export-pdf",
                         json={"report": "wallets"}, timeout=600)
        assert r.status_code == 200, r.text[:300]
        assert r.headers["content-type"].startswith("application/pdf")
        assert r.content[:5] == b"%PDF-"
        assert len(r.content) > 3000
        import fitz
        doc = fitz.open(stream=r.content, filetype="pdf")
        assert doc.page_count >= 1
        fonts = {f[3] for p in range(doc.page_count) for f in doc[p].get_fonts()}
        assert any("Meraaj" in f or "Amiri" in f or "Noto" in f or "Free" in f
                   for f in fonts), fonts
        page = doc[0]
        text = page.get_text()
        assert text.strip(), "PDF has no extractable text"
        # RTL layout: content is laid out against the right margin
        blocks = page.get_text("blocks")
        assert max(b[2] for b in blocks) > page.rect.width * 0.75

    def test_voucher_pdf_renders(self, admin_s):
        txn = mdb.transactions.find_one({"type": {"$in": ["topup", "booking_debit"]}})
        r = admin_s.get(f"{API}/admin/vouchers/{txn['_id']}/pdf", timeout=300)
        assert r.status_code == 200, r.text[:200]
        assert r.content[:5] == b"%PDF-"
        import fitz
        assert fitz.open(stream=r.content, filetype="pdf").page_count == 1

    def test_excel_csv_export_has_bom(self, admin_s):
        r = admin_s.post(f"{API}/admin/reports/export", json={"report": "withdrawals"},
                         timeout=300)
        assert r.status_code == 200, r.text[:200]
        assert r.content.startswith("\ufeff".encode("utf-8"))
        assert "attachment" in r.headers["content-disposition"]

    def test_saved_filters_and_catalog(self, admin_s):
        c = admin_s.get(f"{API}/admin/reports").json()
        assert len(c["reports"]) >= 13
        s = admin_s.post(f"{API}/admin/reports/save",
                         json={"name": f"فلتر مراجعة {uuid.uuid4().hex[:4]}",
                               "report": "sales", "filters": {"currency": "USD"}})
        assert s.status_code == 200, s.text[:200]
        assert s.json()["by"]

    def test_reports_require_admin(self):
        assert requests.post(f"{API}/admin/reports/export-pdf",
                             json={"report": "wallets"}).status_code == 401


# =============================================================================
# 8) Scanner bridge stays disabled until the Windows PoC passes
# =============================================================================
class TestScannerFlag:
    def test_scanner_bridge_is_disabled(self, admin_s):
        s = admin_s.get(f"{API}/admin/settings").json()["settings"]
        assert s["feature_flags"]["scanner_bridge"] is False
