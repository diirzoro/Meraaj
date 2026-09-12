"""General Ledger — a DERIVED read model. No ledger collection, no stored balances.

TRACEABILITY
  GeneralLedgerService.account_ledger ← Rahaal `reportStatement` (party_type='account')  PORT + HARDEN
  normal_balance / signed_movement    ← Rahaal `signOf`                                  PORT
  opening_balance_for_range           ← Rahaal F-016 prior-period opening balance        PORT
  running balance                     ← Rahaal `run[cur]` accumulator                    PORT + HARDEN (Decimal, paging-safe)
  cached balances / updateBalance     ← Rahaal                                           LEAVE (never)
"""
from decimal import Decimal
from typing import Optional

from .errors import AccountingError
from .money import ZERO, as_str, normalise
from .types import AccountType

#: The one central place this accounting rule is expressed.
DEBIT_NORMAL = (AccountType.ASSET.value, AccountType.EXPENSE.value)
CREDIT_NORMAL = (AccountType.LIABILITY.value, AccountType.EQUITY.value,
                 AccountType.REVENUE.value)
MAX_PAGE = 200


def normal_balance(account_type: str) -> str:
    if account_type in DEBIT_NORMAL:
        return "debit"
    if account_type in CREDIT_NORMAL:
        return "credit"
    raise AccountingError("ACCOUNT_TYPE_INVALID",
                          f"نوع حساب غير معروف: {account_type}")


def signed_movement(account_type: str, debit: Decimal, credit: Decimal) -> Decimal:
    """PORT of Rahaal `signOf`: debit-normal = D−C, credit-normal = C−D."""
    return (debit - credit) if normal_balance(account_type) == "debit" \
        else (credit - debit)


class GeneralLedgerService:
    """Read-only. Sources: POSTED journal entries + the chart. Writes nothing, ever."""

    def __init__(self, journal_store, account_store):
        self._journal = journal_store
        self._accounts = account_store

    async def account_ledger(self, entity_id: str, account_code: str,
                             currency: Optional[str] = None,
                             from_date=None, to_date=None,
                             page: int = 1, page_size: int = 50) -> dict:
        if not entity_id or not str(entity_id).strip():
            raise AccountingError("ENTITY_REQUIRED", "الجهة المحاسبية مطلوبة")
        entity_id = str(entity_id).strip()
        code = str(account_code).strip()
        if from_date and to_date and from_date > to_date:
            raise AccountingError("INVALID_DATE_RANGE",
                                  "تاريخ البداية بعد تاريخ النهاية")
        page = max(1, int(page))
        page_size = max(1, min(int(page_size), MAX_PAGE))

        account = await self._accounts.get_by_code(entity_id, code)
        if not account:
            raise AccountingError("ACCOUNT_NOT_FOUND",
                                  f"الحساب {code} غير موجود في هذه الجهة", 404)
        # A historically inactive account MUST remain readable — deactivation hides an
        # account from new postings, never from its own history.
        if account.get("is_group"):
            raise AccountingError(
                "GROUP_ACCOUNT_LEDGER_UNSUPPORTED",
                f"الحساب {code} حساب مجموعة — الأستاذ يُقرأ على الحساب التفصيلي فقط "
                f"(تقارير المجموعات مرحلة لاحقة)")

        # Currency safety: two currencies are NEVER added together and never converted.
        available = await self._journal.line_currencies(entity_id, code)
        if currency:
            currency = str(currency).strip().upper()
        elif len(available) == 1:
            currency = available[0]
        elif len(available) > 1:
            raise AccountingError(
                "CURRENCY_REQUIRED",
                f"الحساب {code} يحتوي حركات بعملات متعددة ({', '.join(available)}) — "
                f"حدد العملة، فلا يجوز جمع عملتين في رصيد واحد")
        else:
            currency = None

        acc_type = account["type"]
        opening = ZERO
        if currency:
            # DEFECT FIX (found in Phase 11A QA): the range opening balance only exists
            # when a `from_date` is given. Without one, the range starts at the beginning
            # of the ledger, so the opening balance is ZERO — summing "everything before
            # no date" counted the whole history twice in `closing_balance`.
            before = await self._journal.sum_lines(entity_id, code, currency,
                                                   to_exclusive=from_date) \
                if from_date else {"debit": ZERO, "credit": ZERO}
            opening = signed_movement(acc_type, before["debit"], before["credit"])
            skipped = await self._journal.sum_lines(
                entity_id, code, currency, from_date=from_date, to_date=to_date,
                skip=(page - 1) * page_size) if page > 1 else {"debit": ZERO,
                                                               "credit": ZERO}
            # Paging never restarts the running balance from zero.
            page_start = opening + signed_movement(acc_type, skipped["debit"],
                                                   skipped["credit"])
            rows = await self._journal.ledger_lines(
                entity_id, code, currency, from_date=from_date, to_date=to_date,
                skip=(page - 1) * page_size, limit=page_size)
            period = await self._journal.sum_lines(entity_id, code, currency,
                                                   from_date=from_date, to_date=to_date)
        else:
            page_start, rows = ZERO, []
            period = {"debit": ZERO, "credit": ZERO, "count": 0}

        running = page_start
        items = []
        for r in rows:
            running = running + signed_movement(acc_type, r["debit"], r["credit"])
            items.append({
                "journal_id": r["journal_id"], "entry_no": r["entry_no"],
                "entry_seq": r["entry_seq"], "date": r["date"].isoformat(),
                "account_code": code, "debit": as_str(r["debit"]),
                "credit": as_str(r["credit"]), "currency": r["currency"],
                "description": r["description"], "memo": r.get("memo"),
                "source_type": r.get("source_type"), "source_id": r.get("source_id"),
                "status": r.get("status"), "posted_at": r["posted_at"].isoformat()
                if hasattr(r.get("posted_at"), "isoformat") else r.get("posted_at"),
                "running_balance": as_str(normalise(running)),
            })

        total_debit, total_credit = period["debit"], period["credit"]
        net = signed_movement(acc_type, total_debit, total_credit)
        return {
            "entity_id": entity_id,
            "account": {"code": code, "name_ar": account.get("name_ar"),
                        "type": acc_type, "normal_balance": normal_balance(acc_type),
                        "is_active": account.get("is_active", True)},
            "currency": currency,
            "available_currencies": available,
            "from_date": from_date.isoformat() if from_date else None,
            "to_date": to_date.isoformat() if to_date else None,
            "opening_balance_for_range": as_str(normalise(opening)),
            "page_opening_balance": as_str(normalise(page_start)),
            "total_debit": as_str(normalise(total_debit)),
            "total_credit": as_str(normalise(total_credit)),
            "net_movement": as_str(normalise(net)),
            "closing_balance": as_str(normalise(opening + net)),
            "movement_count": period.get("count", 0),
            "page": page, "page_size": page_size,
            "items": items,
            "derived": True, "stored_balances": False,
        }
