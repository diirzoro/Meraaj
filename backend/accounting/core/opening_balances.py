"""Opening Balances — a real POSTED journal, never a balance field. Not a migration.

TRACEABILITY
  OpeningBalanceService.open ← Rahaal `POST /journal-entries/opening`          PORT + HARDEN
  adjustment account         ← Rahaal `3103` (`is_system`)                     ADAPT (semantic role, not the number)
  asset/liability/equity restriction ← Rahaal's same restriction + its message PORT
  group / adjustment-account blocks  ← Rahaal                                  PORT
  `opening-equity-close`    ← Rahaal                                           DEFERRED (closing phase)
"""
from decimal import Decimal
from typing import List, Optional
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .errors import AccountingError
from .journal import JournalEntryDraft, JournalLineInput
from .money import ZERO, to_amount
from .roles import OPENING_BALANCE_SUSPENSE
from .types import AccountType

OPENING_SOURCE_TYPE = "opening_balance"
ELIGIBLE_TYPES = (AccountType.ASSET.value, AccountType.LIABILITY.value,
                  AccountType.EQUITY.value)


class OpeningLineInput(BaseModel):
    """Unambiguous by construction: exactly ONE side per account."""
    model_config = ConfigDict(extra="forbid")
    account_code: str = Field(min_length=1, max_length=32)
    debit: Decimal = Decimal("0")
    credit: Decimal = Decimal("0")
    memo: Optional[str] = Field(default=None, max_length=300)


class OpeningBalanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: datetime = Field(description="accounting opening date — mandatory")
    currency: str = Field(min_length=2, max_length=8)
    lines: List[OpeningLineInput] = Field(min_length=1)
    description: Optional[str] = Field(default=None, max_length=500)
    source_key: str = Field(min_length=3, max_length=200)
    allow_after_activity: bool = False


class OpeningBalanceService:
    def __init__(self, posting_service, journal_store, chart):
        self._posting = posting_service
        self._store = journal_store
        self._chart = chart

    async def open(self, entity_id: str, req: OpeningBalanceRequest,
                   by: Optional[str] = None) -> dict:
        if not entity_id or not str(entity_id).strip():
            raise AccountingError("ENTITY_REQUIRED", "الجهة المحاسبية مطلوبة")
        entity_id = str(entity_id).strip()
        if not req.date:
            raise AccountingError(
                "OPENING_DATE_REQUIRED",
                "تاريخ الرصيد الافتتاحي مطلوب — الافتتاح بداية دفتر ولا يُفترض تاريخه")
        currency = str(req.currency).strip().upper()

        # Duplicate-opening protection: ONE opening journal per (entity, currency). A
        # reversed opening no longer counts, so a correction is possible after a reversal.
        existing = await self._store.count_by_source_type(
            entity_id, OPENING_SOURCE_TYPE, currency=currency, exclude_reversed=True)
        if existing:
            raise AccountingError(
                "OPENING_ALREADY_EXISTS",
                f"يوجد قيد أرصدة افتتاحية مُرحَّل بعملة {currency} لهذه الجهة — "
                f"للتصحيح اعكس القيد القائم أولاً ثم أنشئ افتتاحاً جديداً", 409)

        # Existing-activity guard: never silently rewrite the beginning of a live ledger.
        activity = await self._store.count_other_activity(entity_id, OPENING_SOURCE_TYPE)
        if activity and not req.allow_after_activity:
            raise AccountingError(
                "LEDGER_HAS_ACTIVITY",
                f"الدفتر يحتوي {activity} قيداً مُرحَّلاً غير افتتاحي — إضافة أرصدة "
                f"افتتاحية الآن تغيّر بداية التاريخ وتحتاج مراجعة صريحة "
                f"(allow_after_activity)", 409, requires_review=True)

        adjustment = await self._chart.find_by_role(entity_id,
                                                    OPENING_BALANCE_SUSPENSE)
        adj_code = adjustment["code"]

        total_debit, total_credit = ZERO, ZERO
        lines: List[JournalLineInput] = []
        seen = set()
        for idx, line in enumerate(req.lines, start=1):
            code = str(line.account_code).strip()
            if code in seen:
                raise AccountingError("DUPLICATE_OPENING_ACCOUNT",
                                      f"الحساب {code} مكرر في نفس عملية الافتتاح")
            seen.add(code)
            if code == adj_code:
                raise AccountingError(
                    "ADJUSTMENT_ACCOUNT_NOT_ALLOWED",
                    f"حساب تسوية الأرصدة الافتتاحية ({adj_code}) يُستخدم للموازنة "
                    f"داخلياً ولا يُدخَل كرصيد افتتاحي")
            account = await self._chart.find_by_code(entity_id, code)
            if account.get("is_group"):
                raise AccountingError(
                    "GROUP_ACCOUNT_NOT_POSTABLE",
                    f"الحساب {code} حساب مجموعة — الرصيد الافتتاحي على الحساب "
                    f"التفصيلي فقط")
            if account.get("is_active") is False:
                raise AccountingError(
                    "ACCOUNT_INACTIVE",
                    f"الحساب {code} غير نشط — لا يمكن فتح رصيد افتتاحي عليه")
            if account.get("role"):
                raise AccountingError(
                    "SYSTEM_ROLE_ACCOUNT_NOT_ALLOWED",
                    f"الحساب {code} مرتبط بدور محاسبي نظامي ({account['role']}) ولا "
                    f"يُستخدم كرصيد افتتاحي مباشر")
            if account["type"] not in ELIGIBLE_TYPES:
                raise AccountingError(
                    "OPENING_TYPE_NOT_ALLOWED",
                    f"الرصيد الافتتاحي مسموح للأصول والخصوم وحقوق الملكية فقط — "
                    f"الحساب {code} من نوع {account['type']}. نتيجة الإيرادات "
                    f"والمصروفات تحتاج سياسة سنة مالية/إقفال مستقلة")
            debit = to_amount(line.debit, field="debit", line_no=idx)
            credit = to_amount(line.credit, field="credit", line_no=idx)
            if debit > ZERO and credit > ZERO:
                raise AccountingError("INVALID_DEBIT_CREDIT",
                                      f"لا يجوز مدين ودائن معاً للحساب {code}")
            if debit == ZERO and credit == ZERO:
                raise AccountingError("EMPTY_LINE",
                                      f"الحساب {code} بلا قيمة افتتاحية")
            total_debit += debit
            total_credit += credit
            lines.append(JournalLineInput(account_code=code, debit=debit, credit=credit,
                                          currency=currency, memo=line.memo))

        # The balancing line against the adjustment account — the journal must balance
        # exactly, and the Core computes the side rather than trusting the caller.
        difference = total_debit - total_credit
        if difference > ZERO:
            lines.append(JournalLineInput(account_code=adj_code, debit=ZERO,
                                          credit=difference, currency=currency,
                                          memo="موازنة الأرصدة الافتتاحية"))
        elif difference < ZERO:
            lines.append(JournalLineInput(account_code=adj_code, debit=-difference,
                                          credit=ZERO, currency=currency,
                                          memo="موازنة الأرصدة الافتتاحية"))
        else:
            raise AccountingError(
                "OPENING_ALREADY_BALANCED",
                "مجموع المدين يساوي الدائن فلا حاجة لحساب التسوية — راجع المدخلات")

        draft = JournalEntryDraft(
            date=req.date, currency=currency, source_type=OPENING_SOURCE_TYPE,
            source_id=None, lines=lines,
            description=(req.description or f"أرصدة افتتاحية ({currency})"))
        # Posted through the ONE write gateway: same validator, same idempotency, same
        # entry numbering. No direct collection write exists here.
        result = await self._posting.post(entity_id, draft,
                                          source_key=req.source_key, by=by)
        result["opening"] = True
        result["adjustment_account"] = adj_code
        return result
