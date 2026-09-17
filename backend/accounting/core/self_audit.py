"""Accounting Self-Audit — READ-ONLY DIAGNOSTIC. It DETECTS; it never REPAIRS.

TRACEABILITY
  self_audit()            ← Rahaal `validateTenant` / `auditTenant` (run manually, after
                            the fact, and partially repairing)          PORT + HARDEN
  auto-repair / re-sync   ← Rahaal balance re-sync helpers              LEAVE (never)

HARD SEPARATION: DETECT vs REPAIR. This module performs no write of any kind — no journal,
no account, no period, no currency setting, no rate, no balance, no "auto-fix". Every
finding carries a severity, a reference and a RECOMMENDED action for a human.
"""
from typing import Optional

from .contracts import REPORT_LIMITS
from .errors import AccountingError
from .fiscal_year import FiscalYearPolicy
from .ledger import signed_movement
from .money import ZERO, as_str
from .periods import PERIOD_CLOSED
from .roles import (FX_ADJUSTMENT, FX_GAIN, FX_LOSS, FX_RESULT,
                    OPENING_BALANCE_SUSPENSE, RETAINED_EARNINGS)
from .types import AccountType
from .year_state import (YEAR_ACTIVE_CLOSE_STATES, YEAR_CLOSE_SOURCE_TYPE,
                         YEAR_STATES, YEAR_STATE_REOPENED)

CRITICAL, HIGH, MEDIUM, WARNING = "CRITICAL", "HIGH", "MEDIUM", "WARNING"

#: Roles the CORE itself posts to, with the account type each one must have. A chart that
#: lacks one of these cannot perform the corresponding engine operation — which is a
#: finding, not a crash at posting time.
CORE_ROLES = {
    OPENING_BALANCE_SUSPENSE: {"types": (AccountType.EQUITY.value,),
                               "needed_for": "opening balances", "severity": HIGH},
    RETAINED_EARNINGS: {"types": (AccountType.EQUITY.value,),
                        "needed_for": "year closing", "severity": HIGH},
    FX_GAIN: {"types": (AccountType.REVENUE.value,), "needed_for": "realized FX gain",
              "severity": MEDIUM, "fallback": FX_RESULT},
    FX_LOSS: {"types": (AccountType.EXPENSE.value,), "needed_for": "realized FX loss",
              "severity": MEDIUM, "fallback": FX_ADJUSTMENT},
}
UNIQUE_ROLES = tuple(CORE_ROLES) + (FX_RESULT, FX_ADJUSTMENT)


class AccountingSelfAudit:
    def __init__(self, journal_store, account_store, period_store, currency_service,
                 fx_rate_store, reporting_service, period_service):
        self._journal = journal_store
        self._accounts = account_store
        self._periods = period_store
        self._currencies = currency_service
        self._rates = fx_rate_store
        self._reports = reporting_service
        self._period_service = period_service

    async def run(self, entity_id: str) -> dict:
        """ONE entity per run — entity isolation is part of the diagnostic, so no query
        here is ever cross-entity."""
        entity_id = str(entity_id or "").strip()
        if not entity_id:
            raise AccountingError("ENTITY_REQUIRED", "الجهة المحاسبية مطلوبة")
        findings = []
        sections = {}
        for name, runner in (
            ("journals", self._audit_journals),
            ("reversal", self._audit_reversal),
            ("chart", self._audit_chart),
            ("periods", self._audit_periods),
            ("year_close", self._audit_year_close),
            ("currency_fx", self._audit_currency_fx),
            ("equation", self._audit_equation),
        ):
            found, summary = await runner(entity_id)
            findings.extend(found)
            sections[name] = summary
        counts = {level: sum(1 for f in findings if f["severity"] == level)
                  for level in (CRITICAL, HIGH, MEDIUM, WARNING)}
        return {
            "audit": "accounting_self_audit", "entity_id": entity_id,
            "read_only": True, "repairs_performed": 0,
            "separation": "DETECT only — this endpoint never repairs, never posts and "
                          "never mutates any accounting record",
            "sections": sections,
            "counts": counts,
            "healthy": counts[CRITICAL] == 0 and counts[HIGH] == 0,
            "blocking_integration": counts[CRITICAL] > 0,
            "findings": findings,
            "limits": REPORT_LIMITS["performance"],
        }

    # ------------------------------------------------------------------ journals
    @staticmethod
    def _f(code, severity, description, action, **ref):
        return {"code": code, "severity": severity, "description": description,
                "recommended_action": action, **ref}

    async def _audit_journals(self, entity_id: str):
        integrity = await self._journal.audit_integrity(entity_id)
        found = []
        if integrity["unbalanced"]:
            found.append(self._f(
                "JOURNAL_UNBALANCED", CRITICAL,
                f"{integrity['unbalanced']} قيد غير متوازن (مدين ≠ دائن)",
                "راجع القيود المذكورة واعكسها ثم أعد ترحيلها بشكل صحيح",
                reference=integrity["unbalanced_sample"]))
        if integrity["malformed"]:
            found.append(self._f(
                "JOURNAL_MALFORMED", CRITICAL,
                f"{integrity['malformed']} قيد مشوّه (سطور ناقصة/بلا عملة/بلا تاريخ أو "
                f"إجماليات لا تطابق السطور)",
                "لا تُعدَّل يدوياً — تُعكس وتُعاد بشكل صحيح",
                reference=integrity["malformed_sample"]))
        # Lines referencing an account that is not in this entity's chart.
        chart_codes = {a["code"] for a in
                       await self._accounts.list_all(entity_id, include_inactive=True)}
        used = await self._journal.line_account_codes(entity_id)
        orphans = sorted(set(used) - chart_codes)
        if orphans:
            found.append(self._f(
                "POSTING_ACCOUNT_NOT_IN_CHART", CRITICAL,
                f"ترحيلات على حسابات غير موجودة في دليل هذه الجهة: "
                f"{', '.join(orphans[:10])}",
                "لا تُحذف القيود — أضف الحساب المفقود أو اعكس القيود المعنية",
                reference=orphans[:10]))
        return found, {"journal_count": integrity["total"],
                       "currencies": integrity["currencies"],
                       "unbalanced": integrity["unbalanced"],
                       "malformed": integrity["malformed"],
                       "accounts_not_in_chart": len(orphans)}

    # ------------------------------------------------------------------ reversal
    async def _audit_reversal(self, entity_id: str):
        integrity = await self._journal.audit_integrity(entity_id)
        found = []
        if integrity["reversed_without_mirror"]:
            found.append(self._f(
                "REVERSED_WITHOUT_MIRROR", CRITICAL,
                f"{integrity['reversed_without_mirror']} قيد بحالة (معكوس) بلا قيد مرآة",
                "أعد تنفيذ العكس بنفس المفتاح — مسار الاستعادة يُكمل الربط",
                reference=integrity["reversed_without_mirror_sample"]))
        if integrity["pending_reversal_claims"]:
            found.append(self._f(
                "REVERSAL_CLAIM_PENDING", HIGH,
                f"{integrity['pending_reversal_claims']} عملية عكس غير مكتملة "
                f"(claim معلّق)",
                "أعد تنفيذ العكس بنفس المفتاح؛ الـclaim القديم قابل للاسترجاع تلقائياً",
                reference=integrity["pending_reversal_claims_sample"]))
        broken = await self._journal.mirrors_without_original(entity_id)
        if broken:
            found.append(self._f(
                "MIRROR_WITHOUT_ORIGINAL", CRITICAL,
                f"{len(broken)} قيد عكسي يشير إلى قيد أصلي غير موجود",
                "تحقيق محاسبي يدوي — لا تُحذف أي قيد",
                reference=broken[:10]))
        duplicates = await self._journal.duplicate_reversals(entity_id)
        if duplicates:
            found.append(self._f(
                "DUPLICATE_REVERSAL", CRITICAL,
                f"{len(duplicates)} قيد أصلي له أكثر من قيد عكس",
                "تحقيق يدوي؛ الفهرس الفريد يمنع تكرار جديد",
                reference=duplicates[:10]))
        return found, {"reversed_without_mirror": integrity["reversed_without_mirror"],
                       "pending_claims": integrity["pending_reversal_claims"],
                       "mirrors_without_original": len(broken),
                       "duplicate_reversals": len(duplicates)}

    # --------------------------------------------------------------------- chart
    async def _audit_chart(self, entity_id: str):
        rows = await self._accounts.list_all(entity_id, include_inactive=True)
        by_code = {a["code"]: a for a in rows}
        found = []
        missing_parents, cycles, type_mismatch, group_leaf = [], [], [], []
        for a in rows:
            parent = a.get("parent")
            if parent and parent not in by_code:
                missing_parents.append(a["code"])
                continue
            if parent and by_code[parent].get("type") != a.get("type"):
                type_mismatch.append(a["code"])
            if parent and not by_code[parent].get("is_group"):
                group_leaf.append(a["code"])
            seen, cursor = set(), a
            while cursor and cursor.get("parent"):
                if cursor["code"] in seen:
                    cycles.append(a["code"])
                    break
                seen.add(cursor["code"])
                cursor = by_code.get(cursor["parent"])
        for code, severity, items, desc, action in (
            ("CHART_MISSING_PARENT", CRITICAL, missing_parents,
             "حسابات أبوها غير موجود", "أعد بناء الأب أو أصلح حقل parent"),
            ("CHART_CYCLE", CRITICAL, cycles, "سلسلة آباء دائرية",
             "أصلح سلسلة الآباء — التقارير لا تستطيع التجميع"),
            ("CHART_TYPE_MISMATCH", HIGH, type_mismatch,
             "نوع الحساب لا يطابق نوع أبيه", "وحّد النوع مع الأب"),
            ("CHART_PARENT_NOT_GROUP", HIGH, group_leaf,
             "حساب تحت أب غير مجموعة", "حوّل الأب إلى مجموعة أو انقل الحساب"),
        ):
            if items:
                found.append(self._f(code, severity, f"{len(items)} {desc}", action,
                                     reference=sorted(set(items))[:10]))
        # Role integrity + the semantic roles the Core itself needs.
        role_map = {}
        for a in rows:
            if a.get("role"):
                role_map.setdefault(a["role"], []).append(a["code"])
        roles_report = {}
        for role in UNIQUE_ROLES:
            codes = role_map.get(role) or []
            if len(codes) > 1:
                found.append(self._f(
                    "ROLE_NOT_UNIQUE", HIGH,
                    f"الدور {role} مُسند إلى أكثر من حساب: {', '.join(codes)}",
                    "الدور النظامي يجب أن يكون على حساب واحد فقط", reference=codes))
            roles_report[role] = codes
        for role, spec in CORE_ROLES.items():
            codes = role_map.get(role) or []
            account = by_code.get(codes[0]) if codes else None
            fallback = spec.get("fallback")
            if not account and fallback:
                fb = (role_map.get(fallback) or [None])[0]
                account = by_code.get(fb) if fb else None
            if not account:
                if rows:
                    found.append(self._f(
                        "CORE_ROLE_MISSING", spec["severity"],
                        f"لا يوجد حساب بدور {role}"
                        + (f" (ولا بديله {fallback})" if fallback else "")
                        + f" — مطلوب لـ{spec['needed_for']}",
                        "أضف الدور إلى قالب الدليل أو إلى حساب مناسب", role=role))
                continue
            if account["type"] not in spec["types"]:
                found.append(self._f(
                    "CORE_ROLE_TYPE_INVALID", HIGH,
                    f"الحساب {account['code']} بدور {role} نوعه {account['type']} "
                    f"والمتوقع {'/'.join(spec['types'])}",
                    "صحّح نوع الحساب أو انقل الدور", role=role,
                    reference=[account["code"]]))
            if account.get("is_group"):
                found.append(self._f(
                    "CORE_ROLE_NOT_POSTABLE", HIGH,
                    f"الحساب {account['code']} بدور {role} حساب مجموعة ولا يقبل الترحيل",
                    "انقل الدور إلى حساب تفصيلي", role=role))
            if account.get("is_active") is False:
                found.append(self._f(
                    "CORE_ROLE_INACTIVE", MEDIUM,
                    f"الحساب {account['code']} بدور {role} غير نشط",
                    "أعد تنشيطه قبل أي عملية تحتاجه", role=role))
        return found, {"accounts": len(rows), "roles": roles_report,
                       "missing_parents": len(missing_parents), "cycles": len(cycles)}

    # ------------------------------------------------------------------- periods
    async def _audit_periods(self, entity_id: str):
        periods = await self._periods.list_periods(entity_id)
        found = []
        invalid = [p["code"] for p in periods if p["start_date"] > p["end_date"]]
        if invalid:
            found.append(self._f("PERIOD_DATES_INVALID", CRITICAL,
                                 f"{len(invalid)} فترة تاريخ بدايتها بعد نهايتها",
                                 "أصلح تعريف الفترة", reference=invalid[:10]))
        overlaps, gaps = [], []
        ordered = sorted(periods, key=lambda p: p["start_date"])
        for prev, nxt in zip(ordered, ordered[1:]):
            if nxt["start_date"] <= prev["end_date"]:
                overlaps.append(f"{prev['code']}~{nxt['code']}")
            elif (nxt["start_date"] - prev["end_date"]).total_seconds() > 1:
                gaps.append(f"{prev['code']}→{nxt['code']}")
        if overlaps:
            found.append(self._f("PERIOD_OVERLAP", CRITICAL,
                                 f"{len(overlaps)} تداخل بين الفترات",
                                 "فترة واحدة لكل تاريخ — أصلح التعريف",
                                 reference=overlaps[:10]))
        if gaps:
            # A gap is a WARNING, not corruption: a year may legitimately not be generated.
            found.append(self._f("PERIOD_GAP", WARNING,
                                 f"{len(gaps)} فراغ زمني بين الفترات (ليس فساداً مالياً "
                                 f"— قد تكون سنة لم تُنشأ فتراتها)",
                                 "أنشئ فترات السنة الناقصة إن كانت مطلوبة",
                                 reference=gaps[:10]))
        inconsistent = [p["code"] for p in periods
                        if p["status"] == PERIOD_CLOSED and not p.get("closed_at")]
        if inconsistent:
            found.append(self._f("PERIOD_CLOSED_WITHOUT_RECORD", HIGH,
                                 f"{len(inconsistent)} فترة مغلقة بلا سجل إقفال "
                                 f"(من/متى/السبب)",
                                 "راجع سجل الفترة — الإقفال يجب أن يسجّل المنفّذ والسبب",
                                 reference=inconsistent[:10]))
        return found, {"periods": len(periods),
                       "closed": sum(1 for p in periods
                                     if p["status"] == PERIOD_CLOSED),
                       "overlaps": len(overlaps), "gaps": len(gaps)}

    # ---------------------------------------------------------------- year close
    async def _audit_year_close(self, entity_id: str):
        ops = await self._periods.list_year_ops(entity_id)
        found = []
        for op in ops:
            state = op.get("state")
            if state not in YEAR_STATES:
                found.append(self._f("YEAR_OP_STATE_INVALID", HIGH,
                                     f"حالة عملية إقفال غير معروفة: {state}",
                                     "راجع حالة العملية", reference=[op.get("currency")]))
            if state in YEAR_ACTIVE_CLOSE_STATES and not op.get("journal_id"):
                found.append(self._f(
                    "YEAR_CLOSE_WITHOUT_JOURNAL", CRITICAL,
                    f"عملية إقفال ({op.get('fiscal_year')}/{op.get('currency')}) بحالة "
                    f"{state} بلا قيد إقفال",
                    "أعد تنفيذ الإقفال بنفس المفتاح — العملية قابلة للاستكمال"))
            if op.get("journal_id"):
                doc = await self._journal.get(entity_id, op["journal_id"])
                if not doc:
                    found.append(self._f(
                        "YEAR_CLOSE_JOURNAL_MISSING", CRITICAL,
                        f"قيد الإقفال المرتبط بالعملية "
                        f"({op.get('fiscal_year')}/{op.get('currency')}) غير موجود",
                        "تحقيق يدوي — قيد الإقفال لا يُحذف أبداً"))
                elif state == YEAR_STATE_REOPENED and doc.get("status") != "reversed":
                    found.append(self._f(
                        "REOPENED_WITH_ACTIVE_CLOSING", CRITICAL,
                        f"السنة ({op.get('fiscal_year')}/{op.get('currency')}) بحالة "
                        f"معاد فتحها لكن قيد الإقفال ما زال فعّالاً",
                        "أعد تنفيذ إعادة الفتح بنفس المفتاح لإكمال العكس"))
                elif state in YEAR_ACTIVE_CLOSE_STATES \
                        and doc.get("status") == "reversed":
                    found.append(self._f(
                        "CLOSED_WITH_REVERSED_CLOSING", CRITICAL,
                        f"السنة ({op.get('fiscal_year')}/{op.get('currency')}) مقفلة "
                        f"لكن قيد الإقفال معكوس",
                        "أكمل مسار إعادة الفتح المُحكم لتتسق الحالة"))
        # A closing journal with no operation record at all.
        journals = await self._journal.list_by_source_type(entity_id,
                                                            YEAR_CLOSE_SOURCE_TYPE)
        known = {o.get("journal_id") for o in ops}
        strays = [j["entry_no"] for j in journals if j["id"] not in known]
        if strays:
            found.append(self._f("CLOSING_JOURNAL_WITHOUT_OPERATION", HIGH,
                                 f"{len(strays)} قيد إقفال بلا عملية إقفال مسجّلة",
                                 "راجع سجل العمليات", reference=strays[:10]))
        years = {}
        for op in ops:
            years.setdefault(op.get("fiscal_year"), []).append(op)
        partial = [str(y) for y, rows in years.items()
                   if any(r.get("state") in YEAR_ACTIVE_CLOSE_STATES for r in rows)
                   and any(r.get("state") not in YEAR_ACTIVE_CLOSE_STATES
                           for r in rows)]
        if partial:
            found.append(self._f(
                "YEAR_CLOSE_PARTIAL_CURRENCIES", MEDIUM,
                f"سنوات مقفلة لبعض العملات فقط: {', '.join(partial)} — ليست حالة فساد، "
                f"لكن السنة ليست مقفلة بالكامل",
                "أقفل بقية العملات أو اعتبر السنة مقفلة جزئياً", reference=partial))
        return found, {"operations": len(ops),
                       "active_close": sum(1 for o in ops if o.get("state")
                                           in YEAR_ACTIVE_CLOSE_STATES),
                       "reopened": sum(1 for o in ops
                                       if o.get("state") == YEAR_STATE_REOPENED),
                       "partial_years": partial}

    # --------------------------------------------------------------- currency/FX
    async def _audit_currency_fx(self, entity_id: str):
        found = []
        config = await self._currencies.describe(entity_id)
        used = config["currencies_with_history"]
        if not config["configured"]:
            if used:
                found.append(self._f(
                    "BASE_CURRENCY_MISSING", HIGH,
                    f"توجد حركات بعملات {', '.join(used)} بلا تكوين عملات ولا عملة أساس",
                    "حدّد العملة الأساس والعملات المسموحة قبل أي عملية FX"))
        else:
            codes = {c["code"]: c for c in config["currencies"]}
            base = codes.get(config["base_currency"])
            if not base:
                found.append(self._f("BASE_CURRENCY_NOT_CONFIGURED", CRITICAL,
                                     "العملة الأساس غير موجودة في قائمة العملات",
                                     "أعد تكوين العملات"))
            elif not base.get("active", True):
                found.append(self._f("BASE_CURRENCY_INACTIVE", CRITICAL,
                                     f"العملة الأساس {base['code']} معطّلة",
                                     "أعد تنشيط العملة الأساس"))
            missing = [c for c in used if c not in codes]
            if missing:
                found.append(self._f(
                    "CURRENCY_HISTORY_NOT_CONFIGURED", HIGH,
                    f"عملات لها حركات وغير مكوّنة: {', '.join(missing)}",
                    "أضفها إلى التكوين (يمكن تعطيلها لكن لا تُزال)", reference=missing))
        rates = await self._rates.list_rates(entity_id, limit=500)
        invalid = []
        for r in rates:
            value = r.get("rate")
            value = value.to_decimal() if hasattr(value, "to_decimal") else value
            if value is None or value <= 0 or not r.get("effective_date") \
                    or r.get("from_currency") == r.get("to_currency"):
                invalid.append(r.get("id"))
        if invalid:
            found.append(self._f("FX_RATE_INVALID", CRITICAL,
                                 f"{len(invalid)} سعر صرف غير صالح",
                                 "راجع السجلات — لا يُعدَّل سعر مستخدم، يُضاف سعر جديد",
                                 reference=invalid[:10]))
        # A journal that recorded an FX rate reference whose record no longer exists.
        refs = await self._journal.fx_rate_references(entity_id)
        rate_ids = {r["id"] for r in rates}
        dangling = [r for r in refs if r and r not in rate_ids]
        if dangling:
            found.append(self._f(
                "FX_RATE_REFERENCE_MISSING", HIGH,
                f"{len(dangling)} قيد يشير إلى سجل سعر صرف غير موجود",
                "لا تُعدَّل القيود — أعد إدخال سجل السعر بنفس المعرّف أو وثّق الفارق",
                reference=dangling[:10]))
        return found, {"configured": config["configured"],
                       "base_currency": config["base_currency"],
                       "currencies_with_history": used, "rates": len(rates),
                       "invalid_rates": len(invalid),
                       "dangling_rate_references": len(dangling)}

    # ------------------------------------------------------------------ equation
    async def _audit_equation(self, entity_id: str):
        found, per_currency = [], []
        currencies = await self._journal.entity_currencies(entity_id)
        accounts = await self._accounts.list_all(entity_id, include_inactive=True)
        by_code = {a["code"]: a for a in accounts}
        for currency in currencies:
            totals = await self._journal.sum_totals(entity_id, currency)
            difference = totals["debit"] - totals["credit"]
            movements = await self._journal.sum_by_account(entity_id, currency)
            sums = {t: ZERO for t in (AccountType.ASSET.value,
                                      AccountType.LIABILITY.value,
                                      AccountType.EQUITY.value,
                                      AccountType.REVENUE.value,
                                      AccountType.EXPENSE.value)}
            for code, mv in movements.items():
                account = by_code.get(code)
                if not account:
                    continue
                sums[account["type"]] += signed_movement(account["type"], mv["debit"],
                                                          mv["credit"])
            result = sums[AccountType.REVENUE.value] - sums[AccountType.EXPENSE.value]
            equation = sums[AccountType.ASSET.value] - (
                sums[AccountType.LIABILITY.value] + sums[AccountType.EQUITY.value]
                + result)
            row = {"currency": currency,
                   "total_debit": as_str(totals["debit"]),
                   "total_credit": as_str(totals["credit"]),
                   "trial_balance_difference": as_str(difference),
                   "equation_difference": as_str(equation),
                   "balanced": difference == ZERO and equation == ZERO}
            per_currency.append(row)
            if difference != ZERO:
                found.append(self._f(
                    "TRIAL_BALANCE_IMBALANCE", CRITICAL,
                    f"ميزان المراجعة بعملة {currency} غير متوازن (الفرق "
                    f"{row['trial_balance_difference']})",
                    "تحقيق محاسبي — لا إقفال فترة أو سنة قبل التوازن",
                    currency=currency))
            if equation != ZERO:
                found.append(self._f(
                    "ACCOUNTING_EQUATION_BROKEN", CRITICAL,
                    f"معادلة الميزانية بعملة {currency} غير متوازنة (الفرق "
                    f"{row['equation_difference']})",
                    "تحقيق محاسبي فوري", currency=currency))
        return found, {"per_currency": per_currency,
                       "currency_mixing": "impossible by construction — every report and "
                                          "every check above is scoped to ONE currency"}
