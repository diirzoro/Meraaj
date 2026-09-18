"""Accounting Core QA Matrix — Phases 1→10 + Phase 11A (OPEN-017, guards, self-audit).

Runs against an ISOLATED QA entity (`qa-core-<uuid>`) and deletes everything it created at
the end, so the platform entity's collections stay untouched (and empty).

Run:  python -m tests.accounting_core_qa       (from /app/backend)
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from accounting.core import AccountingError, JournalEntryDraft, JournalLineInput  # noqa: E402
from accounting.core import (AccountStore, ChartOfAccounts, CurrencyPolicy,  # noqa: E402
                             JournalStore, JournalUsageProbe, JournalValidator,
                             PostingAccountResolver, JournalPostingService,
                             GeneralLedgerService, JournalReversalService,
                             OpeningBalanceService, ReportingService, PeriodStore,
                             PeriodService, DatabasePeriodGuard, YearCloseService,
                             CurrencySettingsStore, EntityCurrencyService, FXRateStore,
                             FXRateService, FXConversionService, FXResultService,
                             AccountingSelfAudit, OpeningBalanceRequest)
from accounting.core.opening_balances import OpeningLineInput  # noqa: E402
from accounting.core import AccountCreate  # noqa: E402
from accounting.templates import STANDARD_COA  # noqa: E402

RESULTS = []
E1 = f"qa-core-{uuid.uuid4().hex[:8]}"
E2 = f"qa-other-{uuid.uuid4().hex[:8]}"
ACTOR = "qa@meraaj"
FY = datetime.now(timezone.utc).year - 1
D1 = datetime(FY, 3, 10, tzinfo=timezone.utc)


def record(case, ok, detail=""):
    RESULTS.append({"case": case, "status": "PASS" if ok else "FAIL", "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {case} {detail}")


async def expect_error(case, code, coro):
    try:
        await coro
        record(case, False, f"expected {code}, no error raised")
    except AccountingError as exc:
        record(case, exc.code == code, f"got {exc.code}" if exc.code != code else code)


class Ctx:
    pass


async def build(db):
    c = Ctx()
    c.accounts = AccountStore(db)
    c.journals = JournalStore(db)
    c.periods_store = PeriodStore(db)
    c.currency_store = CurrencySettingsStore(db)
    c.rate_store = FXRateStore(db)
    for s in (c.accounts, c.journals, c.periods_store, c.currency_store, c.rate_store):
        await s.ensure_indexes()
    c.chart = ChartOfAccounts(c.accounts, STANDARD_COA,
                              usage_probe=JournalUsageProbe(c.journals))
    c.guard = DatabasePeriodGuard(c.periods_store)
    c.currencies = EntityCurrencyService(c.currency_store, c.journals)
    c.validator = JournalValidator(PostingAccountResolver(c.accounts),
                                   CurrencyPolicy(["SAR", "USD"]),
                                   period_guard=c.guard, currency_gate=c.currencies)
    c.posting = JournalPostingService(c.validator, c.journals)
    c.ledger = GeneralLedgerService(c.journals, c.accounts)
    c.reversal = JournalReversalService(c.journals, c.accounts, c.guard)
    c.opening = OpeningBalanceService(c.posting, c.journals, c.chart)
    c.reports = ReportingService(c.journals, c.accounts)
    c.period_service = PeriodService(c.periods_store, c.journals, c.accounts)
    c.year = YearCloseService(c.posting, c.journals, c.accounts, c.periods_store,
                              c.period_service, reversal_service=c.reversal)
    c.rates = FXRateService(c.rate_store, c.currencies)
    c.convert = FXConversionService(c.rates, c.currencies)
    c.fx = FXResultService(c.posting, c.convert, c.accounts, c.currencies)
    c.audit = AccountingSelfAudit(c.journals, c.accounts, c.periods_store, c.currencies,
                                  c.rate_store, c.reports, c.period_service)
    return c


def draft(lines, date=D1, currency="SAR", source_type="manual", description="قيد اختبار"):
    return JournalEntryDraft(date=date, currency=currency, source_type=source_type,
                             description=description,
                             lines=[JournalLineInput(**l) for l in lines])


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    c = await build(db)

    # ---------------------------------------------------------------- PHASE 1-2
    seed = await c.chart.seed_template(E1, by=ACTOR)
    record("P1.seed_chart", seed.get("accounts", 0) > 0, f"accounts={seed.get('accounts')}")
    await c.chart.seed_template(E2, by=ACTOR)
    tree = await c.chart.build_tree(E1)
    record("P2.tree_roots", len(tree) == 5, f"roots={len(tree)}")
    nxt = await c.chart.next_code(E1, "1101")
    record("P2.code_generation", nxt["next_code"].startswith("1101"), nxt["next_code"])
    codes = await asyncio.gather(*[c.chart.create_account(
        E1, AccountCreate(
            parent="1102", name=f"QA conc {i}", name_ar=f"تزامن {i}", type="asset"), by=ACTOR)
        for i in range(5)])
    record("P2.code_concurrency_unique",
           len({x["code"] for x in codes}) == 5,
           str(sorted(x["code"] for x in codes)))
    audit = await c.chart.audit_chart(E1)
    record("P2.chart_audit_clean",
           not audit.get("duplicates") and not audit.get("missing"),
           str(audit.get("classification")))

    cash = await c.chart.find_by_role(E1, "cash_on_hand")
    bank = await c.chart.find_by_role(E1, "banks_and_wallets")
    revenue = await c.chart.find_by_role(E1, "service_revenue")
    expense = await c.chart.find_by_role(E1, "operating_expenses")
    retained = await c.chart.find_by_role(E1, "retained_earnings")
    # Leaf posting accounts under the group roles.
    async def leaf(entity, role, label, acc_type):
        """Use the role account when it is already a posting (leaf) account; otherwise
        create one CUSTOM child under it."""
        acc = await c.chart.find_by_role(entity, role)
        if not acc.get("is_group"):
            return acc["code"]
        created = await c.chart.create_account(entity, AccountCreate(
            parent=acc["code"], name=label, name_ar=label, type=acc_type), by=ACTOR)
        return created["code"]

    cash_leaf = await leaf(E1, "cash_on_hand", "QA cash", "asset")
    bank_leaf = await leaf(E1, "banks_and_wallets", "QA bank", "asset")
    rev_leaf = await leaf(E1, "service_revenue", "QA revenue", "revenue")
    exp_leaf = await leaf(E1, "operating_expenses", "QA expense", "expense")

    # ------------------------------------------------------------------ PHASE 3
    await expect_error("P3.unbalanced_rejected", "JOURNAL_UNBALANCED",
                       c.posting.post(E1, draft([
                           {"account_code": cash_leaf, "debit": "100"},
                           {"account_code": rev_leaf, "credit": "90"}]), by=ACTOR))
    await expect_error("P3.group_posting_rejected", "GROUP_ACCOUNT_NOT_POSTABLE",
                       c.posting.post(E1, draft([
                           {"account_code": cash["code"], "debit": "10"},
                           {"account_code": rev_leaf, "credit": "10"}]), by=ACTOR))
    await expect_error("P3.negative_rejected", "INVALID_DEBIT_CREDIT",
                       c.posting.post(E1, draft([
                           {"account_code": cash_leaf, "debit": "-10"},
                           {"account_code": rev_leaf, "credit": "-10"}]), by=ACTOR))
    await expect_error("P3.future_date_rejected", "FUTURE_DATE_NOT_ALLOWED",
                       c.posting.post(E1, draft(
                           [{"account_code": cash_leaf, "debit": "10"},
                            {"account_code": rev_leaf, "credit": "10"}],
                           date=datetime.now(timezone.utc) + timedelta(days=2)),
                           by=ACTOR))
    await expect_error("P3.precision_rejected", "INVALID_AMOUNT_PRECISION",
                       c.posting.post(E1, draft([
                           {"account_code": cash_leaf, "debit": "10.005"},
                           {"account_code": rev_leaf, "credit": "10.005"}]), by=ACTOR))
    await expect_error("P3.cross_entity_account", "CROSS_ENTITY_ACCOUNT",
                       c.posting.post(E2, draft([
                           {"account_code": cash_leaf, "debit": "10"},
                           {"account_code": rev_leaf, "credit": "10"}]), by=ACTOR))
    await expect_error("P3.multi_currency_rejected", "MULTI_CURRENCY_UNSUPPORTED",
                       c.posting.post(E1, draft([
                           {"account_code": cash_leaf, "debit": "10",
                            "currency": "SAR"},
                           {"account_code": rev_leaf, "credit": "10",
                            "currency": "USD"}]), by=ACTOR))

    # ------------------------------------------------------------------ PHASE 4
    p1 = await c.posting.post(E1, draft([
        {"account_code": cash_leaf, "debit": "1000"},
        {"account_code": rev_leaf, "credit": "1000"}],
        source_type="sale"), source_key="qa:sale:1", by=ACTOR)
    record("P4.posted", p1["posted"] and p1["entry_no"].startswith("JE-"), p1["entry_no"])
    replay = await c.posting.post(E1, draft([
        {"account_code": cash_leaf, "debit": "1000"},
        {"account_code": rev_leaf, "credit": "1000"}],
        source_type="sale"), source_key="qa:sale:1", by=ACTOR)
    record("P4.idempotent_replay", replay["idempotent_replay"] and
           replay["id"] == p1["id"], replay["entry_no"])
    await expect_error("P4.idempotency_conflict", "IDEMPOTENCY_CONFLICT",
                       c.posting.post(E1, draft([
                           {"account_code": cash_leaf, "debit": "999"},
                           {"account_code": rev_leaf, "credit": "999"}],
                           source_type="sale"), source_key="qa:sale:1", by=ACTOR))
    await expect_error("P4.source_key_required", "SOURCE_KEY_REQUIRED",
                       c.posting.post(E1, draft([
                           {"account_code": cash_leaf, "debit": "5"},
                           {"account_code": rev_leaf, "credit": "5"}],
                           source_type="sale"), by=ACTOR))
    concurrent = await asyncio.gather(*[c.posting.post(E1, draft([
        {"account_code": cash_leaf, "debit": "50"},
        {"account_code": rev_leaf, "credit": "50"}], source_type="sale"),
        source_key="qa:sale:concurrent", by=ACTOR) for _ in range(5)],
        return_exceptions=True)
    created = [r for r in concurrent if isinstance(r, dict) and r.get("posted")]
    record("P4.posting_concurrency_single_journal", len(created) == 1,
           f"created={len(created)} of 5")
    # Used-account protection (Phase 2 guard now enforced by the real probe).
    used_account = await c.chart.find_by_code(E1, cash_leaf)
    await expect_error("P4.used_account_delete_blocked", "coa.has_postings",
                       c.chart.delete_account(E1, used_account["id"], by=ACTOR))

    # ---------------------------------------------------------------- PHASE 5
    await c.posting.post(E1, draft([
        {"account_code": exp_leaf, "debit": "400"},
        {"account_code": cash_leaf, "credit": "400"}], source_type="expense"),
        source_key="qa:expense:1", by=ACTOR)
    led = await c.ledger.account_ledger(E1, cash_leaf)
    record("P5.ledger_totals", led["total_debit"] == "1050.00" and
           led["total_credit"] == "400.00", f"{led['total_debit']}/{led['total_credit']}")
    record("P5.ledger_closing", led["closing_balance"] == "650.00",
           led["closing_balance"])
    record("P5.ledger_running_balance",
           led["items"][-1]["running_balance"] == "650.00",
           led["items"][-1]["running_balance"])
    record("P5.ledger_derived", led["derived"] and not led["stored_balances"], "")

    # ---------------------------------------------------------------- PHASE 6
    rev = await c.reversal.reverse(E1, p1["id"], reason="اختبار العكس", by=ACTOR)
    record("P6.reversal_created", rev["reversed"] and
           rev["original_status"] == "reversed", rev["reversal"]["entry_no"])
    rev2 = await c.reversal.reverse(E1, p1["id"], reason="اختبار العكس", by=ACTOR)
    record("P6.reversal_idempotent", rev2["idempotent_replay"], "")
    await expect_error("P6.double_reversal_blocked", "ALREADY_REVERSED",
                       c.reversal.reverse(E1, p1["id"], reason="ثانية",
                                          by=ACTOR, source_key="qa:rev:other"))
    await expect_error("P6.reversal_of_reversal_blocked",
                       "REVERSAL_OF_REVERSAL_NOT_ALLOWED",
                       c.reversal.reverse(E1, rev["reversal"]["id"], reason="x",
                                          by=ACTOR))
    led_after = await c.ledger.account_ledger(E1, cash_leaf)
    record("P6.reversed_original_still_in_ledger",
           led_after["movement_count"] == led["movement_count"] + 1,
           f"{led['movement_count']}→{led_after['movement_count']}")

    # ---------------------------------------------------------------- PHASE 7
    op = await c.opening.open(E2, OpeningBalanceRequest(
        date=D1, currency="SAR", source_key="qa:open:e2",
        lines=[OpeningLineInput(account_code=(await c.chart.create_account(
            E2, AccountCreate(parent=(await c.chart.find_by_role(
                E2, "cash_on_hand"))["code"], name="QA cash", name_ar="صندوق", type="asset"), by=ACTOR))["code"], debit=Decimal("500"))]),
        by=ACTOR)
    record("P7.opening_posted", op["posted"] and op["opening"], op["entry_no"])
    await expect_error("P7.opening_duplicate_blocked", "OPENING_ALREADY_EXISTS",
                       c.opening.open(E2, OpeningBalanceRequest(
                           date=D1, currency="SAR", source_key="qa:open:e2b",
                           lines=[OpeningLineInput(
                               account_code=op["lines"][0]["account_code"],
                               debit=Decimal("10"))]), by=ACTOR))

    # ---------------------------------------------------------------- PHASE 8
    tb = await c.reports.trial_balance(E1, currency="SAR")
    record("P8.trial_balance_balanced", tb["balanced"],
           f"{tb['total_debit']}/{tb['total_credit']}")
    inc = await c.reports.income_statement(E1, currency="SAR")
    record("P8.income_statement", inc["revenue"]["total"] == "50.00" and
           inc["expenses"]["total"] == "400.00",
           f"rev={inc['revenue']['total']} exp={inc['expenses']['total']} "
           f"(1000 revenue reversed, 50 remains)")
    bs = await c.reports.balance_sheet(E1, currency="SAR")
    record("P8.balance_sheet_equation", bs["equation_holds"], bs["difference"])

    # ------------------------------------------------------- PHASE 9 (periods)
    fiscal = await c.period_service.generate_year(E1, FY, by=ACTOR)
    record("P9.periods_generated", fiscal["created"] == 12, str(fiscal["created"]))
    await expect_error("P9.periods_duplicate_blocked", "PERIODS_ALREADY_EXIST",
                       c.period_service.generate_year(E1, FY, by=ACTOR))
    march = next(p for p in (await c.period_service.list_periods(E1, FY))["items"]
                 if p["code"].endswith("P03"))
    pf = await c.period_service.close_preflight(E1, march["id"])
    record("P9.preflight_can_close", pf["can_close"], str(pf["blockers"]))
    closed = await c.period_service.close(E1, march["id"], "إقفال اختبار", by=ACTOR,
                                          force_sequence=True)
    record("P9.period_closed", closed["closed"], closed["period"]["status"])
    await expect_error("P9.posting_in_closed_period_blocked", "PERIOD_CLOSED",
                       c.posting.post(E1, draft([
                           {"account_code": cash_leaf, "debit": "10"},
                           {"account_code": rev_leaf, "credit": "10"}]), by=ACTOR))
    await expect_error("P9.reversal_in_closed_period_blocked", "PERIOD_CLOSED",
                       c.reversal.reverse(E1, created[0]["id"], reason="داخل مغلقة",
                                          by=ACTOR, date=D1))
    await expect_error("P9.opening_in_closed_period_blocked", "PERIOD_CLOSED",
                       c.opening.open(E1, OpeningBalanceRequest(
                           date=D1, currency="SAR", source_key="qa:open:e1",
                           lines=[OpeningLineInput(account_code=bank_leaf,
                                                   debit=Decimal("100"))],
                           allow_after_activity=True), by=ACTOR))
    reopened = await c.period_service.reopen(E1, march["id"], "مراجعة", by=ACTOR)
    record("P9.period_reopened_history_kept", reopened["reopened"] and
           reopened["period"]["closed_at"] is not None and
           len(reopened["period"]["history"]) == 2,
           str([h["action"] for h in reopened["period"]["history"]]))
    after_reopen = await c.posting.post(E1, draft([
        {"account_code": bank_leaf, "debit": "20"},
        {"account_code": rev_leaf, "credit": "20"}]), by=ACTOR)
    record("P9.posting_after_reopen", after_reopen["posted"], after_reopen["entry_no"])

    # ---------------------------------------------------- PHASE 9 (year close)
    yc = await c.year.close_year(E1, FY, "SAR", by=ACTOR, reason="إقفال سنوي اختباري")
    record("P9.year_closed", yc["closed"] and yc["verification"]["ok"],
           f"net={yc['net_result']} entry={yc['closing_entry']['entry_no']}")
    record("P9.year_close_verification_checks",
           all(yc["verification"]["checks"].values()),
           str(yc["verification"]["checks"]))
    record("P9.year_close_locked_periods", yc["periods_locked"] >= 12,
           str(yc["periods_locked"]))
    yc2 = await c.year.close_year(E1, FY, "SAR", by=ACTOR)
    record("P9.year_close_no_duplicate", yc2.get("already_closed") is True,
           str(yc2.get("operation", {}).get("state")))
    inc_after = await c.reports.income_statement(
        E1, currency="SAR", from_date=datetime(FY, 1, 1, tzinfo=timezone.utc),
        to_date=datetime(FY, 12, 31, 23, 59, tzinfo=timezone.utc))
    record("P9.historical_income_statement_preserved",
           inc_after["expenses"]["total"] == "400.00",
           f"exp={inc_after['expenses']['total']} (exclude_closing)")
    inc_incl = await c.reports.income_statement(
        E1, currency="SAR", from_date=datetime(FY, 1, 1, tzinfo=timezone.utc),
        to_date=datetime(FY, 12, 31, 23, 59, 59, 999999, tzinfo=timezone.utc),
        exclude_closing=False)
    record("P9.book_view_after_close_zeroed",
           inc_incl["net_result"] == "0.00",
           f"net={inc_incl['net_result']} (closing entries included)")
    bs_after = await c.reports.balance_sheet(E1, currency="SAR")
    record("P9.balance_sheet_no_double_count", bs_after["equation_holds"],
           f"diff={bs_after['difference']} "
           f"unclosed={bs_after['equity']['unclosed_cumulative_result']} "
           f"(residual = movements dated OUTSIDE the closed year)")
    retained_ledger = await c.ledger.account_ledger(E1, retained["code"],
                                                    currency="SAR")
    record("P9.retained_earnings_holds_result",
           retained_ledger["closing_balance"] == yc["net_result"],
           f"{retained_ledger['closing_balance']} vs {yc['net_result']}")

    # --------------------------------------------- PHASE 11A (OPEN-017 + guard)
    closing_id = yc["closing_entry"]["id"]
    await expect_error("P11A.direct_year_close_reversal_blocked",
                       "YEAR_CLOSE_REVERSAL_NOT_ALLOWED",
                       c.reversal.reverse(E1, closing_id, reason="محاولة مباشرة",
                                          by=ACTOR))
    locked_period = next(p for p in (await c.period_service.list_periods(E1, FY))["items"]
                         if p["code"].endswith("P05"))
    await expect_error("P11A.period_reopen_inside_closed_year_blocked",
                       "YEAR_CLOSED_REOPEN_DEFERRED",
                       c.period_service.reopen(E1, locked_period["id"], "محاولة",
                                               by=ACTOR))
    ro = await c.year.reopen_year(E1, FY, currency="SAR", reason="تصحيح مالي",
                                  by=ACTOR)
    record("P11A.year_reopened", ro["reopened"] and
           all(ro["reversal_checks"].values()),
           f"reversal={ro['reversal_entry']['entry_no']} "
           f"periods={ro['periods_unlocked']}")
    record("P11A.closing_journal_preserved_not_deleted",
           (await c.journals.get(E1, closing_id)) is not None and
           (await c.journals.get(E1, closing_id))["status"] == "reversed", "")
    ro2 = await c.year.reopen_year(E1, FY, currency="SAR", reason="تصحيح مالي",
                                   by=ACTOR)
    record("P11A.year_reopen_idempotent", ro2.get("already_reopened") is True, "")
    record("P11A.post_reopen_result_restored",
           ro["post_reopen_verification"]["result_accounts_live_again"] and
           ro["post_reopen_verification"]["trial_balance_balanced"],
           str(ro["post_reopen_verification"]))
    post_reopen = await c.posting.post(E1, draft([
        {"account_code": exp_leaf, "debit": "30"},
        {"account_code": cash_leaf, "credit": "30"}]), by=ACTOR)
    record("P11A.posting_allowed_after_year_reopen", post_reopen["posted"],
           post_reopen["entry_no"])

    # ------------------------------------------------- PHASE 10 (currency + FX)
    cfg = await c.currencies.configure(E1, "SAR", ["SAR", "USD"], by=ACTOR)
    record("P10.currency_configured", cfg["base_currency"] == "SAR", str(
        [x["code"] for x in cfg["currencies"]]))
    await expect_error("P10.currency_not_allowed", "CURRENCY_NOT_ALLOWED",
                       c.currencies.assert_allowed(E1, "YER"))
    await c.currencies.set_active(E1, "USD", False, by=ACTOR)
    await expect_error("P10.inactive_currency_blocks_posting", "CURRENCY_INACTIVE",
                       c.posting.post(E1, draft([
                           {"account_code": cash_leaf, "debit": "10"},
                           {"account_code": rev_leaf, "credit": "10"}],
                           currency="USD"), by=ACTOR))
    await c.currencies.set_active(E1, "USD", True, by=ACTOR)
    await expect_error("P10.base_currency_change_blocked",
                       "BASE_CURRENCY_CHANGE_REQUIRES_MIGRATION",
                       c.currencies.configure(E1, "USD", ["SAR", "USD"], by=ACTOR))
    rate = await c.rates.add_rate(E1, "USD", "3.75", D1, by=ACTOR)
    record("P10.rate_added", rate["created"], rate["rate"]["rate"])
    replay_rate = await c.rates.add_rate(E1, "USD", "3.75", D1, by=ACTOR)
    record("P10.rate_idempotent", replay_rate["idempotent_replay"], "")
    await expect_error("P10.rate_immutable", "FX_RATE_IMMUTABLE",
                       c.rates.add_rate(E1, "USD", "3.80", D1, by=ACTOR))
    await expect_error("P10.rate_invalid", "INVALID_FX_RATE",
                       c.rates.add_rate(E1, "USD", "-1", D1 + timedelta(days=1),
                                        by=ACTOR))
    conv = await c.convert.convert(E1, "100", "USD", date=D1 + timedelta(days=5))
    record("P10.conversion", conv["converted_amount"] == "375.00" and
           conv["rate_id"] == rate["rate"]["id"], conv["converted_amount"])
    await expect_error("P10.no_silent_rate_before_effective_date", "FX_RATE_NOT_FOUND",
                       c.convert.convert(E1, "100", "USD",
                                         date=D1 - timedelta(days=5)))
    fx_gain = await c.fx.post_realized_difference(
        E1, bank_leaf, "25.50", "qa:fx:gain:1", by=ACTOR,
        date=datetime.now(timezone.utc),
        fx_metadata={"rate_id": rate["rate"]["id"]})
    record("P10.fx_gain_journal_balanced",
           fx_gain["total_debit"] == fx_gain["total_credit"] == "25.50",
           f"{fx_gain['entry_no']} {fx_gain['fx']['result_account']}")
    fx_replay = await c.fx.post_realized_difference(
        E1, bank_leaf, "25.50", "qa:fx:gain:1", by=ACTOR,
        date=datetime.now(timezone.utc))
    record("P10.fx_idempotent", fx_replay["idempotent_replay"], "")
    fx_loss = await c.fx.post_realized_difference(
        E1, bank_leaf, "-12", "qa:fx:loss:1", by=ACTOR,
        date=datetime.now(timezone.utc))
    record("P10.fx_loss_direction",
           fx_loss["lines"][0]["debit"] == "12.00" and
           fx_loss["fx"]["kind"] == "loss", fx_loss["fx"]["result_account"])
    fx_reversal = await c.reversal.reverse(E1, fx_gain["id"], reason="تصحيح فرق عملة",
                                           by=ACTOR)
    record("P10.fx_reversal_keeps_currency",
           fx_reversal["reversal"]["currency"] == fx_gain["currency"], "")
    record("P10.rate_metadata_snapshot",
           (fx_gain.get("metadata") or {}).get("fx", {}).get("rate_id") ==
           rate["rate"]["id"], "")

    # -------------------------------------------------- entity isolation + audit
    tb_e2 = await c.reports.trial_balance(E2, currency="SAR")
    record("ISO.entity_isolation_reports",
           tb_e2["total_debit"] == "500.00" and tb_e2["balanced"],
           f"E2 debit={tb_e2['total_debit']}")
    e1_entries = await c.journals.list_entries(E1, limit=200)
    record("ISO.no_cross_entity_journals",
           all(j["entity_id"] == E1 for j in e1_entries), f"{len(e1_entries)} entries")
    sa = await c.audit.run(E1)
    record("P11A.self_audit_clean", sa["counts"]["CRITICAL"] == 0,
           f"critical={sa['counts']['CRITICAL']} high={sa['counts']['HIGH']} "
           f"medium={sa['counts']['MEDIUM']} warning={sa['counts']['WARNING']}")
    record("P11A.self_audit_read_only", sa["read_only"] and
           sa["repairs_performed"] == 0, "")
    record("P11A.self_audit_equation",
           all(r["balanced"] for r in sa["sections"]["equation"]["per_currency"]),
           str(sa["sections"]["equation"]["per_currency"]))
    if sa["findings"]:
        print("   self-audit findings:", [(f["code"], f["severity"])
                                          for f in sa["findings"]])

    # ---------------------------------------------------------------- CLEAN UP
    removed = {}
    for coll in ("accounting_accounts", "accounting_journal_entries",
                 "accounting_entity_settings", "accounting_periods",
                 "accounting_year_close_ops", "accounting_currency_settings",
                 "accounting_fx_rates"):
        r = await db[coll].delete_many({"entity_id": {"$in": [E1, E2]}})
        removed[coll] = r.deleted_count
    left = {coll: await db[coll].count_documents({})
            for coll in ("accounting_accounts", "accounting_journal_entries",
                         "accounting_entity_settings", "accounting_periods",
                         "accounting_year_close_ops", "accounting_currency_settings",
                         "accounting_fx_rates")}
    record("QA.cleanup_all_collections_empty", all(v == 0 for v in left.values()),
           str(left))
    print("\nremoved:", removed)

    failed = [r for r in RESULTS if r["status"] == "FAIL"]
    print(f"\n==== QA SUMMARY: {len(RESULTS) - len(failed)} PASS / {len(failed)} FAIL ====")
    for f in failed:
        print("FAIL:", f["case"], f["detail"])
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
