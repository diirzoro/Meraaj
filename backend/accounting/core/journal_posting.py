"""THE single write gateway for accounting truth.

    Draft/Input → Central Validation → Idempotency → Atomic Entry Number → POSTED → Immutable

Nothing else in the system may write a journal: the store is private to this service, there
is no `skip_validation` flag, no bypass for "automatic" sources, and no update or delete
path for a posted entry. This is the structural fix for the reference implementation, where
`createJournalEntry()` inserted straight into the collection from ~40 different call sites
with no validation and no idempotency.

TRACEABILITY
  post()                    ← Rahaal `createJournalEntry`                     PORT + HARDEN
  idempotency (source_key)  ← Rahaal `meraaj_booking_ref` + `postLockId` mutex PORT + HARDEN (DB-unique)
  entry_no allocation       ← (no Rahaal equivalent)                          NEW
  fingerprint/conflict      ← (no Rahaal equivalent)                          NEW
  quota check               ← Rahaal `journal_quota`                          LEAVE (commercial logic)
  updateBalance()           ← Rahaal cached balances                          LEAVE (never in the Core)
"""
import hashlib
import json
import uuid
from typing import Optional

from .errors import AccountingError
from .journal import JournalEntryDraft, JournalStatus, utc_now
from .journal_store import IDEMPOTENCY_INDEX, JournalStore
from .journal_validator import JournalValidator, ValidatedJournal
from .money import as_str

#: Source types treated as MANUAL: a human is entering the journal, so no external
#: operation exists to be idempotent about, and `source_key` stays optional.
MANUAL_SOURCE_TYPES = ("manual",)
ENTRY_NO_PREFIX = "JE"
ENTRY_NO_PAD = 6


def financial_fingerprint(journal: ValidatedJournal) -> str:
    """Deterministic identity of the FINANCIAL content of a journal.

    Included (the things that make it this journal and not another):
        entity_id, currency, source_type, source_id,
        and the multiset of lines as (account_code, debit, credit, line currency),
        sorted so JSON/line ordering can never change the fingerprint.

    Deliberately EXCLUDED:
        • date and any timestamp — a retry arrives later, and the server generates `date`
          when the caller omits it, so including it would break every legitimate retry
        • description and line memos — wording is not financial identity
        • actor — the same operation retried by another worker is still the same operation
        • entry_no / id — assigned by us, not by the caller
    No business semantics enter the fingerprint: the Core hashes accounting facts only.

    CALLER CONTRACT (must be honoured by every non-manual producer): ONE `source_key` per
    real financial operation, never a reused or shared key. The fingerprint detects a key
    reused with DIFFERENT amounts (→ IDEMPOTENCY_CONFLICT); it cannot detect two genuinely
    distinct operations that reuse one key AND happen to carry identical amounts — those
    would be answered as a replay. Key construction is the producer's responsibility (it
    owns the operation identity); the Core treats the key as an opaque string.
    """
    payload = {
        "entity_id": journal.entity_id,
        "currency": journal.currency,
        "source_type": journal.source_type,
        "source_id": journal.source_id,
        "lines": sorted([[l.account_code, as_str(l.debit), as_str(l.credit), l.currency]
                         for l in journal.lines]),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def format_entry_no(sequence: int) -> str:
    """`JE-000001` — entity-scoped and CONTINUOUS (not reset per year).

    A yearly sequence would require a fiscal-year definition, which belongs to the
    period-closing phase and is not decided yet; a continuous counter is the simplest
    stable policy, is portable to any project, and never depends on a calendar.
    """
    return f"{ENTRY_NO_PREFIX}-{sequence:0{ENTRY_NO_PAD}d}"


class JournalPostingService:
    def __init__(self, validator: JournalValidator, store: JournalStore):
        self._validator = validator
        self._store = store

    async def post(self, entity_id: str, draft: JournalEntryDraft,
                   source_key: Optional[str] = None,
                   by: Optional[str] = None,
                   metadata: Optional[dict] = None) -> dict:
        """`metadata` (Phase 10 COMPATIBILITY FIX, minimal): NON-FINANCIAL context stored
        alongside the entry — currently the FX rate snapshot, so a historical FX figure is
        reproducible from the journal itself. It is EXCLUDED from the fingerprint (it is
        not financial identity) and it can never add, change or balance a line."""
        # 1) CENTRAL VALIDATION — the same assert_valid() as the dry-run. No second
        #    validator exists, and there is no way to reach persistence without it.
        journal = await self._validator.assert_valid(entity_id, draft)
        entity_id = journal.entity_id

        # 2) IDEMPOTENCY POLICY
        source_key = (str(source_key).strip() or None) if source_key else None
        if not source_key and draft.source_type not in MANUAL_SOURCE_TYPES:
            raise AccountingError(
                "SOURCE_KEY_REQUIRED",
                f"مصدر القيد '{draft.source_type}' مصدر آلي/خارجي — مفتاح العملية "
                f"(source_key) إلزامي لمنع تكرار القيد عند إعادة المحاولة")
        fingerprint = financial_fingerprint(journal)

        if source_key:
            existing = await self._store.find_by_source_key(entity_id, source_key)
            if existing:
                return self._replay_or_conflict(existing, fingerprint, source_key)

        # 3) ATOMIC ENTRY NUMBER — allocated AFTER the idempotency pre-check so a retry
        #    of an already-posted operation does not burn a number.
        sequence = await self._store.allocate_entry_no(entity_id)
        entry_no = format_entry_no(sequence)
        now = utc_now()
        doc = {
            "id": str(uuid.uuid4()),
            "entity_id": entity_id,
            "entry_no": entry_no,
            "entry_seq": sequence,
            "status": JournalStatus.POSTED.value,
            "date": journal.date,
            "description": journal.description,
            "currency": journal.currency,
            "lines": [{
                "line_no": line.line_no,
                "account_code": line.account_code,
                "debit": self._store.to_db_amount(line.debit),
                "credit": self._store.to_db_amount(line.credit),
                "currency": line.currency,
                "memo": line.memo,
            } for line in journal.lines],
            "total_debit": self._store.to_db_amount(journal.total_debit),
            "total_credit": self._store.to_db_amount(journal.total_credit),
            "source_type": journal.source_type,
            "source_id": journal.source_id,
            "source_key": source_key,          # absent-as-None: excluded from the index
            "fingerprint": fingerprint,
            "metadata": dict(metadata) if metadata else None,
            "reversal_of": None,
            "reversed_by_entry": None,
            "created_at": now,
            "created_by": by,
            "posted_at": now,
            "posted_by": by,
            "reversed_at": None,
            "reversed_by": None,
        }

        # 4) PERSIST — the unique index is the final authority under concurrency.
        inserted, duplicate_index = await self._store.insert_posted(doc)
        if not inserted:
            if duplicate_index == IDEMPOTENCY_INDEX and source_key:
                # A concurrent request won the race: re-read and answer idempotently.
                existing = await self._store.find_by_source_key(entity_id, source_key)
                if existing:
                    return self._replay_or_conflict(existing, fingerprint, source_key,
                                                    entry_no_wasted=entry_no)
            raise AccountingError(
                "JOURNAL_WRITE_CONFLICT",
                f"تعارض في كتابة القيد ({duplicate_index}) — لم يُحفظ أي قيد، أعد "
                f"المحاولة", 409)

        return {"posted": True, "idempotent_replay": False,
                **self.public(doc), "warnings": journal.warnings}

    # ---------------------------------------------------------------- idempotency
    @staticmethod
    def _replay_or_conflict(existing: dict, fingerprint: str, source_key: str,
                            entry_no_wasted: Optional[str] = None) -> dict:
        """Retry semantics:
          • same key + identical financial content → NOT a new journal; the existing entry
            is returned with `idempotent_replay: true`
          • same key + DIFFERENT financial content → never a silent success:
            `IDEMPOTENCY_CONFLICT`, because the same financial key producing different
            debits/credits means a bug or a reused key.
        """
        if existing.get("fingerprint") == fingerprint:
            result = {"posted": False, "idempotent_replay": True,
                      **JournalPostingService.public(existing)}
            if entry_no_wasted:
                result["entry_no_allocated_unused"] = entry_no_wasted
            return result
        raise AccountingError(
            "IDEMPOTENCY_CONFLICT",
            f"مفتاح العملية '{source_key}' مستخدم بالفعل للقيد "
            f"{existing.get('entry_no')} بمحتوى مالي مختلف — لن يُنشأ قيد جديد ولن "
            f"يُعتبر إعادة محاولة ناجحة", 409,
            existing_entry_no=existing.get("entry_no"),
            existing_entry_id=existing.get("id"))

    # --------------------------------------------------------------------- reads
    @staticmethod
    def public(doc: dict) -> dict:
        """Serialisation for the API: Decimal128 → canonical string, never a float."""
        return {
            "id": doc["id"],
            "entity_id": doc["entity_id"],
            "entry_no": doc.get("entry_no"),
            "status": doc.get("status"),
            "date": doc["date"].isoformat() if hasattr(doc.get("date"), "isoformat")
            else doc.get("date"),
            "description": doc.get("description"),
            "currency": doc.get("currency"),
            "lines": [{
                "line_no": line.get("line_no"),
                "account_code": line.get("account_code"),
                "debit": JournalStore.from_db_amount(line.get("debit")),
                "credit": JournalStore.from_db_amount(line.get("credit")),
                "currency": line.get("currency"),
                "memo": line.get("memo"),
            } for line in doc.get("lines", [])],
            "total_debit": JournalStore.from_db_amount(doc.get("total_debit")),
            "total_credit": JournalStore.from_db_amount(doc.get("total_credit")),
            "source_type": doc.get("source_type"),
            "source_id": doc.get("source_id"),
            "source_key": doc.get("source_key"),
            "fingerprint": doc.get("fingerprint"),
            "metadata": doc.get("metadata"),
            "reversal_of": doc.get("reversal_of"),
            "reversed_by_entry": doc.get("reversed_by_entry"),
            "created_at": doc["created_at"].isoformat()
            if hasattr(doc.get("created_at"), "isoformat") else doc.get("created_at"),
            "created_by": doc.get("created_by"),
            "posted_at": doc["posted_at"].isoformat()
            if hasattr(doc.get("posted_at"), "isoformat") else doc.get("posted_at"),
            "posted_by": doc.get("posted_by"),
            "immutable": True,
        }

    async def get(self, entity_id: str, entry_id: str) -> dict:
        doc = await self._store.get(entity_id, entry_id)
        if not doc:
            raise AccountingError("JOURNAL_NOT_FOUND", "القيد غير موجود", 404)
        return self.public(doc)

    async def get_by_source_key(self, entity_id: str, source_key: str) -> dict:
        doc = await self._store.find_by_source_key(entity_id, source_key)
        if not doc:
            raise AccountingError("JOURNAL_NOT_FOUND",
                                  "لا يوجد قيد بهذا المفتاح في هذه الجهة", 404)
        return self.public(doc)

    async def list_entries(self, entity_id: str, limit: int = 50,
                           source_type: Optional[str] = None) -> list:
        docs = await self._store.list_entries(entity_id, limit, source_type)
        return [self.public(d) for d in docs]
