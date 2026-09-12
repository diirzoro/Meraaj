"""Year-close operation state vocabulary — shared by the period and year-close services.

Kept in its own module so `period_service` and `year_close` can both use it without a
circular import. NEW (Rahaal had no recoverable closing state at all).
"""
YEAR_STATE_STARTED = "started"
YEAR_STATE_JOURNAL_POSTED = "journal_posted"
YEAR_STATE_VERIFIED = "verified"
YEAR_STATE_COMPLETED = "completed"
YEAR_STATE_FAILED = "failed"
#: OPEN-017 — controlled reopen states. A reopen is a FORWARD state, never a rollback of
#: history: the closing journal survives, reversed by a mirror entry.
YEAR_STATE_REOPEN_STARTED = "reopen_started"
YEAR_STATE_REOPENED = "reopened"

YEAR_STATES = (YEAR_STATE_STARTED, YEAR_STATE_JOURNAL_POSTED, YEAR_STATE_VERIFIED,
               YEAR_STATE_COMPLETED, YEAR_STATE_FAILED, YEAR_STATE_REOPEN_STARTED,
               YEAR_STATE_REOPENED)
#: States in which the year's closing effect is still ACTIVE in the books.
YEAR_ACTIVE_CLOSE_STATES = (YEAR_STATE_COMPLETED, YEAR_STATE_REOPEN_STARTED)
YEAR_CLOSE_SOURCE_TYPE = "year_close"
YEAR_REOPEN_SOURCE_PREFIX = "year_reopen"
