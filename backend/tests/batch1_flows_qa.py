"""Batch 1 consolidated QA — booking (B2B/B2C/Rahal), settlement, cancellations, ads.

Isolated accounting entity; everything created here is deleted at the end.
Run: python tests/batch1_flows_qa.py   (from /app/backend)
"""
import asyncio
import os
import sys
import uuid
from decimal import Decimal

from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")

from bson import ObjectId  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from accounting.core import (AccountCreate, AccountStore, ChartOfAccounts,  # noqa: E402
                             CurrencyPolicy, CurrencySettingsStore,
                             DatabasePeriodGuard, EntityCurrencyService,
                             JournalPostingService, JournalStore, JournalUsageProbe,
                             JournalValidator, PeriodStore, PostingAccountResolver,
                             ReportingService)
from accounting.integration import (AccountLinkService, AccountingBridge,  # noqa: E402
                                    BusinessAccountingReconciliation)
from accounting.integration.account_links import LinkKey as K  # noqa: E402
from accounting.templates import STANDARD_COA  # noqa: E402

R = []
E = f"qa-b1-{uuid.uuid4().hex[:8]}"
BUYER = {"_id": ObjectId(), "office_name": "مكتب مشتري", "role": "office"}
SELLER = {"_id": ObjectId(), "office_name": "مكتب بائع", "role": "office"}
ADMIN = {"_id": ObjectId(), "name": "QA Admin"}


def rec(case, ok, detail=""):
    R.append((case, ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {case} {detail}")


def sides(res):
    d = sum(Decimal(x["debit"]) for x in res["lines"])
    c = sum(Decimal(x["credit"]) for x in res["lines"])
    return d, c


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    accounts, journals = AccountStore(db), JournalStore(db)
    periods, cstore = PeriodStore(db), CurrencySettingsStore(db)
    links = AccountLinkService(db, accounts, None)
    for s in (accounts, journals, periods, cstore, links):
        await s.ensure_indexes()
    chart = ChartOfAccounts(accounts, STANDARD_COA,
                            usage_probe=JournalUsageProbe(journals))
    links._chart = chart
    currencies = EntityCurrencyService(cstore, journals)
    posting = JournalPostingService(JournalValidator(
        PostingAccountResolver(accounts), CurrencyPolicy(["SAR", "USD"]),
        period_guard=DatabasePeriodGuard(periods), currency_gate=currencies), journals)
    reports = ReportingService(journals, accounts)
    bridge = AccountingBridge(db, E, posting, links)
    recon = BusinessAccountingReconciliation(db, E, journals, bridge)
    await chart.seed_template(E, by="qa")
    await currencies.configure(E, "SAR", ["SAR", "USD"], by="qa")

    async def leaf(role, label, t):
        acc = await chart.find_by_role(E, role)
        if not acc.get("is_group"):
            return acc["code"]
        return (await chart.create_account(E, AccountCreate(
            parent=acc["code"], name=label, name_ar=label, type=t), by="qa"))["code"]

    await leaf("cash_on_hand", "QA cash", "asset")
    payable_parent = (await chart.find_by_role(E, "payables"))["code"]
    for key, label in ((K.OFFICE_WALLET_LIABILITY, "محافظ المكاتب"),
                       (K.SELLER_PAYABLE, "مستحقات البائعين"),
                       (K.DEFERRED_PLATFORM_REVENUE, "إيراد مؤجّل")):
        code = (await chart.create_account(E, AccountCreate(
            parent=payable_parent, name=label, name_ar=label, type="liability"),
            by="qa"))["code"]
        await links.set_link(E, key, code, by="qa")
    rev_parent = (await chart.find_by_role(E, "operating_revenue_group"))["code"] \
        if (await chart.find_by_role(E, "operating_revenue_group")) else None
    service_rev = await chart.find_by_role(E, "service_revenue")
    for key, label in ((K.COMMISSION_REVENUE, "إيراد عمولات"),
                       (K.ADS_REVENUE, "إيراد إعلانات"),
                       (K.CANCELLATION_FEE_REVENUE, "إيراد رسوم إلغاء")):
        parent = rev_parent or service_rev["parent"]
        code = (await chart.create_account(E, AccountCreate(
            parent=parent, name=label, name_ar=label, type="revenue"),
            by="qa"))["code"]
        await links.set_link(E, key, code, by="qa")

    import accounting.booking_events as bev
    import accounting.business_events as be
    be.accounting_bridge = lambda: bridge
    bev.accounting_bridge = lambda: bridge
    links_map = {k: (await links.resolve(E, k))["account_code"]
                 for k in (K.OFFICE_WALLET_LIABILITY, K.SELLER_PAYABLE,
                           K.DEFERRED_PLATFORM_REVENUE, K.COMMISSION_REVENUE,
                           K.ADS_REVENUE, K.CANCELLATION_FEE_REVENUE)}

    def amount_on(res, code, side):
        return sum(Decimal(x[side]) for x in res["lines"]
                   if x["account_code"] == code)

    # ------------------------------------------------------- B2B booking (PD-1)
    b2b_id = str(ObjectId())
    b2b = {"seller_id": str(SELLER["_id"]), "package_title": "برنامج B2B",
           "currency": "SAR", "net_cost_total": 1000.0, "platform_fee": 100.0,
           "amount_charged": 1100.0, "buyer_type": "office",
           "marketer_commission": 0.0}
    r = await bev.emit_booking_created(b2b, b2b_id, BUYER)
    d, c = sides(r)
    rec("B2B.booking_balanced", r.get("posted") and d == c == Decimal("1100.00"),
        f"{d}/{c}")
    rec("B2B.booking_arithmetic_invariant",
        amount_on(r, links_map[K.OFFICE_WALLET_LIABILITY], "debit") == Decimal("1100.00")
        and amount_on(r, links_map[K.SELLER_PAYABLE], "credit") == Decimal("1000.00")
        and amount_on(r, links_map[K.DEFERRED_PLATFORM_REVENUE], "credit")
        == Decimal("100.00"), "1100 = 1000 + 100 deferred")
    rec("B2B.no_revenue_at_booking",
        amount_on(r, links_map[K.COMMISSION_REVENUE], "credit") == Decimal("0"), "")
    inc = await reports.income_statement(E, currency="SAR")
    rec("PD1.income_statement_zero_after_booking",
        inc["revenue"]["total"] == "0.00", inc["revenue"]["total"])

    s = await bev.emit_booking_settlement(b2b, b2b_id, SELLER)
    d, c = sides(s)
    rec("B2B.settlement_balanced", s.get("posted") and d == c, f"{d}/{c}")
    rec("PD1A.deferred_recognized_once",
        amount_on(s, links_map[K.DEFERRED_PLATFORM_REVENUE], "debit")
        == Decimal("100.00")
        and amount_on(s, links_map[K.COMMISSION_REVENUE], "credit")
        == Decimal("200.00"), "100 deferred + 100 seller-side fee = 200 revenue")
    inc = await reports.income_statement(E, currency="SAR")
    rec("PD2.no_double_revenue_same_fee", inc["revenue"]["total"] == "200.00",
        inc["revenue"]["total"])
    retry = await bev.emit_booking_settlement(b2b, b2b_id, SELLER)
    rec("B2B.settlement_retry_idempotent", retry.get("idempotent_replay") is True, "")
    conc = await asyncio.gather(*[bev.emit_booking_settlement(b2b, b2b_id, SELLER)
                                  for _ in range(5)], return_exceptions=True)
    rec("B2B.settlement_concurrency_single_effect",
        not [x for x in conc if isinstance(x, dict) and x.get("posted")
             and not x.get("idempotent_replay")], "")

    # ------------------------------------------------------- B2C booking + marketer
    b2c_id = str(ObjectId())
    b2c = {"seller_id": str(SELLER["_id"]), "package_title": "برنامج B2C",
           "currency": "SAR", "net_cost_total": 800.0, "platform_fee": 0.0,
           "amount_charged": 1000.0, "buyer_type": "individual",
           "marketer_commission": 50.0}
    r2 = await bev.emit_booking_created(b2c, b2c_id, BUYER)
    rec("B2C.booking_deferred_is_margin",
        amount_on(r2, links_map[K.DEFERRED_PLATFORM_REVENUE], "credit")
        == Decimal("200.00"), "200 margin deferred (incl. marketer share)")
    s2 = await bev.emit_booking_settlement(b2c, b2c_id, SELLER)
    d, c = sides(s2)
    rec("B2C.settlement_balanced", d == c, f"{d}/{c}")
    rec("B2C.marketer_commission_is_liability_not_expense",
        amount_on(s2, links_map[K.OFFICE_WALLET_LIABILITY], "credit")
        == Decimal("850.00")
        and amount_on(s2, links_map[K.COMMISSION_REVENUE], "credit")
        == Decimal("150.00"), "800 seller + 50 marketer ; 150 platform revenue")

    # ----------------------------------------------------- Rahal booking (PD-6)
    rahal_id = str(ObjectId())
    rahal = {**b2b, "package_title": "برنامج رحال", "rahal_ref": "RHL-1"}
    r3 = await bev.emit_booking_created(rahal, rahal_id, BUYER)
    rec("PD6.rahal_booking_effect_at_approval",
        r3.get("posted") and (r3.get("metadata") or {}).get("business", {})
        .get("is_rahal") is True, r3.get("entry_no"))

    # ------------------------------------------------------ blue cancellation
    blue_id = str(ObjectId())
    blue = {**b2b, "package_title": "إلغاء أزرق"}
    await bev.emit_booking_created(blue, blue_id, BUYER)
    cb = await bev.emit_cancel_blue(blue, blue_id, refund=1080.0, admin_fee=20.0,
                                   buyer=BUYER)
    d, c = sides(cb)
    rec("BLUE.balanced_and_arithmetic", cb.get("posted") and d == c
        and amount_on(cb, links_map[K.OFFICE_WALLET_LIABILITY], "credit")
        == Decimal("1080.00")
        and amount_on(cb, links_map[K.CANCELLATION_FEE_REVENUE], "credit")
        == Decimal("20.00"), f"{d}/{c} — 1080 refund + 20 fee = 1100")
    rec("PD3.no_negative_revenue_line",
        all(Decimal(x["debit"]) >= 0 and Decimal(x["credit"]) >= 0
            for x in cb["lines"]), "")
    rec("PD3.deferred_released_not_reversed_by_negative",
        amount_on(cb, links_map[K.DEFERRED_PLATFORM_REVENUE], "debit")
        == Decimal("100.00"), "")

    # ---------------------------------------------------- yellow cancellation
    yellow_id = str(ObjectId())
    yellow = {**b2b, "package_title": "إلغاء أصفر"}
    await bev.emit_booking_created(yellow, yellow_id, BUYER)
    cy = await bev.emit_cancel_yellow(yellow, yellow_id, deduction=200.0,
                                     platform_cut=40.0, seller_keeps=160.0,
                                     refund=900.0, buyer=BUYER)
    d, c = sides(cy)
    rec("YELLOW.balanced", cy.get("posted") and d == c, f"{d}/{c}")
    rec("PD5.platform_cut_is_revenue_seller_keeps_is_payable",
        amount_on(cy, links_map[K.CANCELLATION_FEE_REVENUE], "credit")
        == Decimal("40.00")
        and amount_on(cy, links_map[K.SELLER_PAYABLE], "credit") >= Decimal("160.00"),
        "40 platform revenue · 160 seller payable")
    rec("PD5B.components_sum_to_reality",
        Decimal("900.00") + Decimal("40.00") + Decimal("160.00")
        == Decimal("1100.00"), "900 refund + 40 cut + 160 seller = 1100")

    # ------------------------------------------------------------- disputes
    dsp_id = str(ObjectId())
    dsp = {**b2b, "package_title": "نزاع استرداد"}
    await bev.emit_booking_created(dsp, dsp_id, BUYER)
    opened = await bridge.post_event("dispute_opened", event_id=dsp_id,
                                     currency="SAR", amount=0, lines=[],
                                     business_actor=BUYER)
    rec("DISPUTE.open_posts_no_journal",
        opened.get("skipped") and not opened.get("posted"), str(opened.get("reason")))
    dr = await bev.emit_dispute_refund(dsp, dsp_id, 1100.0, BUYER, ADMIN)
    d, c = sides(dr)
    rec("DISPUTE.refund_balanced_no_revenue", dr.get("posted") and d == c
        and amount_on(dr, links_map[K.OFFICE_WALLET_LIABILITY], "credit")
        == Decimal("1100.00")
        and amount_on(dr, links_map[K.COMMISSION_REVENUE], "credit") == Decimal("0")
        and amount_on(dr, links_map[K.DEFERRED_PLATFORM_REVENUE], "debit")
        == Decimal("100.00"), f"{d}/{c}")
    rec("DISPUTE.refund_idempotent",
        (await bev.emit_dispute_refund(dsp, dsp_id, 1100.0, BUYER, ADMIN))
        .get("idempotent_replay") is True, "")
    rel_id = str(ObjectId())
    rel_b = {**b2b, "package_title": "نزاع لصالح البائع"}
    await bev.emit_booking_created(rel_b, rel_id, BUYER)
    dl = await bev.emit_dispute_release(rel_b, rel_id, SELLER, ADMIN)
    d, c = sides(dl)
    rec("DISPUTE.release_is_earning_point", dl.get("posted") and d == c
        and amount_on(dl, links_map[K.COMMISSION_REVENUE], "credit")
        == Decimal("200.00")
        and amount_on(dl, links_map[K.DEFERRED_PLATFORM_REVENUE], "debit")
        == Decimal("100.00"), f"{d}/{c} — 100 مؤجّل + 100 عمولة بائع")
    rec("DISPUTE.release_idempotent",
        (await bev.emit_dispute_release(rel_b, rel_id, SELLER, ADMIN))
        .get("idempotent_replay") is True, "")
    rec("DISPUTE.refund_and_release_have_separate_keys",
        dr["source_key"] != dl["source_key"], "")

    # --------------------------------------------------- commission override
    ov_id = str(ObjectId())
    ov = {**b2b, "package_title": "تعديل عمولة"}
    await bev.emit_booking_created(ov, ov_id, BUYER)
    up = await bev.emit_commission_adjustment(ov, ov_id, 50.0, ADMIN)
    d, c = sides(up)
    rec("COMM.override_moves_to_deferred_not_revenue", up.get("posted") and d == c
        and amount_on(up, links_map[K.DEFERRED_PLATFORM_REVENUE], "credit")
        == Decimal("50.00")
        and amount_on(up, links_map[K.COMMISSION_REVENUE], "credit") == Decimal("0"),
        f"{d}/{c}")
    down = await bev.emit_commission_adjustment(ov, ov_id, -30.0, ADMIN)
    rec("COMM.override_negative_delta_reverses_sides",
        amount_on(down, links_map[K.DEFERRED_PLATFORM_REVENUE], "debit")
        == Decimal("30.00") and down["source_key"] != up["source_key"], "")

    # ------------------------------------------------------------------- ads
    ad_id = str(ObjectId())
    ad = {"title": "إعلان QA", "kind": "ad"}
    hold = await bridge.post_event("ads_hold", event_id=ad_id, currency="SAR",
                                   amount=300, lines=[], business_actor=BUYER)
    rel = await bridge.post_event("ads_release", event_id=ad_id, currency="SAR",
                                  amount=300, lines=[], business_actor=BUYER)
    rec("ADS.hold_and_release_no_journal",
        hold.get("skipped") and rel.get("skipped"), "")
    cap = await bev.emit_ads_capture(ad, ad_id, 300.0, "SAR", BUYER, ADMIN)
    d, c = sides(cap)
    rec("PD4A.capture_single_revenue_effect", cap.get("posted")
        and d == c == Decimal("300.00")
        and amount_on(cap, links_map[K.ADS_REVENUE], "credit") == Decimal("300.00"),
        f"{d}/{c}")
    cap2 = await bev.emit_ads_capture(ad, ad_id, 300.0, "SAR", BUYER, ADMIN)
    rec("PD4A.capture_retry_idempotent", cap2.get("idempotent_replay") is True, "")
    ref = await bev.emit_ads_refund(ad, ad_id, 120.0, "SAR", BUYER, ADMIN,
                                    "قرار إداري")
    rec("PD4C.explicit_refund_only_approved_amount", ref.get("posted")
        and amount_on(ref, links_map[K.ADS_REVENUE], "debit") == Decimal("120.00"), "")
    rec("ACTOR.accounting_actor_is_system_for_auto_entries",
        (r.get("metadata") or {}).get("business", {}).get("actor_kind") == "system"
        and (r.get("metadata") or {}).get("business", {}).get("business_actor_id")
        == str(BUYER["_id"]), "")
    rec("ACTOR.approval_actor_recorded_for_ads",
        (cap.get("metadata") or {}).get("business", {}).get("accounting_actor_id")
        == str(ADMIN["_id"]), "")

    # ------------------------------------------- static revenue idempotency audit
    import re as _re
    calls, missing = 0, []
    for path in ("market.py", "admin.py", "commissions.py", "integration.py",
                 "ads_billing.py"):
        src = open(f"/app/backend/{path}", encoding="utf-8").read()
        for m in _re.finditer(r"await log_platform_revenue\(", src):
            start = m.end()
            depth, i = 1, start
            while depth and i < len(src):
                depth += {"(": 1, ")": -1}.get(src[i], 0)
                i += 1
            call = src[start:i]
            calls += 1
            if "key=" not in call:
                missing.append(f"{path}:{src[:m.start()].count(chr(10)) + 1}")
    rec("IDEM.every_platform_revenue_call_has_stable_key", not missing,
        f"{calls - len(missing)}/{calls} — missing: {missing}")

    # ------------------------------------------------------------- invariants
    tb = await reports.trial_balance(E, currency="SAR")
    bs = await reports.balance_sheet(E, currency="SAR")
    rec("INV.trial_balance_balanced", tb["balanced"],
        f"{tb['total_debit']}/{tb['total_credit']}")
    rec("INV.balance_sheet_equation", bs["equation_holds"], bs["difference"])
    rec("INV.no_duplicate_source_keys",
        not await journals.duplicate_source_keys(E), "")
    rec("INV.no_currency_mixing", tb["currency"] == "SAR"
        and tb["available_currencies"] == ["SAR"], str(tb["available_currencies"]))
    r_rec = await recon.run()
    rec("RECON.extended_sections_cover_new_flows",
        {s["event"] for s in r_rec["sections"]} >=
        {"booking_debit", "booking_settlement", "ads_capture"},
        str([s["event"] for s in r_rec["sections"]]))
    rec("RECON.read_only", r_rec["read_only"] and r_rec["repairs_performed"] == 0, "")

    removed = {}
    for coll in ("accounting_accounts", "accounting_journal_entries",
                 "accounting_entity_settings", "accounting_periods",
                 "accounting_year_close_ops", "accounting_currency_settings",
                 "accounting_fx_rates", "accounting_account_links",
                 "accounting_integration_failures"):
        removed[coll] = (await db[coll].delete_many(
            {"entity_id": {"$regex": "^qa-"}})).deleted_count
    left = {c: await db[c].count_documents({}) for c in removed}
    rec("QA.cleanup_collections_empty", all(v == 0 for v in left.values()), str(left))

    failed = [c for c, ok in R if not ok]
    print(f"\n==== BATCH 1 FLOWS QA: {len(R) - len(failed)} PASS / {len(failed)} FAIL ====")
    for f in failed:
        print("FAIL:", f)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
