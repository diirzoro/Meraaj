"""Core Accounting Reports (Phase 8) — Trial Balance, Income Statement, Balance Sheet.

EVERY figure here is DERIVED from journal entries at read time. There is no report
collection, no cached balance, no stored total.

TRACEABILITY
  ReportingService.trial_balance    ← Rahaal `reportTrialBalance`            PORT + HARDEN
  ReportingService.income_statement ← Rahaal `reportIncomeStatement`         PORT + HARDEN
  ReportingService.balance_sheet    ← Rahaal `reportBalanceSheet`            PORT + HARDEN
  group roll-up                     ← Rahaal parent-sum loop                 PORT + HARDEN (real parent chain)
  cached/stored balances            ← Rahaal `account.balance`               LEAVE (never)

HARDEN vs Rahaal:
  • Rahaal summed across currencies into one column. Here a report is ALWAYS for exactly
    one currency; two currencies are never added and never converted.
  • Rahaal rolled parents up by code prefix. Here the roll-up walks the REAL `parent`
    chain, so a custom code can never silently land under the wrong group.
  • Rahaal trusted its own totals. Here each report re-checks the accounting identity and
    reports `balanced` / `equation_holds` explicitly.
  • A REVERSED original keeps its accounting history (the mirror entry neutralises it), so
    the underlying query matches POSTED *and* REVERSED — the pair nets to zero naturally.
"""
from decimal import Decimal
from typing import Optional

from .errors import AccountingError
from .ledger import normal_balance, signed_movement
from .money import ZERO, as_str, normalise
from .roles import RETAINED_EARNINGS
from .types import AccountType

CURRENT_PERIOD_RESULT = "current_period_result"


class ReportingService:
    """Read-only. Sources: journal entries + the chart. Writes nothing, ever."""

    def __init__(self, journal_store, account_store):
        self._journal = journal_store
        self._accounts = account_store

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _entity(entity_id: str) -> str:
        entity_id = str(entity_id or "").strip()
        if not entity_id:
            raise AccountingError("ENTITY_REQUIRED", "الجهة المحاسبية مطلوبة")
        return entity_id

    @staticmethod
    def _range(from_date, to_date):
        if from_date and to_date and from_date > to_date:
            raise AccountingError("INVALID_DATE_RANGE",
                                  "تاريخ البداية بعد تاريخ النهاية")

    async def _resolve_currency(self, entity_id: str,
                                currency: Optional[str]) -> tuple:
        """A report NEVER mixes currencies. With more than one currency present and none
        requested, the caller must choose — the Core refuses to guess or convert."""
        available = await self._journal.entity_currencies(entity_id)
        if currency:
            return str(currency).strip().upper(), available
        if len(available) == 1:
            return available[0], available
        if len(available) > 1:
            raise AccountingError(
                "CURRENCY_REQUIRED",
                f"توجد حركات بعملات متعددة ({', '.join(available)}) — حدد العملة، "
                f"فلا يجوز جمع عملتين في تقرير واحد")
        return None, available

    async def _movements(self, entity_id: str, currency: Optional[str],
                         from_date=None, to_date=None) -> dict:
        """`{account_code: {debit, credit}}` for the LEAF postings only (a group account can
        never be posted to, so every row returned here is a real posting account)."""
        if not currency:
            return {}
        return await self._journal.sum_by_account(entity_id, currency,
                                                  from_date=from_date, to_date=to_date)

    async def _chart_index(self, entity_id: str) -> tuple:
        accounts = await self._accounts.list_all(entity_id, include_inactive=True)
        if not accounts:
            raise AccountingError(
                "CHART_NOT_SEEDED",
                "دليل الحسابات غير مُهيّأ لهذه الجهة — لا يمكن إصدار تقرير", 409)
        by_code = {a["code"]: a for a in accounts}
        return accounts, by_code

    @staticmethod
    def _rollup(by_code: dict, movements: dict) -> dict:
        """Walk the REAL parent chain so each group carries the sum of its own subtree.
        A missing parent is a chart integrity problem, not something to guess around."""
        totals = {code: {"debit": ZERO, "credit": ZERO, "own_debit": ZERO,
                         "own_credit": ZERO} for code in by_code}
        for code, mv in movements.items():
            node = by_code.get(code)
            if not node:
                raise AccountingError(
                    "REPORT_ORPHAN_POSTING",
                    f"يوجد ترحيل على حساب {code} غير موجود في الدليل — راجع سلامة الدليل",
                    409)
            totals[code]["own_debit"] += mv["debit"]
            totals[code]["own_credit"] += mv["credit"]
            seen = set()
            cursor = node
            while cursor is not None:
                ccode = cursor["code"]
                if ccode in seen:      # defensive: a cyclic parent chain must not hang
                    raise AccountingError("REPORT_CHART_CYCLE",
                                          f"سلسلة آباء دائرية عند الحساب {ccode}", 409)
                seen.add(ccode)
                totals[ccode]["debit"] += mv["debit"]
                totals[ccode]["credit"] += mv["credit"]
                parent = cursor.get("parent")
                cursor = by_code.get(parent) if parent else None
        return totals

    @staticmethod
    def _row(account: dict, agg: dict) -> dict:
        acc_type = account["type"]
        debit, credit = agg["debit"], agg["credit"]
        balance = signed_movement(acc_type, debit, credit)
        return {
            "code": account["code"], "name_ar": account.get("name_ar"),
            "name_en": account.get("name_en"), "type": acc_type,
            "level": account.get("level"), "parent": account.get("parent"),
            "is_group": bool(account.get("is_group")),
            "is_active": account.get("is_active", True),
            "normal_balance": normal_balance(acc_type),
            "total_debit": as_str(normalise(debit)),
            "total_credit": as_str(normalise(credit)),
            "balance": as_str(normalise(balance)),
            # The presentation columns an accountant expects: one side only.
            "debit_balance": as_str(normalise(debit - credit)) if debit > credit
            else as_str(ZERO),
            "credit_balance": as_str(normalise(credit - debit)) if credit > debit
            else as_str(ZERO),
        }

    @staticmethod
    def _type_total(by_code: dict, totals: dict, acc_type: str) -> Decimal:
        """Sum the type using ROOT accounts only — summing every level would count the same
        posting once per ancestor."""
        total = ZERO
        for code, acc in by_code.items():
            if acc["type"] != acc_type:
                continue
            parent = acc.get("parent")
            if parent and by_code.get(parent, {}).get("type") == acc_type:
                continue            # not a root of this type
            agg = totals[code]
            total += signed_movement(acc_type, agg["debit"], agg["credit"])
        return total

    # ------------------------------------------------------------ trial balance
    async def trial_balance(self, entity_id: str, currency: Optional[str] = None,
                            from_date=None, to_date=None,
                            include_zero: bool = False,
                            include_groups: bool = True) -> dict:
        entity_id = self._entity(entity_id)
        self._range(from_date, to_date)
        currency, available = await self._resolve_currency(entity_id, currency)
        accounts, by_code = await self._chart_index(entity_id)
        movements = await self._movements(entity_id, currency, from_date, to_date)
        totals = self._rollup(by_code, movements)

        rows, sum_debit, sum_credit = [], ZERO, ZERO
        for acc in sorted(accounts, key=lambda a: a["code"]):
            agg = totals[acc["code"]]
            is_group = bool(acc.get("is_group"))
            if not include_groups and is_group:
                continue
            if not include_zero and agg["debit"] == ZERO and agg["credit"] == ZERO:
                continue
            rows.append(self._row(acc, agg))
            if not is_group:
                # ONLY leaf accounts enter the trial-balance totals — adding group rows
                # would double-count every posting.
                sum_debit += agg["debit"]
                sum_credit += agg["credit"]

        difference = sum_debit - sum_credit
        return {
            "report": "trial_balance", "entity_id": entity_id,
            "currency": currency, "available_currencies": available,
            "from_date": from_date.isoformat() if from_date else None,
            "to_date": to_date.isoformat() if to_date else None,
            "include_groups": include_groups, "include_zero": include_zero,
            "total_debit": as_str(normalise(sum_debit)),
            "total_credit": as_str(normalise(sum_credit)),
            "difference": as_str(normalise(difference)),
            # Exact decimals — no epsilon, so an out-of-balance trial balance is a real
            # data problem and never a rounding artefact.
            "balanced": difference == ZERO,
            "account_count": len(rows),
            "posting_account_count": sum(1 for r in rows if not r["is_group"]),
            "rows": rows,
            "derived": True, "stored_balances": False,
        }

    # --------------------------------------------------------- income statement
    async def income_statement(self, entity_id: str, currency: Optional[str] = None,
                               from_date=None, to_date=None,
                               include_zero: bool = False) -> dict:
        entity_id = self._entity(entity_id)
        self._range(from_date, to_date)
        currency, available = await self._resolve_currency(entity_id, currency)
        accounts, by_code = await self._chart_index(entity_id)
        movements = await self._movements(entity_id, currency, from_date, to_date)
        totals = self._rollup(by_code, movements)

        def section(acc_type: str) -> list:
            out = []
            for acc in sorted(accounts, key=lambda a: a["code"]):
                if acc["type"] != acc_type:
                    continue
                agg = totals[acc["code"]]
                if not include_zero and agg["debit"] == ZERO and agg["credit"] == ZERO:
                    continue
                out.append(self._row(acc, agg))
            return out

        revenue = self._type_total(by_code, totals, AccountType.REVENUE.value)
        expense = self._type_total(by_code, totals, AccountType.EXPENSE.value)
        net = revenue - expense
        return {
            "report": "income_statement", "entity_id": entity_id,
            "currency": currency, "available_currencies": available,
            "from_date": from_date.isoformat() if from_date else None,
            "to_date": to_date.isoformat() if to_date else None,
            "revenue": {"total": as_str(normalise(revenue)),
                        "rows": section(AccountType.REVENUE.value)},
            "expenses": {"total": as_str(normalise(expense)),
                         "rows": section(AccountType.EXPENSE.value)},
            "net_result": as_str(normalise(net)),
            "result_kind": "profit" if net > ZERO else ("loss" if net < ZERO
                                                        else "breakeven"),
            "note": "نتيجة الفترة مشتقة من الحركات ولم تُقفل في حقوق الملكية بعد "
                    "(الإقفال مرحلة لاحقة)",
            "derived": True, "stored_balances": False,
        }

    # ------------------------------------------------------------ balance sheet
    async def balance_sheet(self, entity_id: str, currency: Optional[str] = None,
                            as_of=None, from_date=None,
                            include_zero: bool = False) -> dict:
        """`as_of` is inclusive. `from_date` scopes ONLY the period-result line (the
        un-closed profit/loss of the current period); assets, liabilities and equity are
        always cumulative from the beginning of the ledger."""
        entity_id = self._entity(entity_id)
        self._range(from_date, as_of)
        currency, available = await self._resolve_currency(entity_id, currency)
        accounts, by_code = await self._chart_index(entity_id)
        movements = await self._movements(entity_id, currency, to_date=as_of)
        totals = self._rollup(by_code, movements)

        def section(acc_type: str) -> list:
            out = []
            for acc in sorted(accounts, key=lambda a: a["code"]):
                if acc["type"] != acc_type:
                    continue
                agg = totals[acc["code"]]
                if not include_zero and agg["debit"] == ZERO and agg["credit"] == ZERO:
                    continue
                out.append(self._row(acc, agg))
            return out

        assets = self._type_total(by_code, totals, AccountType.ASSET.value)
        liabilities = self._type_total(by_code, totals, AccountType.LIABILITY.value)
        equity = self._type_total(by_code, totals, AccountType.EQUITY.value)

        # Period result, derived. NO closing journal is written here: closing belongs to
        # the period/year-closing phase, so this appears as an explicit derived line.
        period_movements = await self._movements(entity_id, currency,
                                                 from_date=from_date, to_date=as_of) \
            if from_date else movements
        period_totals = self._rollup(by_code, period_movements)
        revenue = self._type_total(by_code, period_totals, AccountType.REVENUE.value)
        expense = self._type_total(by_code, period_totals, AccountType.EXPENSE.value)
        period_result = revenue - expense

        # Anything outside the period window still belongs to equity in the identity, so
        # the cumulative result is what closes the equation, not the period slice.
        cumulative_revenue = self._type_total(by_code, totals,
                                              AccountType.REVENUE.value)
        cumulative_expense = self._type_total(by_code, totals,
                                              AccountType.EXPENSE.value)
        cumulative_result = cumulative_revenue - cumulative_expense

        equity_total = equity + cumulative_result
        difference = assets - (liabilities + equity_total)
        retained = await self._accounts.find_one_by_role(entity_id, RETAINED_EARNINGS)
        return {
            "report": "balance_sheet", "entity_id": entity_id,
            "currency": currency, "available_currencies": available,
            "as_of": as_of.isoformat() if as_of else None,
            "period_from": from_date.isoformat() if from_date else None,
            "assets": {"total": as_str(normalise(assets)),
                       "rows": section(AccountType.ASSET.value)},
            "liabilities": {"total": as_str(normalise(liabilities)),
                            "rows": section(AccountType.LIABILITY.value)},
            "equity": {
                "posted_total": as_str(normalise(equity)),
                "rows": section(AccountType.EQUITY.value),
                CURRENT_PERIOD_RESULT: as_str(normalise(period_result)),
                "unclosed_cumulative_result": as_str(normalise(cumulative_result)),
                "total": as_str(normalise(equity_total)),
                "retained_earnings_account": (retained or {}).get("code"),
                "closing_performed": False,
            },
            "total_liabilities_and_equity": as_str(normalise(liabilities + equity_total)),
            "difference": as_str(normalise(difference)),
            "equation": "الأصول = الالتزامات + حقوق الملكية + نتيجة الفترة غير المقفلة",
            "equation_holds": difference == ZERO,
            "derived": True, "stored_balances": False,
        }
