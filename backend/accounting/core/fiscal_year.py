"""Fiscal year — GENERIC and configurable. Never hardcoded January–December.

TRACEABILITY
  fiscal year definition ← Rahaal implicit calendar year (`new Date().getFullYear()`)  HARDEN
  period generation      ← (no Rahaal equivalent: Rahaal had no period documents)      NEW

REPRESENTATION (the simplest portable one): a fiscal year is fully described by
`start_month` + `start_day` + `period_length`. The fiscal year LABEL is the calendar year of
its START date — one rule, stated once, so "FY2026" is never ambiguous.
"""
from calendar import monthrange
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .errors import AccountingError

PERIOD_MONTH = "month"
PERIOD_QUARTER = "quarter"
PERIOD_LENGTHS = (PERIOD_MONTH, PERIOD_QUARTER)
DEFAULT_FISCAL = {"start_month": 1, "start_day": 1, "period_length": PERIOD_MONTH}
FISCAL_YEAR_LABEL_RULE = "the calendar year of the fiscal year START date"


@dataclass(frozen=True)
class FiscalYearPolicy:
    start_month: int = 1
    start_day: int = 1
    period_length: str = PERIOD_MONTH

    @classmethod
    def from_doc(cls, doc) -> "FiscalYearPolicy":
        doc = doc or DEFAULT_FISCAL
        return cls(int(doc.get("start_month", 1)), int(doc.get("start_day", 1)),
                   str(doc.get("period_length", PERIOD_MONTH)))

    def validate(self) -> "FiscalYearPolicy":
        if not 1 <= self.start_month <= 12:
            raise AccountingError("FISCAL_CONFIG_INVALID",
                                  "شهر بداية السنة المالية يجب أن يكون بين 1 و 12")
        if not 1 <= self.start_day <= 28:
            # Capped at 28 on purpose: a start day of 29–31 does not exist in every month,
            # so it cannot define a stable yearly boundary.
            raise AccountingError(
                "FISCAL_CONFIG_INVALID",
                "يوم بداية السنة المالية يجب أن يكون بين 1 و 28 (لضمان وجوده في كل شهر)")
        if self.period_length not in PERIOD_LENGTHS:
            raise AccountingError("FISCAL_CONFIG_INVALID",
                                  f"طول الفترة غير مدعوم: {self.period_length}")
        return self

    def as_dict(self) -> dict:
        return {"start_month": self.start_month, "start_day": self.start_day,
                "period_length": self.period_length,
                "fiscal_year_label_rule": FISCAL_YEAR_LABEL_RULE}

    # ------------------------------------------------------------------ geometry
    def year_start(self, fiscal_year: int) -> datetime:
        return datetime(int(fiscal_year), self.start_month, self.start_day,
                        tzinfo=timezone.utc)

    def year_end(self, fiscal_year: int) -> datetime:
        """Inclusive end: the last instant before the next fiscal year starts."""
        return self.year_start(int(fiscal_year) + 1) - timedelta(microseconds=1)

    def fiscal_year_of(self, date: datetime) -> int:
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        boundary = self.year_start(date.year)
        return date.year if date >= boundary else date.year - 1

    def periods_of(self, fiscal_year: int) -> list:
        """Contiguous, non-overlapping, gap-free periods covering exactly one fiscal year."""
        months = 1 if self.period_length == PERIOD_MONTH else 3
        start = self.year_start(fiscal_year)
        year_end = self.year_end(fiscal_year)
        out, index, cursor = [], 1, start
        while cursor <= year_end:
            nxt = self._add_months(cursor, months)
            end = min(nxt - timedelta(microseconds=1), year_end)
            out.append({"sequence": index, "start_date": cursor, "end_date": end})
            cursor, index = nxt, index + 1
        return out

    @staticmethod
    def _add_months(date: datetime, months: int) -> datetime:
        month = date.month - 1 + months
        year = date.year + month // 12
        month = month % 12 + 1
        day = min(date.day, monthrange(year, month)[1])
        return date.replace(year=year, month=month, day=day)
