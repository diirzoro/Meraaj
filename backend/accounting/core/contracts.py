"""Declared CORE CONTRACTS — the policies later phases and adapters must honour.

Nothing here executes accounting logic. These are the decisions that were previously
implicit (and therefore re-invented per call site), written down ONCE in the Core so an
adapter can implement them without guessing.

TRACEABILITY
  accounting date policy ← Rahaal UTC+3 hardcoded in helpers        ADAPT (policy, not a constant)
  source_key contract    ← Rahaal `meraaj_booking_ref` (one key per booking)  PORT + HARDEN (per financial EVENT)
  report limits          ← Rahaal unbounded `find().toArray()`      HARDEN
"""

# ---------------------------------------------------------------------------------------
# OPEN-016 — TIMEZONE / ACCOUNTING DATE POLICY
# ---------------------------------------------------------------------------------------
ACCOUNTING_DATE_POLICY = {
    "rule": "The accounting date of a journal is an EXPLICIT financial input, not a "
            "server clock reading. The Core stores it as a timezone-aware UTC datetime "
            "and never shifts it afterwards.",
    "producer_contract": "A producer that means 'the 31st of the month' must send that "
                         "date; the Core will not re-interpret it in a business timezone.",
    "server_timestamp_use": "utc_now() is used ONLY for audit stamps (created_at, "
                            "posted_at, closed_at, reversed_at) and as the fallback date "
                            "of a manual journal that omits one.",
    "naive_datetime": "treated as UTC (documented, never silently localised)",
    "hardcoded_offsets": "NONE — the Core contains no Yemen/Saudi/UTC+3 constant "
                         "(Rahaal hardcoded UTC+3 inside date helpers)",
    "entity_timezone": "NOT part of the Core: it changes nothing about the correctness of "
                       "an explicit accounting date. Presentation timezone belongs to the "
                       "UI/adapter layer.",
    "period_boundaries": "fiscal periods are UTC half-open ranges built from the fiscal "
                         "policy; a period end is inclusive to the last microsecond",
    "status": "OPEN-016 RESOLVED BY EXPLICIT ACCOUNTING-DATE POLICY",
}

# ---------------------------------------------------------------------------------------
# source_key — THE IDEMPOTENCY CONTRACT FOR ANY FUTURE ADAPTER
# ---------------------------------------------------------------------------------------
SOURCE_KEY_CONTRACT = {
    "purpose": "ONE key per FINANCIAL EFFECT, so a retry can never produce a second "
               "journal and two different effects can never collapse into one.",
    "shape": "{producer}:{entity_id}:{business_object}:{financial_event}:{event_id}",
    "example_generic": "ads:<entity_id>:campaign-9f31:charge:inv-2026-0007",
    "segments": {
        "producer": "the adapter/module that owns the operation (never the Core)",
        "entity_id": "the accounting entity the effect belongs to",
        "business_object": "stable identifier of the object (booking, campaign, wallet…)",
        "financial_event": "WHICH effect on that object (charge, refund, settlement, "
                           "commission, fee, payout…) — this segment is what makes two "
                           "effects on ONE object distinguishable",
        "event_id": "stable identifier of that specific occurrence (never a timestamp, "
                    "never a random value generated per attempt)",
    },
    "rules": [
        "deterministic: the same financial effect always produces the same key",
        "stable: it never changes across retries, workers or restarts",
        "immutable: once posted, the key is never re-used for a different effect",
        "unique per financial effect: NOT per business object — a booking with a charge "
        "and a later refund yields TWO keys",
        "retry-safe: identical financial content → idempotent replay; different content "
        "under the same key → IDEMPOTENCY_CONFLICT (never a silent success)",
        "opaque to the Core: the Core parses no segment and infers no business meaning",
        "no volatile input: no now(), no uuid4() generated at attempt time, no attempt "
        "counter",
    ],
    "reserved_prefixes": {
        "reversal:{original_journal_id}": "the reversal engine",
        "year_close:{entity}:{fiscal_year}:{currency}": "year closing",
        "year_reopen:{entity}:{fiscal_year}:{currency}": "controlled year reopen",
        "opening:*": "opening balances (producer-supplied)",
    },
    "enforcement": "unique partial index (entity_id, source_key) + financial fingerprint",
    "manual_exception": "source_type='manual' may omit the key (a human operation has no "
                        "external retry to be idempotent about)",
}

# ---------------------------------------------------------------------------------------
# LARGE-DATA SAFEGUARDS (bounded reads; no premature optimisation)
# ---------------------------------------------------------------------------------------
MAX_LEDGER_PAGE = 200
MAX_REPORT_ROWS = 5000
MAX_JOURNAL_LIST = 200
REPORT_LIMITS = {
    "ledger": {"paginated": True, "max_page_size": MAX_LEDGER_PAGE,
               "ordering": "date → entry_seq → line_no (deterministic, never natural "
                           "order)",
               "running_balance": "paging-safe: the page opening balance is derived, so a "
                                  "later page never restarts from zero"},
    "trial_balance": {"paginated": False, "max_rows": MAX_REPORT_ROWS,
                      "aggregation": "ONE indexed aggregation per report (never one query "
                                     "per account)",
                      "truncation": "rows beyond max_rows are omitted and the response "
                                    "says so (`truncated: true`); TOTALS are never "
                                    "truncated because they are computed in the "
                                    "aggregation, not from the rows"},
    "statements": {"paginated": False, "max_rows": MAX_REPORT_ROWS,
                   "note": "income statement and balance sheet are chart-sized, not "
                           "journal-sized"},
    "journal_list": {"max_limit": MAX_JOURNAL_LIST},
    "performance": "PERFORMANCE VALIDATION — DEFERRED TO LOAD TESTING: correctness and "
                   "bounded reads are proven; throughput at production scale cannot be "
                   "proven without production-scale data, and is not claimed.",
}
