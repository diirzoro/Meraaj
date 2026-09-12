"""THE central journal validator — the single choke point every journal must pass.

WHY THIS EXISTS (the headline defect of the reference implementation):
In Rahaal, `createJournalEntry()` performed NO validation at all — it built the document and
inserted it. Balance checking lived in `createManualJournal` only, so every AUTOMATIC posting
path (tickets, visas, packages, the Meraaj bridge, FX) could insert an unbalanced journal
silently; the imbalance was detectable afterwards only by running `validateTenant`. Likewise
`validateJournalLines` was called by some paths and not others, and the closed-period check
was duplicated per route (and missing from the manual-journal path).

The Core removes that entire class of bug structurally: "debit = credit", "no negatives",
"no posting to a group account", "account belongs to this entity", "currency is allowed" and
"the period is open" are ENGINE INVARIANTS enforced in one place. No business route decides
them, and no future path can bypass them, because the posting phase will be built on
`assert_valid()` — a journal that has not passed through here has no way to become posted.

TRACEABILITY
  JournalValidator.validate()        ← Rahaal `validateJournalLines`                  PORT + HARDEN
  balance enforcement                ← Rahaal `createManualJournal` (|D-C| > 0.01)    PORT + HARDEN (exact, central)
  negative-amount rejection          ← Rahaal `if (d < 0 || c < 0)`                   PORT
  "line with an amount needs a real account" ← Rahaal `hasAmount && (!code || code==='MANUAL')`  PORT
  group-posting block                ← Rahaal F-008                                   PORT
  minimum two lines                  ← Rahaal `createManualJournal`                   PORT
  future-date rejection              ← Rahaal `isFutureDocDate`                       PORT
  active-account block, both-sides block, precision block, cross-entity block          HARDEN / NEW

Phase 3 does NOT post, store, number or reverse anything. `assert_valid()` returns a
normalised, validated journal in memory and nothing else.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from .currency import CurrencyPolicy
from .errors import AccountingError
from .journal import (JournalEntryDraft, JournalLineInput, JournalStatus, utc_now)
from .money import ZERO, BALANCE_TOLERANCE, to_amount, as_str, DEFAULT_SCALE, normalise
from .periods import NULL_PERIOD_GUARD, PeriodGuard
from .posting_accounts import PostingAccountResolver

MIN_LINES = 2


@dataclass
class ValidatedLine:
    line_no: int
    account_code: str
    debit: Decimal
    credit: Decimal
    currency: str
    memo: Optional[str] = None

    def public(self) -> dict:
        return {"line_no": self.line_no, "account_code": self.account_code,
                "debit": as_str(self.debit), "credit": as_str(self.credit),
                "currency": self.currency, "memo": self.memo}


@dataclass
class ValidatedJournal:
    """A journal proven to satisfy every engine invariant. It carries NO id, NO entry number
    and NO status transition: it is an in-memory validation result, not a stored entry."""
    entity_id: str
    date: datetime
    description: str
    currency: str
    source_type: str
    source_id: Optional[str]
    lines: List[ValidatedLine]
    total_debit: Decimal
    total_credit: Decimal
    status: JournalStatus = JournalStatus.DRAFT
    warnings: List[str] = field(default_factory=list)

    def public(self) -> dict:
        return {
            "entity_id": self.entity_id,
            "date": self.date.isoformat(),
            "description": self.description,
            "currency": self.currency,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "status": self.status.value,
            "lines": [l.public() for l in self.lines],
            "total_debit": as_str(self.total_debit),
            "total_credit": as_str(self.total_credit),
            "balanced": self.total_debit == self.total_credit,
            "warnings": self.warnings,
        }


class JournalValidator:
    def __init__(self, resolver: PostingAccountResolver, currency_policy: CurrencyPolicy,
                 period_guard: Optional[PeriodGuard] = None,
                 scale: int = DEFAULT_SCALE):
        self.resolver = resolver
        self.currency = currency_policy
        # Phase 3 ships the open guard; the closing phase injects the real one and every
        # journal is covered at once, with no route to update.
        self.period = period_guard or NULL_PERIOD_GUARD
        self.scale = scale

    # ------------------------------------------------------------------ public
    async def assert_valid(self, entity_id: str,
                           draft: JournalEntryDraft) -> ValidatedJournal:
        """Raise on the FIRST violation (Rahaal's behaviour, with its line numbers) and
        return the normalised journal when everything holds."""
        entity_id = self._require_entity(entity_id)
        date = self._normalise_date(draft.date)
        lines = self._check_shape(draft)
        entry_currency = (self.currency.normalise(draft.currency)
                          if draft.currency else None)

        # One entity-scoped query for the whole journal (Rahaal's batching, ported).
        codes = [l.account_code for l in lines]
        accounts = await self.resolver.load(entity_id, codes)

        validated, currencies = [], []
        total_debit, total_credit = ZERO, ZERO
        for idx, line in enumerate(lines, start=1):
            debit, credit = self._check_debit_credit(line, idx)
            code = line.account_code
            if not code:
                raise AccountingError(
                    "ACCOUNT_REQUIRED",
                    f"يجب اختيار حساب معتمد من دليل الحسابات (السطر {idx})")
            account = accounts.get(code)
            if not account:
                cross = await self.resolver.exists_in_other_entity(entity_id, code)
                raise self.resolver.missing(entity_id, code, idx, cross)
            self.resolver.assert_postable(account, line_no=idx)

            line_currency = self.currency.normalise(line.currency or entry_currency
                                                    or draft.currency, line_no=idx)
            currencies.append(line_currency)
            total_debit += debit
            total_credit += credit
            validated.append(ValidatedLine(line_no=idx, account_code=code, debit=debit,
                                           credit=credit, currency=line_currency,
                                           memo=line.memo))

        # Single-currency only in this phase: a mixed-currency journal is REJECTED, never
        # accepted by a model that cannot verify its balance.
        journal_currency = self.currency.assert_single_currency(currencies)
        if entry_currency and entry_currency != journal_currency:
            raise AccountingError(
                "INVALID_CURRENCY",
                f"عملة القيد ({entry_currency}) لا تطابق عملة السطور ({journal_currency})")

        total_debit, total_credit = normalise(total_debit, self.scale), \
            normalise(total_credit, self.scale)
        self._check_balanced(total_debit, total_credit, journal_currency)

        # The period gate lives HERE, not in a business route.
        await self.period.assert_open(entity_id, date)

        warnings = []
        if not self.period.enforced:
            warnings.append("period_guard_not_enforced: no closing mechanism exists yet")
        return ValidatedJournal(
            entity_id=entity_id, date=date, description=draft.description.strip(),
            currency=journal_currency, source_type=draft.source_type,
            source_id=draft.source_id, lines=validated, total_debit=total_debit,
            total_credit=total_credit, status=JournalStatus.DRAFT, warnings=warnings)

    async def validate(self, entity_id: str, draft: JournalEntryDraft) -> dict:
        """Non-raising wrapper for a dry-run report. Validation only: nothing is stored,
        numbered, posted or reversed."""
        try:
            journal = await self.assert_valid(entity_id, draft)
            return {"ok": True, "errors": [], "journal": journal.public(),
                    "persisted": False, "posted": False}
        except AccountingError as exc:
            return {"ok": False, "errors": [exc.to_dict()], "journal": None,
                    "persisted": False, "posted": False}

    # ----------------------------------------------------------------- checks
    @staticmethod
    def _require_entity(entity_id: str) -> str:
        if not entity_id or not str(entity_id).strip():
            raise AccountingError("ENTITY_REQUIRED", "الجهة المحاسبية (entity) مطلوبة")
        return str(entity_id).strip()

    @staticmethod
    def _normalise_date(value: Optional[datetime]) -> datetime:
        """PORT — Rahaal `isFutureDocDate`: a journal may not be dated in the future.
        ADAPT — naive datetimes are treated as UTC; the Core never guesses a business
        timezone (Rahaal hardcoded UTC+3, which is a project setting, not an accounting
        rule, and belongs to the reporting phase)."""
        date = value or utc_now()
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        if date > utc_now():
            raise AccountingError("FUTURE_DATE_NOT_ALLOWED",
                                  "لا يمكن تسجيل قيد بتاريخ مستقبلي")
        return date

    @staticmethod
    def _check_shape(draft: JournalEntryDraft) -> List[JournalLineInput]:
        lines = list(draft.lines or [])
        if not lines:
            raise AccountingError("JOURNAL_NO_LINES", "القيد لا يحتوي أي سطور")
        if len(lines) < MIN_LINES:
            raise AccountingError(
                "JOURNAL_TOO_FEW_LINES",
                f"القيد المزدوج يحتاج {MIN_LINES} سطرين على الأقل (مدين ودائن)")
        if not draft.description or not draft.description.strip():
            raise AccountingError("DESCRIPTION_REQUIRED", "بيان القيد مطلوب")
        return lines

    def _check_debit_credit(self, line: JournalLineInput, line_no: int):
        """The unambiguous rule, stated once:
             a line is EITHER  debit  > 0 and credit = 0
                        OR     credit > 0 and debit  = 0
        Rejected: negatives (PORT), both sides non-zero (HARDEN — Rahaal allowed it), both
        sides zero i.e. a line with no accounting value (HARDEN — Rahaal skipped such lines
        and let them into the document), and non-finite/over-precise amounts (HARDEN).
        """
        debit = to_amount(line.debit, field="debit", line_no=line_no, scale=self.scale)
        credit = to_amount(line.credit, field="credit", line_no=line_no, scale=self.scale)
        if debit < ZERO or credit < ZERO:
            raise AccountingError(
                "INVALID_DEBIT_CREDIT",
                f"لا يُسمح بقيم سالبة في القيد (المدين={as_str(debit)}، "
                f"الدائن={as_str(credit)}) — السطر {line_no}")
        if debit > ZERO and credit > ZERO:
            raise AccountingError(
                "INVALID_DEBIT_CREDIT",
                f"لا يجوز أن يحتوي السطر مديناً ودائناً في وقت واحد — السطر {line_no}")
        if debit == ZERO and credit == ZERO:
            raise AccountingError(
                "EMPTY_LINE",
                f"السطر {line_no} بلا قيمة محاسبية — يجب إدخال مدين أو دائن أكبر من صفر")
        return debit, credit

    @staticmethod
    def _check_balanced(total_debit: Decimal, total_credit: Decimal,
                        currency: str) -> None:
        """HARDEN — Rahaal compared JavaScript floats with a 0.01 tolerance and only inside
        the manual path. Here the comparison is EXACT (decimals) and CENTRAL: for a
        single-currency journal, debit must equal credit within that currency.
        Multi-currency balancing is deferred to the currency engine, and until then a
        mixed-currency journal is rejected outright rather than mis-validated."""
        difference = total_debit - total_credit
        if abs(difference) > BALANCE_TOLERANCE:
            raise AccountingError(
                "JOURNAL_UNBALANCED",
                f"القيد غير متوازن بعملة {currency}: إجمالي المدين "
                f"{as_str(total_debit)} ≠ إجمالي الدائن {as_str(total_credit)} "
                f"(الفرق {as_str(difference)})")
