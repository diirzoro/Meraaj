"""The BRIDGE: a business financial event → a balanced journal in the central ledger.

TRACEABILITY
  bridge                ← Rahaal inline journal building inside business routes  ADAPT
  business balance write← Rahaal `updateBalance` inside the same helper          LEAVE (kept apart)

TWO SEPARATE EFFECTS, NEVER MERGED:
  • BUSINESS effect  — `adjust_wallet` / `log_txn` stay exactly as they are (business
    remains the source of truth for the operation's own state and balance).
  • ACCOUNTING effect — a balanced journal in `meraaj-platform`, the accounting source of
    truth. The bridge NEVER touches a wallet, never `$inc`s a balance and never re-uses a
    journal to move a business balance.

NO ATOMICITY IS CLAIMED across the two. Instead: a deterministic `source_key` (so a retry
replays), and a read-only reconciliation that DETECTS any business event whose journal is
missing. A failed journal never rolls back a completed business operation, and never
silently disappears — it is recorded as a failure and stays detectable.
"""
from decimal import Decimal
from typing import Optional

from ..core import AccountingError, JournalEntryDraft, JournalLineInput
from ..core.journal import utc_now
from .events import FINANCIAL_EVENTS, build_source_key

FAILURE_COLLECTION_SUFFIX = "integration_failures"


class AccountingBridge:
    def __init__(self, database, entity_id: str, posting_service, link_service,
                 collection_prefix: str = "accounting_"):
        self._db = database
        self._entity = entity_id
        self._posting = posting_service
        self._links = link_service
        self._prefix = collection_prefix

    @property
    def failures(self):
        return self._db[f"{self._prefix}{FAILURE_COLLECTION_SUFFIX}"]

    # ------------------------------------------------------------------ public API
    async def post_event(self, event: str, *, event_id: str, currency: str,
                         amount, lines, business_actor: dict,
                         accounting_actor: Optional[dict] = None,
                         description: str = "", date=None,
                         business_ref: Optional[dict] = None,
                         raise_on_error: bool = False) -> dict:
        """`lines` = [(link_key, "debit"|"credit", amount)] — resolved through the link
        service, so no account number is ever named by business code.

        BUSINESS ACTOR ≠ ACCOUNTING ACTOR: both identities are carried into the journal
        metadata (and the accounting actor is the `by` of the posting), because the person
        who made the sale is not necessarily the person who posted its journal.
        """
        spec = FINANCIAL_EVENTS.get(event)
        if not spec:
            raise AccountingError("UNKNOWN_FINANCIAL_EVENT",
                                  f"حدث مالي غير معروف: {event}", 400)
        if not spec.posts_journal:
            return {"posted": False, "skipped": True, "event": event,
                    "reason": "declared_non_accounting_event", "note": spec.note}

        source_key = build_source_key(self._entity, spec.business_object, event, event_id)
        actor = (accounting_actor or business_actor or {})
        by = actor.get("label") or actor.get("id") or "system"
        try:
            journal_lines = []
            for link_key, side, value in lines:
                resolved = await self._links.resolve(self._entity, link_key)
                value = Decimal(str(value))
                journal_lines.append(JournalLineInput(
                    account_code=resolved["account_code"],
                    debit=value if side == "debit" else Decimal("0"),
                    credit=value if side == "credit" else Decimal("0"),
                    currency=currency,
                    memo=f"{spec.label_ar} — {link_key}"))
            draft = JournalEntryDraft(
                date=date or utc_now(), currency=currency,
                source_type=event, source_id=str(event_id),
                description=description or spec.label_ar, lines=journal_lines)
            metadata = {"business": {
                "event": event, "business_object": spec.business_object,
                "business_object_id": str(event_id),
                "business_actor_id": (business_actor or {}).get("id"),
                "business_actor": (business_actor or {}).get("label"),
                "accounting_actor_id": actor.get("id"),
                "accounting_actor": by,
                "actor_kind": actor.get("kind", "human"),
                **(business_ref or {})}}
            result = await self._posting.post(self._entity, draft,
                                              source_key=source_key, by=by,
                                              metadata=metadata)
            await self.failures.delete_many({"source_key": source_key})
            result["event"] = event
            result["source_key"] = source_key
            return result
        except AccountingError as exc:
            # The business operation already happened. The accounting gap is RECORDED and
            # stays detectable/retryable — it is never swallowed and never auto-fixed.
            await self._record_failure(event, event_id, source_key, currency, amount,
                                       exc, by)
            if raise_on_error:
                raise
            return {"posted": False, "failed": True, "event": event,
                    "source_key": source_key, "error": exc.code,
                    "message": exc.message,
                    "note": "الأثر التجاري تم، والأثر المحاسبي فشل ومسجّل وقابل "
                            "للاستدراك بنفس المفتاح (يظهر في المطابقة)"}
        except Exception as exc:  # noqa: BLE001
            # A completed business operation must never be broken by the accounting side.
            # Unexpected failures are recorded with the same key and remain retryable.
            await self._record_failure(
                event, event_id, source_key, currency, amount,
                type("E", (), {"code": "UNEXPECTED_ACCOUNTING_ERROR",
                               "message": str(exc)})(), by)
            if raise_on_error:
                raise
            return {"posted": False, "failed": True, "event": event,
                    "source_key": source_key, "error": "UNEXPECTED_ACCOUNTING_ERROR",
                    "message": str(exc)}

    async def _record_failure(self, event, event_id, source_key, currency, amount,
                              exc, by) -> None:
        await self.failures.update_one(
            {"source_key": source_key},
            {"$set": {"entity_id": self._entity, "event": event,
                      "business_object_id": str(event_id), "currency": currency,
                      "amount": str(amount), "error_code": exc.code,
                      "error_message": exc.message, "actor": by,
                      "last_attempt_at": utc_now(), "resolved": False},
             "$inc": {"attempts": 1}},
            upsert=True)

    async def list_failures(self, limit: int = 100) -> list:
        return await self.failures.find({"entity_id": self._entity}, {"_id": 0}) \
            .sort([("last_attempt_at", -1)]).to_list(length=min(limit, 500))
