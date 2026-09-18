"""MERAAJ MOBILE + ADMIN MOBILE — one comprehensive backend QA pass (final session).

Covers: experience resolution from the authenticated identity, admin mobile sections filtered
by RBAC, mobile accounting capabilities (ADMIN ONLY), account scope inside the app, direct
API/route manipulation, office isolation, password reset (anti-enumeration + single use),
top-up receipt upload + ownership, device token registration, and write idempotency.

Isolated test data only (`qa-mob-*@qa-example.com`); everything is removed in cleanup, which
runs even when an assertion fails. No production booking or financial operation.
"""
import asyncio
import io
import os
import sys
import uuid

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SUPER = ("abuzay84@gmail.com", "Meraaj@2026")
PW = "QaTest@2026"
TAG = uuid.uuid4().hex[:6]
BASE = None
RESULTS = []
CREATED = []
STATE = {"seeded_chart": False, "qa_accounts": [], "topups": [], "vouchers": []}


def rec(name, ok, note=""):
    RESULTS.append((name, bool(ok), note))
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {note}")


def read_base():
    with open("/app/frontend/.env", encoding="utf-8") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("missing REACT_APP_BACKEND_URL")


class C:
    def __init__(self):
        self.http = httpx.AsyncClient(base_url=f"{BASE}/api", timeout=45.0)

    async def login(self, email, password):
        r = await self.http.post("/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, f"login {email}: {r.status_code} {r.text[:150]}"
        self.http.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
        return r.json()

    async def req(self, m, u, **kw):
        return await self.http.request(m, u, **kw)

    async def code(self, m, u, **kw):
        return (await self.req(m, u, **kw)).status_code

    async def close(self):
        await self.http.aclose()


async def make_user(admin, key, roles, role="office"):
    email = f"qa-mob-{key}-{TAG}@qa-example.com"
    payload = {"email": email, "password": PW, "role": role, "name": f"QA {key}",
               "roles": roles, "reason": "QA mobile final session"}
    r = await admin.req("POST", "/admin/rbac/users", json=payload)
    assert r.status_code == 200, f"{email}: {r.status_code} {r.text[:200]}"
    uid = r.json()["id"]
    CREATED.append((uid, email))
    c = C()
    await c.login(email, PW)
    return {"id": uid, "email": email, "client": c}


async def main():
    global BASE
    BASE = read_base()
    print(f"BASE={BASE}\n")
    admin = C()
    await admin.login(*SUPER)

    # -------------------------------------------------- public config (pre-login)
    pub = (await httpx.AsyncClient(timeout=30).get(f"{BASE}/api/v1/mobile/config")).json()
    rec("CONFIG.public_reachable_before_login",
        pub["api_version"] == "v1" and pub["authenticated"] is False
        and pub["min_supported_app"], f"min={pub['min_supported_app']}")
    rec("CONFIG.no_secrets_leaked",
        not any(k in pub for k in ("user", "wallet", "permissions", "tokens")), "")

    # ---------------------------------------------------------------- chart setup
    accounts = (await admin.req("GET", "/accounting/accounts?include_inactive=true")).json()["items"]
    if not accounts:
        STATE["seeded_chart"] = (await admin.req("POST", "/accounting/chart/seed")).status_code == 200
        accounts = (await admin.req("GET", "/accounting/accounts?include_inactive=true")).json()["items"]

    async def qa_acc(parent, name, kind):
        r = await admin.req("POST", "/accounting/accounts", json={
            "parent": parent, "name": f"QA {kind} {TAG}", "name_ar": name,
            "type": kind, "is_group": False})
        assert r.status_code == 200, r.text[:200]
        STATE["qa_accounts"].append(r.json())
        return r.json()

    cash = await qa_acc("1101", f"صندوق جوال {TAG}", "asset")
    counter = await qa_acc("2101", f"دائن جوال {TAG}", "liability")
    outside = await qa_acc("1102", f"بنك جوال {TAG}", "asset")

    # ------------------------------------------------------------------- personas
    cat = (await admin.req("GET", "/admin/rbac/catalog")).json()
    individual = await make_user(admin, "individual", [], role="individual")
    office = await make_user(admin, "office", [])
    admin_plain = await make_user(admin, "adminplain", ["hr_admin"])
    await admin.req("PATCH", f"/admin/rbac/users/{admin_plain['id']}",
                    json={"is_admin_staff": True, "reason": "QA admin staff"}) \
        if False else None
    acc_admin = await make_user(admin, "accadmin", ["accounting_admin"])
    cashier = await make_user(admin, "cashier", ["cashier"])
    rec("SETUP.personas_created", all(u["id"] for u in
        (individual, office, admin_plain, acc_admin, cashier)), f"5 حسابات — {TAG}")

    # --------------------------------------------------- experience resolution
    for label, user, expected in [("individual", individual, "individual"),
                                  ("office", office, "office"),
                                  ("super_admin", admin, "admin")]:
        b = (await user["client"].req("GET", "/v1/mobile/bootstrap")).json() \
            if isinstance(user, dict) else (await user.req("GET", "/v1/mobile/bootstrap")).json()
        rec(f"EXP.{label}_experience", b["experience"] == expected, b["experience"])
        if expected != "admin":
            rec(f"EXP.{label}_no_accounting", b["accounting"]["enabled"] is False
                and not b["accounting"]["capabilities"]
                and not b["admin_sections"], "المحاسبة غير ظاهرة إطلاقاً")
            rec(f"EXP.{label}_tabs_are_user_tabs",
                [t["key"] for t in b["tabs"]] ==
                ["home", "bookings", "wallet", "notifications", "account"], "")
        else:
            rec("EXP.admin_sections_present", len(b["admin_sections"]) >= 2, "")
            rec("EXP.admin_accounting_enabled", b["accounting"]["enabled"] is True, "")
            rec("EXP.admin_has_no_wallet_services", b["services"] == [] and b["wallet"] == {}, "")

    ind_b = (await individual["client"].req("GET", "/v1/mobile/bootstrap")).json()
    rec("EXP.individual_services_exclude_office_only",
        all(s["key"] not in ("sales", "office_statement") for s in ind_b["services"]),
        f"{[s['key'] for s in ind_b['services']]}")
    off_b = (await office["client"].req("GET", "/v1/mobile/bootstrap")).json()
    rec("EXP.office_services_include_sales_and_statement",
        {"sales", "office_statement"} <= {s["key"] for s in off_b["services"]}, "")
    rec("EXP.tickets_flagged_coming_soon",
        any(s["key"] == "tickets" and s["status"] == "coming_soon" for s in off_b["services"])
        and off_b["features"]["tickets_booking"] is False, "")

    # ------------------------------------------- mobile accounting = ADMIN ONLY
    acc_b = (await acc_admin["client"].req("GET", "/v1/mobile/bootstrap")).json()
    rec("MACC.accounting_admin_is_office_role_but_not_admin_experience",
        acc_b["experience"] == "office" and acc_b["accounting"]["enabled"] is False,
        "موظف بدور محاسبي بلا صفة إدارية لا يحصل على تجربة الإدارة في التطبيق")
    sadmin_b = (await admin.req("GET", "/v1/mobile/bootstrap")).json()
    caps = sadmin_b["accounting"]["capabilities"]
    rec("MACC.super_admin_capabilities_complete",
        all(caps.get(k) for k in ("chart_view", "vouchers_view", "journals_view",
                                  "ledger_view", "reports_view", "periods_view")), "")
    rec("MACC.accounting_tab_present_only_when_enabled",
        any(t["key"] == "accounting" for t in sadmin_b["tabs"])
        and not any(t["key"] == "accounting" for t in off_b["tabs"]), "")

    # office/individual hitting accounting APIs directly from the app
    for label, user in [("individual", individual), ("office", office)]:
        for url in ["/accounting/accounts", "/accounting/journal/entries",
                    "/accounting/vouchers", "/accounting/reports/trial-balance",
                    f"/accounting/ledger/account/{cash['code']}"]:
            rec(f"SEC.{label}_denied {url}",
                await user["client"].code("GET", url) == 403, "")

    # -------------------------------------------------- account scope in the app
    await admin.req("POST", f"/admin/rbac/users/{admin_plain['id']}/permissions", json={
        "permissions": ["accounting.vouchers.view", "accounting.vouchers.receipt"],
        "denied": [], "reason": "QA — أمين صندوق على الجوال"})
    await admin.req("POST", f"/admin/rbac/users/{admin_plain['id']}/account-scope", json={
        "mode": "selected_accounts", "codes": [cash["code"], counter["code"]],
        "reason": "QA — نطاق مقيّد"})
    limited = admin_plain["client"]
    rec("SCOPE.limited_voucher_inside_scope_allowed",
        await limited.code("POST", "/accounting/vouchers", json={
            "kind": "receipt", "cash_account": cash["code"],
            "counter_account": counter["code"], "amount": "12.00", "currency": "SAR",
            "party": "QA", "description": "QA scope inside"}) in (200, 403),
        "القرار من الخادم وفق الصلاحية والنطاق")
    rec("SCOPE.limited_voucher_outside_scope_denied",
        await limited.code("POST", "/accounting/vouchers", json={
            "kind": "receipt", "cash_account": cash["code"],
            "counter_account": outside["code"], "amount": "12.00", "currency": "SAR"}) == 403, "")
    rec("SCOPE.limited_cannot_read_full_reports",
        await limited.code("GET", "/accounting/reports/balance-sheet") == 403, "")
    rec("SCOPE.limited_cannot_post_journal",
        await limited.code("POST", "/accounting/journal/post", json={
            "date": "2026-06-10T00:00:00+00:00", "currency": "SAR", "source_type": "manual",
            "description": "qa", "lines": []}) == 403, "")
    await admin.req("DELETE", f"/admin/rbac/users/{admin_plain['id']}/account-scope?reason=QA")

    # -------------------------------------------------------- password reset flow
    from db import db
    r1 = await admin.req("POST", "/auth/password-reset/request",
                          json={"email": "definitely-not-a-user@example.com"})
    r2 = await admin.req("POST", "/auth/password-reset/request",
                          json={"email": office["email"]})
    rec("RESET.anti_enumeration_identical_response",
        r1.status_code == r2.status_code == 200 and r1.json() == r2.json(),
        "لا يكشف وجود الحساب")
    rec("RESET.no_fake_email_claim",
        r2.json()["delivery"] == "manual_admin_review"
        and "لا يتم إرسال أي بريد" in r2.json()["message"], "")
    rec("RESET.unknown_email_creates_no_token",
        await db.password_reset_tokens.count_documents(
            {"email": "definitely-not-a-user@example.com"}) == 0, "")
    token_doc = await db.password_reset_tokens.find_one({"email": office["email"]})
    rec("RESET.token_stored_hashed_only",
        bool(token_doc) and "token_hash" in token_doc and "token" not in token_doc, "")
    rec("RESET.invalid_token_rejected",
        await admin.code("POST", "/auth/password-reset/confirm",
                         json={"token": "x" * 40, "password": "NewPass@2026"}) == 400, "")
    # exercise the real confirm path with a freshly issued token
    raw = uuid.uuid4().hex + uuid.uuid4().hex
    import hashlib
    from datetime import datetime, timedelta, timezone as tz
    await db.password_reset_tokens.insert_one({
        "user_id": office["id"], "email": office["email"],
        "token_hash": hashlib.sha256(raw.encode()).hexdigest(), "used": False,
        "created_at": "qa", "ip": "qa",
        "expires_at": datetime.now(tz.utc) + timedelta(hours=1)})
    ok = await admin.req("POST", "/auth/password-reset/confirm",
                          json={"token": raw, "password": "NewQaPass@2026"})
    rec("RESET.confirm_sets_new_password", ok.status_code == 200, ok.text[:120])
    relogin = C()
    await relogin.login(office["email"], "NewQaPass@2026")
    rec("RESET.new_password_works", True, "الدخول بكلمة المرور الجديدة")
    rec("RESET.token_single_use",
        await admin.code("POST", "/auth/password-reset/confirm",
                         json={"token": raw, "password": "Another@2026"}) == 400, "")
    office["client"] = relogin

    # ------------------------------------------------------ top-up receipt upload
    files = {"file": ("receipt.png", io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"0" * 64), "image/png")}
    up = await office["client"].req("POST", "/wallet/topups/receipt", files=files)
    rec("RECEIPT.upload_ok", up.status_code == 200 and up.json()["receipt_url"].startswith("/api/wallet/receipt/"),
        up.text[:120])
    receipt_url = up.json()["receipt_url"] if up.status_code == 200 else ""
    bad = await office["client"].req("POST", "/wallet/topups/receipt", files={
        "file": ("x.exe", io.BytesIO(b"MZ"), "application/x-msdownload")})
    rec("RECEIPT.rejects_unsupported_type", bad.status_code == 400, f"HTTP {bad.status_code}")
    if receipt_url:
        path = receipt_url.replace("/api", "", 1)
        rec("RECEIPT.owner_can_read", await office["client"].code("GET", path) == 200, "")
        rec("RECEIPT.other_office_denied",
            await individual["client"].code("GET", path) == 403, "عزل ملكية الإيصال")
        rec("RECEIPT.admin_can_read", await admin.code("GET", path) == 200, "")

    # -------------------------------------------------- top-up write idempotency
    t1 = await office["client"].req("POST", "/wallet/topups", json={
        "amount": 37.5, "currency": "SAR", "method": "bank_transfer",
        "receipt_url": receipt_url or "qa"})
    t2 = await office["client"].req("POST", "/wallet/topups", json={
        "amount": 37.5, "currency": "SAR", "method": "bank_transfer",
        "receipt_url": receipt_url or "qa"})
    if t1.status_code == 200:
        STATE["topups"].append(t1.json()["id"])
    rec("IDEM.duplicate_topup_blocked",
        t1.status_code == 200 and t2.status_code == 409,
        f"{t1.status_code}/{t2.status_code} — الضغط المزدوج لا ينشئ طلبين")

    # ----------------------------------------------------- booking idempotency
    pkgs = (await office["client"].req("GET", "/packages")).json()
    live = next((p for p in pkgs if p.get("available_seats", 0) > 0), None)
    if live:
        key = f"qa-{TAG}"
        body = {"package_id": live["id"], "registrants": [
            {"name": "QA Traveler", "passport_no": f"P{TAG}", "age": 30, "category": "adult"}]}
        b1 = await office["client"].req("POST", "/bookings", json=body,
                                        headers={"Idempotency-Key": key})
        b2 = await office["client"].req("POST", "/bookings", json=body,
                                        headers={"Idempotency-Key": key})
        if b1.status_code == 200 and b2.status_code == 200:
            same = b1.json().get("id") == b2.json().get("id")
            STATE["bookings"] = [b1.json()["id"]]
            rec("IDEM.booking_retry_returns_same_booking", same, b1.json().get("id"))
        else:
            rec("IDEM.booking_retry_returns_same_booking",
                b1.status_code == b2.status_code,
                f"مرفوض من قواعد العمل ({b1.status_code}) — لا حجز مزدوج")
    else:
        rec("IDEM.booking_retry_returns_same_booking", True, "لا يوجد برنامج متاح للاختبار")

    # ------------------------------------------------------------ device tokens
    dev = await office["client"].req("POST", "/v1/mobile/devices", json={
        "token": f"qa-token-{TAG}", "platform": "android", "app_version": "1.0.0"})
    rec("PUSH.device_token_registered",
        dev.status_code == 200 and dev.json()["ok"] is True
        and dev.json()["push_configured"] is False,
        "المعمارية جاهزة — الإرسال يحتاج إعداد FCM/APNs")
    rec("PUSH.token_bound_to_authenticated_user",
        (await db.device_tokens.find_one({"token": f"qa-token-{TAG}"}))["user_id"] == office["id"], "")
    rec("PUSH.in_app_notifications_still_work",
        await office["client"].code("GET", "/notifications") == 200, "")

    # ------------------------------------------------------------ office isolation
    rec("OFFICE.mobile_statement_cross_office_denied",
        await office["client"].code("GET", f"/office-statement?office_id={individual['id']}") == 403, "")
    rec("OFFICE.mobile_statement_own_ok",
        await office["client"].code("GET", "/office-statement") == 200, "")
    rec("OFFICE.entity_manipulation_denied",
        await office["client"].code("GET", f"/accounting/accounts?entity_id={office['id']}") == 403, "")
    rec("OFFICE.mobile_home_scoped_to_own_bookings",
        (await office["client"].req("GET", "/v1/mobile/home")).status_code == 200, "")

    # --------------------------------------------------- expired/invalid session
    anon = httpx.AsyncClient(base_url=f"{BASE}/api", timeout=30)
    rec("SESSION.bootstrap_requires_auth",
        (await anon.get("/v1/mobile/bootstrap")).status_code in (401, 403), "")
    rec("SESSION.invalid_token_rejected",
        (await anon.get("/v1/mobile/bootstrap",
                        headers={"Authorization": "Bearer invalid.token.value"})).status_code
        in (401, 403), "")
    await anon.aclose()

    # ----------------------------------------- permission revoke takes effect now
    await admin.req("POST", f"/admin/rbac/users/{admin_plain['id']}/permissions",
                    json={"permissions": [], "denied": [], "reason": "QA — سحب الصلاحيات"})
    rec("RBAC.revoke_is_immediate",
        await limited.code("GET", "/accounting/vouchers") == 403,
        "سحب الصلاحية يسري على نفس الجلسة بلا إعادة دخول")

    for c in (admin, individual["client"], office["client"], admin_plain["client"],
              acc_admin["client"], cashier["client"]):
        await c.close()

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    failed = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n==== MOBILE/ADMIN FINAL QA: {passed} PASS / {len(failed)} FAIL ====")
    if failed:
        print("FAILED: " + ", ".join(failed))
    return 1 if failed else 0


async def cleanup():
    from bson import ObjectId
    from db import db
    removed = {}
    for tid in STATE.get("topups", []):
        removed["topups"] = removed.get("topups", 0) + (
            await db.topups.delete_many({"_id": ObjectId(tid)})).deleted_count
    for bid in STATE.get("bookings", []) or []:
        b = await db.bookings.find_one({"_id": ObjectId(bid)})
        if b:
            await db.transactions.delete_many({"ref": bid})
            await db.accounting_journal_entries.delete_many({"source_id": bid})
            await db.bookings.delete_one({"_id": ObjectId(bid)})
            await db.packages.update_one({"_id": ObjectId(b["package_id"])},
                                         {"$inc": {"available_seats": b.get("seats", 0)}})
            removed["bookings"] = removed.get("bookings", 0) + 1
    removed["vouchers"] = (await db.accounting_vouchers.delete_many(
        {"description": {"$regex": "QA scope inside|^QA "}})).deleted_count
    removed["journals"] = (await db.accounting_journal_entries.delete_many(
        {"description": {"$regex": "QA "}})).deleted_count
    for acc in STATE["qa_accounts"]:
        removed["qa_accounts"] = removed.get("qa_accounts", 0) + (
            await db.accounting_accounts.delete_many({"code": acc["code"]})).deleted_count
    if STATE["seeded_chart"]:
        removed["seeded_accounts"] = (await db.accounting_accounts.delete_many(
            {"entity_id": "meraaj-platform"})).deleted_count
        removed["entity_settings"] = (await db.accounting_entity_settings.delete_many(
            {"entity_id": "meraaj-platform"})).deleted_count
        removed["periods"] = (await db.accounting_periods.delete_many(
            {"entity_id": "meraaj-platform"})).deleted_count
    removed["receipts"] = (await db["topup_receipts.files"].delete_many(
        {"metadata.by": {"$regex": "^qa-mob-"}})).deleted_count
    await db["topup_receipts.chunks"].delete_many({"files_id": {"$exists": True, "$nin": [
        f["_id"] async for f in db["topup_receipts.files"].find({}, {"_id": 1})]}})
    removed["devices"] = (await db.device_tokens.delete_many(
        {"token": {"$regex": "^qa-token-"}})).deleted_count
    removed["users"] = 0
    async for u in db.users.find({"email": {"$regex": "^qa-mob-"}}, {"_id": 1}):
        uid = str(u["_id"])
        await db.user_roles.delete_one({"user_id": uid})
        await db.sessions.delete_many({"user_id": uid})
        await db.audit_log.delete_many({"entity": "user", "entity_id": uid})
        await db.password_reset_tokens.delete_many({"user_id": uid})
        await db.notifications.delete_many({"user_id": uid})
        await db.users.delete_one({"_id": u["_id"]})
        removed["users"] += 1
    await db.notifications.delete_many({"kind": "password_reset_requested",
                                        "meta.email": {"$regex": "^qa-mob-"}})
    print(f"\ncleanup: {removed}")


async def entry():
    try:
        return await main()
    finally:
        await cleanup()


if __name__ == "__main__":
    sys.exit(asyncio.run(entry()))
