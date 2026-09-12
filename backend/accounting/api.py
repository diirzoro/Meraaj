"""HTTP surface for the Accounting Module — Phase 1 (Chart of Accounts only).

Every route is a thin transport wrapper: it resolves the entity, checks the permission and
delegates to the Core. No accounting rule lives here (the reference implementation kept its
rules inside the route handler; that is exactly what is being fixed by porting them into
`core/chart.py`).
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from .adapters import (accounting_perm, actor_label, chart, resolve_entity,
                       PLATFORM_ENTITY)
from .core import AccountCreate, AccountUpdate, AccountingError

router = APIRouter(prefix="/api/accounting", tags=["accounting"])

VIEW = "accounting.accounts.view"
MANAGE = "accounting.accounts.manage"


def _fail(exc: AccountingError):
    raise HTTPException(exc.http_status, exc.message)


@router.get("/meta")
async def meta(user: dict = Depends(accounting_perm(VIEW))):
    coa = chart()
    return {
        "phase": 1,
        "scope": "chart_of_accounts_only",
        "platform_entity": PLATFORM_ENTITY,
        "template": coa.template.key,
        "template_title": coa.template.title,
        "coa_version": coa.template.version,
        "template_accounts": len(coa.template.accounts),
        "not_implemented_yet": ["journal", "posting", "ledger", "reversal",
                                "opening_balances", "period_closing", "reports",
                                "currency_engine", "account_linking"],
    }


@router.get("/accounts")
async def list_accounts(entity_id: Optional[str] = None, include_inactive: bool = True,
                        user: dict = Depends(accounting_perm(VIEW))):
    eid = await resolve_entity(user, entity_id)
    try:
        return {"entity_id": eid,
                "items": await chart().list_accounts(eid, include_inactive)}
    except AccountingError as e:
        _fail(e)


@router.get("/accounts/tree")
async def accounts_tree(entity_id: Optional[str] = None, include_inactive: bool = True,
                        user: dict = Depends(accounting_perm(VIEW))):
    eid = await resolve_entity(user, entity_id)
    try:
        return {"entity_id": eid, "roots": await chart().build_tree(eid, include_inactive)}
    except AccountingError as e:
        _fail(e)


@router.get("/accounts/next-code")
async def next_code(parent: str = Query(..., min_length=1), entity_id: Optional[str] = None,
                    user: dict = Depends(accounting_perm(VIEW))):
    eid = await resolve_entity(user, entity_id)
    try:
        return await chart().next_code(eid, parent.strip())
    except AccountingError as e:
        _fail(e)


@router.get("/chart/audit")
async def chart_audit(entity_id: Optional[str] = None,
                      user: dict = Depends(accounting_perm(VIEW))):
    eid = await resolve_entity(user, entity_id)
    try:
        return await chart().audit_chart(eid)
    except AccountingError as e:
        _fail(e)


@router.get("/chart/validate")
async def chart_validate(entity_id: Optional[str] = None,
                         user: dict = Depends(accounting_perm(VIEW))):
    eid = await resolve_entity(user, entity_id)
    try:
        return await chart().validate_chart(eid)
    except AccountingError as e:
        _fail(e)


@router.post("/chart/seed")
async def chart_seed(entity_id: Optional[str] = None,
                     user: dict = Depends(accounting_perm(MANAGE))):
    eid = await resolve_entity(user, entity_id)
    try:
        return await chart().seed_template(eid, by=actor_label(user))
    except AccountingError as e:
        _fail(e)


@router.post("/accounts")
async def create_account(payload: AccountCreate, entity_id: Optional[str] = None,
                         user: dict = Depends(accounting_perm(MANAGE))):
    eid = await resolve_entity(user, entity_id)
    try:
        return await chart().create_account(eid, payload, by=actor_label(user))
    except AccountingError as e:
        _fail(e)


@router.get("/accounts/{account_id}")
async def get_account(account_id: str, entity_id: Optional[str] = None,
                      user: dict = Depends(accounting_perm(VIEW))):
    eid = await resolve_entity(user, entity_id)
    try:
        return await chart().get_account(eid, account_id)
    except AccountingError as e:
        _fail(e)


@router.patch("/accounts/{account_id}")
async def update_account(account_id: str, payload: AccountUpdate,
                         entity_id: Optional[str] = None,
                         user: dict = Depends(accounting_perm(MANAGE))):
    eid = await resolve_entity(user, entity_id)
    try:
        return await chart().update_account(eid, account_id, payload,
                                            by=actor_label(user))
    except AccountingError as e:
        _fail(e)


@router.post("/accounts/{account_id}/deactivate")
async def deactivate_account(account_id: str, entity_id: Optional[str] = None,
                             user: dict = Depends(accounting_perm(MANAGE))):
    eid = await resolve_entity(user, entity_id)
    try:
        return await chart().set_active(eid, account_id, False, by=actor_label(user))
    except AccountingError as e:
        _fail(e)


@router.post("/accounts/{account_id}/activate")
async def activate_account(account_id: str, entity_id: Optional[str] = None,
                           user: dict = Depends(accounting_perm(MANAGE))):
    eid = await resolve_entity(user, entity_id)
    try:
        return await chart().set_active(eid, account_id, True, by=actor_label(user))
    except AccountingError as e:
        _fail(e)


@router.delete("/accounts/{account_id}")
async def delete_account(account_id: str, entity_id: Optional[str] = None,
                         user: dict = Depends(accounting_perm(MANAGE))):
    eid = await resolve_entity(user, entity_id)
    try:
        return await chart().delete_account(eid, account_id)
    except AccountingError as e:
        _fail(e)
