"""Year Closing — revenue/expense closing entries → verification → period locking.

TRACEABILITY
  close_year()               ← Rahaal `POST /year-close` (single-shot, no state)   PORT + HARDEN
  revenue/expense zeroing    ← Rahaal closing entry construction                   PORT + HARDEN (types/tree, no hardcoded codes)
  retained earnings transfer ← Rahaal `3102` hardcoded                             ADAPT (semantic role)
  `closed_years` flag first  ← Rahaal (year flagged before entries verified)       LEAVE (order reversed here)
  cached balance closing     ← Rahaal `updateBalance`                              LEAVE (no stored balance)
  year reopen                ← Rahaal `closed_years` pull                          DEFERRED — CONTROLLED YEAR REOPEN

THREE SEPARATE THINGS, in this order and never merged:
  1) FINANCIAL CLOSING ENTRIES — a real balanced journal through the ONE write gateway.
  2) POST-CLOSE VERIFICATION  — recomputed from journals; a failure means NO final close.
  3) PERIOD LOCKING + FINAL STATE — the year is declared CLOSED only after 1 and 2 pass.

Closing journals are posted BEFORE the periods are locked, on purpose: the journal is dated
inside the year, and PeriodGuard (correctly) refuses any date inside a closed period.

NO DATABASE TRANSACTION IS CLAIMED. Atomicity that does not exist is not pretended: the
workflow is RESUMABLE instead — deterministic `source_key`s, a persisted operation state per
(entity, fiscal_year, currency), and idempotent posting. A retry continues; it never
duplicates.
"""
from decimal import Decimal
from typing import Optional

from .errors import AccountingError
from .journal import JournalEntryDraft, JournalLineInput, utc_now
from .ledger import signed_movement
from .money import ZERO, as_str, normalise
from .roles import RETAINED_EARNINGS
from .types import AccountType
from .year_state import (YEAR_ACTIVE_CLOSE_STATES, YEAR_CLOSE_SOURCE_TYPE,
                         YEAR_STATE_COMPLETED, YEAR_STATE_FAILED,
                         YEAR_STATE_JOURNAL_POSTED, YEAR_STATE_REOPENED,
                         YEAR_STATE_REOPEN_STARTED, YEAR_STATE_STARTED,
                         YEAR_STATE_VERIFIED)

RESULT_TYPES = (AccountType.REVENUE.value, AccountType.EXPENSE.value)


def year_close_source_key(entity_id: str, fiscal_year: int, currency: str) -> str:
    """DETERMINISTIC by construction: the same (entity, year, currency) can only ever
    produce ONE closing journal, because the idempotency key is a pure function of them and
    the database enforces its uniqueness."""
    return f"year_close:{entity_id}:{int(fiscal_year)}:{currency}"


class YearCloseService:
    def __init__(self, posting_service, journal_store, account_store, period_store,
                 period_service, reversal_service=None):
        self._posting = posting_service
        self._journal = journal_store
        self._accounts = account_store
        self._periods = period_store
        self._period_service = period_service
        # Injected so the controlled reopen can reverse a closing journal through the ONE
        # reversal engine. The Core never deletes or edits a posted journal.
        self._reversal = reversal_service

    # --------------------------------------------------------------------- read
    async def status(self, entity_id: str, fiscal_year: int) -> dict:
        entity_id = self._entity(entity_id)
        fiscal_year = int(fiscal_year)
        policy = await self._period_service.policy(entity_id)
        periods = await self._periods.list_periods(entity_id, fiscal_year)
        ops = await self._periods.list_year_ops(entity_id, fiscal_year)
        return {
            "entity_id": entity_id, "fiscal_year": fiscal_year,
            "fiscal": policy.as_dict(),
            "range": {"start": policy.year_start(fiscal_year).isoformat(),
                      "end": policy.year_end(fiscal_year).isoformat()},
            "periods": {"total": len(periods),
                        "closed": sum(1 for p in periods if p["status"] == "closed")},
            "currencies": [{"currency": o["currency"], "state": o.get("state"),
                            "entry_no": o.get("entry_no"),
                            "net_result": o.get("net_result"),
                            "verified": o.get("state") in (YEAR_STATE_VERIFIED,
                                                           YEAR_STATE_COMPLETED),
                            "error": o.get("error")} for o in ops],
            # A year is CLOSED only per-currency: SAR completed while USD failed is
            # NEVER reported as "year closed".
            "fully_closed_currencies": [o["currency"] for o in ops
                                        if o.get("state") == YEAR_STATE_COMPLETED],
            "year_reopen": "DEFERRED — CONTROLLED YEAR REOPEN",
        }

    # -------------------------------------------------------------------- close
    async def close_year(self, entity_id: str, fiscal_year: int, currency: str,
                         by: Optional[str] = None,
                         reason: Optional[str] = None) -> dict:
        """ONE currency per call. Currencies are closed INDEPENDENTLY and are never added
        together or converted — the books of each currency close on their own."""
        entity_id = self._entity(entity_id)
        fiscal_year = int(fiscal_year)
        currency = str(currency or "").strip().upper()
        if not currency:
            raise AccountingError("CURRENCY_REQUIRED", "عملة الإقفال مطلوبة")
        if not by:
            raise AccountingError("ACTOR_REQUIRED", "هوية المنفّذ مطلوبة")
        reason = (reason or f"إقفال السنة المالية {fiscal_year} ({currency})").strip()

        policy = await self._period_service.policy(entity_id)
        start, end = policy.year_start(fiscal_year), policy.year_end(fiscal_year)
        if end > utc_now():
            raise AccountingError(
                "FISCAL_YEAR_NOT_ENDED",
                f"السنة المالية {fiscal_year} لم تنتهِ بعد ({end.date()}) — "
                f"لا يمكن إقفالها")
        periods = await self._periods.list_periods(entity_id, fiscal_year)
        if not periods:
            raise AccountingError(
                "PERIODS_NOT_DEFINED",
                f"لا توجد فترات محاسبية للسنة {fiscal_year} — أنشئ الفترات أولاً", 409)

        source_key = year_close_source_key(entity_id, fiscal_year, currency)
        op = await self._periods.start_year_op({
            "entity_id": entity_id, "fiscal_year": fiscal_year, "currency": currency,
            "state": YEAR_STATE_STARTED, "source_key": source_key,
            "journal_id": None, "entry_no": None, "net_result": None,
            "reason": reason, "started_at": utc_now(), "started_by": by,
            "updated_at": utc_now(), "error": None,
        })
        if op and op.get("state") == YEAR_STATE_COMPLETED:
            return {"closed": False, "idempotent_replay": True,
                    "already_closed": True, "operation": self._op_public(op),
                    "message": f"السنة المالية {fiscal_year} بعملة {currency} مقفلة "
                               f"مسبقاً بالقيد {op.get('entry_no')}"}

        # 1) CLOSING ENTRIES — computed from journals, never from a cached balance, and
        #    resolved through account TYPES (no hardcoded account code anywhere).
        plan = await self._build_plan(entity_id, currency, start, end)
        if plan["net_result"] == ZERO and not plan["lines"]:
            await self._periods.update_year_op(entity_id, fiscal_year, currency, {
                "state": YEAR_STATE_FAILED, "updated_at": utc_now(),
                "error": "NO_RESULT_ACCOUNTS_MOVEMENT"})
            raise AccountingError(
                "NOTHING_TO_CLOSE",
                f"لا توجد حركات إيرادات أو مصروفات بعملة {currency} في السنة "
                f"{fiscal_year} — لا شيء لإقفاله", 409)

        retained = await self._accounts.find_one_by_role(entity_id, RETAINED_EARNINGS)
        if not retained:
            raise AccountingError(
                "RETAINED_EARNINGS_ACCOUNT_MISSING",
                f"لا يوجد حساب بدور {RETAINED_EARNINGS} في دليل هذه الجهة — إقفال "
                f"النتيجة يحتاج هذا الدور (لا يُستخدم رقم حساب ثابت)", 409)
        if retained.get("is_group"):
            raise AccountingError("GROUP_ACCOUNT_NOT_POSTABLE",
                                  f"حساب الأرباح المحتجزة {retained['code']} حساب مجموعة",
                                  409)

        lines = [JournalLineInput(account_code=row["code"], debit=row["debit"],
                                  credit=row["credit"], currency=currency,
                                  memo=row["memo"]) for row in plan["lines"]]
        net = plan["net_result"]
        # Profit → CREDIT retained earnings; Loss → DEBIT retained earnings.
        if net > ZERO:
            lines.append(JournalLineInput(account_code=retained["code"], debit=ZERO,
                                          credit=net, currency=currency,
                                          memo=f"ترحيل نتيجة السنة {fiscal_year} (ربح)"))
        elif net < ZERO:
            lines.append(JournalLineInput(account_code=retained["code"], debit=-net,
                                          credit=ZERO, currency=currency,
                                          memo=f"ترحيل نتيجة السنة {fiscal_year} (خسارة)"))
        else:
            # Revenue and expense both closed out to exactly zero result: the closing
            # entry still zeroes the result accounts, and no equity transfer is needed.
            pass

        draft = JournalEntryDraft(
            date=end, currency=currency, source_type=YEAR_CLOSE_SOURCE_TYPE,
            source_id=str(fiscal_year), lines=lines,
            description=f"قيد إقفال السنة المالية {fiscal_year} ({currency}) — {reason}")
        posted = await self._posting.post(entity_id, draft, source_key=source_key, by=by)
        await self._periods.update_year_op(entity_id, fiscal_year, currency, {
            "state": YEAR_STATE_JOURNAL_POSTED, "journal_id": posted.get("id"),
            "entry_no": posted.get("entry_no"), "net_result": as_str(net),
            "retained_earnings_account": retained["code"],
            "updated_at": utc_now(), "error": None})

        # 2) POST-CLOSE VERIFICATION — recomputed from the journals themselves.
        verification = await self._verify(entity_id, currency, start, end, net,
                                          retained["code"], posted)
        if not verification["ok"]:
            await self._periods.update_year_op(entity_id, fiscal_year, currency, {
                "state": YEAR_STATE_FAILED, "updated_at": utc_now(),
                "error": "VERIFICATION_FAILED", "verification": verification})
            raise AccountingError(
                "YEAR_CLOSE_VERIFICATION_FAILED",
                "قيد الإقفال مُرحَّل لكن التحقق بعد الإقفال فشل — لم تُقفل السنة ولم "
                "تُقفل الفترات. صحّح ثم أعد المحاولة (نفس المفتاح لن يُنشئ قيداً ثانياً)",
                409, verification=verification,
                closing_entry_no=posted.get("entry_no"))
        await self._periods.update_year_op(entity_id, fiscal_year, currency, {
            "state": YEAR_STATE_VERIFIED, "verification": verification,
            "updated_at": utc_now()})

        # 3) PERIOD LOCKING + FINAL STATE — last, and only after verification passed.
        now = utc_now()
        locked = await self._periods.close_all_open(entity_id, fiscal_year, {
            "at": now,
            "set": {"closed_at": now, "closed_by": by,
                    "close_reason": f"إقفال سنوي ({currency}) — {reason}"},
            "entry": {"action": "close", "at": now, "by": by,
                      "reason": f"year_close:{currency} — {reason}"}})
        op = await self._periods.update_year_op(entity_id, fiscal_year, currency, {
            "state": YEAR_STATE_COMPLETED, "periods_locked": locked,
            "completed_at": now, "updated_at": now, "error": None})

        return {"closed": True, "idempotent_replay": bool(posted.get("idempotent_replay")),
                "fiscal_year": fiscal_year, "currency": currency,
                "net_result": as_str(net),
                "result_kind": "profit" if net > ZERO else ("loss" if net < ZERO
                                                            else "breakeven"),
                "retained_earnings_account": retained["code"],
                "closing_entry": posted, "verification": verification,
                "periods_locked": locked, "operation": self._op_public(op or {}),
                "closing_journal_immutable": True,
                "year_reopen": "DEFERRED — CONTROLLED YEAR REOPEN"}

    # ------------------------------------------------------------------ planning
    async def _build_plan(self, entity_id: str, currency: str, start, end) -> dict:
        """Revenue and expense balances derived from journals for the fiscal year, in ONE
        currency. Closing journals themselves are excluded from the computation, so a retry
        can never close an already-closed result a second time."""
        movements = await self._journal.sum_by_account(
            entity_id, currency, from_date=start, to_date=end,
            exclude_source_types=(YEAR_CLOSE_SOURCE_TYPE,))
        accounts = await self._accounts.list_all(entity_id, include_inactive=True)
        by_code = {a["code"]: a for a in accounts}
        rows, revenue, expense = [], ZERO, ZERO
        for code, mv in sorted(movements.items()):
            account = by_code.get(code)
            if not account or account["type"] not in RESULT_TYPES:
                continue
            if account.get("is_group"):
                continue
            balance = signed_movement(account["type"], mv["debit"], mv["credit"])
            if balance == ZERO:
                continue
            if account["type"] == AccountType.REVENUE.value:
                revenue += balance
                # Revenue is credit-normal: close it by DEBITing its balance back to zero.
                rows.append({"code": code, "debit": balance, "credit": ZERO,
                             "memo": "إقفال إيراد"})
            else:
                expense += balance
                rows.append({"code": code, "debit": ZERO, "credit": balance,
                             "memo": "إقفال مصروف"})
        return {"lines": rows, "revenue": normalise(revenue),
                "expense": normalise(expense),
                "net_result": normalise(revenue - expense)}

    # -------------------------------------------------------------- verification
    async def _verify(self, entity_id: str, currency: str, start, end,
                      net: Decimal, retained_code: str, posted: dict) -> dict:
        """Nothing is trusted: revenue and expense are re-read INCLUDING the closing
        journal and must now be zero, the transferred result must equal the computed
        result, and the book must still balance."""
        after = await self._journal.sum_by_account(entity_id, currency,
                                                    from_date=start, to_date=end)
        accounts = await self._accounts.list_all(entity_id, include_inactive=True)
        by_code = {a["code"]: a for a in accounts}
        revenue_left, expense_left = ZERO, ZERO
        for code, mv in after.items():
            account = by_code.get(code)
            if not account or account["type"] not in RESULT_TYPES:
                continue
            balance = signed_movement(account["type"], mv["debit"], mv["credit"])
            if account["type"] == AccountType.REVENUE.value:
                revenue_left += balance
            else:
                expense_left += balance
        retained_mv = after.get(retained_code) or {"debit": ZERO, "credit": ZERO}
        transferred = retained_mv["credit"] - retained_mv["debit"]
        totals = await self._journal.sum_totals(entity_id, currency, start, end)
        journal_debit = Decimal(posted.get("total_debit") or "0")
        journal_credit = Decimal(posted.get("total_credit") or "0")
        checks = {
            "revenue_closed_to_zero": normalise(revenue_left) == ZERO,
            "expense_closed_to_zero": normalise(expense_left) == ZERO,
            "result_transferred_to_equity": normalise(transferred) == normalise(net),
            "closing_journal_balanced": journal_debit == journal_credit,
            "trial_balance_balanced": totals["debit"] == totals["credit"],
        }
        return {"ok": all(checks.values()), "checks": checks,
                "revenue_remaining": as_str(normalise(revenue_left)),
                "expense_remaining": as_str(normalise(expense_left)),
                "transferred_to_retained_earnings": as_str(normalise(transferred)),
                "expected_net_result": as_str(normalise(net)),
                "trial_balance": {"debit": as_str(totals["debit"]),
                                  "credit": as_str(totals["credit"])},
                "currency": currency}

    # ----------------------------------------------------------------- helpers
    @staticmethod
    def _op_public(op: dict) -> dict:
        def iso(v):
            return v.isoformat() if hasattr(v, "isoformat") else v
        return {"state": op.get("state"), "fiscal_year": op.get("fiscal_year"),
                "currency": op.get("currency"), "source_key": op.get("source_key"),
                "journal_id": op.get("journal_id"), "entry_no": op.get("entry_no"),
                "net_result": op.get("net_result"),
                "periods_locked": op.get("periods_locked"),
                "started_at": iso(op.get("started_at")),
                "completed_at": iso(op.get("completed_at")),
                "error": op.get("error"),
                "resumable": op.get("state") not in (YEAR_STATE_COMPLETED,)}

    @staticmethod
    def _entity(entity_id: str) -> str:
        entity_id = str(entity_id or "").strip()
        if not entity_id:
            raise AccountingError("ENTITY_REQUIRED", "الجهة المحاسبية مطلوبة")
        return entity_id

    async def reopen_year(self, entity_id: str, fiscal_year: int,
                          currency: str = None, reason: str = None,
                          by: str = None) -> dict:
        """OPEN-017 — CONTROLLED YEAR REOPEN, one currency per call.

        Rahaal's equivalent was `closed_years.pull(year)`: a status flip that left the
        closing entries in place, so the books stayed closed while the flag said open —
        the exact contradiction this workflow exists to prevent. There was nothing to PORT
        beyond the intent, hence NEW.

        ORDER (and why): claim the operation atomically → reverse the closing journal
        through the reversal engine (the ONLY correction mechanism; nothing is deleted or
        edited) → verify the mirror exists → unlock the periods → mark the operation
        REOPENED → post-reopen verification. The periods are unlocked AFTER the reversal
        because the mirror entry is dated inside the year, and PeriodGuard (correctly)
        refuses any date inside a closed period.
        """
        entity_id = self._entity(entity_id)
        fiscal_year = int(fiscal_year)
        currency = str(currency or "").strip().upper()
        if not currency:
            raise AccountingError(
                "CURRENCY_REQUIRED",
                "عملة إعادة الفتح مطلوبة — كل عملة تُعاد فتحها باستقلال")
        if not by:
            raise AccountingError("ACTOR_REQUIRED", "هوية المنفّذ مطلوبة")
        if not reason or not str(reason).strip():
            raise AccountingError("REASON_REQUIRED", "سبب إعادة فتح السنة مطلوب")
        reason = str(reason).strip()
        if self._reversal is None:
            raise AccountingError("REVERSAL_ENGINE_UNAVAILABLE",
                                  "محرّك العكس غير موصول — لا يمكن إعادة فتح السنة", 500)

        op = await self._periods.get_year_op(entity_id, fiscal_year, currency)
        if not op:
            raise AccountingError(
                "YEAR_CLOSE_NOT_FOUND",
                f"لا توجد عملية إقفال للسنة {fiscal_year} بعملة {currency}", 404)
        if op.get("state") == YEAR_STATE_REOPENED:
            return {"reopened": False, "idempotent_replay": True,
                    "already_reopened": True, "operation": self._op_public(op),
                    "message": f"السنة {fiscal_year} بعملة {currency} مُعاد فتحها مسبقاً"}
        if op.get("state") not in YEAR_ACTIVE_CLOSE_STATES:
            raise AccountingError(
                "YEAR_NOT_CLOSED",
                f"حالة عملية الإقفال ({op.get('state')}) لا تسمح بإعادة الفتح — "
                f"إعادة الفتح تخص سنة مقفلة فعلياً", 409)
        journal_id = op.get("journal_id")
        if not journal_id:
            raise AccountingError(
                "YEAR_CLOSE_JOURNAL_MISSING",
                "عملية الإقفال بلا قيد إقفال مرتبط — حالة غير متسقة تحتاج مراجعة "
                "(راجع /self-audit)", 409)

        now = utc_now()
        # 1) ATOMIC CLAIM — a final state is never used as a temporary lock; the filter is
        #    the concurrency guard, so the second concurrent request matches nothing.
        claimed = await self._periods.transition_year_op(
            entity_id, fiscal_year, currency,
            (YEAR_STATE_COMPLETED, YEAR_STATE_REOPEN_STARTED), YEAR_STATE_REOPEN_STARTED,
            {"reopen_reason": reason, "reopen_started_at": now, "reopened_by": by,
             "updated_at": now},
            {"action": "reopen_started", "at": now, "by": by, "reason": reason})
        if not claimed:
            raise AccountingError(
                "YEAR_REOPEN_IN_PROGRESS",
                "عملية إعادة فتح أخرى قائمة على نفس السنة/العملة — أعد المحاولة", 409)

        # 2) REVERSE THE CLOSING JOURNAL — deterministic key ⇒ retry-safe and resumable.
        reversal_key = f"year_reopen:{entity_id}:{fiscal_year}:{currency}"
        reversal = await self._reversal.reverse(
            entity_id, journal_id,
            reason=f"إعادة فتح السنة المالية {fiscal_year} ({currency}) — {reason}",
            by=by, source_key=reversal_key, allow_closing_reversal=True)
        mirror = reversal.get("reversal") or {}

        # 3) VERIFY THE REVERSAL before anything is unlocked.
        original_after = await self._journal.get(entity_id, journal_id)
        mirror_doc = await self._journal.find_reversal_of(entity_id, journal_id)
        reversal_checks = {
            "closing_journal_reversed":
                (original_after or {}).get("status") == "reversed",
            "mirror_entry_exists": bool(mirror_doc),
            "mirror_links_to_original":
                (mirror_doc or {}).get("reversal_of") == journal_id,
            "mirror_balanced": bool(mirror_doc) and
                self._journal.from_db_amount(mirror_doc.get("total_debit")) ==
                self._journal.from_db_amount(mirror_doc.get("total_credit")),
        }
        if not all(reversal_checks.values()):
            await self._periods.update_year_op(entity_id, fiscal_year, currency, {
                "updated_at": utc_now(), "error": "REVERSAL_VERIFICATION_FAILED",
                "reversal_checks": reversal_checks})
            raise AccountingError(
                "YEAR_REOPEN_VERIFICATION_FAILED",
                "تعذر التحقق من عكس قيد الإقفال — لم تُفتح الفترات ولم تتغير حالة "
                "السنة. أعد المحاولة بنفس المفتاح (لن يُنشأ قيد عكس ثانٍ)", 409,
                checks=reversal_checks)

        # 4) UNLOCK THE DATES — only when no OTHER currency still has an active closing
        #    effect on the same fiscal year. A year with SAR reopened and USD still closed
        #    is NOT an open year.
        others = [o for o in await self._periods.list_year_ops(entity_id, fiscal_year)
                  if o.get("currency") != currency
                  and o.get("state") in YEAR_ACTIVE_CLOSE_STATES]
        periods_unlocked = 0
        if not others:
            unlock_now = utc_now()
            periods_unlocked = await self._periods.reopen_all_closed(
                entity_id, fiscal_year, {
                    "at": unlock_now,
                    "set": {"reopened_at": unlock_now, "reopened_by": by,
                            "reopen_reason": f"إعادة فتح سنوية ({currency}) — {reason}"},
                    "entry": {"action": "reopen", "at": unlock_now, "by": by,
                              "reason": f"year_reopen:{currency} — {reason}"}})

        # 5) FINAL STATE + post-reopen verification (the result accounts are live again).
        done = utc_now()
        op = await self._periods.transition_year_op(
            entity_id, fiscal_year, currency, (YEAR_STATE_REOPEN_STARTED,),
            YEAR_STATE_REOPENED,
            {"reopened_at": done, "updated_at": done, "error": None,
             "reopen_reversal_entry_no": mirror.get("entry_no"),
             "reopen_reversal_journal_id": mirror.get("id"),
             "periods_unlocked": periods_unlocked,
             "reversal_checks": reversal_checks},
            {"action": "reopened", "at": done, "by": by, "reason": reason})

        policy = await self._period_service.policy(entity_id)
        start, end = policy.year_start(fiscal_year), policy.year_end(fiscal_year)
        plan = await self._build_plan(entity_id, currency, start, end)
        totals = await self._journal.sum_totals(entity_id, currency, start, end)
        post_checks = {
            "result_accounts_live_again": bool(plan["lines"]),
            "trial_balance_balanced": totals["debit"] == totals["credit"],
            "closing_journal_preserved": True,
            "periods_unlocked_or_blocked_by_other_currency":
                periods_unlocked > 0 or bool(others),
        }
        return {
            "reopened": True, "idempotent_replay": bool(reversal.get("idempotent_replay")),
            "fiscal_year": fiscal_year, "currency": currency,
            "closing_entry_no": op.get("entry_no") if op else None,
            "reversal_entry": mirror,
            "reversal_checks": reversal_checks,
            "periods_unlocked": periods_unlocked,
            "blocked_by_other_currencies": [o["currency"] for o in others],
            "year_open": periods_unlocked > 0 and not others,
            "net_result_restored": as_str(plan["net_result"]),
            "post_reopen_verification": post_checks,
            "no_deletion": "قيد الإقفال محفوظ ومعكوس بقيد مرآة — لم يُحذف ولم يُعدَّل",
            "operation": self._op_public(op or {}),
        }
