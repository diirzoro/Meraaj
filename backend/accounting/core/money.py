"""Monetary representation for the Accounting Core.

DECISION (documented, no data exists yet so nothing is migrated):

  • In-Core representation .... `decimal.Decimal`, never `float`.
  • Parsing ................... ints/strings/Decimals are exact; a JSON float is converted
                                through `str(value)` so `0.1` becomes Decimal("0.1") and not
                                0.1000000000000000055511151231257827. A non-finite value
                                (NaN / Infinity) is rejected, never silently coerced.
  • Scale ..................... every amount is quantised to `DEFAULT_SCALE` (2) with
                                ROUND_HALF_UP at the boundary, BEFORE any arithmetic, so two
                                sides of a journal can never disagree by a rounding artefact.
  • Future DB representation .. BSON `Decimal128` (exact, no binary-float drift). Phase 3
                                stores nothing, so this is a recorded decision, not code.
  • Balance tolerance ......... ZERO. See BALANCE_TOLERANCE below.

HARDEN vs Rahaal: Rahaal computed money with JavaScript numbers (IEEE-754 binary floats) and
compensated with a fuzzy comparison `Math.abs(totalD - totalC) > 0.01`. That tolerance is a
symptom of the representation, not an accounting rule: it silently accepts a journal that is
off by up to one cent. With exact decimals the comparison can be exact, so the tolerance is
deliberately NOT ported and is fixed at zero.
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Optional, Union

from .errors import AccountingError

DEFAULT_SCALE = 2
ZERO = Decimal("0")
#: Upper magnitude accepted for a single monetary value. Anything larger cannot be
#: quantised inside the default decimal context, so it is rejected as a domain error
#: instead of surfacing an internal `InvalidOperation`.
MAX_AMOUNT = Decimal("9" * 18)          # 999,999,999,999,999,999
# Exact decimals make a fuzzy epsilon unnecessary — and a non-zero tolerance would let an
# unbalanced journal through. Kept as a named constant so the decision is explicit.
BALANCE_TOLERANCE = Decimal("0")

Amount = Union[int, str, Decimal, float]


def _quantum(scale: int) -> Decimal:
    return Decimal(1).scaleb(-scale)


def to_amount(value: Amount, *, field: str, line_no: Optional[int] = None,
              scale: int = DEFAULT_SCALE) -> Decimal:
    """Parse and quantise one monetary value, or raise a domain error.

    Rejects: None, empty, non-numeric text, NaN, Infinity, and any value that cannot be
    represented exactly at the configured scale without rounding away real precision
    (e.g. 10.005 at scale 2 is rejected rather than silently becoming 10.01 or 10.00).
    """
    where = f" (السطر {line_no})" if line_no else ""
    if value is None or (isinstance(value, str) and not value.strip()):
        return ZERO.quantize(_quantum(scale))
    try:
        raw = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError):
        raise AccountingError("INVALID_AMOUNT",
                              f"قيمة غير صالحة في الحقل {field}: {value!r}{where}")
    if not raw.is_finite():
        raise AccountingError("INVALID_AMOUNT",
                              f"قيمة مالية غير منتهية (NaN/Infinity) في {field}{where}")
    if abs(raw) > MAX_AMOUNT:
        # A finite value can still be too large to quantise inside the decimal context
        # (InvalidOperation). Refuse it as a DOMAIN error instead of leaking an internal
        # exception — the validator's contract is "raise AccountingError or return".
        raise AccountingError(
            "AMOUNT_OUT_OF_RANGE",
            f"قيمة الحقل {field} تتجاوز الحد الأقصى المسموح ({MAX_AMOUNT}){where}")
    try:
        quantised = raw.quantize(_quantum(scale), rounding=ROUND_HALF_UP)
    except (InvalidOperation, OverflowError):
        raise AccountingError(
            "AMOUNT_OUT_OF_RANGE",
            f"تعذر تمثيل قيمة الحقل {field} بدقة محاسبية: {raw}{where}")
    if quantised != raw:
        raise AccountingError(
            "INVALID_AMOUNT_PRECISION",
            f"دقة القيمة في {field} تتجاوز {scale} منزلة عشرية: {raw}{where} — "
            f"لا يقوم النظام بالتقريب نيابة عنك")
    return quantised


def normalise(value: Decimal, scale: int = DEFAULT_SCALE) -> Decimal:
    return value.quantize(_quantum(scale), rounding=ROUND_HALF_UP)


def as_str(value: Decimal) -> str:
    """Canonical string form used in API responses — no float ever crosses the boundary."""
    return format(value, "f")
