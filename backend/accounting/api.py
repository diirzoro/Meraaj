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
                       journal_validator, resolve_entity, PLATFORM_ENTITY)
from .core import (AccountCreate, AccountUpdate, AccountingError, IMMUTABLE_FIELDS,
                   JournalEntryDraft, JournalStatus, JOURNAL_DOCUMENT_CONTRACT,
                   MIN_LINES, DEFAULT_SCALE, BALANCE_TOLERANCE, as_str)

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
        "phase": 3,
        "scope": "chart_of_accounts + journal_model + central_validation_only",
        "platform_entity": PLATFORM_ENTITY,
        "template": coa.template.key,
        "template_title": coa.template.title,
        "coa_version": coa.template.version,
        "template_accounts": len(coa.template.accounts),
        "roles": sorted(a.role for a in coa.template.accounts if a.role),
        "immutable_fields": list(IMMUTABLE_FIELDS),
        "journal_usage_probe": "unavailable (no posted journal exists in this phase)",
        "journal": {
            "statuses": [s.value for s in JournalStatus],
            "min_lines": MIN_LINES,
            "monetary_scale": DEFAULT_SCALE,
            "monetary_representation": "decimal.Decimal in core, Decimal128 in DB (future)",
            "balance_tolerance": as_str(BALANCE_TOLERANCE),
            "currency": currency_policy().describe(),
            "persistence": "none — Phase 3 validates in memory and stores nothing",
            "entry_no": "allocated only at posting time (atomic, entity-scoped) — a draft "
                        "never carries an accounting number",
            "source_key_idempotency": "deferred to its own phase, with its unique index",
            "period_guard": "boundary wired, not enforced (no closing mechanism yet)",
            "document_contract": JOURNAL_DOCUMENT_CONTRACT,
        },
        "not_implemented_yet": ["posting_workflow", "general_ledger", "reversal",
                                "opening_balances", "period_closing", "reports",
                                "currency_engine", "account_linking"],
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
