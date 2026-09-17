"""Period lifecycle — generate, preflight, CLOSE (= lock dates), REOPEN.

TRACEABILITY
  close period            ← Rahaal `closed_years` push on tenant_settings      PORT + HARDEN (documents + preflight)
  reopen                  ← Rahaal `closed_years` pull (history lost)           PORT + HARDEN (history appended, never erased)
  close preflight         ← Rahaal `validateTenant` run manually, after the fact NEW (mandatory, before the lock)
  balance recalculation on close ← Rahaal                                        LEAVE (no cached balance exists)

WHAT "CLOSE" MEANS HERE: it locks accounting DATES. It does not rewrite a journal, does not
delete anything, does not touch a balance (none is stored) and never uses `$inc`.
"""
import uuid
from typing import Optional

from .errors import AccountingError
from .fiscal_year import FiscalYearPolicy
from .journal import utc_now
from .money import ZERO, as_str
from .periods import PERIOD_CLOSED, PERIOD_OPEN
from .year_state import YEAR_ACTIVE_CLOSE_STATES

PERIOD_CODE_FMT = "FY{year}-P{seq:02d}"


class PeriodService:
    def __init__(self, period_store, journal_store, account_store):
        self._periods = period_store
        self._journal = journal_store
        self._accounts = account_store

    # ------------------------------------------------------------ fiscal config
    async def policy(self, entity_id: str) -> FiscalYearPolicy:
        return FiscalYearPolicy.from_doc(await self._periods.get_fiscal(entity_id))

    async def configure_fiscal(self, entity_id: str, start_month: int, start_day: int,
                               period_length: str, by: Optional[str] = None) -> dict:
        entity_id = self._entity(entity_id)
        policy = FiscalYearPolicy(int(start_month), int(start_day),
                                  str(period_length)).validate()
        existing = await self._periods.list_periods(entity_id)
        if existing:
            # Changing the year boundary after periods exist would silently re-slice
            # history, so it is refused rather than applied.
            raise AccountingError(
                "FISCAL_CONFIG_LOCKED",
                f"توجد {len(existing)} فترة محاسبية مُنشأة لهذه الجهة — تغيير بداية "
                f"السنة المالية يعيد تقسيم التاريخ ويحتاج قراراً مستقلاً", 409)
        await self._periods.set_fiscal(entity_id, {**policy.as_dict(),
                                                   "configured_by": by,
                                                   "configured_at": utc_now()})
        return {"configured": True, "entity_id": entity_id, "fiscal": policy.as_dict()}

    # ------------------------------------------------------- period generation
    async def generate_year(self, entity_id: str, fiscal_year: int,
                            by: Optional[str] = None) -> dict:
        entity_id = self._entity(entity_id)
        fiscal_year = int(fiscal_year)
        policy = await self.policy(entity_id)
        if await self._periods.list_periods(entity_id, fiscal_year):
            raise AccountingError(
                "PERIODS_ALREADY_EXIST",
                f"فترات السنة المالية {fiscal_year} منشأة مسبقاً لهذه الجهة", 409)
        now = utc_now()
        docs = []
        for slot in policy.periods_of(fiscal_year):
            docs.append({
                "id": str(uuid.uuid4()), "entity_id": entity_id,
                "code": PERIOD_CODE_FMT.format(year=fiscal_year, seq=slot["sequence"]),
                "fiscal_year": fiscal_year, "sequence": slot["sequence"],
                "start_date": slot["start_date"], "end_date": slot["end_date"],
                "status": PERIOD_OPEN,
                "closed_at": None, "closed_by": None, "close_reason": None,
                "reopened_at": None, "reopened_by": None, "reopen_reason": None,
                "history": [], "created_at": now, "created_by": by,
                "updated_at": now,
            })
        await self._periods.insert_many(docs)
        return {"created": len(docs), "entity_id": entity_id,
                "fiscal_year": fiscal_year, "fiscal": policy.as_dict(),
                "periods": [self.public(d) for d in docs]}

    # ------------------------------------------------------------------- reads
    @staticmethod
    def public(doc: dict) -> dict:
        def iso(v):
            return v.isoformat() if hasattr(v, "isoformat") else v
        return {"id": doc["id"], "code": doc["code"],
                "fiscal_year": doc["fiscal_year"], "sequence": doc.get("sequence"),
                "start_date": iso(doc["start_date"]), "end_date": iso(doc["end_date"]),
                "status": doc["status"],
                "closed_at": iso(doc.get("closed_at")), "closed_by": doc.get("closed_by"),
                "close_reason": doc.get("close_reason"),
                "reopened_at": iso(doc.get("reopened_at")),
                "reopened_by": doc.get("reopened_by"),
                "reopen_reason": doc.get("reopen_reason"),
                "history": [{**h, "at": iso(h.get("at"))}
                            for h in (doc.get("history") or [])]}

    async def list_periods(self, entity_id: str,
                           fiscal_year: Optional[int] = None) -> dict:
        entity_id = self._entity(entity_id)
        docs = await self._periods.list_periods(entity_id, fiscal_year)
        return {"entity_id": entity_id, "fiscal": (await self.policy(entity_id)).as_dict(),
                "items": [self.public(d) for d in docs]}

    async def period_for_date(self, entity_id: str, date) -> dict:
        entity_id = self._entity(entity_id)
        doc = await self._periods.find_containing(entity_id, date)
        return {"entity_id": entity_id, "date": date.isoformat(),
                "period": self.public(doc) if doc else None,
                "posting_allowed": not (doc and doc["status"] == PERIOD_CLOSED),
                "note": "تاريخ بلا فترة معرّفة ليس مغلقاً — عدم وجود فترة ليس إقفالاً"}

    # --------------------------------------------------------------- preflight
    async def close_preflight(self, entity_id: str, period_id: str) -> dict:
        """Every critical inconsistency BLOCKS the close. Each currency is verified
        INDEPENDENTLY — a balanced SAR book never compensates an unbalanced USD book."""
        entity_id = self._entity(entity_id)
        period = await self._require_period(entity_id, period_id)
        blockers, warnings = [], []
        if period["status"] == PERIOD_CLOSED:
            blockers.append({"code": "PERIOD_ALREADY_CLOSED",
                             "message": f"الفترة {period['code']} مغلقة بالفعل"})
        if not await self._accounts.count_accounts(entity_id):
            warnings.append({"code": "CHART_NOT_SEEDED",
                             "message": "لا يوجد دليل حسابات لهذه الجهة"})

        start, end = period["start_date"], period["end_date"]
        integrity = await self._journal.audit_integrity(entity_id, start, end)
        for key, code, msg in (
            ("malformed", "MALFORMED_JOURNALS",
             "قيود بلا سطور/بلا عملة/بلا تاريخ أو بإجماليات غير متوافقة"),
            ("unbalanced", "UNBALANCED_JOURNALS", "قيود غير متوازنة داخل الفترة"),
            ("pending_reversal_claims", "REVERSAL_CLAIM_PENDING",
             "عمليات عكس غير مكتملة (claim معلّق) داخل الفترة"),
            ("reversed_without_mirror", "REVERSAL_INCONSISTENT",
             "قيود بحالة معكوس بلا قيد مرآة مقابل"),
        ):
            count = integrity.get(key) or 0
            if count:
                blockers.append({"code": code, "count": count, "message": msg,
                                 "sample": integrity.get(f"{key}_sample") or []})

        currencies = []
        for currency in integrity.get("currencies") or []:
            sums = await self._journal.sum_totals(entity_id, currency, start, end)
            difference = sums["debit"] - sums["credit"]
            row = {"currency": currency, "total_debit": as_str(sums["debit"]),
                   "total_credit": as_str(sums["credit"]),
                   "difference": as_str(difference), "balanced": difference == ZERO}
            currencies.append(row)
            if not row["balanced"]:
                blockers.append({
                    "code": "TRIAL_BALANCE_UNBALANCED", "currency": currency,
                    "message": f"ميزان المراجعة بعملة {currency} غير متوازن "
                               f"(الفرق {row['difference']})"})

        earlier_open = [p for p in await self._periods.list_periods(entity_id)
                        if p["end_date"] < start and p["status"] != PERIOD_CLOSED]
        if earlier_open:
            warnings.append({
                "code": "EARLIER_PERIODS_OPEN", "count": len(earlier_open),
                "message": "توجد فترات أقدم ما زالت مفتوحة — الإقفال بالتسلسل هو الأسلم",
                "codes": [p["code"] for p in earlier_open]})

        return {"entity_id": entity_id, "period": self.public(period),
                "journal_count": integrity.get("total") or 0,
                "currencies": currencies, "blockers": blockers, "warnings": warnings,
                "can_close": not blockers}

    # ------------------------------------------------------------------- close
    async def close(self, entity_id: str, period_id: str, reason: str,
                    by: Optional[str] = None, force_sequence: bool = False) -> dict:
        entity_id = self._entity(entity_id)
        reason = self._require_reason(reason, "سبب الإقفال مطلوب")
        by = self._require_actor(by)
        preflight = await self.close_preflight(entity_id, period_id)
        if preflight["blockers"]:
            raise AccountingError(
                "PERIOD_CLOSE_BLOCKED",
                "لا يمكن إقفال الفترة: توجد مخالفات محاسبية حرجة", 409,
                blockers=preflight["blockers"])
        sequence_warning = next((w for w in preflight["warnings"]
                                 if w["code"] == "EARLIER_PERIODS_OPEN"), None)
        if sequence_warning and not force_sequence:
            raise AccountingError(
                "EARLIER_PERIODS_OPEN",
                f"{sequence_warning['message']} ({', '.join(sequence_warning['codes'])})",
                409, periods=sequence_warning["codes"], requires_review=True)

        now = utc_now()
        updated = await self._periods.set_status(
            entity_id, period_id, PERIOD_OPEN, PERIOD_CLOSED,
            {"at": now,
             "set": {"closed_at": now, "closed_by": by, "close_reason": reason},
             "entry": {"action": "close", "at": now, "by": by, "reason": reason}})
        if not updated:
            raise AccountingError("PERIOD_CLOSE_CONFLICT",
                                  "تغيّرت حالة الفترة أثناء التنفيذ — أعد المحاولة", 409)
        return {"closed": True, "locks": "accounting dates only — no journal was "
                                          "rewritten, deleted or re-valued",
                "period": self.public(updated),
                "preflight_warnings": preflight["warnings"]}

    # ------------------------------------------------------------------ reopen
    async def reopen(self, entity_id: str, period_id: str, reason: str,
                     by: Optional[str] = None) -> dict:
        entity_id = self._entity(entity_id)
        reason = self._require_reason(reason, "سبب إعادة الفتح مطلوب")
        by = self._require_actor(by)
        period = await self._require_period(entity_id, period_id)
        if period["status"] != PERIOD_CLOSED:
            raise AccountingError("PERIOD_NOT_CLOSED",
                                  f"الفترة {period['code']} غير مغلقة")
        ops = [o for o in await self._periods.list_year_ops(entity_id,
                                                            period["fiscal_year"])
               if o.get("state") in YEAR_ACTIVE_CLOSE_STATES]
        if ops:
            # Reopening a period inside a CLOSED YEAR requires unwinding the closing
            # journals — a controlled financial workflow, not a status flip.
            raise AccountingError(
                "YEAR_CLOSED_REOPEN_DEFERRED",
                f"السنة المالية {period['fiscal_year']} مقفلة بقيود إقفال "
                f"({', '.join(o['currency'] for o in ops)}) — إعادة فتح فترة داخلها "
                f"تحتاج مسار إعادة الفتح المُحكم للسنة (POST /year-close/{{fy}}/reopen)، "
                f"ولن تُحذف قيود الإقفال بأي حال", 409,
                required_path="POST /api/accounting/year-close/{fiscal_year}/reopen")
        now = utc_now()
        # `closed_at/closed_by/close_reason` are intentionally NOT cleared — the close
        # actually happened, and erasing it would falsify the audit trail.
        updated = await self._periods.set_status(
            entity_id, period_id, PERIOD_CLOSED, PERIOD_OPEN,
            {"at": now,
             "set": {"reopened_at": now, "reopened_by": by, "reopen_reason": reason},
             "entry": {"action": "reopen", "at": now, "by": by, "reason": reason}})
        if not updated:
            raise AccountingError("PERIOD_REOPEN_CONFLICT",
                                  "تغيّرت حالة الفترة أثناء التنفيذ — أعد المحاولة", 409)
        return {"reopened": True,
                "close_history_preserved": True,
                "period": self.public(updated)}

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _entity(entity_id: str) -> str:
        entity_id = str(entity_id or "").strip()
        if not entity_id:
            raise AccountingError("ENTITY_REQUIRED", "الجهة المحاسبية مطلوبة")
        return entity_id

    @staticmethod
    def _require_reason(reason: str, message: str) -> str:
        if not reason or not str(reason).strip():
            raise AccountingError("REASON_REQUIRED", message)
        return str(reason).strip()

    @staticmethod
    def _require_actor(by: Optional[str]) -> str:
        if not by:
            raise AccountingError("ACTOR_REQUIRED", "هوية المنفّذ مطلوبة")
        return by

    async def _require_period(self, entity_id: str, period_id: str) -> dict:
        doc = await self._periods.get(entity_id, period_id) \
            or await self._periods.get_by_code(entity_id, period_id)
        if not doc:
            raise AccountingError("PERIOD_NOT_FOUND", "الفترة المحاسبية غير موجودة", 404)
        return doc
