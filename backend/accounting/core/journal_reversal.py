"""Reversal Engine — the ONLY way a posted entry is neutralised. Original never changes.

TRACEABILITY
  JournalReversalService.reverse ← Rahaal mirror entry in the Meraaj cancel/settlement paths  PORT + HARDEN
  mirror line construction       ← Rahaal debit/credit swap                                   PORT
  double-reversal prevention     ← Rahaal `findOne(prior)` + `postLockId` mutex               PORT + HARDEN (atomic claim + unique index)
  `deleteOne` + recreate         ← Rahaal manual-journal edit path                            LEAVE (rejected outright)
  refund / wallet semantics      ← Rahaal business paths                                      LEAVE (the Core knows none)
"""
import uuid
from typing import Optional

from .errors import AccountingError
from .journal import JournalStatus, utc_now
from .journal_posting import JournalPostingService, format_entry_no
from .journal_store import ENTRY_NO_INDEX, REVERSAL_INDEX
from .year_state import YEAR_CLOSE_SOURCE_TYPE
from datetime import timedelta

#: A claim older than this with no mirror journal is abandoned and may be reclaimed.
STALE_CLAIM_SECONDS = 120

REVERSAL_SOURCE_TYPE = "reversal"


class JournalReversalService:
    def __init__(self, journal_store, account_store, period_guard):
        self._store = journal_store
        self._accounts = account_store
        self._period = period_guard

    async def reverse(self, entity_id: str, original_id: str, reason: str,
                      by: Optional[str] = None, date=None,
                      source_key: Optional[str] = None,
                      allow_closing_reversal: bool = False) -> dict:
        """`allow_closing_reversal` is INTERNAL: only the controlled year-reopen workflow
        passes it. No HTTP route exposes it, so a year-closing journal can never be
        reversed through the generic reversal endpoint (which would leave the year state
        CLOSED while its closing effect had disappeared)."""
        entity_id = (entity_id or "").strip()
        if not entity_id:
            raise AccountingError("ENTITY_REQUIRED", "الجهة المحاسبية مطلوبة")
        if not reason or not str(reason).strip():
            raise AccountingError("REVERSAL_REASON_REQUIRED", "سبب العكس مطلوب")
        if not by:
            raise AccountingError("ACTOR_REQUIRED", "هوية المنفّذ مطلوبة")

        original = await self._store.get(entity_id, original_id)
        if not original:
            raise AccountingError("JOURNAL_NOT_FOUND", "القيد الأصلي غير موجود", 404)
        if original.get("source_type") == REVERSAL_SOURCE_TYPE:
            raise AccountingError(
                "REVERSAL_OF_REVERSAL_NOT_ALLOWED",
                "لا يجوز عكس قيد عكسي — أنشئ قيداً صحيحاً جديداً بدلاً من ذلك")
        if original.get("source_type") == YEAR_CLOSE_SOURCE_TYPE \
                and not allow_closing_reversal:
            # HARDEN: reversing a closing journal directly would desynchronise the year
            # state from the books. It must travel through the controlled reopen, which
            # also unlocks the periods and moves the operation state forward.
            raise AccountingError(
                "YEAR_CLOSE_REVERSAL_NOT_ALLOWED",
                f"القيد {original.get('entry_no')} قيد إقفال سنوي — لا يُعكس مباشرة؛ "
                f"استخدم مسار إعادة فتح السنة المُحكم حتى لا تتناقض حالة السنة مع "
                f"الدفاتر", 409,
                fiscal_year=original.get("source_id"),
                required_path="POST /api/accounting/year-close/{fiscal_year}/reopen")
        # DEFECT FIX (found in Phase 11A QA): the idempotency check runs BEFORE the
        # already-reversed check, so an identical RETRY of the same reversal request is an
        # idempotent replay instead of a 409. A different key against an already-reversed
        # entry still gets ALREADY_REVERSED below.
        key = (str(source_key).strip() if source_key else f"reversal:{original_id}")
        already = await self._store.find_by_source_key(entity_id, key)
        if already:
            return {"reversed": False, "idempotent_replay": True,
                    "reversal": JournalPostingService.public(already),
                    "original_entry_no": original.get("entry_no")}
        if original.get("status") == JournalStatus.REVERSED.value:
            existing = await self._store.find_reversal_of(entity_id, original_id)
            raise AccountingError(
                "ALREADY_REVERSED",
                f"القيد {original.get('entry_no')} معكوس مسبقاً بالقيد "
                f"{(existing or {}).get('entry_no')}", 409,
                reversal_entry_no=(existing or {}).get("entry_no"),
                reversal_entry_id=(existing or {}).get("id"))
        if original.get("status") != JournalStatus.POSTED.value:
            raise AccountingError("NOT_POSTED", "لا يمكن عكس قيد غير مُرحَّل")

        reversal_date = date or utc_now()
        if getattr(reversal_date, "tzinfo", None) is None:
            from datetime import timezone
            reversal_date = reversal_date.replace(tzinfo=timezone.utc)
        if reversal_date > utc_now():
            raise AccountingError("FUTURE_DATE_NOT_ALLOWED",
                                  "لا يمكن عكس قيد بتاريخ مستقبلي")
        # Same boundary as every other write. Not enforced until the closing phase.
        await self._period.assert_open(entity_id, reversal_date)

        lines = await self._mirror_lines(entity_id, original)

        reversal_id = str(uuid.uuid4())
        now = utc_now()
        # A4/A7 — CRASH RECOVERY: an earlier attempt may have claimed the original and
        # died before writing the mirror. If a mirror exists, finish the link; otherwise
        # the claim is completable/reclaimable without any manual DB edit.
        orphan = original.get("reversal_claim") or None
        if orphan:
            mirror = await self._store.find_reversal_of(entity_id, original_id)
            if mirror:
                await self._store.finalize_reversal(
                    entity_id, original_id, mirror["id"],
                    orphan.get("reason") or str(reason).strip(),
                    orphan.get("by") or by, utc_now())
                return {"reversed": False, "idempotent_replay": True,
                        "recovered": True,
                        "reversal": JournalPostingService.public(mirror),
                        "original_entry_no": original.get("entry_no")}
            reversal_id = orphan.get("reversal_id") or reversal_id

        # 1) ATOMIC CLAIM — status stays POSTED (a final accounting status is never used
        #    as a temporary lock); the filter itself is the concurrency guard.
        claimed = await self._store.claim_for_reversal(
            entity_id, original_id, reversal_id, str(reason).strip(), by, now,
            stale_before=now - timedelta(seconds=STALE_CLAIM_SECONDS))
        if not claimed:
            existing = await self._store.find_reversal_of(entity_id, original_id)
            raise AccountingError(
                "REVERSAL_IN_PROGRESS",
                "عملية عكس أخرى قائمة على هذا القيد — أعد المحاولة بعد لحظات", 409,
                reversal_entry_no=(existing or {}).get("entry_no"))

        # 2) Mirror entry, then compensate the claim if the insert fails.
        sequence = await self._store.allocate_entry_no(entity_id)
        doc = {
            "id": reversal_id, "entity_id": entity_id,
            "entry_no": format_entry_no(sequence), "entry_seq": sequence,
            "status": JournalStatus.POSTED.value, "date": reversal_date,
            "description": f"عكس القيد {original.get('entry_no')} — {reason}",
            "currency": original.get("currency"), "lines": lines,
            "total_debit": original.get("total_credit"),
            "total_credit": original.get("total_debit"),
            "source_type": REVERSAL_SOURCE_TYPE, "source_id": original_id,
            "source_key": key, "fingerprint": None,
            "reversal_of": original_id, "reversal_reason": str(reason).strip(),
            "reversed_by_entry": None,
            "created_at": now, "created_by": by,
            "posted_at": now, "posted_by": by,
            "reversed_at": None, "reversed_by": None,
        }
        inserted, duplicate_index = await self._store.insert_posted(doc)
        if inserted:
            # 3) FINALIZE — only now does the original become REVERSED.
            await self._store.finalize_reversal(entity_id, original_id, reversal_id,
                                                str(reason).strip(), by, now)
        if not inserted:
            released = await self._store.release_reversal_claim(entity_id, original_id,
                                                                reversal_id)
            raise AccountingError(
                "REVERSAL_WRITE_CONFLICT",
                f"تعذر إنشاء قيد العكس ({duplicate_index}) — "
                f"{'أُعيد القيد الأصلي إلى حالته' if released else 'راجع القيد الأصلي يدوياً'}",
                409, index=duplicate_index, claim_released=released)

        original_after = await self._store.get(entity_id, original_id)
        return {"reversed": True, "idempotent_replay": False,
                "reversal": JournalPostingService.public(doc),
                "original": JournalPostingService.public(original_after),
                "original_status": (original_after or {}).get("status"),
                "period_guard_enforced": self._period.enforced}

    async def _mirror_lines(self, entity_id: str, original: dict) -> list:
        """REVERSAL VALIDATION MODE — deliberately narrow, and not the normal validator.

        The accounts must still EXIST in the same entity, but an account deactivated AFTER
        the original was posted must not make history impossible to correct: so
        `ACCOUNT_INACTIVE` is not applied here. The mode cannot be abused to post a new
        journal on an inactive account because nothing is caller-supplied: accounts,
        amounts and currencies are copied verbatim from the original, debit and credit are
        merely swapped, and no line may be added, dropped or edited.
        """
        mirror = []
        for line in original.get("lines", []):
            code = line.get("account_code")
            account = await self._accounts.get_by_code(entity_id, code)
            if not account:
                raise AccountingError(
                    "ACCOUNT_NOT_FOUND",
                    f"حساب القيد الأصلي {code} غير موجود في الدليل — لا يمكن العكس", 409)
            if account.get("is_group"):
                raise AccountingError("GROUP_ACCOUNT_NOT_POSTABLE",
                                      f"الحساب {code} أصبح حساب مجموعة", 409)
            mirror.append({
                "line_no": line.get("line_no"), "account_code": code,
                "debit": line.get("credit"), "credit": line.get("debit"),
                "currency": line.get("currency"),
                "memo": f"عكس: {line.get('memo')}" if line.get("memo") else "عكس",
            })
        if not mirror:
            raise AccountingError("JOURNAL_NO_LINES", "القيد الأصلي بلا سطور")
        return mirror
