"""Journal Entry + Journal Line models, and the journal status model.

TRACEABILITY
  JournalLineInput   ← Rahaal JE line `{account_code, account_name, debit, credit, currency,
                       party_type, party_id, party_name}`                    PORT + ADAPT
  JournalEntryDraft  ← Rahaal `createJournalEntry({date, description, ref_type, ref_id,
                       currency, lines})` + `opts.extra`                     PORT + ADAPT
  JournalStatus      ← (no equivalent: in Rahaal "the document exists" meant "posted")  HARDEN
  entry_no           ← (no equivalent: Rahaal had no human-readable number)   NEW (boundary only)
  reversal_of / reversed_by_entry ← Rahaal reversal-by-mirror-entry in the Meraaj paths  NEW (fields only)

ADAPT — what a line is NOT allowed to know:
Rahaal lines carried `party_type/party_id/party_name` with the values `client | supplier |
box | manual | account | revenue | expense`, i.e. the ledger knew the business party model.
The generic line keeps ONLY the accounting facts (account, debit, credit, currency, memo).
Linking a subject (an office, a wallet, a campaign) to an account is the job of the account
linking phase, through the adapter — never of the Core.
"""
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class JournalStatus(str, Enum):
    """HARDEN — the single most important deviation from the reference implementation.

    Rahaal had no status at all: inserting a document meant it was posted, editing a manual
    journal meant DELETE + re-insert, and a reversal was detectable only by guessing from
    `ref_type`. The Core states the lifecycle explicitly:

      DRAFT    — exists, is validated on demand, has no accounting effect, may be edited or
                 discarded. Never carries an accounting entry number.
      POSTED   — accounting truth. IMMUTABLE: never edited, never deleted. A correction is a
                 new reversal entry plus a new entry, never a destructive rewrite.
      REVERSED — a posted entry that has been neutralised by a mirror entry. The ORIGINAL
                 survives untouched; `reversed_by_entry` points at the mirror.

    Phase 3 defines the states and their rules. It does NOT implement the transitions:
    there is no posting workflow and no reversal engine in this phase.
    """
    DRAFT = "draft"
    POSTED = "posted"
    REVERSED = "reversed"


#: Transitions the later phases are allowed to implement. Declared here so the state machine
#: lives with the model instead of being reinvented inside a route (Rahaal's mistake).
ALLOWED_TRANSITIONS = {
    JournalStatus.DRAFT: (JournalStatus.POSTED,),
    JournalStatus.POSTED: (JournalStatus.REVERSED,),
    JournalStatus.REVERSED: (),
}

#: A posted or reversed entry is frozen: no field of it may ever be rewritten in place.
IMMUTABLE_STATUSES = (JournalStatus.POSTED, JournalStatus.REVERSED)


class JournalLineInput(BaseModel):
    """One debit-or-credit line. `extra="forbid"`: a business module cannot smuggle
    `party_id`, `wallet_id`, `ad_id` or any other domain field into the ledger."""
    model_config = ConfigDict(extra="forbid")

    account_code: str = Field(min_length=1, max_length=32)
    debit: Decimal = Decimal("0")
    credit: Decimal = Decimal("0")
    currency: Optional[str] = None          # falls back to the entry currency, as in Rahaal
    memo: Optional[str] = Field(default=None, max_length=300)

    @field_validator("account_code")
    @classmethod
    def _clean_code(cls, v: str) -> str:
        return str(v).strip()


class JournalEntryDraft(BaseModel):
    """The generic input shape for any journal, from any source.

    There is deliberately no `booking_id`, `ad_id`, `wallet_id`, `office_id`, `ticket_id` or
    any other business field: a source identifies itself through the generic
    `source_type` / `source_id` pair (Rahaal's `ref_type`/`ref_id`, renamed to the neutral
    vocabulary of the memo).
    """
    model_config = ConfigDict(extra="forbid")

    date: Optional[datetime] = None
    description: str = Field(min_length=1, max_length=500)
    currency: Optional[str] = None
    source_type: str = Field(default="manual", min_length=1, max_length=64)
    source_id: Optional[str] = Field(default=None, max_length=128)
    lines: List[JournalLineInput] = Field(default_factory=list)

    @field_validator("source_type")
    @classmethod
    def _clean_source(cls, v: str) -> str:
        return str(v).strip().lower()


#: The document shape a journal will be stored in when the posting phase creates the
#: collection. Declared as a contract (no collection, no index, nothing written in Phase 3)
#: so the posting phase inherits the field names instead of inventing them.
JOURNAL_DOCUMENT_CONTRACT = {
    "id": "str(uuid4) — stable internal identifier, never reused",
    "entity_id": "str — accounting entity scope, mandatory on every read and write",
    "entry_no": "str|None — human-readable accounting number; allocated ONLY at posting "
                "time, atomically and entity-scoped. A draft never has one.",
    "date": "datetime (tz-aware, UTC)",
    "description": "str",
    "status": "draft | posted | reversed",
    "currency": "str — entry currency (single-currency journals in this phase)",
    "lines": "[{account_code, debit, credit, currency, memo}] — amounts as Decimal128",
    "total_debit": "Decimal128 — stored so a ledger read never re-adds the lines",
    "total_credit": "Decimal128",
    "source_type": "str — generic source discriminator (was Rahaal ref_type)",
    "source_id": "str|None — generic source identifier (was Rahaal ref_id)",
    "source_key": "DEFERRED to the idempotency phase, together with its unique index",
    "reversal_of": "str|None — id of the entry this entry reverses",
    "reversed_by_entry": "str|None — id of the mirror entry that reversed this entry",
    "created_at/created_by": "datetime / actor label",
    "posted_at/posted_by": "datetime / actor label — set by the posting phase",
    "reversed_at/reversed_by": "datetime / actor label — set by the reversal phase",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
