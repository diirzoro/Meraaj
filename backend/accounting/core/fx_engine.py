"""FX conversion + realized FX result posting (Phase 10C).

TRACEABILITY
  FXConversionService.convert ← Rahaal inline `amount * rate` on JS floats      PORT + HARDEN (Decimal, explicit rate record)
  FX gain/loss accounts       ← Rahaal hardcoded `4104` / `5201`                 ADAPT (semantic roles only)
  FX difference posting       ← Rahaal `updateBalance` side-effect               HARDEN (balanced journal only)
  unrealized revaluation      ← Rahaal periodic revaluation                      DEFERRED — FX REVALUATION

PRECISION BOUNDARY (declared, and different on purpose):
  • rate scale        = 8  (a rate is not money)
  • calculation scale = 12 (intermediate multiplication only)
  • posting scale     = the Phase 3 money policy (2) — applied ONCE, at the boundary where
                        the amount becomes a journal line. The money policy is NOT changed.

MULTI-CURRENCY JOURNAL POLICY — UNCHANGED: one journal = one currency. FX is represented by
a conversion RESULT expressed in one currency and, when it has a financial effect, by a
balanced journal in that currency. The Phase 3 invariant is deliberately not reopened.
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from bson.decimal128 import Decimal128

from .errors import AccountingError
from .fx_rates import RATE_DIRECTION, RATE_SELECTION_POLICY
from .journal import JournalEntryDraft, JournalLineInput, utc_now
from .money import DEFAULT_SCALE, ZERO, as_str, normalise, to_amount
from .roles import FX_ADJUSTMENT, FX_GAIN, FX_LOSS, FX_RESULT

CALC_SCALE = 12
FX_SOURCE_TYPE = "fx_result"
#: Roles are resolved in order; the Core never names an account CODE.
GAIN_ROLE_CHAIN = (FX_GAIN, FX_RESULT)
LOSS_ROLE_CHAIN = (FX_LOSS, FX_ADJUSTMENT)
SUPPORTED_EFFECTS = ("realized_fx_difference",)
DEFERRED_EFFECTS = {"unrealized_revaluation": "DEFERRED — FX REVALUATION"}


class FXConversionService:
    """Read-only. Converts an amount using ONE declared direction and ONE declared rate
    selection policy, and always returns the rate it used so the figure is reproducible."""

    def __init__(self, rate_service, currency_service):
        self._rates = rate_service
        self._currencies = currency_service

    async def convert(self, entity_id: str, amount, from_currency: str,
                      to_currency: Optional[str] = None, date=None) -> dict:
        entity_id = str(entity_id or "").strip()
        if not entity_id:
            raise AccountingError("ENTITY_REQUIRED", "الجهة المحاسبية مطلوبة")
        base = await self._currencies.base_currency(entity_id)
        frm = str(from_currency).strip().upper()
        to = str(to_currency).strip().upper() if to_currency else base
        original = to_amount(amount, field="amount")
        if original <= ZERO:
            raise AccountingError("INVALID_AMOUNT",
                                  "مبلغ التحويل يجب أن يكون أكبر من صفر")
        accounting_date = date or utc_now()
        if getattr(accounting_date, "tzinfo", None) is None:
            from datetime import timezone
            accounting_date = accounting_date.replace(tzinfo=timezone.utc)

        if frm == to:
            return {"entity_id": entity_id, "original_amount": as_str(original),
                    "from_currency": frm, "to_currency": to, "rate": "1",
                    "converted_amount": as_str(original), "identity": True,
                    "rate_id": None, "rate_effective_date": None, "rate_source": None,
                    "direction": RATE_DIRECTION,
                    "selection_policy": RATE_SELECTION_POLICY,
                    "calculation_scale": CALC_SCALE, "posting_scale": DEFAULT_SCALE}

        rate_doc = await self._rates.resolve(entity_id, frm, to, accounting_date)
        rate = rate_doc["rate"].to_decimal() if isinstance(rate_doc["rate"], Decimal128) \
            else Decimal(str(rate_doc["rate"]))
        raw = (original * rate).quantize(Decimal(1).scaleb(-CALC_SCALE),
                                          rounding=ROUND_HALF_UP)
        converted = normalise(raw, DEFAULT_SCALE)
        return {
            "entity_id": entity_id, "original_amount": as_str(original),
            "from_currency": frm, "to_currency": to, "rate": format(rate, "f"),
            "raw_converted_amount": format(raw, "f"),
            "converted_amount": as_str(converted), "identity": False,
            "rate_id": rate_doc["id"],
            "rate_effective_date": rate_doc["effective_date"].isoformat(),
            "rate_source": rate_doc.get("source"),
            "direction": RATE_DIRECTION, "selection_policy": RATE_SELECTION_POLICY,
            "calculation_scale": CALC_SCALE, "posting_scale": DEFAULT_SCALE,
            "rounding": "ROUND_HALF_UP once, at the posting boundary",
            "accounting_date": accounting_date.isoformat(),
        }


class FXResultService:
    """The only FX path with a financial effect, and it produces a BALANCED JOURNAL through
    the single write gateway. No `$inc`, no cached FX balance, no direct account mutation."""

    def __init__(self, posting_service, conversion_service, account_store,
                 currency_service):
        self._posting = posting_service
        self._conversion = conversion_service
        self._accounts = account_store
        self._currencies = currency_service

    async def post_realized_difference(self, entity_id: str, account_code: str,
                                       amount, source_key: str,
                                       currency: Optional[str] = None,
                                       date=None, description: Optional[str] = None,
                                       by: Optional[str] = None,
                                       fx_metadata: Optional[dict] = None) -> dict:
        """A REALIZED FX difference: the settlement already happened, so the difference is
        a real gain or loss. `amount > 0` = gain, `amount < 0` = loss, expressed in the
        posting currency (the base currency unless one is given explicitly).

        Unrealized revaluation is NOT half-built here — see DEFERRED_EFFECTS.
        """
        entity_id = str(entity_id or "").strip()
        if not entity_id:
            raise AccountingError("ENTITY_REQUIRED", "الجهة المحاسبية مطلوبة")
        if not by:
            raise AccountingError("ACTOR_REQUIRED", "هوية المنفّذ مطلوبة")
        if not source_key or not str(source_key).strip():
            raise AccountingError(
                "SOURCE_KEY_REQUIRED",
                "مفتاح العملية (source_key) إلزامي لكل أثر مالي لفروق العملة — "
                "لمنع تكرار قيد التحويل عند إعادة المحاولة")
        posting_currency = str(currency).strip().upper() if currency \
            else await self._currencies.base_currency(entity_id)
        signed = to_amount(amount, field="amount")
        if signed == ZERO:
            raise AccountingError("FX_DIFFERENCE_ZERO",
                                  "فرق العملة صفر — لا يوجد أثر محاسبي لترحيله")

        account = await self._accounts.get_by_code(entity_id, str(account_code).strip())
        if not account:
            raise AccountingError("ACCOUNT_NOT_FOUND",
                                  f"الحساب {account_code} غير موجود في هذه الجهة", 404)
        if account.get("is_group"):
            raise AccountingError("GROUP_ACCOUNT_NOT_POSTABLE",
                                  f"الحساب {account_code} حساب مجموعة", 409)

        is_gain = signed > ZERO
        magnitude = signed if is_gain else -signed
        result_account = await self._resolve_role(
            entity_id, GAIN_ROLE_CHAIN if is_gain else LOSS_ROLE_CHAIN,
            "ربح" if is_gain else "خسارة")
        memo = "فرق عملة محقق"
        if is_gain:
            lines = [
                JournalLineInput(account_code=account["code"], debit=magnitude,
                                 credit=ZERO, currency=posting_currency, memo=memo),
                JournalLineInput(account_code=result_account["code"], debit=ZERO,
                                 credit=magnitude, currency=posting_currency,
                                 memo=memo)]
        else:
            lines = [
                JournalLineInput(account_code=result_account["code"], debit=magnitude,
                                 credit=ZERO, currency=posting_currency, memo=memo),
                JournalLineInput(account_code=account["code"], debit=ZERO,
                                 credit=magnitude, currency=posting_currency,
                                 memo=memo)]

        draft = JournalEntryDraft(
            date=date, currency=posting_currency, source_type=FX_SOURCE_TYPE,
            source_id=None, lines=lines,
            description=(description or f"فرق عملة محقق ({posting_currency})"))
        # Rate metadata travels as NON-FINANCIAL journal metadata, so a historical FX
        # figure can be reproduced from the journal itself.
        metadata = {"fx": {"effect": "realized_fx_difference",
                           "direction": RATE_DIRECTION,
                           "selection_policy": RATE_SELECTION_POLICY,
                           **(fx_metadata or {})}}
        result = await self._posting.post(entity_id, draft,
                                          source_key=str(source_key).strip(), by=by,
                                          metadata=metadata)
        result["fx"] = {"effect": "realized_fx_difference",
                        "kind": "gain" if is_gain else "loss",
                        "amount": as_str(magnitude),
                        "currency": posting_currency,
                        "result_account": result_account["code"],
                        "result_account_role": result_account.get("role"),
                        "counterpart_account": account["code"],
                        "correction_path": "reversal only — never edit or delete",
                        "deferred": DEFERRED_EFFECTS}
        return result

    async def _resolve_role(self, entity_id: str, chain, label: str) -> dict:
        for role in chain:
            account = await self._accounts.find_one_by_role(entity_id, role)
            if account:
                if account.get("is_group"):
                    raise AccountingError(
                        "GROUP_ACCOUNT_NOT_POSTABLE",
                        f"حساب فروق العملة ({account['code']}) حساب مجموعة", 409)
                return account
        raise AccountingError(
            "FX_RESULT_ACCOUNT_MISSING",
            f"لا يوجد حساب بدور {' أو '.join(chain)} في دليل هذه الجهة — ترحيل "
            f"{label} فروق العملة يحتاج دوراً محاسبياً (لا رقم حساب ثابت)", 409)

    def describe(self) -> dict:
        return {"supported_effects": list(SUPPORTED_EFFECTS),
                "deferred_effects": DEFERRED_EFFECTS,
                "journal_policy": "one journal = one currency (Phase 3 invariant kept)",
                "gain_role_chain": list(GAIN_ROLE_CHAIN),
                "loss_role_chain": list(LOSS_ROLE_CHAIN),
                "idempotency": "source_key required; retry replays the existing journal",
                "correction": "Reversal Engine only — FX journals are immutable",
                "period_guard": "FX posting passes the central validator, so a closed "
                                "period blocks it like any other journal"}
