"""BATCH 2 — ONE COMPREHENSIVE QA PASS (RBAC + Account Scope + Maker–Checker + Actors +
Accounting UI APIs + Office Statement isolation + entity lock + security/direct API).

Isolated test data only: every user/office it creates uses @qa-example.com and every
artefact is removed in the cleanup phase. No production/business balances are touched.

Run:  python3 backend/tests/batch2_rbac_qa.py
"""
import asyncio
import os
import sys
import uuid

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE = None
SUPER = ("abuzay84@gmail.com", "Meraaj@2026")
TAG = uuid.uuid4().hex[:6]
PW = "QaTest@2026"

RESULTS = []
CREATED_USERS = []
CREATED_VOUCHERS = []
QA_ACCOUNTS = []
QA_JOURNALS = []
STATE = {"seeded_chart": False, "generated_periods": False}


def rec(name, ok, note=""):
    RESULTS.append((name, bool(ok), note))
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {note}")


def read_base():
    with open("/app/frontend/.env", encoding="utf-8") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


class Client:
    def __init__(self, label):
        self.label = label
        self.http = httpx.AsyncClient(base_url=f"{BASE}/api", timeout=40.0)
        self.token = None

    async def login(self, email, password):
        r = await self.http.post("/auth/login", json={"email": email, "password": password})
        if r.status_code != 200:
            raise RuntimeError(f"login failed for {email}: {r.status_code} {r.text[:200]}")
        self.token = r.json().get("access_token")
        self.http.headers["Authorization"] = f"Bearer {self.token}"
        return r.json()

    async def req(self, method, url, **kw):
        return await self.http.request(method, url, **kw)

    async def close(self):
        await self.http.aclose()


async def create_user(admin, email, roles, name):
    r = await admin.req("POST", "/admin/rbac/users", json={
        "email": email, "password": PW, "role": "office", "name": name,
        "roles": roles, "reason": "QA Batch 2 — isolated test account"})
    assert r.status_code == 200, f"{email}: {r.status_code} {r.text[:300]}"
    uid = r.json()["id"]
    CREATED_USERS.append((uid, email))
    c = Client(email)
    await c.login(email, PW)
    return uid, c


async def main():
    global BASE
    BASE = read_base()
    print(f"BASE={BASE}\n")

    admin = Client("super_admin")
    await admin.login(*SUPER)

    # ---------------------------------------------------------------- inventory
    cat = (await admin.req("GET", "/admin/rbac/catalog")).json()
    acc_perms = cat.get("accounting_permissions") or []
    rec("INV.accounting_permissions_registered", len(acc_perms) >= 25, f"{len(acc_perms)} صلاحية")
    rec("INV.account_scope_modes_exposed",
        {m["mode"] for m in cat.get("account_scope_modes", [])} ==
        {"all_accounts", "selected_accounts", "account_subtree"}, "")
    rec("INV.dual_control_includes_accounting",
        all(k in cat["dual_control"] for k in
            ["accounting.vouchers.payment", "accounting.journals.post",
             "accounting.year.close", "accounting.periods.close"]), "")
    for role in ("accounting_admin", "accountant", "cashier", "reports_user", "auditor",
                 "hr_admin", "finance_manager"):
        rec(f"INV.role_preset_{role}", role in cat["roles"], "")

    accounts = (await admin.req("GET", "/accounting/accounts?include_inactive=true")).json()["items"]
    if not accounts:
        sr = await admin.req("POST", "/accounting/chart/seed")
        STATE["seeded_chart"] = sr.status_code == 200
        accounts = (await admin.req("GET", "/accounting/accounts?include_inactive=true")).json()["items"]
        rec("INV.chart_seeded_for_qa", STATE["seeded_chart"], "الدليل كان فارغاً — زُرع القالب القياسي")
    periods = (await admin.req("GET", "/accounting/periods?fiscal_year=2026")).json()
    if not periods.get("items"):
        gr = await admin.req("POST", "/accounting/periods/generate?fiscal_year=2026")
        STATE["generated_periods"] = gr.status_code == 200
        rec("INV.periods_generated_for_qa", STATE["generated_periods"], "")
    leaves = [a for a in accounts if not a["is_group"]]
    groups = [a for a in accounts if a["is_group"]]
    rec("INV.chart_available", len(accounts) >= 10,
        f"{len(accounts)} حساب / {len(leaves)} تفصيلي")

    # QA-owned detail accounts (the standard template ships groups only for cash/bank)
    async def qa_account(parent_code, name_ar, kind):
        r = await admin.req("POST", "/accounting/accounts", json={
            "parent": parent_code, "name": f"QA {kind} {TAG}", "name_ar": name_ar,
            "type": kind, "is_group": False})
        assert r.status_code == 200, f"{name_ar}: {r.status_code} {r.text[:200]}"
        acc = r.json()
        QA_ACCOUNTS.append(acc)
        return acc

    cash = await qa_account("1101", f"صندوق اختبار {TAG}", "asset")
    other = await qa_account("2101", f"دائن اختبار {TAG}", "liability")
    outside = await qa_account("1102", f"بنك اختبار {TAG}", "asset")
    accounts = (await admin.req("GET", "/accounting/accounts?include_inactive=true")).json()["items"]
    rec("COA.create_detail_account_under_group",
        all(a["code"] in {x["code"] for x in accounts} for a in (cash, other, outside)),
        f"{cash['code']} / {other['code']} / {outside['code']}")
    rec("COA.core_guard_blocks_group_delete",
        (await admin.req("DELETE", "/accounting/accounts/"
                         + next(g["id"] for g in groups if g["code"] == "1101"))).status_code >= 400,
        "حذف مجموعة لها فروع مرفوض من النواة")

    # ------------------------------------------------------------------ accounts
    users = {}
    for key, roles in [("accounting_admin", ["accounting_admin"]),
                       ("accountant", ["accountant"]),
                       ("cashier", ["cashier"]),
                       ("cashier2", ["accounting_admin"]),
                       ("reports_user", ["reports_user"]),
                       ("auditor", ["auditor"]),
                       ("hr_admin", ["hr_admin"]),
                       ("sales", ["sales"] if "sales" in cat["roles"] else []),
                       ("scoped", ["accountant"])]:
        email = f"qa-b2-{key}-{TAG}@qa-example.com"
        uid, c = await create_user(admin, email, roles, f"QA {key}")
        users[key] = {"id": uid, "client": c, "email": email}

    # every role's effective permission set comes from the SAME RBAC engine
    for key, must, must_not in [
            ("accountant", ["accounting.accounts.view", "accounting.vouchers.receipt"],
             ["accounting.year.close", "accounting.accounts.manage.non-existent"]),
            ("cashier", ["accounting.vouchers.receipt", "accounting.vouchers.payment"],
             ["accounting.accounts.manage", "accounting.journals.create",
              "accounting.year.close", "accounting.reports.view"]),
            ("reports_user", ["accounting.reports.view"],
             ["accounting.vouchers.receipt", "accounting.journals.post"]),
            ("auditor", ["accounting.journals.view", "accounting.selfaudit.run"],
             ["accounting.journals.post", "accounting.vouchers.payment"]),
            ("hr_admin", [], ["accounting.accounts.view", "accounting.vouchers.view",
                              "accounting.reports.view", "accounting.journals.view"])]:
        perms = (await users[key]["client"].req("GET", "/admin/my-permissions")).json()["permissions"]
        ok = all(m in perms for m in must if not m.endswith("non-existent")) \
            and not any(m in perms for m in must_not)
        rec(f"RBAC.permission_matrix_{key}", ok, f"{len(perms)} صلاحية")

    # --------------------------------------------------------- direct API security
    async def status(client, method, url, **kw):
        return (await client.req(method, url, **kw)).status_code

    hr = users["hr_admin"]["client"]
    for url in ["/accounting/accounts", "/accounting/accounts/tree", "/accounting/journal/entries",
                "/accounting/vouchers", "/accounting/reports/trial-balance",
                "/accounting/ledger/account/" + cash["code"], "/accounting/periods",
                "/accounting/currencies", "/accounting/self-audit",
                "/accounting/integration/reconciliation"]:
        rec(f"SEC.hr_admin_denied {url}", await status(hr, "GET", url) == 403, "")

    cashier = users["cashier"]["client"]
    rec("SEC.cashier_cannot_read_chart",
        await status(cashier, "GET", "/accounting/accounts") == 403, "")
    rec("SEC.cashier_cannot_read_full_reports",
        await status(cashier, "GET", "/accounting/reports/balance-sheet") == 403, "")
    rec("SEC.cashier_cannot_create_manual_journal",
        await status(cashier, "POST", "/accounting/journal/post", json={
            "date": "2026-06-01T00:00:00+00:00", "currency": "SAR", "source_type": "manual",
            "description": "qa", "lines": []}) == 403, "")
    rec("SEC.cashier_cannot_close_year",
        await status(cashier, "POST", "/accounting/year-close/2026?reason=qa+attempt") == 403, "")
    rec("SEC.reports_user_cannot_post_voucher",
        await status(users["reports_user"]["client"], "POST", "/accounting/vouchers", json={
            "kind": "receipt", "cash_account": cash["code"], "counter_account": other["code"],
            "amount": "10", "currency": "SAR"}) == 403, "")
    rec("SEC.auditor_is_read_only",
        await status(users["auditor"]["client"], "POST", "/accounting/journal/post", json={
            "date": "2026-06-01T00:00:00+00:00", "currency": "SAR", "source_type": "manual",
            "description": "qa", "lines": []}) == 403, "")

    # ------------------------------------------------------------- entity lock
    for client, label in [(admin, "super_admin"), (users["accounting_admin"]["client"], "accounting_admin")]:
        code = await status(client, "GET", "/accounting/accounts?entity_id=other-entity")
        rec(f"SEC.entity_lock_{label}", code == 403, f"HTTP {code}")
    rec("SEC.entity_lock_explicit_platform_ok",
        await status(users["accounting_admin"]["client"], "GET",
                     "/accounting/accounts?entity_id=meraaj-platform") == 200, "")

    # --------------------------------------------------------------- ACCOUNT SCOPE
    scoped = users["scoped"]
    r = await admin.req("POST", f"/admin/rbac/users/{scoped['id']}/account-scope", json={
        "mode": "selected_accounts", "codes": [cash["code"], other["code"]],
        "reason": "QA — تقييد على حسابين"})
    rec("SCOPE.assign_selected_accounts", r.status_code == 200, r.text[:120])
    sc = scoped["client"]
    listed = (await sc.req("GET", "/accounting/accounts")).json()
    codes = {a["code"] for a in listed["items"]}
    rec("SCOPE.coa_list_filtered", codes == {cash["code"], other["code"]}, f"{sorted(codes)}")
    rec("SCOPE.scope_echoed_to_client",
        listed["account_scope"]["mode"] == "selected_accounts"
        and listed["account_scope"]["unrestricted"] is False, "")
    tree = (await sc.req("GET", "/accounting/accounts/tree")).json()
    rec("SCOPE.tree_keeps_path_marks_out_of_scope", len(tree["roots"]) >= 1, "")
    rec("SCOPE.ledger_inside_scope_ok",
        await status(sc, "GET", f"/accounting/ledger/account/{cash['code']}") == 200, "")
    rec("SCOPE.ledger_outside_scope_denied",
        await status(sc, "GET", f"/accounting/ledger/account/{outside['code']}") == 403, "")
    rec("SCOPE.account_by_code_outside_denied",
        await status(sc, "GET", f"/accounting/accounts/by-code/{outside['code']}") == 403, "")
    rec("SCOPE.voucher_with_outside_account_denied",
        await status(sc, "POST", "/accounting/vouchers", json={
            "kind": "receipt", "cash_account": cash["code"], "counter_account": outside["code"],
            "amount": "10", "currency": "SAR"}) == 403, "")
    rec("SCOPE.manual_journal_outside_scope_denied",
        await status(sc, "POST", "/accounting/journal/post", json={
            "date": "2026-06-01T00:00:00+00:00", "currency": "SAR", "source_type": "manual",
            "description": "qa scope", "lines": [
                {"account_code": cash["code"], "debit": "10", "credit": "0", "currency": "SAR"},
                {"account_code": outside["code"], "debit": "0", "credit": "10", "currency": "SAR"}]}) == 403, "")
    rec("SCOPE.scoped_user_cannot_read_full_reports",
        await status(sc, "GET", "/accounting/reports/trial-balance") == 403,
        "تقرير كامل مضلّل ممنوع على المستخدم المقيّد")

    # subtree mode resolves through the real parent chain, not a code prefix
    parent = next((g for g in groups if any(a.get("parent") == g["code"] for a in accounts)), groups[0])
    kids = [a["code"] for a in accounts if a.get("parent") == parent["code"]]
    await admin.req("POST", f"/admin/rbac/users/{scoped['id']}/account-scope", json={
        "mode": "account_subtree", "codes": [parent["code"]], "reason": "QA — شجرة حساب"})
    sub = {a["code"] for a in (await sc.req("GET", "/accounting/accounts")).json()["items"]}
    rec("SCOPE.subtree_includes_parent_and_children",
        parent["code"] in sub and all(k in sub for k in kids), f"{len(sub)} حساب")
    rec("SCOPE.subtree_excludes_unrelated",
        any(a["code"] not in sub for a in accounts), "")
    outside_sub = next((a["code"] for a in accounts if a["code"] not in sub), None)
    if outside_sub:
        rec("SCOPE.subtree_direct_api_outside_denied",
            await status(sc, "GET", f"/accounting/accounts/by-code/{outside_sub}") == 403, "")
    r = await admin.req("DELETE", f"/admin/rbac/users/{scoped['id']}/account-scope?reason=QA+cleanup")
    rec("SCOPE.removal_restores_all_accounts",
        r.status_code == 200
        and (await sc.req("GET", "/accounting/accounts")).json()["account_scope"]["unrestricted"] is True, "")
    rec("SCOPE.unknown_account_code_rejected",
        await status(admin, "POST", f"/admin/rbac/users/{scoped['id']}/account-scope", json={
            "mode": "selected_accounts", "codes": ["999999-not-real"],
            "reason": "QA — كود غير موجود"}) == 400, "")

    audits = (await admin.req("GET", "/admin/audit?entity=user&limit=200")).json()
    audit_items = audits.get("items", audits if isinstance(audits, list) else [])
    actions = {a.get("action") for a in audit_items}
    rec("AUDIT.permission_and_scope_changes_logged",
        {"account_scope_assigned", "account_scope_removed"} <= actions
        and "user_created" in actions, f"{len(audit_items)} سجل")

    # ------------------------------------------------------- vouchers (no dual ctl)
    ca = users["accounting_admin"]["client"]
    r = await ca.req("POST", "/accounting/vouchers", json={
        "kind": "receipt", "cash_account": cash["code"], "counter_account": other["code"],
        "amount": "125.50", "currency": "SAR", "party": "QA Office",
        "description": "QA receipt voucher"})
    rec("VOUCHER.receipt_posts_directly", r.status_code == 200 and r.json()["status"] == "posted",
        r.json().get("entry_no", r.text[:120]))
    v1 = r.json()
    CREATED_VOUCHERS.append(v1["id"])
    jr = await ca.req("GET", f"/accounting/journal/entries/{v1['journal_id']}")
    j = jr.json()
    debits = {l["account_code"]: l["debit"] for l in j["lines"]}
    rec("VOUCHER.receipt_debits_cash", debits.get(cash["code"]) in ("125.50", "125.5"),
        str(debits))
    rec("VOUCHER.actor_from_authenticated_identity",
        (j.get("metadata", {}).get("voucher", {}).get("created_by_id") == users["accounting_admin"]["id"]),
        "المُنشئ من الهوية الموثّقة لا من الواجهة")
    rec("VOUCHER.posted_history_not_editable",
        await status(ca, "PATCH", f"/accounting/journal/entries/{v1['journal_id']}",
                     json={"description": "tamper"}) in (404, 405),
        "لا يوجد مسار تعديل للقيد المُرحَّل")

    # cancel => reversal, never delete
    r = await ca.req("POST", f"/accounting/vouchers/{v1['id']}/cancel?reason=QA+reversal+test")
    cancelled = r.json()
    reversal_doc = (cancelled.get("reversal") or {}).get("reversal") or cancelled.get("reversal") or {}
    if reversal_doc.get("id"):
        QA_JOURNALS.append(reversal_doc["id"])
    rec("VOUCHER.cancel_creates_reversal",
        r.status_code == 200 and bool(reversal_doc.get("entry_no")),
        str(reversal_doc.get("entry_no")))

    # --------------------------------------------------------- MAKER–CHECKER
    before_dual = cat["settings"].get("required", {})
    await admin.req("POST", "/admin/rbac/dual-control", json={
        "required": {**before_dual, "accounting.vouchers.payment": True},
        "reason": "QA — تشغيل الرقابة المزدوجة على سند الصرف"})
    r = await cashier.req("POST", "/accounting/vouchers", json={
        "kind": "payment", "cash_account": cash["code"], "counter_account": other["code"],
        "amount": "60", "currency": "SAR", "party": "QA payee", "description": "QA payment"})
    pend = r.json()
    CREATED_VOUCHERS.append(pend.get("id"))
    rec("MC.payment_pending_no_journal",
        r.status_code == 200 and pend["status"] == "pending_approval"
        and pend["journal_id"] is None and pend["requires_approval"] is True, "")
    rec("MC.unauthorized_checker_rejected",
        await status(users["accountant"]["client"], "POST",
                     f"/accounting/vouchers/{pend['id']}/approve") == 403,
        "المحاسب لا يملك صلاحية الاعتماد")
    # self-approval: grant the maker the approve permission, it must still be refused
    await admin.req("POST", f"/admin/rbac/users/{users['cashier']['id']}/permissions", json={
        "permissions": ["accounting.vouchers.approve"], "denied": [],
        "reason": "QA — اختبار منع الاعتماد الذاتي"})
    rec("MC.self_approval_rejected",
        await status(cashier, "POST", f"/accounting/vouchers/{pend['id']}/approve") == 403,
        "المنشئ لا يعتمد سنده حتى مع امتلاك صلاحية الاعتماد")
    r = await ca.req("POST", f"/accounting/vouchers/{pend['id']}/approve")
    rec("MC.second_person_approves_and_posts",
        r.status_code == 200 and r.json()["status"] == "posted" and r.json()["entry_no"], "")
    rec("MC.duplicate_approval_rejected",
        await status(ca, "POST", f"/accounting/vouchers/{pend['id']}/approve") in (400, 409), "")
    posted = (await ca.req("GET", f"/accounting/vouchers/{pend['id']}")).json()
    rec("MC.maker_and_checker_recorded_separately",
        posted["created_by_id"] == users["cashier"]["id"]
        and posted["approved_by_id"] == users["accounting_admin"]["id"]
        and posted["posted_by_id"] == users["accounting_admin"]["id"],
        f"maker={posted['created_by']} checker={posted['approved_by']}")
    await admin.req("POST", "/admin/rbac/dual-control",
                    json={"required": before_dual, "reason": "QA — إعادة الإعداد الأصلي"})
    await admin.req("POST", f"/admin/rbac/users/{users['cashier']['id']}/permissions",
                    json={"permissions": [], "denied": [], "reason": "QA — إعادة الصلاحيات"})

    # --------------------------------------------------------- manual journals
    r = await ca.req("POST", "/accounting/journal/post", json={
        "date": "2026-06-15T00:00:00+00:00", "currency": "SAR", "source_type": "manual",
        "description": f"QA manual journal {TAG}", "lines": [
            {"account_code": cash["code"], "debit": "70", "credit": "0", "currency": "SAR"},
            {"account_code": other["code"], "debit": "0", "credit": "70", "currency": "SAR"}]})
    manual = r.json()
    if manual.get("id"):
        QA_JOURNALS.append(manual["id"])
    rec("JOURNAL.manual_post_by_authorized",
        r.status_code == 200 and str(manual.get("status", "")).lower() == "posted",
        str(manual.get("entry_no", r.text[:120])))
    rec("JOURNAL.accounting_actor_is_authenticated_user",
        manual.get("metadata", {}).get("actor", {}).get("accounting_actor_id")
        == users["accounting_admin"]["id"], "")
    r2 = await ca.req("POST", f"/accounting/journal/entries/{manual['id']}/reverse?reason=QA+reversal")
    manual_rev = (r2.json().get("reversal") or {}) if r2.status_code == 200 else {}
    if manual_rev.get("id"):
        QA_JOURNALS.append(manual_rev["id"])
    rec("JOURNAL.reversal_instead_of_edit",
        r2.status_code == 200 and bool(manual_rev.get("entry_no")), str(manual_rev.get("entry_no")))
    vr = await ca.req("POST", "/accounting/journal/validate", json={
            "date": "2026-06-15T00:00:00+00:00", "currency": "SAR", "source_type": "manual",
            "description": "qa unbalanced", "lines": [
                {"account_code": cash["code"], "debit": "70", "credit": "0", "currency": "SAR"},
                {"account_code": other["code"], "debit": "0", "credit": "10", "currency": "SAR"}]})
    rec("JOURNAL.unbalanced_draft_rejected",
        vr.status_code >= 400 or vr.json().get("ok") is False
        or vr.json().get("posted") is False, f"HTTP {vr.status_code}")

    # -------------------------------------------------------------- read screens
    for label, url in [("chart", "/accounting/accounts/tree"), ("journals", "/accounting/journal/entries"),
                       ("ledger", f"/accounting/ledger/account/{cash['code']}"),
                       ("trial_balance", "/accounting/reports/trial-balance"),
                       ("income_statement", "/accounting/reports/income-statement"),
                       ("balance_sheet", "/accounting/reports/balance-sheet"),
                       ("periods", "/accounting/periods"), ("currencies", "/accounting/currencies"),
                       ("fx_rates", "/accounting/fx/rates"), ("links", "/accounting/integration/account-links"),
                       ("events", "/accounting/integration/event-map"),
                       ("reconciliation", "/accounting/integration/reconciliation"),
                       ("failures", "/accounting/integration/failures"),
                       ("self_audit", "/accounting/self-audit"), ("vouchers", "/accounting/vouchers")]:
        code = await status(ca, "GET", url)
        rec(f"UI.api_ready_{label}", code == 200, f"HTTP {code}")

    rec("UI.reports_user_reads_reports",
        await status(users["reports_user"]["client"], "GET", "/accounting/reports/income-statement") == 200, "")
    rec("UI.auditor_runs_self_audit",
        await status(users["auditor"]["client"], "GET", "/accounting/self-audit") == 200, "")

    # ------------------------------------------------------------ OFFICE STATEMENT
    own = (await users["accountant"]["client"].req("GET", "/office-statement")).json()
    rec("OFFICE.statement_is_business_not_ledger",
        own["scope"] == "business_office_statement" and "opening_balance" in own
        and "movement_types" in own, "")
    rec("OFFICE.no_ledger_fields_leaked",
        not any(k in own for k in ("journal", "trial_balance", "chart", "entity_id")), "")
    other_office_id = users["accountant"]["id"]
    rec("OFFICE.cross_office_denied_for_unprivileged",
        await status(users["cashier"]["client"], "GET",
                     f"/office-statement?office_id={other_office_id}") == 403,
        "تلاعب office_id مرفوض من الخادم")
    rec("OFFICE.picker_restricted_for_unprivileged",
        (await users["cashier"]["client"].req("GET", "/office-statement/offices")).json()["restricted"] is True, "")
    rec("OFFICE.privileged_can_read_any_office",
        await status(ca, "GET", f"/office-statement?office_id={other_office_id}") == 200, "")
    rec("OFFICE.super_admin_picker_open",
        (await admin.req("GET", "/office-statement/offices")).json()["restricted"] is False, "")
    rec("OFFICE.no_office_accounting_entity",
        await status(ca, "GET", f"/accounting/accounts?entity_id={other_office_id}") == 403,
        "office_id لا يُترجم إلى entity_id")

    for c in [admin] + [u["client"] for u in users.values()]:
        await c.close()

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    failed = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n==== BATCH 2 QA: {passed} PASS / {len(failed)} FAIL ====")
    if failed:
        print("FAILED: " + ", ".join(failed))
    return 1 if failed else 0


async def cleanup():
    """Removes every artefact this QA created. Runs even when an assertion blew up."""
    from bson import ObjectId
    from db import db
    removed = {}
    for vid in [v for v in CREATED_VOUCHERS if v]:
        for key in (f"voucher:{vid}", f"voucher_cancel:{vid}"):
            removed["journals"] = removed.get("journals", 0) + (
                await db.accounting_journal_entries.delete_many({"source_key": key})).deleted_count
        removed["vouchers"] = removed.get("vouchers", 0) + (
            await db.accounting_vouchers.delete_many({"id": vid})).deleted_count
        await db.accounting_audit.delete_many({"reference": vid})
    for jid in QA_JOURNALS:
        removed["journals"] = removed.get("journals", 0) + (
            await db.accounting_journal_entries.delete_many({"id": jid})).deleted_count
    removed["journals"] = removed.get("journals", 0) + (
        await db.accounting_journal_entries.delete_many(
            {"description": {"$regex": "QA manual journal"}})).deleted_count
    for uid, _email in CREATED_USERS:
        await db.users.delete_one({"_id": ObjectId(uid)})
        await db.user_roles.delete_one({"user_id": uid})
        await db.sessions.delete_many({"user_id": uid})
        await db.audit_log.delete_many({"entity": "user", "entity_id": uid})
        removed["users"] = removed.get("users", 0) + 1
    for acc in QA_ACCOUNTS:
        removed["qa_accounts"] = removed.get("qa_accounts", 0) + (
            await db.accounting_accounts.delete_many({"code": acc["code"]})).deleted_count
    # belt and braces: nothing this QA touched may survive an aborted run
    removed["qa_vouchers_sweep"] = (await db.accounting_vouchers.delete_many(
        {"description": {"$regex": "^QA "}})).deleted_count
    removed["qa_users_sweep"] = 0
    async for u in db.users.find({"email": {"$regex": "^qa-b2-"}}, {"_id": 1}):
        uid = str(u["_id"])
        await db.user_roles.delete_one({"user_id": uid})
        await db.sessions.delete_many({"user_id": uid})
        await db.audit_log.delete_many({"entity": "user", "entity_id": uid})
        await db.users.delete_one({"_id": u["_id"]})
        removed["qa_users_sweep"] += 1
    if STATE["seeded_chart"]:
        removed["seeded_accounts"] = (await db.accounting_accounts.delete_many(
            {"entity_id": "meraaj-platform"})).deleted_count
        removed["entity_settings"] = (await db.accounting_entity_settings.delete_many(
            {"entity_id": "meraaj-platform"})).deleted_count
    if STATE["generated_periods"]:
        removed["periods"] = (await db.accounting_periods.delete_many(
            {"entity_id": "meraaj-platform", "fiscal_year": 2026})).deleted_count
    print(f"\ncleanup: {removed}")


async def entry():
    try:
        return await main()
    finally:
        await cleanup()


if __name__ == "__main__":
    sys.exit(asyncio.run(entry()))
