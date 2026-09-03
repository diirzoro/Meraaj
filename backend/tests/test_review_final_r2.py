"""FINAL client validation round (iteration_14).

Covers: (A) inclusive reports date filtering, (B) /admin/backups destinations + download +
validate + drill + restore guard + import validation, (C) real admin controls, (D) read-only
financial statement, (E) confirmed-defect fixes (dashboard-v2 duplicate alerts, order-detail 500).

PROHIBITED (never executed here): reconciliation adjust with dry_run=false, real maintenance
cleanup, outbox retries, restore over the working DB, record deletion of non-test data.
"""
import io
import json
import os
import uuid
from datetime import date, timedelta

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

from conftest import API, client, new_office, fund_office, make_package  # noqa: F401

backend_env = dotenv_values("/app/backend/.env")
mongo = MongoClient(backend_env.get("MONGO_URL"))
mdb = mongo[backend_env.get("DB_NAME")]

TODAY = date.today().isoformat()
R = "اختبار المراجعة النهائية"


# ------------------------------------------------------------------ E: dashboard-v2
class TestDashboardAlerts:
    def test_dashboard_v2_loads(self, admin):
        r = admin.get(f"{API}/admin/analytics", timeout=120)
        assert r.status_code == 200, r.text[:300]
        assert "alerts" in r.json()

    def test_alerts_have_no_duplicates(self, admin):
        alerts = admin.get(f"{API}/admin/analytics", timeout=120).json().get("alerts") or []
        pairs = [(a.get("type"), a.get("message")) for a in alerts]
        dupes = [p for p in set(pairs) if pairs.count(p) > 1]
        assert not dupes, f"duplicate risk alerts: {dupes}"

    def test_alert_messages_unique(self, admin):
        alerts = admin.get(f"{API}/admin/analytics", timeout=120).json().get("alerts") or []
        msgs = [a.get("message") for a in alerts]
        assert len(msgs) == len(set(msgs)), f"repeated messages: {msgs}"


# ------------------------------------------------------------------ auth/session regression
class TestAuthRegression:
    def test_buyer_login_and_dual_wallet(self):
        r = requests.post(f"{API}/auth/login",
                          json={"email": "buyer@test.com", "password": "Test@1234"}, timeout=60)
        assert r.status_code == 200, r.text[:300]
        tok = r.json()["access_token"]
        w = client(tok).get(f"{API}/wallet", timeout=60)
        assert w.status_code == 200, w.text[:300]
        body = w.json()
        wallet = body.get("wallet", body)
        for cur in ("SAR", "USD"):
            assert cur in wallet, f"missing {cur} bucket: {list(wallet)}"
            for k in ("available", "pending", "total"):
                assert k in wallet[cur], f"{cur} missing {k}"

    def test_admin_permissions_not_empty(self, admin):
        r = admin.get(f"{API}/admin/my-permissions", timeout=60)
        assert r.status_code == 200, r.text[:300]
        assert r.json().get("permissions"), "admin permissions empty"


# ------------------------------------------------------------------ A: reports date filtering
DATED = ["sales", "profit", "programs", "travelers", "cancellations", "withdrawals",
         "users", "audit", "escrow"]
SNAP = ["wallets", "credit", "offices", "fx"]


class TestReportsDateFiltering:
    @pytest.mark.parametrize("report", DATED)
    def test_dated_report_flags(self, admin, report):
        r = admin.post(f"{API}/admin/reports/run",
                       json={"report": report, "date_from": TODAY, "date_to": TODAY}, timeout=180)
        assert r.status_code == 200, f"{report}: {r.status_code} {r.text[:300]}"
        d = r.json()
        assert d["filters"]["date_inclusive"] is True
        assert d.get("snapshot") is False, f"{report} wrongly flagged snapshot"
        assert d.get("period_note"), "missing period_note"

    @pytest.mark.parametrize("report", ["sales", "profit", "cancellations",
                                        "withdrawals", "audit"])
    def test_rows_inside_range(self, admin, report):
        """Every returned row's own date column must fall inside the inclusive range."""
        frm = (date.today() - timedelta(days=30)).isoformat()
        r = admin.post(f"{API}/admin/reports/run",
                       json={"report": report, "date_from": frm, "date_to": TODAY}, timeout=180)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["columns"][0] == "التاريخ", f"{report} first column is {d['columns'][0]}"
        out = [row[0] for row in d["rows"] if not (frm <= str(row[0])[:10] <= TODAY)]
        assert not out, f"{report}: {len(out)} rows outside {frm}..{TODAY}: {out[:5]}"

    def test_narrow_single_day_range(self, admin):
        r = admin.post(f"{API}/admin/reports/run",
                       json={"report": "sales", "date_from": TODAY, "date_to": TODAY}, timeout=180)
        rows = r.json()["rows"]
        bad = [x[0] for x in rows if str(x[0])[:10] != TODAY]
        assert not bad, f"single-day filter leaked rows: {bad[:5]}"

    def test_inclusive_boundary_includes_today(self, admin):
        """A booking created now must appear when date_to == today (upper bound inclusive)."""
        seller, _, _ = new_office("RPTS")
        pkg = make_package(seller)
        buyer, _, _ = new_office("RPTB")
        fund_office(_ADMIN[0], buyer, 5000)
        rb = buyer.post(f"{API}/bookings", json={
            "package_id": pkg["id"] if "id" in pkg else pkg["_id"],
            "registrants": [{"name": "QA Traveler", "passport_no": f"P{uuid.uuid4().hex[:6]}",
                             "age": 30, "category": "adult"}]}, timeout=60)
        assert rb.status_code == 200, rb.text[:300]
        r = _ADMIN[0].post(f"{API}/admin/reports/run",
                           json={"report": "sales", "date_from": TODAY, "date_to": TODAY},
                           timeout=180)
        titles = [row[1] for row in r.json()["rows"]]
        assert pkg.get("title") in titles, "today's booking missing from an inclusive today..today range"

    @pytest.mark.parametrize("report", SNAP)
    def test_snapshot_reports(self, admin, report):
        r = admin.post(f"{API}/admin/reports/run",
                       json={"report": report, "date_from": TODAY, "date_to": TODAY}, timeout=180)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["snapshot"] is True, f"{report} should be snapshot"
        assert "لا ينطبق" in d["period_note"], d["period_note"]

    def test_currency_filter(self, admin):
        for cur in ("SAR", "USD"):
            r = admin.post(f"{API}/admin/reports/run",
                           json={"report": "sales", "currency": cur}, timeout=180)
            assert r.status_code == 200, r.text[:300]
            bad = [row[-1] for row in r.json()["rows"] if row[-1] != cur]
            assert not bad, f"currency filter {cur} leaked: {set(bad)}"

    def test_export_csv(self, admin):
        r = admin.post(f"{API}/admin/reports/export",
                       json={"report": "sales", "date_from": TODAY, "date_to": TODAY}, timeout=180)
        assert r.status_code == 200, r.text[:200]
        assert "csv" in r.headers.get("content-type", "")
        assert r.text.startswith("\ufeff"), "missing UTF-8 BOM for Excel"

    def test_export_pdf(self, admin):
        r = admin.post(f"{API}/admin/reports/export-pdf",
                       json={"report": "sales", "date_from": TODAY, "date_to": TODAY}, timeout=180)
        assert r.status_code == 200, r.text[:200]
        assert r.content[:4] == b"%PDF", r.content[:20]

    def test_saved_filter(self, admin):
        name = f"TEST_saved_{uuid.uuid4().hex[:6]}"
        r = admin.post(f"{API}/admin/reports/save", json={
            "name": name, "report": "sales",
            "filters": {"date_from": TODAY, "date_to": TODAY}}, timeout=60)
        assert r.status_code == 200, r.text[:300]
        cat = admin.get(f"{API}/admin/reports", timeout=60).json()
        assert any(s["name"] == name for s in cat["saved"]), "saved filter not persisted"
        mdb.saved_reports.delete_many({"name": name})


# ------------------------------------------------------------------ E: order detail 500
_ADMIN = []


@pytest.fixture(scope="module", autouse=True)
def _bind_admin(admin):
    _ADMIN.clear()
    _ADMIN.append(admin)
    return admin


class TestOrderDetailNo500:
    def test_20_bookings_full(self, admin):
        ids = [str(b["_id"]) for b in mdb.bookings.find({}, {"_id": 1}).limit(20)]
        rahal = [str(b["_id"]) for b in mdb.bookings.find(
            {"$or": [{"source": "rahal"}, {"rahal_ref": {"$ne": None}}]}, {"_id": 1}).limit(5)]
        weird = [str(b["_id"]) for b in mdb.bookings.find(
            {"$or": [{"package_id": {"$not": {"$regex": "^[0-9a-f]{24}$"}}},
                     {"buyer_id": {"$not": {"$regex": "^[0-9a-f]{24}$"}}}]}, {"_id": 1}).limit(5)]
        targets = list(dict.fromkeys(ids + rahal + weird))
        assert len(targets) >= 15, f"only {len(targets)} bookings available"
        fails = []
        for bid in targets:
            r = admin.get(f"{API}/admin/bookings/{bid}/full", timeout=90)
            if r.status_code != 200:
                fails.append((bid, r.status_code, r.text[:150]))
        assert not fails, f"{len(fails)}/{len(targets)} failed: {fails[:5]}"

    def test_synthetic_legacy_reference_booking(self, admin):
        """Non-ObjectId package/buyer/seller references must not blow up the order detail."""
        from bson import ObjectId
        doc = {"_id": ObjectId(), "package_id": "LEGACY-PKG-REF", "buyer_id": "LEGACY-BUYER",
               "seller_id": "LEGACY-SELLER", "package_title": "TEST_legacy_ref",
               "seats": 1, "amount_charged": 100.0, "net_cost_total": 80.0,
               "platform_fee": 10.0, "currency": "SAR", "status": "blue",
               "registrants": [], "created_at": "2026-07-01T00:00:00+00:00"}
        mdb.bookings.insert_one(doc)
        bid = str(doc["_id"])
        try:
            r = admin.get(f"{API}/admin/bookings/{bid}/full", timeout=60)
            assert r.status_code == 200, f"/full: {r.status_code} {r.text[:200]}"
            f = admin.get(f"{API}/admin/bookings/{bid}/financials", timeout=60)
            assert f.status_code == 200, f"/financials: {f.status_code} {f.text[:200]}"
        finally:
            mdb.bookings.delete_one({"_id": doc["_id"]})

    def test_unknown_id_is_clean_404(self, admin):
        r = admin.get(f"{API}/admin/bookings/{uuid.uuid4().hex[:24]}/full", timeout=60)
        assert r.status_code == 404, f"{r.status_code} {r.text[:200]}"

    def test_garbage_id_not_500(self, admin):
        r = admin.get(f"{API}/admin/bookings/not-an-objectid/full", timeout=60)
        assert r.status_code in (400, 404, 422), f"{r.status_code} {r.text[:200]}"


# ------------------------------------------------------------------ D: financial statement
FIN_KEYS = ["paid", "pending", "released", "refunded", "due_from_buyer", "due_to_seller",
            "platform_commission", "platform_net", "transferred", "remaining",
            "currency", "status", "settled"]


class TestFinancialStatement:
    def test_financials_shape(self, admin):
        bids = [str(b["_id"]) for b in mdb.bookings.find({}, {"_id": 1}).limit(10)]
        for bid in bids:
            r = admin.get(f"{API}/admin/bookings/{bid}/financials", timeout=60)
            assert r.status_code == 200, f"{bid}: {r.status_code} {r.text[:200]}"
            d = r.json()
            fin = d.get("financials") or {}
            missing = [k for k in FIN_KEYS if k not in fin]
            assert not missing, f"{bid} missing {missing}"
            assert isinstance(d.get("movements"), list), "movements not a list"
            assert fin["currency"] in ("SAR", "USD"), fin["currency"]
            assert fin["paid"] >= 0 and fin["remaining"] == fin["pending"]

    def test_financials_legacy_ids_no_500(self, admin):
        weird = [str(b["_id"]) for b in mdb.bookings.find(
            {"$or": [{"package_id": {"$not": {"$regex": "^[0-9a-f]{24}$"}}},
                     {"buyer_id": {"$not": {"$regex": "^[0-9a-f]{24}$"}}},
                     {"seller_id": {"$not": {"$regex": "^[0-9a-f]{24}$"}}}]},
            {"_id": 1}).limit(10)]
        fails = []
        for bid in weird:
            r = admin.get(f"{API}/admin/bookings/{bid}/financials", timeout=60)
            if r.status_code != 200:
                fails.append((bid, r.status_code, r.text[:120]))
        assert not fails, f"financials failed for legacy-id bookings: {fails[:5]}"

    def test_view_does_not_change_money(self, admin):
        b = mdb.bookings.find_one({})
        buyer = mdb.users.find_one({"_id": __import__("bson").ObjectId(b["buyer_id"])}) \
            if len(str(b.get("buyer_id") or "")) == 24 else None
        before = json.dumps((buyer or {}).get("wallet"), sort_keys=True) if buyer else None
        txn_before = mdb.transactions.count_documents({})
        for _ in range(3):
            admin.get(f"{API}/admin/bookings/{str(b['_id'])}/financials", timeout=60)
        assert mdb.transactions.count_documents({}) == txn_before, "viewing created transactions"
        if buyer:
            after = mdb.users.find_one({"_id": buyer["_id"]}).get("wallet")
            assert json.dumps(after, sort_keys=True) == before, "wallet changed by a read-only view"


# ------------------------------------------------------------------ B: backups
class TestBackups:
    def test_storage_destinations(self, admin):
        r = admin.get(f"{API}/admin/backups/storage", timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        keys = [x["key"] for x in d["destinations"]]
        assert keys == ["download", "server", "cloud", "server_and_download"], keys
        cloud = [x for x in d["destinations"] if x["key"] == "cloud"][0]
        assert cloud["available"] is False, "cloud should be unavailable without env keys"
        assert d["encrypted"] is True, "BACKUP_PASSPHRASE not effective"

    def test_cloud_destination_refused(self, admin):
        r = admin.post(f"{API}/admin/backups/run",
                       json={"reason": R, "destination": "cloud"}, timeout=300)
        assert r.status_code == 400, f"{r.status_code} {r.text[:200]}"

    def test_reason_mandatory(self, admin):
        r = admin.post(f"{API}/admin/backups/run",
                       json={"reason": "", "destination": "server"}, timeout=300)
        assert r.status_code == 422, f"{r.status_code} {r.text[:200]}"

    def test_run_server_and_download(self, admin):
        r = admin.post(f"{API}/admin/backups/run",
                       json={"reason": R, "destination": "server_and_download"}, timeout=600)
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        assert d["destination"] == "server_and_download"
        assert d["encrypted"] is True and d["file"].endswith(".enc"), d
        assert d["integrity"] == "valid" and len(d["sha256"]) == 64
        assert d.get("download_url"), "no download_url for a download destination"
        a = mdb.audit_log.find_one({"entity": "backup", "action": "backup_run",
                                    "after.file": d["file"]})
        assert a and a["after"]["destination"] == "server_and_download", "destination not audited"

    def test_download_backup(self, admin):
        f = _latest_file()
        r = admin.get(f"{API}/admin/backups/{f}/download", timeout=300)
        assert r.status_code == 200, r.text[:200]
        assert r.headers.get("content-type") == "application/octet-stream"
        assert "attachment" in r.headers.get("content-disposition", "")
        assert len(r.content) > 1000, len(r.content)
        assert mdb.audit_log.find_one({"action": "backup_downloaded", "entity_id": f})

    def test_validate_backup(self, admin):
        f = _latest_file()
        r = admin.post(f"{API}/admin/backups/validate", json={"file": f}, timeout=300)
        assert r.status_code == 200, r.text[:200]
        d = r.json()
        assert d["valid"] is True and d["encrypted"] is True and len(d["sha256"]) == 64, d

    def test_validate_missing_file_404(self, admin):
        r = admin.post(f"{API}/admin/backups/validate",
                       json={"file": "meraaj-nope.archive.gz.enc"}, timeout=60)
        assert r.status_code == 404, r.status_code

    def test_isolated_restore_drill(self, admin):
        f = _latest_file()
        users_before = mdb.users.count_documents({})
        r = admin.post(f"{API}/admin/backups/verify", json={"file": f, "reason": R}, timeout=900)
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        assert d["result"] == "success" and d["documents"] > 0, d
        drill = f"{backend_env.get('DB_NAME')}_restore_drill"
        assert drill not in mongo.list_database_names(), "drill database not dropped"
        assert mdb.users.count_documents({}) == users_before, "working DB touched by the drill"

    def test_production_restore_refused(self, admin):
        f = _latest_file()
        r = admin.post(f"{API}/admin/backups/restore", json={
            "file": f, "confirm_phrase": "أؤكد الاستعادة", "reason": R * 2}, timeout=120)
        assert r.status_code == 403, f"{r.status_code} {r.text[:200]}"
        assert "ALLOW_RESTORE" in r.text or "معطّلة" in r.text


def _latest_file():
    rec = mdb.backups.find_one({"result": "success", "file": {"$ne": None},
                                "storage": {"$ne": "gridfs"}}, sort=[("at", -1)])
    assert rec, "no server-side backup available"
    return rec["file"]


class TestBackupImport:
    def test_corrupted_file_rejected_with_detail(self, admin):
        name = "bad.archive.gz.enc"
        payload = b"this-is-not-an-encrypted-mongodump-archive" * 40
        before = mdb.backups.count_documents({})
        r = requests.post(f"{API}/admin/backups/upload",
                          files={"file": (name, io.BytesIO(payload), "application/octet-stream")},
                          data={"reason": R},
                          headers={"Authorization": admin.headers["Authorization"]}, timeout=300)
        assert r.status_code == 400, f"{r.status_code} {r.text[:300]}"
        msg = r.json().get("detail", "")
        assert "مرفوض" in msg and "الحجم" in msg, msg
        assert ".archive.gz" in msg and "BACKUP_PASSPHRASE" in msg, msg
        assert mdb.backups.count_documents({}) == before, "rejected file was stored"
        a = mdb.audit_log.find_one({"action": "backup_upload_rejected"},
                                   sort=[("at", -1)])
        assert a and a["after"]["size"] == len(payload), f"no audit entry: {a}"

    def test_bad_extension_rejected(self, admin):
        r = requests.post(f"{API}/admin/backups/upload",
                          files={"file": ("evil.zip", io.BytesIO(b"PK\x03\x04"), "application/zip")},
                          data={"reason": R},
                          headers={"Authorization": admin.headers["Authorization"]}, timeout=120)
        assert r.status_code == 400 and "امتداد" in r.text, r.text[:200]

    def test_valid_backup_accepted(self, admin):
        f = _latest_file()
        blob = admin.get(f"{API}/admin/backups/{f}/download", timeout=300).content
        r = requests.post(f"{API}/admin/backups/upload",
                          files={"file": (f"reimport-{f}", io.BytesIO(blob),
                                          "application/octet-stream")},
                          data={"reason": R},
                          headers={"Authorization": admin.headers["Authorization"]}, timeout=600)
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        assert d["integrity"] == "valid" and d["storage"] == "gridfs", d
        assert d["validation"]["ok"] is True and d["encrypted"] is True
        assert mdb.backups.find_one({"file": d["file"], "storage": "gridfs"}), "not stored"

    def test_plaintext_archive_accepted_rca(self, admin):
        """RCA probe: an UNencrypted .archive.gz is accepted, which proves the encrypted
        rejection above comes from _inspect() deciding encryption from the temp file's
        extension instead of the uploaded file name."""
        import subprocess
        f = _latest_file()
        pw = backend_env.get("BACKUP_PASSPHRASE")
        plain = "/tmp/rca-meraaj-plain.archive.gz"
        subprocess.run(["openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2",
                        "-in", f"/app/backups/{f}", "-out", plain, "-pass", f"pass:{pw}"],
                       check=True, capture_output=True)
        with open(plain, "rb") as fh:
            blob = fh.read()
        r = requests.post(f"{API}/admin/backups/upload",
                          files={"file": ("meraaj-rca-plain.archive.gz", io.BytesIO(blob),
                                          "application/octet-stream")},
                          data={"reason": R},
                          headers={"Authorization": admin.headers["Authorization"]}, timeout=600)
        os.remove(plain)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["encrypted"] is False and d["integrity"] == "valid", d
        mdb.backups.delete_many({"file": d["file"]})


# ------------------------------------------------------------------ maintenance
class TestMaintenance:
    def test_policies(self, admin):
        r = admin.get(f"{API}/admin/maintenance/policies", timeout=180)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d.get("cleanable") and d.get("protected"), list(d)
        kinds = [c["kind"] for c in d["cleanable"]]
        assert "webhook_attempts" in kinds and "read_notifications" in kinds, kinds
        prot = [p["collection"] for p in d["protected"]]
        for c in ("audit_log", "transactions", "bookings", "users", "packages"):
            assert c in prot, f"{c} not listed as protected"

    def test_preview(self, admin):
        for kind in _kinds(admin):
            r = admin.post(f"{API}/admin/maintenance/preview",
                           json={"kind": kind, "retention_days": 30}, timeout=180)
            assert r.status_code == 200, f"{kind}: {r.status_code} {r.text[:200]}"
            d = r.json()
            assert "matched" in d and isinstance(d.get("sample"), list), list(d)
            assert d["matched"] == len(d["sample"]) or d["matched"] >= len(d["sample"])

    def test_dry_run_deletes_nothing(self, admin):
        for kind in _kinds(admin):
            coll = _kind_collection(kind)
            before = mdb[coll].count_documents({})
            r = admin.post(f"{API}/admin/maintenance/cleanup", json={
                "kind": kind, "retention_days": 30, "dry_run": True,
                "reason": R}, timeout=180)
            assert r.status_code == 200, f"{kind}: {r.status_code} {r.text[:200]}"
            d = r.json()
            assert d["dry_run"] is True and d["deleted"] == 0, d
            assert mdb[coll].count_documents({}) == before, f"{kind} dry-run deleted rows"

    def test_wrong_confirm_phrase_refused(self, admin):
        kind = "sim_inbox"
        coll = _kind_collection(kind)
        before = mdb[coll].count_documents({})
        r = admin.post(f"{API}/admin/maintenance/cleanup", json={
            "kind": kind, "retention_days": 365, "dry_run": False,
            "confirm_phrase": "أؤكد", "reason": R}, timeout=180)
        assert r.status_code in (400, 403), f"{r.status_code} {r.text[:200]}"
        assert mdb[coll].count_documents({}) == before, "rows deleted despite wrong phrase"

    @pytest.mark.parametrize("kind", ["audit_log", "transactions", "bookings", "users"])
    def test_protected_type_refused(self, admin, kind):
        before = mdb[kind].count_documents({})
        r = admin.post(f"{API}/admin/maintenance/cleanup", json={
            "kind": kind, "retention_days": 30, "dry_run": True, "reason": R}, timeout=180)
        assert r.status_code in (400, 403), f"{kind}: {r.status_code} {r.text[:200]}"
        assert "محمي" in r.text or "محميّ" in r.text, r.text[:200]
        r2 = admin.post(f"{API}/admin/maintenance/preview",
                        json={"kind": kind, "retention_days": 30}, timeout=180)
        assert r2.status_code in (400, 403), f"preview {kind}: {r2.status_code}"
        assert mdb[kind].count_documents({}) == before

    def test_unknown_kind_refused(self, admin):
        r = admin.post(f"{API}/admin/maintenance/cleanup", json={
            "kind": "whatever", "dry_run": True, "reason": R}, timeout=120)
        assert r.status_code == 400, r.status_code

    def test_history(self, admin):
        r = admin.get(f"{API}/admin/maintenance/history", timeout=180)
        assert r.status_code == 200, r.text[:200]


_KINDS = []


def _kinds(admin):
    if not _KINDS:
        d = admin.get(f"{API}/admin/maintenance/policies", timeout=180).json()
        _KINDS.extend([c["kind"] for c in d["cleanable"]])
    return _KINDS


KIND_COLL = {"webhook_attempts": "rahal_outbox", "inbound_log": "rahal_inbound_log",
             "read_notifications": "notifications", "notification_log": "notification_log",
             "closed_tasks": "admin_tasks", "revoked_sessions": "sessions",
             "sim_inbox": "rahal_sim_inbox"}


def _kind_collection(kind: str):
    assert kind in KIND_COLL, f"unknown cleanable kind {kind} — update KIND_COLL"
    return KIND_COLL[kind]


# ------------------------------------------------------------------ C: admin controls
class TestAdminControls:
    def test_org_lifecycle(self, admin):
        email = f"test_org_{uuid.uuid4().hex[:8]}@qa-example.com"
        r = admin.post(f"{API}/admin/orgs", json={
            "office_name": "TEST_مؤسسة المراجعة", "owner_name": "QA Owner", "email": email,
            "password": "Test@1234", "phone": "0770000000", "governorate": "بغداد",
            "commercial_license": "TEST-LIC-1", "reason": R}, timeout=120)
        assert r.status_code == 200, r.text[:300]
        oid_ = r.json()["id"]
        assert mdb.audit_log.find_one({"entity": "org", "entity_id": oid_,
                                       "action": "org_created", "reason": R})

        # edit
        e = admin.patch(f"{API}/admin/orgs/{oid_}",
                        json={"office_name": "TEST_مؤسسة معدلة", "reason": R}, timeout=120)
        assert e.status_code == 200, e.text[:300]
        det = admin.get(f"{API}/admin/orgs/{oid_}", timeout=120).json()
        assert det["office"]["office_name"] == "TEST_مؤسسة معدلة", "edit not persisted"

        # reason mandatory
        bad = admin.patch(f"{API}/admin/orgs/{oid_}", json={"phone": "0771"}, timeout=60)
        assert bad.status_code == 422, bad.status_code

        # suspend + reactivate
        s = admin.post(f"{API}/admin/users/{oid_}/suspend",
                       json={"suspend": True, "reason": R}, timeout=120)
        assert s.status_code == 200, s.text[:300]
        assert admin.get(f"{API}/admin/orgs/{oid_}", timeout=60).json()["office"]["status"] == "suspended"
        lg = requests.post(f"{API}/auth/login", json={"email": email, "password": "Test@1234"},
                           timeout=60)
        assert lg.status_code in (401, 403), f"suspended office could log in: {lg.status_code}"
        a = admin.post(f"{API}/admin/users/{oid_}/suspend",
                       json={"suspend": False, "reason": R}, timeout=120)
        assert a.status_code == 200, a.text[:300]
        assert admin.get(f"{API}/admin/orgs/{oid_}", timeout=60).json()["office"]["status"] == "active"
        assert requests.post(f"{API}/auth/login",
                             json={"email": email, "password": "Test@1234"},
                             timeout=60).status_code == 200

        # branch add + edit
        b = admin.post(f"{API}/admin/orgs/{oid_}/branches",
                       json={"name": "TEST_فرع", "city": "بغداد"}, timeout=120)
        assert b.status_code == 200, b.text[:300]
        bid = b.json()["id"] if "id" in b.json() else b.json()["_id"]
        be = admin.patch(f"{API}/admin/branches/{bid}",
                         json={"name": "TEST_فرع معدل", "reason": R}, timeout=120)
        assert be.status_code == 200, be.text[:300]
        assert mdb.office_branches.find_one({"name": "TEST_فرع معدل"}), "branch edit not persisted"

        # staff add + login account + roles edit
        st = admin.post(f"{API}/admin/orgs/{oid_}/staff", json={
            "name": "TEST_موظف", "job_title": "محاسب", "branch_id": bid,
            "roles": ["limited_user"]}, timeout=120)
        assert st.status_code == 200, st.text[:300]
        sid = st.json().get("id") or st.json().get("_id")
        semail = f"test_staff_{uuid.uuid4().hex[:8]}@qa-example.com"
        ac = admin.post(f"{API}/admin/staff/{sid}/account", json={
            "email": semail, "password": "Staff@1234", "roles": ["limited_user"]}, timeout=120)
        assert ac.status_code == 200, ac.text[:300]
        assert ac.json()["shares_office_wallet"] is True
        suser = mdb.users.find_one({"email": semail})
        assert suser and "wallet" not in suser, "staff account got its own wallet"
        assert str(suser["parent_office_id"]) == oid_

        # staff login shares the office wallet + non-empty permissions
        sl = requests.post(f"{API}/auth/login", json={"email": semail, "password": "Staff@1234"},
                           timeout=60)
        assert sl.status_code == 200, sl.text[:300]
        ss = client(sl.json()["access_token"])
        me = ss.get(f"{API}/auth/me", timeout=60).json()
        assert str(me.get("id") or me.get("_id")) == oid_, f"staff not acting as the office: {me}"
        ow = ss.get(f"{API}/wallet", timeout=60)
        assert ow.status_code == 200, ow.text[:200]
        perms = ss.get(f"{API}/admin/my-permissions", timeout=60)
        assert perms.status_code == 200, perms.text[:200]
        assert perms.json().get("permissions"), "staff permissions came back empty"

        re_ = admin.patch(f"{API}/admin/staff/{sid}",
                          json={"roles": ["accountant"], "reason": R}, timeout=120)
        assert re_.status_code == 200, re_.text[:300]
        assert mdb.user_roles.find_one({"user_id": str(suser["_id"])})["roles"] == ["accountant"]

        _CLEAN.extend([("users", oid_), ("users", str(suser["_id"]))])

    def test_rbac_user_lifecycle(self, admin):
        email = f"test_rbacu_{uuid.uuid4().hex[:8]}@qa-example.com"
        r = admin.post(f"{API}/admin/rbac/users", json={
            "email": email, "password": "Test@1234", "role": "individual",
            "name": "TEST_مستخدم", "phone": "0770000001", "roles": ["limited_user"],
            "reason": R}, timeout=120)
        assert r.status_code == 200, r.text[:300]
        uid = r.json().get("id") or r.json().get("user_id")
        lg = requests.post(f"{API}/auth/login", json={"email": email, "password": "Test@1234"},
                           timeout=60)
        assert lg.status_code == 200, lg.text[:300]
        old_token = lg.json()["access_token"]

        ed = admin.patch(f"{API}/admin/rbac/users/{uid}",
                         json={"phone": "0779999999", "reason": R}, timeout=120)
        assert ed.status_code == 200, ed.text[:300]
        assert mdb.users.find_one({"_id": __import__("bson").ObjectId(uid)})["phone"] == "0779999999"

        pm = admin.post(f"{API}/admin/rbac/users/{uid}/permissions",
                        json={"permissions": ["reports.view"], "reason": R}, timeout=120)
        assert pm.status_code == 200, pm.text[:300]
        star = admin.post(f"{API}/admin/rbac/users/{uid}/permissions",
                          json={"permissions": ["*"], "reason": R}, timeout=120)
        assert star.status_code == 400, f"'*' granted via extra permissions: {star.status_code}"

        pr = admin.post(f"{API}/admin/rbac/users/{uid}/password-reset",
                        json={"new_password": "NewPass@2026", "reason": R}, timeout=120)
        assert pr.status_code == 200, pr.text[:300]
        old = client(old_token).get(f"{API}/auth/me", timeout=60)
        assert old.status_code in (401, 403), f"old token still valid after reset: {old.status_code}"
        assert requests.post(f"{API}/auth/login",
                             json={"email": email, "password": "NewPass@2026"},
                             timeout=60).status_code == 200

        fl = admin.post(f"{API}/admin/users/{uid}/force-logout", json={"reason": R}, timeout=120)
        assert fl.status_code == 200, fl.text[:300]
        _CLEAN.append(("users", uid))

    def test_program_controls(self, admin):
        seller = mdb.users.find_one({"role": "office", "status": "active"})
        sid = str(seller["_id"])
        r = admin.post(f"{API}/admin/programs", json={
            "seller_id": sid, "title": f"TEST_برنامج_{uuid.uuid4().hex[:6]}",
            "departure_date": "2026-12-01", "return_date": "2026-12-10",
            "net_cost_per_seat": 100.0, "final_sale_price": 130.0,
            "buyer_office_commission": 20.0, "currency": "SAR", "total_seats": 10,
            "reason": R}, timeout=120)
        assert r.status_code == 200, r.text[:300]
        pid = r.json()["id"]
        assert mdb.packages.find_one({"_id": __import__("bson").ObjectId(pid)})["source"] == "admin"

        p = admin.patch(f"{API}/admin/programs/{pid}",
                        json={"changes": {"total_seats": 12}, "reason": R}, timeout=120)
        assert p.status_code == 200, p.text[:300]

        for state in ("unlisted", "archived", "listed"):
            s = admin.post(f"{API}/admin/programs/{pid}/state",
                           json={"state": state, "reason": R}, timeout=120)
            assert s.status_code == 200, f"{state}: {s.text[:200]}"

        # seats cannot go below sold seats: book 2 seats then try 1
        buyer, _, _ = new_office("PROGB")
        fund_office(admin, buyer, 5000)
        bk = buyer.post(f"{API}/bookings", json={
            "package_id": pid,
            "registrants": [{"name": "T1", "passport_no": f"P{uuid.uuid4().hex[:6]}",
                             "age": 30, "category": "adult"},
                            {"name": "T2", "passport_no": f"P{uuid.uuid4().hex[:6]}",
                             "age": 31, "category": "adult"}]}, timeout=120)
        assert bk.status_code == 200, bk.text[:300]
        low = admin.patch(f"{API}/admin/programs/{pid}",
                          json={"changes": {"total_seats": 1}, "reason": R}, timeout=120)
        assert low.status_code == 400, f"seats reduced below sold: {low.status_code} {low.text[:200]}"
        assert "المباعة" in low.text or "المقاعد" in low.text

    def test_credit_controls(self, admin):
        office = mdb.users.find_one({"role": "office", "status": "active"})
        oid_ = str(office["_id"])
        try:
            g = admin.post(f"{API}/admin/credit/{oid_}",
                           json={"currency": "SAR", "limit": 5000, "reason": R}, timeout=120)
            assert g.status_code == 200, g.text[:300]
            row = mdb.credit_limits.find_one({"office_id": oid_, "currency": "SAR"})
            assert row and row["limit"] == 5000, row
            assert mdb.credit_events.find_one({"office_id": oid_}), "no credit audit event"

            f1 = admin.post(f"{API}/admin/credit/{oid_}/freeze",
                            json={"currency": "SAR", "frozen": True, "reason": R}, timeout=120)
            assert f1.status_code == 200, f1.text[:300]
            assert mdb.credit_limits.find_one({"office_id": oid_,
                                               "currency": "SAR"})["status"] == "frozen"
            f2 = admin.post(f"{API}/admin/credit/{oid_}/freeze",
                            json={"currency": "SAR", "frozen": False, "reason": R}, timeout=120)
            assert f2.status_code == 200, f2.text[:300]
            assert mdb.credit_limits.find_one({"office_id": oid_,
                                               "currency": "SAR"})["status"] == "active"
        finally:
            admin.post(f"{API}/admin/credit/{oid_}",
                       json={"currency": "SAR", "limit": 0, "reason": "إرجاع حالة الاختبار"},
                       timeout=120)


_CLEAN = []


@pytest.fixture(scope="module", autouse=True)
def _cleanup():
    yield
    from bson import ObjectId
    for coll, _id in _CLEAN:
        try:
            mdb[coll].update_one({"_id": ObjectId(_id)},
                                 {"$set": {"status": "active"}, "$unset": {"force_logout_at": ""}})
        except Exception:
            pass
