"""HTTP surface for the Accounting Module — Phases 1-2 (Chart of Accounts only).

API BOUNDARY (enforced): this file is a TRANSPORT layer.
    Request → Adapter/Context (entity + actor + permission) → Core → Response
No accounting rule lives here. The Core raises `AccountingError`, which carries no HTTP
dependency; one exception handler registered on the app performs the single HTTP mapping.
(The reference implementation kept its rules inside the route handler — that is exactly
what porting them into `core/` fixed.)
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from .adapters import (accounting_perm, actor_label, chart, currency_policy,
                       journal_validator, posting_service, ledger_service,
                       reversal_service, opening_service, reporting_service,
                       period_service, year_close_service, entity_currencies,
                       fx_rate_service, fx_conversion_service, fx_result_service,
                       resolve_entity, PLATFORM_ENTITY)
from .core import (AccountCreate, AccountUpdate, AccountingError, IMMUTABLE_FIELDS,
                   JournalEntryDraft, JournalStatus, JOURNAL_DOCUMENT_CONTRACT,
                   MIN_LINES, DEFAULT_SCALE, BALANCE_TOLERANCE, as_str,
                   format_entry_no, MANUAL_SOURCE_TYPES, OpeningBalanceRequest)
from datetime import datetime

router = APIRouter(prefix="/api/accounting", tags=["accounting"])

VIEW = "accounting.accounts.view"
MANAGE = "accounting.accounts.manage"


def install_error_handler(app) -> None:
    """The ONE place where a Core error becomes an HTTP response."""

    @app.exception_handler(AccountingError)
    async def _handle(request: Request, exc: AccountingError):  # noqa: ANN001
        return JSONResponse(status_code=exc.http_status,
                            content={"detail": exc.message, "error": exc.code,
                                     **exc.details})


@router.get("/meta")
async def meta(user: dict = Depends(accounting_perm(VIEW))):
    coa = chart()
    return {
        "phase": 10,
        "scope": "chart + posting + general ledger + reversal + opening balances "
                 "+ core reports + period/year closing + multi-currency & FX",
        "platform_entity": PLATFORM_ENTITY,
        "template": coa.template.key,
        "template_title": coa.template.title,
        "coa_version": coa.template.version,
        "template_accounts": len(coa.template.accounts),
        "roles": sorted(a.role for a in coa.template.accounts if a.role),
        "immutable_fields": list(IMMUTABLE_FIELDS),
        "journal_usage_probe": "active — a POSTED entry referencing an account blocks "
                               "its deletion and any structural change",
        "journal": {
            "statuses": [s.value for s in JournalStatus],
            "min_lines": MIN_LINES,
            "monetary_scale": DEFAULT_SCALE,
            "monetary_representation": "decimal.Decimal in core, BSON Decimal128 in DB",
            "balance_tolerance": as_str(BALANCE_TOLERANCE),
            "currency": currency_policy().describe(),
            "persistence": "POSTED entries only — drafts are never stored",
            "single_write_gateway": "JournalPostingService (no other write path exists)",
            "entry_no_format": f"{format_entry_no(1)} — entity-scoped, continuous, "
                               f"allocated atomically at posting time",
            "entry_no_gap_policy": "uniqueness is guaranteed; rare gaps are possible and "
                                   "auditable, and a number is never re-used",
            "idempotency": {
                "key": "source_key (opaque string — the Core never interprets it)",
                "required_for": "every non-manual source_type",
                "optional_for": list(MANUAL_SOURCE_TYPES),
                "enforced_by": "unique partial index (entity_id, source_key)",
                "retry": "identical financial content → idempotent replay of the existing "
                         "entry",
                "conflict": "same key + different financial content → IDEMPOTENCY_CONFLICT",
            },
            "immutability": "no update and no delete endpoint for a posted entry; a "
                            "correction will be a reversal entry plus a new entry",
            "period_guard": "ENFORCED — a date inside a closed period is refused with "
                            "PERIOD_CLOSED before any financial effect",
            "document_contract": JOURNAL_DOCUMENT_CONTRACT,
        },
        "reports": {
            "available": ["trial_balance", "income_statement", "balance_sheet"],
            "derivation": "computed from POSTED + REVERSED journal entries at read time "
                          "— no report collection, no cached balance",
            "currency_rule": "one report = one currency; two currencies are never added "
                             "and never converted",
            "group_rollup": "real parent chain (not code prefix); totals count posting "
                            "accounts only, so no posting is double-counted",
            "closing": "the period result is a DERIVED equity line; no closing journal "
                       "is written (period/year closing is a later phase)",
        },
        "closing": {
            "period_model": "accounting_periods documents — entity scoped, "
                            "fiscal-year scoped, open|closed, close/reopen history "
                            "appended and never erased",
            "period_guard": "ENFORCED centrally in the journal validator and the "
                            "reversal engine — journal posting, reversal, opening "
                            "balances and closing journals are all covered; no "
                            "route-specific guard exists",
            "close_meaning": "locks accounting DATES only — no journal rewrite, no "
                             "balance cache, no $inc, no delete",
            "fiscal_year": "configurable start_month/start_day + month|quarter periods; "
                           "the label is the calendar year of the START date",
            "year_close": "closing journal (source_type=year_close) → verification → "
                          "period locking → final state, in that order and never merged",
            "year_close_idempotency": "deterministic source_key + unique index on "
                                      "(entity, fiscal_year, currency) → a double year "
                                      "close is impossible; a retry resumes",
            "multi_currency_close": "each currency closes INDEPENDENTLY; SAR completed "
                                    "while USD failed is never reported as 'year closed'",
            "retained_earnings": "resolved by semantic role, never by account number",
            "year_reopen": "DEFERRED — CONTROLLED YEAR REOPEN (closing journals are "
                           "never deleted)",
        },
        "fx": {
            "base_currency": "EXPLICIT per entity — never inferred from the first "
                             "journal and never defaulted to a specific code",
            "currency_gate": "new postings require configured + allowed + active; "
                             "history of a deactivated currency stays readable",
            "rate_direction": "rate = units of to_currency per 1 unit of from_currency "
                              "(one direction only, everywhere)",
            "rate_selection": "latest effective_date <= accounting date — no silent "
                              "'latest rate'",
            "rate_immutability": "a rate for an existing effective_date is never "
                                 "rewritten; add a new effective_date instead",
            "precision": "rate scale 8, calculation scale 12, posting scale = the "
                         "Phase 3 money policy (2) applied once at the boundary",
            "journal_policy": "one journal = one currency (the Phase 3 invariant is NOT "
                              "reopened)",
            "fx_effect": "realized FX difference only, always as a balanced journal via "
                         "the single write gateway; gain/loss accounts by semantic role",
            "deferred": {"unrealized_revaluation": "DEFERRED — FX REVALUATION",
                         "consolidated_reporting": "DEFERRED — CONSOLIDATED FX REPORTING"},
            "correction": "Reversal Engine only — an FX journal is immutable",
        },
        "not_implemented_yet": ["account_linking", "business_integration",
                                "fx_revaluation", "consolidated_fx_reporting",
                                "controlled_year_reopen"],
    }


@router.post("/journal/validate")
async def validate_journal(payload: JournalEntryDraft, entity_id: Optional[str] = None,
                           user: dict = Depends(accounting_perm(VIEW))):
    """DRY-RUN ONLY — runs the central journal validator and returns its verdict.

    Nothing is stored, numbered, posted or reversed: `persisted:false, posted:false`. This
    is the same `assert_valid()` the posting phase will be built on, so a journal that
    cannot pass here can never become posted.
    """
    eid = await resolve_entity(user, entity_id)
    return await journal_validator().validate(eid, payload)


@router.post("/journal/post")
async def post_journal(payload: JournalEntryDraft, entity_id: Optional[str] = None,
                       source_key: Optional[str] = Query(default=None, max_length=200),
                       user: dict = Depends(accounting_perm(MANAGE))):
    """The ONLY way a journal can be written.

    API → Adapter → JournalPostingService → JournalValidator → JournalStore.
    The endpoint holds no accounting rule: it resolves the entity and the actor and
    delegates. There is no update or delete counterpart — a posted entry is immutable.
    """
    eid = await resolve_entity(user, entity_id)
    return await posting_service().post(eid, payload, source_key=source_key,
                                        by=actor_label(user))


@router.get("/journal/entries")
async def list_journal(entity_id: Optional[str] = None,
                       limit: int = Query(default=50, ge=1, le=200),
                       source_type: Optional[str] = None,
                       user: dict = Depends(accounting_perm(VIEW))):
    eid = await resolve_entity(user, entity_id)
    return {"entity_id": eid,
            "items": await posting_service().list_entries(eid, limit, source_type)}


@router.get("/journal/by-source-key/{source_key}")
async def journal_by_source_key(source_key: str, entity_id: Optional[str] = None,
                                user: dict = Depends(accounting_perm(VIEW))):
    eid = await resolve_entity(user, entity_id)
    return await posting_service().get_by_source_key(eid, source_key)


@router.get("/journal/entries/{entry_id}")
async def get_journal(entry_id: str, entity_id: Optional[str] = None,
                      user: dict = Depends(accounting_perm(VIEW))):
    eid = await resolve_entity(user, entity_id)
    return await posting_service().get(eid, entry_id)


# ------------------------------------------------- general ledger (read-only)
@router.get("/ledger/account/{account_code}")
async def account_ledger(account_code: str, entity_id: Optional[str] = None,
                         currency: Optional[str] = None,
                         from_date: Optional[datetime] = None,
                         to_date: Optional[datetime] = None,
                         page: int = Query(default=1, ge=1),
                         page_size: int = Query(default=50, ge=1, le=200),
                         user: dict = Depends(accounting_perm(VIEW))):
    """Derived read model over POSTED journals. Nothing is stored or cached."""
    eid = await resolve_entity(user, entity_id)
    return await ledger_service().account_ledger(
        eid, account_code, currency=currency, from_date=from_date, to_date=to_date,
        page=page, page_size=page_size)


# ------------------------------------------------------------------- reversal
@router.post("/journal/entries/{entry_id}/reverse")
async def reverse_journal(entry_id: str, reason: str = Query(..., min_length=3,
                                                             max_length=500),
                          entity_id: Optional[str] = None,
                          source_key: Optional[str] = Query(default=None,
                                                            max_length=200),
                          date: Optional[datetime] = None,
                          user: dict = Depends(accounting_perm(MANAGE))):
    """Creates a mirror entry. The original is never edited or deleted — only its
    reversal metadata is claimed, atomically, by this service."""
    eid = await resolve_entity(user, entity_id)
    return await reversal_service().reverse(eid, entry_id, reason=reason,
                                            by=actor_label(user), date=date,
                                            source_key=source_key)


# ----------------------------------------------------------- opening balances
@router.post("/opening-balances")
async def post_opening_balances(payload: OpeningBalanceRequest,
                                entity_id: Optional[str] = None,
                                user: dict = Depends(accounting_perm(MANAGE))):
    """Produces a POSTED opening journal through the single write gateway. This is an
    accounting capability, not a migration or a backfill of any existing data."""
    eid = await resolve_entity(user, entity_id)
    return await opening_service().open(eid, payload, by=actor_label(user))


# ------------------------------------------------------- core reports (Phase 8)
@router.get("/reports/trial-balance")
async def trial_balance(entity_id: Optional[str] = None,
                        currency: Optional[str] = None,
                        from_date: Optional[datetime] = None,
                        to_date: Optional[datetime] = None,
                        include_zero: bool = False, include_groups: bool = True,
                        user: dict = Depends(accounting_perm(VIEW))):
    """Derived from journal entries at read time — nothing is stored or cached."""
    eid = await resolve_entity(user, entity_id)
    return await reporting_service().trial_balance(
        eid, currency=currency, from_date=from_date, to_date=to_date,
        include_zero=include_zero, include_groups=include_groups)


@router.get("/reports/income-statement")
async def income_statement(entity_id: Optional[str] = None,
                           currency: Optional[str] = None,
                           from_date: Optional[datetime] = None,
                           to_date: Optional[datetime] = None,
                           include_zero: bool = False,
                           exclude_closing: bool = True,
                           user: dict = Depends(accounting_perm(VIEW))):
    """`exclude_closing=true` (default) keeps a HISTORICAL income statement meaningful
    after a year close — the closing entries stay in the book, not in performance."""
    eid = await resolve_entity(user, entity_id)
    return await reporting_service().income_statement(
        eid, currency=currency, from_date=from_date, to_date=to_date,
        include_zero=include_zero, exclude_closing=exclude_closing)


@router.get("/reports/balance-sheet")
async def balance_sheet(entity_id: Optional[str] = None,
                        currency: Optional[str] = None,
                        as_of: Optional[datetime] = None,
                        from_date: Optional[datetime] = None,
                        include_zero: bool = False,
                        user: dict = Depends(accounting_perm(VIEW))):
    eid = await resolve_entity(user, entity_id)
    return await reporting_service().balance_sheet(
        eid, currency=currency, as_of=as_of, from_date=from_date,
        include_zero=include_zero)


# ------------------------------------------- periods & year closing (Phase 9)
@router.get("/periods")
async def list_periods(entity_id: Optional[str] = None,
                       fiscal_year: Optional[int] = None,
                       user: dict = Depends(accounting_perm(VIEW))):
    eid = await resolve_entity(user, entity_id)
    return await period_service().list_periods(eid, fiscal_year)


@router.get("/periods/for-date")
async def period_for_date(date: datetime, entity_id: Optional[str] = None,
                          user: dict = Depends(accounting_perm(VIEW))):
    eid = await resolve_entity(user, entity_id)
    return await period_service().period_for_date(eid, date)


@router.post("/periods/fiscal-config")
async def configure_fiscal(start_month: int = Query(..., ge=1, le=12),
                           start_day: int = Query(1, ge=1, le=28),
                           period_length: str = Query("month"),
                           entity_id: Optional[str] = None,
                           user: dict = Depends(accounting_perm(MANAGE))):
    """The fiscal year is CONFIGURABLE — never hardcoded January–December."""
    eid = await resolve_entity(user, entity_id)
    return await period_service().configure_fiscal(
        eid, start_month, start_day, period_length, by=actor_label(user))


@router.post("/periods/generate")
async def generate_periods(fiscal_year: int = Query(..., ge=1970, le=2999),
                           entity_id: Optional[str] = None,
                           user: dict = Depends(accounting_perm(MANAGE))):
    eid = await resolve_entity(user, entity_id)
    return await period_service().generate_year(eid, fiscal_year,
                                                by=actor_label(user))


@router.get("/periods/{period_id}/close-preflight")
async def period_close_preflight(period_id: str, entity_id: Optional[str] = None,
                                 user: dict = Depends(accounting_perm(VIEW))):
    """READ-ONLY. Any critical inconsistency blocks the close before it is attempted."""
    eid = await resolve_entity(user, entity_id)
    return await period_service().close_preflight(eid, period_id)


@router.post("/periods/{period_id}/close")
async def close_period(period_id: str,
                       reason: str = Query(..., min_length=3, max_length=500),
                       force_sequence: bool = False,
                       entity_id: Optional[str] = None,
                       user: dict = Depends(accounting_perm(MANAGE))):
    """Close = LOCK accounting dates. No journal is rewritten, deleted or re-valued."""
    eid = await resolve_entity(user, entity_id)
    return await period_service().close(eid, period_id, reason=reason,
                                        by=actor_label(user),
                                        force_sequence=force_sequence)


@router.post("/periods/{period_id}/reopen")
async def reopen_period(period_id: str,
                        reason: str = Query(..., min_length=3, max_length=500),
                        entity_id: Optional[str] = None,
                        user: dict = Depends(accounting_perm(MANAGE))):
    """The close record is never erased — reopen is appended to the period history."""
    eid = await resolve_entity(user, entity_id)
    return await period_service().reopen(eid, period_id, reason=reason,
                                         by=actor_label(user))


@router.get("/year-close/{fiscal_year}")
async def year_close_status(fiscal_year: int, entity_id: Optional[str] = None,
                            user: dict = Depends(accounting_perm(VIEW))):
    eid = await resolve_entity(user, entity_id)
    return await year_close_service().status(eid, fiscal_year)


@router.post("/year-close/{fiscal_year}")
async def close_year(fiscal_year: int,
                     currency: str = Query(..., min_length=2, max_length=8),
                     reason: Optional[str] = Query(default=None, max_length=500),
                     entity_id: Optional[str] = None,
                     user: dict = Depends(accounting_perm(MANAGE))):
    """ONE currency per call — currencies close independently and are never mixed."""
    eid = await resolve_entity(user, entity_id)
    return await year_close_service().close_year(eid, fiscal_year, currency,
                                                 by=actor_label(user), reason=reason)


@router.post("/year-close/{fiscal_year}/reopen")
async def reopen_year(fiscal_year: int, entity_id: Optional[str] = None,
                      user: dict = Depends(accounting_perm(MANAGE))):
    """DEFERRED — CONTROLLED YEAR REOPEN. Refused explicitly rather than half-built."""
    eid = await resolve_entity(user, entity_id)
    return await year_close_service().reopen_year(eid, fiscal_year)


# --------------------------------------- currencies & FX engine (Phase 10)
@router.get("/currencies")
async def currency_settings(entity_id: Optional[str] = None,
                            user: dict = Depends(accounting_perm(VIEW))):
    eid = await resolve_entity(user, entity_id)
    return await entity_currencies().describe(eid)


@router.post("/currencies")
async def configure_currencies(base_currency: str = Query(..., min_length=2,
                                                          max_length=8),
                               currencies: str = Query(..., min_length=2),
                               entity_id: Optional[str] = None,
                               user: dict = Depends(accounting_perm(MANAGE))):
    """Base currency becomes EXPLICIT here — it is never inferred from the first journal."""
    eid = await resolve_entity(user, entity_id)
    codes = [c for c in currencies.split(",") if c.strip()]
    return await entity_currencies().configure(eid, base_currency, codes,
                                               by=actor_label(user))


@router.post("/currencies/{currency}/active")
async def set_currency_active(currency: str, active: bool = Query(...),
                             entity_id: Optional[str] = None,
                             user: dict = Depends(accounting_perm(MANAGE))):
    """Deactivation blocks NEW postings only — the history stays readable and reportable."""
    eid = await resolve_entity(user, entity_id)
    return await entity_currencies().set_active(eid, currency, active,
                                                by=actor_label(user))


@router.get("/fx/rates")
async def list_fx_rates(entity_id: Optional[str] = None,
                        from_currency: Optional[str] = None,
                        to_currency: Optional[str] = None,
                        limit: int = Query(default=100, ge=1, le=500),
                        user: dict = Depends(accounting_perm(VIEW))):
    eid = await resolve_entity(user, entity_id)
    return await fx_rate_service().list_rates(eid, from_currency, to_currency, limit)


@router.post("/fx/rates")
async def add_fx_rate(from_currency: str = Query(..., min_length=2, max_length=8),
                      rate: str = Query(..., min_length=1),
                      effective_date: datetime = Query(...),
                      to_currency: Optional[str] = Query(default=None, max_length=8),
                      source: Optional[str] = Query(default=None, max_length=64),
                      entity_id: Optional[str] = None,
                      user: dict = Depends(accounting_perm(MANAGE))):
    """`rate` is a STRING on purpose: no float ever enters the FX engine."""
    eid = await resolve_entity(user, entity_id)
    return await fx_rate_service().add_rate(eid, from_currency, rate, effective_date,
                                            to_currency=to_currency, source=source,
                                            by=actor_label(user))


@router.get("/fx/convert")
async def fx_convert(amount: str = Query(..., min_length=1),
                     from_currency: str = Query(..., min_length=2, max_length=8),
                     to_currency: Optional[str] = Query(default=None, max_length=8),
                     date: Optional[datetime] = None,
                     entity_id: Optional[str] = None,
                     user: dict = Depends(accounting_perm(VIEW))):
    """Read-only conversion. Returns the rate it used, so the figure is reproducible."""
    eid = await resolve_entity(user, entity_id)
    return await fx_conversion_service().convert(eid, amount, from_currency,
                                                 to_currency=to_currency, date=date)


@router.post("/fx/realized-difference")
async def post_fx_difference(account_code: str = Query(..., min_length=1),
                             amount: str = Query(..., min_length=1),
                             source_key: str = Query(..., min_length=3, max_length=200),
                             currency: Optional[str] = Query(default=None, max_length=8),
                             description: Optional[str] = Query(default=None,
                                                                max_length=500),
                             date: Optional[datetime] = None,
                             entity_id: Optional[str] = None,
                             user: dict = Depends(accounting_perm(MANAGE))):
    """A realized FX difference becomes a BALANCED JOURNAL through the single write
    gateway (`amount > 0` = gain, `amount < 0` = loss). No account balance is mutated."""
    eid = await resolve_entity(user, entity_id)
    return await fx_result_service().post_realized_difference(
        eid, account_code, amount, source_key, currency=currency, date=date,
        description=description, by=actor_label(user))


# ------------------------------------------------------------------ read paths
@router.get("/accounts")
async def list_accounts(entity_id: Optional[str] = None, include_inactive: bool = True,
                        user: dict = Depends(accounting_perm(VIEW))):
    eid = await resolve_entity(user, entity_id)
    return {"entity_id": eid,
            "items": await chart().list_accounts(eid, include_inactive)}


@router.get("/accounts/tree")
async def accounts_tree(entity_id: Optional[str] = None, include_inactive: bool = True,
                        user: dict = Depends(accounting_perm(VIEW))):
    eid = await resolve_entity(user, entity_id)
    return {"entity_id": eid, "roots": await chart().build_tree(eid, include_inactive)}


@router.get("/accounts/next-code")
async def next_code(parent: str = Query(..., min_length=1), entity_id: Optional[str] = None,
                    user: dict = Depends(accounting_perm(VIEW))):
    eid = await resolve_entity(user, entity_id)
    return await chart().next_code(eid, parent.strip())


@router.get("/accounts/by-code/{code}")
async def account_by_code(code: str, entity_id: Optional[str] = None,
                          user: dict = Depends(accounting_perm(VIEW))):
    eid = await resolve_entity(user, entity_id)
    return await chart().find_by_code(eid, code)


@router.get("/accounts/by-role/{role}")
async def account_by_role(role: str, entity_id: Optional[str] = None,
                          user: dict = Depends(accounting_perm(VIEW))):
    eid = await resolve_entity(user, entity_id)
    return await chart().find_by_role(eid, role)


@router.get("/chart/audit")
async def chart_audit(entity_id: Optional[str] = None,
                      user: dict = Depends(accounting_perm(VIEW))):
    eid = await resolve_entity(user, entity_id)
    return await chart().audit_chart(eid)


@router.get("/chart/validate")
async def chart_validate(entity_id: Optional[str] = None,
                         user: dict = Depends(accounting_perm(VIEW))):
    eid = await resolve_entity(user, entity_id)
    return await chart().validate_chart(eid)


# ----------------------------------------------------------------- write paths
@router.post("/chart/seed")
async def chart_seed(entity_id: Optional[str] = None,
                     user: dict = Depends(accounting_perm(MANAGE))):
    eid = await resolve_entity(user, entity_id)
    return await chart().seed_template(eid, by=actor_label(user))


@router.post("/accounts")
async def create_account(payload: AccountCreate, entity_id: Optional[str] = None,
                         user: dict = Depends(accounting_perm(MANAGE))):
    eid = await resolve_entity(user, entity_id)
    return await chart().create_account(eid, payload, by=actor_label(user))


@router.get("/accounts/{account_id}")
async def get_account(account_id: str, entity_id: Optional[str] = None,
                      user: dict = Depends(accounting_perm(VIEW))):
    eid = await resolve_entity(user, entity_id)
    return await chart().get_account(eid, account_id)


@router.patch("/accounts/{account_id}")
async def update_account(account_id: str, payload: AccountUpdate,
                         entity_id: Optional[str] = None,
                         user: dict = Depends(accounting_perm(MANAGE))):
    eid = await resolve_entity(user, entity_id)
    return await chart().update_account(eid, account_id, payload, by=actor_label(user))


@router.post("/accounts/{account_id}/deactivate")
async def deactivate_account(account_id: str, entity_id: Optional[str] = None,
                             user: dict = Depends(accounting_perm(MANAGE))):
    eid = await resolve_entity(user, entity_id)
    return await chart().set_active(eid, account_id, False, by=actor_label(user))


@router.post("/accounts/{account_id}/activate")
async def activate_account(account_id: str, entity_id: Optional[str] = None,
                           user: dict = Depends(accounting_perm(MANAGE))):
    eid = await resolve_entity(user, entity_id)
    return await chart().set_active(eid, account_id, True, by=actor_label(user))


@router.delete("/accounts/{account_id}")
async def delete_account(account_id: str, entity_id: Optional[str] = None,
                         user: dict = Depends(accounting_perm(MANAGE))):
    eid = await resolve_entity(user, entity_id)
    return await chart().delete_account(eid, account_id, by=actor_label(user))
