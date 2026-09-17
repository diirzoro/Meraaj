"""P1 Integration QA — account links, source_key, topup/withdrawal/B2B effects,
retry/duplicate/concurrency, failure recording, reconciliation detection, actor identity.

Isolated: a throwaway accounting entity + throwaway office users, all deleted at the end.
Run: python tests/integration_p1_qa.py     (from /app/backend)
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")

from bson import ObjectId  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from accounting.core import (AccountCreate, AccountingError, AccountStore,  # noqa: E402
                             ChartOfAccounts, CurrencyPolicy, DatabasePeriodGuard,
                             JournalPostingService, JournalStore, JournalUsageProbe,
                             JournalValidator, PeriodStore, PostingAccountResolver,
                             ReportingService, EntityCurrencyService,
                             CurrencySettingsStore)
from accounting.integration import (AccountLinkService, AccountingBridge,  # noqa: E402
                                    BusinessAccountingReconciliation, build_source_key)
from accounting.integration.account_links import LinkKey  # noqa: E402
from accounting.templates import STANDARD_COA  # noqa: E402

RESULTS = []
E = f"qa-int-{uuid.uuid4().hex[:8]}"
DATE = datetime.now(timezone.utc)
OFFICE_A = {"_id": ObjectId(), "office_name": "مكتب QA A", "email": "qa-a@x"}
OFFICE_B = {"_id": ObjectId(), "office_name": "مكتب QA B", "email": "qa-b@x"}
ADMIN = {"_id": ObjectId(), "name": "QA Accounting Admin", "email": "qa-admin@x"}


def record(case, ok, detail=""):
    RESULTS.append({"case": case, "ok": ok, "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {case} {detail}")


async def expect_error(case, code, coro):
    try:
        await coro
        record(case, False, f"expected {code}, none raised")
    except AccountingError as exc:
        record(case, exc.code == code, exc.code)


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    accounts = AccountStore(db)
    journals = JournalStore(db)
    periods = PeriodStore(db)
    currency_store = CurrencySettingsStore(db)
    links = AccountLinkService(db, accounts, None)
    for s in (accounts, journals, periods, currency_store, links):
        await s.ensure_indexes()
    chart = ChartOfAccounts(accounts, STANDARD_COA,
                            usage_probe=JournalUsageProbe(journals))
    links._chart = chart
    currencies = EntityCurrencyService(currency_store, journals)
    validator = JournalValidator(PostingAccountResolver(accounts),
                                 CurrencyPolicy(["SAR", "USD"]),
                                 period_guard=DatabasePeriodGuard(periods),
                                 currency_gate=currencies)
    posting = JournalPostingService(validator, journals)
    reports = ReportingService(journals, accounts)
    bridge = AccountingBridge(db, E, posting, links)
    recon = BusinessAccountingReconciliation(db, E, journals, bridge)

    await chart.seed_template(E, by="qa")
    await currencies.configure(E, "SAR", ["SAR", "USD"], by="qa")
    # Real setup: the standard chart ships GROUP role accounts, so the platform creates
    # its own posting leaves under them (exactly what an admin would do).
    async def leaf(role, label, acc_type):
        acc = await chart.find_by_role(E, role)
        if not acc.get("is_group"):
            return acc["code"]
        return (await chart.create_account(E, AccountCreate(
            parent=acc["code"], name=label, name_ar=label, type=acc_type),
            by="qa"))["code"]

    cash_code = await leaf("cash_on_hand", "QA cash box", "asset")
    await leaf("banks_and_wallets", "QA bank", "asset")
    wallet_liability_code = await leaf("payables", "QA office wallets", "liability")

    # ------------------------------------------------------------- account links
    desc = await links.describe(E)
    record("LINK.describe_reports_readiness", isinstance(desc["links"], list)
           and len(desc["links"]) >= 10, f"{len(desc['links'])} links")
    resolved = await links.resolve(E, LinkKey.OFFICE_WALLET_LIABILITY)
    record("LINK.resolve_by_semantic_role",
           resolved["source"].startswith("semantic_role")
           and resolved["account_code"] == wallet_liability_code,
           f"{resolved['account_code']} ({resolved['source']})")
    await expect_error("LINK.unknown_key_rejected", "UNKNOWN_ACCOUNT_LINK",
                       links.resolve(E, "not_a_link"))
    revenue = await chart.find_by_role(E, "service_revenue")
    await expect_error("LINK.type_mismatch_rejected", "ACCOUNT_TYPE_MISMATCH",
                       links.set_link(E, LinkKey.CASH, revenue["code"], by="qa"))
    group = await chart.find_by_role(E, "assets")
    await expect_error("LINK.group_account_rejected", "GROUP_ACCOUNT_NOT_POSTABLE",
                       links.set_link(E, LinkKey.CASH, group["code"], by="qa"))
    await expect_error("LINK.missing_account_rejected", "ACCOUNT_NOT_FOUND",
                       links.set_link(E, LinkKey.CASH, "99999", by="qa"))
    cash = await chart.find_by_role(E, "cash_on_hand")
    explicit = await links.set_link(E, LinkKey.CASH, cash_code, by="qa")
    record("LINK.explicit_link_wins", explicit["account_code"] == cash_code
           and (await links.resolve(E, LinkKey.CASH))["source"] == "explicit_link",
           cash_code)

    # ----------------------------------------------------------------- source_key
    key = build_source_key(E, "topup", "wallet_topup", "abc123")
    record("KEY.shape", key == f"meraaj:{E}:topup:wallet_topup:abc123", key)
    record("KEY.deterministic",
           key == build_source_key(E, "topup", "wallet_topup", "abc123"), "")
    record("KEY.distinct_per_financial_event",
           build_source_key(E, "booking", "booking_debit", "b1") !=
           build_source_key(E, "booking", "booking_settlement", "b1"), "")
    try:
        build_source_key(E, "topup", "wallet_topup", "")
        record("KEY.missing_segment_rejected", False, "no error")
    except ValueError:
        record("KEY.missing_segment_rejected", True, "ValueError")

    # ------------------------------------------------------- declared non-events
    skipped = await bridge.post_event("ads_hold", event_id="ad1", currency="SAR",
                                      amount=10, lines=[], business_actor=None)
    record("EVENT.hold_posts_no_journal", skipped.get("skipped") is True
           and not skipped.get("posted"), skipped.get("reason"))

    # ------------------------------------------------------------------- flows
    from accounting.business_events import (actor_from_user, emit_b2b_transfer,
                                            emit_wallet_topup, emit_wallet_withdrawal)
    import accounting.business_events as be
    be.accounting_bridge = lambda: bridge   # isolate to the QA entity

    topup_id = str(ObjectId())
    topup = {"office_id": str(OFFICE_A["_id"]), "office_name": "مكتب QA A",
             "amount": 1000.0, "currency": "SAR", "method": "bank"}
    r1 = await emit_wallet_topup(topup, topup_id, OFFICE_A, ADMIN)
    record("FLOW.topup_journal_balanced", r1.get("posted")
           and r1["total_debit"] == r1["total_credit"] == "1000.00", r1.get("entry_no"))
    meta = (r1.get("metadata") or {}).get("business", {})
    record("ACTOR.business_vs_accounting_separated",
           meta.get("business_actor_id") == str(OFFICE_A["_id"])
           and meta.get("accounting_actor_id") == str(ADMIN["_id"]),
           f"business={meta.get('business_actor')} acct={meta.get('accounting_actor')}")
    retry = await emit_wallet_topup(topup, topup_id, OFFICE_A, ADMIN)
    record("FLOW.topup_retry_idempotent", retry.get("idempotent_replay")
           and retry["id"] == r1["id"], "")
    conc = await asyncio.gather(*[emit_wallet_topup(topup, topup_id, OFFICE_A, ADMIN)
                                  for _ in range(5)], return_exceptions=True)
    fresh = [x for x in conc if isinstance(x, dict) and x.get("posted")
             and not x.get("idempotent_replay")]
    record("FLOW.topup_concurrent_no_duplicate", len(fresh) == 0, f"new={len(fresh)}")

    wid = str(ObjectId())
    wd = {"office_id": str(OFFICE_A["_id"]), "office_name": "مكتب QA A",
          "amount": 400.0, "currency": "SAR", "method": "bank"}
    r2 = await emit_wallet_withdrawal(wd, wid, OFFICE_A, ADMIN)
    liability = (await links.resolve(E, LinkKey.OFFICE_WALLET_LIABILITY))["account_code"]
    debit_line = next(x for x in r2["lines"] if x["debit"] != "0.00")
    record("FLOW.withdrawal_debits_liability",
           debit_line["account_code"] == liability and debit_line["debit"] == "400.00",
           f"{debit_line['account_code']}")

    tid = str(ObjectId())
    tr = {"from_office_id": str(OFFICE_A["_id"]), "to_office_id": str(OFFICE_B["_id"]),
          "from_office_name": "مكتب QA A", "to_office_name": "مكتب QA B",
          "amount": 250.0, "currency": "SAR"}
    r3 = await emit_b2b_transfer(tr, tid, OFFICE_A, ADMIN)
    b2b_meta = (r3.get("metadata") or {}).get("business", {})
    record("FLOW.b2b_liability_transfer_no_revenue",
           r3.get("posted") and all(x["account_code"] == liability for x in r3["lines"])
           and b2b_meta.get("from_office_id") == str(OFFICE_A["_id"])
           and b2b_meta.get("to_office_id") == str(OFFICE_B["_id"]),
           f"both lines on {liability}")

    sysact = actor_from_user(None)
    record("ACTOR.system_actor_not_fake_human",
           sysact["kind"] == "system" and sysact["id"] == "system", sysact["label"])

    # --------------------------------------------------------- accounting integrity
    tb = await reports.trial_balance(E, currency="SAR")
    record("INTEGRITY.trial_balance_balanced", tb["balanced"],
           f"{tb['total_debit']}/{tb['total_credit']}")
    inc = await reports.income_statement(E, currency="SAR")
    record("INTEGRITY.no_fake_revenue_from_wallet_flows",
           inc["revenue"]["total"] == "0.00" and inc["expenses"]["total"] == "0.00",
           f"rev={inc['revenue']['total']} exp={inc['expenses']['total']}")
    bs = await reports.balance_sheet(E, currency="SAR")
    record("INTEGRITY.balance_sheet_equation", bs["equation_holds"], bs["difference"])
    record("INTEGRITY.liability_reflects_net_wallet",
           bs["liabilities"]["total"] == "600.00",
           f"liabilities={bs['liabilities']['total']} (1000 − 400)")
    dupes = await journals.duplicate_source_keys(E)
    record("INTEGRITY.no_duplicate_source_keys", not dupes, str(dupes))

    # ------------------------------------------------- failure path (missing link)
    await links.links.delete_many({"entity_id": E})
    await db.accounting_accounts.update_many(
        {"entity_id": E, "role": "cash_on_hand"}, {"$set": {"role": None}})
    await db.accounting_accounts.update_many(
        {"entity_id": E, "code": cash_code}, {"$set": {"is_active": False}})
    broken_id = str(ObjectId())
    fail = await emit_wallet_topup({**topup, "amount": 50.0}, broken_id, OFFICE_A, ADMIN)
    record("FAILURE.recorded_not_swallowed", fail.get("failed") is True
           and fail.get("error") in ("ACCOUNT_LINK_MISSING", "ACCOUNT_INACTIVE"),
           fail.get("error"))
    failures = await bridge.list_failures()
    record("FAILURE.listed_for_retry", any(f["business_object_id"] == broken_id
                                            for f in failures),
           f"{len(failures)} recorded")

    # -------------------------------------------------------------- reconciliation
    await db.topups.insert_one({"_id": ObjectId(broken_id), "status": "approved",
                                "amount": 50.0, "currency": "SAR",
                                "office_id": str(OFFICE_A["_id"]),
                                "created_at": DATE.isoformat(), "qa": E})
    rec = await recon.run()
    codes = [f["code"] for f in rec["findings"]]
    record("RECON.detects_business_event_without_journal",
           "BUSINESS_EVENT_WITHOUT_JOURNAL" in codes, str(codes))
    record("RECON.detects_failed_effect", "ACCOUNTING_EFFECT_FAILED" in codes, "")
    record("RECON.read_only_no_repair", rec["read_only"]
           and rec["repairs_performed"] == 0, "")

    # ---------------------------------------------------------------- clean up
    await db.topups.delete_many({"qa": E})
    removed = {}
    for coll in ("accounting_accounts", "accounting_journal_entries",
                 "accounting_entity_settings", "accounting_periods",
                 "accounting_year_close_ops", "accounting_currency_settings",
                 "accounting_fx_rates", "accounting_account_links",
                 "accounting_integration_failures"):
        removed[coll] = (await db[coll].delete_many(
            {"entity_id": {"$regex": "^qa-"}})).deleted_count
    left = {c: await db[c].count_documents({}) for c in removed}
    record("QA.cleanup_collections_empty", all(v == 0 for v in left.values()), str(left))

    failed = [r for r in RESULTS if not r["ok"]]
    print(f"\n==== P1 INTEGRATION QA: {len(RESULTS) - len(failed)} PASS / "
          f"{len(failed)} FAIL ====")
    for f in failed:
        print("FAIL:", f["case"], f["detail"])
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
