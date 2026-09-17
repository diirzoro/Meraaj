"""Currency policy BOUNDARY — no FX engine, and no project currency inside the Core.

Rahaal hardcoded `CURRENCIES = ['USD','SAR','YER']` and `BASE_CURRENCY = 'YER'` in its
source. The Core must never know a project's currencies, so the allowed set (and the
optional base currency) are INJECTED by the host project's adapter.

Phase 3 supports SINGLE-CURRENCY journals only, and says so out loud: a journal whose lines
carry more than one currency is REJECTED with `MULTI_CURRENCY_UNSUPPORTED` rather than being
accepted by a model that cannot yet balance it. Rejecting an unsupported case is the only
safe behaviour — accepting it would let a structurally invalid journal into the system.

The line-level `currency` field is preserved (Rahaal's design, and the right one), so the
multi-currency engine can later add: base currency, FX rates, FX difference accounts and
per-currency balancing WITHOUT changing the line model.
"""
from typing import Optional, Sequence

from .errors import AccountingError


class CurrencyPolicy:
    def __init__(self, allowed: Sequence[str], base: Optional[str] = None,
                 allow_multi_currency: bool = False):
        cleaned = [str(c).strip().upper() for c in allowed if str(c).strip()]
        if not cleaned:
            raise ValueError("CurrencyPolicy requires at least one allowed currency")
        self.allowed = tuple(dict.fromkeys(cleaned))
        self.base = base.strip().upper() if base else None
        if self.base and self.base not in self.allowed:
            raise ValueError("base currency must be one of the allowed currencies")
        # Multi-currency balancing needs FX conversion, which belongs to its own phase.
        self.allow_multi_currency = bool(allow_multi_currency)

    def normalise(self, currency: Optional[str], *, line_no: int = None) -> str:
        where = f" (السطر {line_no})" if line_no else ""
        if not currency or not str(currency).strip():
            raise AccountingError("INVALID_CURRENCY", f"العملة مطلوبة{where}")
        code = str(currency).strip().upper()
        if code not in self.allowed:
            raise AccountingError(
                "INVALID_CURRENCY",
                f"عملة غير مدعومة: {code}{where} — العملات المسموحة: "
                f"{', '.join(self.allowed)}")
        return code

    def assert_single_currency(self, currencies: Sequence[str]) -> str:
        distinct = sorted(set(currencies))
        if len(distinct) == 1:
            return distinct[0]
        if not distinct:
            # Unreachable from the validator (a line without a currency is rejected before
            # this point); kept as an explicit refusal rather than a silent default.
            raise AccountingError("INVALID_CURRENCY",
                                  "لا يمكن تحديد عملة القيد — لا توجد سطور بعملة صالحة")
        if not self.allow_multi_currency:
            raise AccountingError(
                "MULTI_CURRENCY_UNSUPPORTED",
                f"القيد يحتوي أكثر من عملة ({', '.join(distinct)}) — القيود متعددة "
                f"العملات غير مدعومة في هذه المرحلة (تحتاج محرك أسعار الصرف وحسابات "
                f"فروق العملة)، ولن يُقبل قيد لا يمكن التحقق من توازنه")
        raise AccountingError(
            "MULTI_CURRENCY_NOT_IMPLEMENTED",
            "معالجة القيود متعددة العملات لم تُنفَّذ بعد")

    def describe(self) -> dict:
        return {"allowed": list(self.allowed), "base": self.base,
                "multi_currency_supported": False}
