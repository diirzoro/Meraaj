"""Meraaj adapter — the ONLY layer that knows both the Accounting Core and Meraaj.

It supplies what the Core refuses to know:
  • which database and collections to use          (injected Motor handle from Meraaj)
  • how a Meraaj request maps to an accounting ENTITY
  • how a Meraaj user maps to a permission decision
  • which chart profile this project seeds

PORT note — tenant isolation: Rahaal resolved `tenant_id` from the session and scoped every
query with it. The Core keeps that exact rule but under a neutral name (`entity_id`), and
this adapter is the place where `entity_id` is derived. Nothing inside the Core mentions
`org_id`, offices, or Meraaj.

OPEN DECISION (deliberately not decided here): whether Meraaj keeps ONE platform ledger or
one ledger per office. Phase 1 therefore uses a single explicit platform entity key, and a
super-admin may address any other entity key explicitly. No accounting behaviour depends on
that choice yet, so the decision stays fully reversible until the journal phase.
"""
import os
from typing import Optional

from fastapi import Depends, HTTPException

from db import db
from security import get_current_user

from ..core import AccountStore, ChartOfAccounts
from ..core import (CurrencyPolicy, JournalValidator, PostingAccountResolver,
                    JournalStore, JournalUsageProbe,
                    JournalPostingService, GeneralLedgerService,
                    JournalReversalService, OpeningBalanceService,
                    ReportingService, PeriodStore, PeriodService,
                    DatabasePeriodGuard, YearCloseService, CurrencySettingsStore,
                    EntityCurrencyService, FXRateStore, FXRateService,
                    FXConversionService, FXResultService, AccountingSelfAudit)
from ..core.template import TemplateAccount as T
from ..core.types import AccountType as AT, AccountOrigin as AO
from ..core.roles import (CLIENT_WALLET_LIABILITY, ADS_REVENUE,
                          PLATFORM_COMMISSION_REVENUE, REFUNDS_AND_REVERSALS)
from ..templates import STANDARD_COA

PLATFORM_ENTITY = os.environ.get("ACCOUNTING_PLATFORM_ENTITY", "meraaj-platform")

# Meraaj chart profile = the ported standard chart + the accounts this platform needs.
# These rows are DATA ONLY: no wallet, ads, commission or booking logic is implied here,
# and nothing in the Core or in Meraaj posts to them in Phase 1.
MERAAJ_EXTRA_ACCOUNTS = [
    T("2102", "Client wallet liabilities", "التزامات محافظ العملاء", AT.LIABILITY,
      "21", True, AO.STANDARD, CLIENT_WALLET_LIABILITY, accepts_children=True),
    T("4106", "Advertising and promotion revenue", "إيرادات الإعلانات والعروض الترويجية",
      AT.REVENUE, "41", True, AO.STANDARD, ADS_REVENUE, accepts_children=True),
    T("4107", "Platform commission revenue", "إيرادات عمولات المنصة", AT.REVENUE,
      "41", True, AO.STANDARD, PLATFORM_COMMISSION_REVENUE, accepts_children=True),
    T("5102", "Refunds and reversals", "مردودات واستردادات", AT.EXPENSE,
      "51", False, AO.STANDARD, REFUNDS_AND_REVERSALS),
]

MERAAJ_COA = STANDARD_COA.extend(
    key="meraaj_v1",
    title="دليل حسابات معراج (قياسي مستخرج من Rahaal + حسابات المنصة)",
    extra=MERAAJ_EXTRA_ACCOUNTS,
)

_store = AccountStore(db, collection_prefix="accounting_")
_journal_store = JournalStore(db, collection_prefix="accounting_")
# Phase 4: the usage probe is now REAL — the chart lifecycle guards written in Phase 2 start
# enforcing historical posting protection without any change to them.
_usage_probe = JournalUsageProbe(_journal_store)
_chart = ChartOfAccounts(_store, MERAAJ_COA, usage_probe=_usage_probe)

# Currency boundary: the Core knows no project currency, so the allowed set is supplied here
# by Meraaj. `ACCOUNTING_BASE_CURRENCY` is intentionally left UNSET — the base-currency
# decision is still open and belongs to the currency-engine phase, and nothing in the
# journal model depends on it while journals are single-currency.
_ALLOWED_CURRENCIES = [c for c in os.environ.get("ACCOUNTING_CURRENCIES", "SAR,USD")
                       .split(",") if c.strip()]
_currency_policy = CurrencyPolicy(allowed=_ALLOWED_CURRENCIES,
                                  base=os.environ.get("ACCOUNTING_BASE_CURRENCY") or None,
                                  allow_multi_currency=False)
# Period guard: the REAL database-backed guard (Phase 9). Injecting it here means every
# posting path — journal, reversal, opening, year-close — is covered at once, with no
# route-level check anywhere.
_period_store = PeriodStore(db, collection_prefix="accounting_")
_period_guard = DatabasePeriodGuard(_period_store)
# Currency configuration (Phase 10): the per-entity policy that decides configured /
# allowed / active. The static env-driven policy below remains the fallback for an entity
# that has no configuration yet, so Phases 1-8 behave unchanged.
_currency_settings_store = CurrencySettingsStore(db, collection_prefix="accounting_")
_entity_currencies = EntityCurrencyService(_currency_settings_store, _journal_store)
_journal_validator = JournalValidator(PostingAccountResolver(_store), _currency_policy,
                                      period_guard=_period_guard,
                                      currency_gate=_entity_currencies)
# The ONE write gateway for accounting truth. The journal store is deliberately not
# exported: nothing outside this service may write a journal.
_posting_service = JournalPostingService(_journal_validator, _journal_store)
_ledger_service = GeneralLedgerService(_journal_store, _store)
_reversal_service = JournalReversalService(_journal_store, _store, _period_guard)
_opening_service = OpeningBalanceService(_posting_service, _journal_store, _chart)
# Phase 8 — reports are pure read models over the same two sources.
_reporting_service = ReportingService(_journal_store, _store)
# Phase 9 — periods, fiscal year and year closing.
_period_service = PeriodService(_period_store, _journal_store, _store)
_year_close_service = YearCloseService(_posting_service, _journal_store, _store,
                                       _period_store, _period_service,
                                       reversal_service=_reversal_service)
# Phase 10 — FX rates, conversion and the realized FX result engine.
_fx_rate_store = FXRateStore(db, collection_prefix="accounting_")
_fx_rate_service = FXRateService(_fx_rate_store, _entity_currencies)
_fx_conversion = FXConversionService(_fx_rate_service, _entity_currencies)
_fx_result_service = FXResultService(_posting_service, _fx_conversion, _store,
                                     _entity_currencies)
# Phase 11A — read-only diagnostic. It shares the same stores but writes nothing.
_self_audit = AccountingSelfAudit(_journal_store, _store, _period_store,
                                  _entity_currencies, _fx_rate_store,
                                  _reporting_service, _period_service)


def self_audit_service() -> AccountingSelfAudit:
    return _self_audit


async def record_accounting_audit(entity_id: str, action: str, actor: str,
                                  reason: str = None, before=None, after=None,
                                  reference: str = None) -> None:
    """REUSES the existing Meraaj audit infrastructure (`db.audit_log` + the unified audit
    trail in `enterprise.py`) instead of building a second audit engine. It lives in the
    ADAPTER because the Core must not know Meraaj's audit schema; the Core already records
    actor/time/reason ON the accounting documents themselves.
    """
    from datetime import datetime, timezone
    await db.audit_log.insert_one({
        "entity": "accounting", "entity_id": reference or entity_id,
        "action": action, "actor": actor, "at": datetime.now(timezone.utc),
        "before": before, "after": {"accounting_entity": entity_id,
                                     "reason": reason, **(after or {})},
    })


def period_service() -> PeriodService:
    return _period_service


def year_close_service() -> YearCloseService:
    return _year_close_service


def entity_currencies() -> EntityCurrencyService:
    return _entity_currencies


def fx_rate_service() -> FXRateService:
    return _fx_rate_service


def fx_conversion_service() -> FXConversionService:
    return _fx_conversion


def fx_result_service() -> FXResultService:
    return _fx_result_service


def ledger_service() -> GeneralLedgerService:
    return _ledger_service


def reporting_service() -> ReportingService:
    return _reporting_service


def reversal_service() -> JournalReversalService:
    return _reversal_service


def opening_service() -> OpeningBalanceService:
    return _opening_service


def store() -> AccountStore:
    return _store


def chart() -> ChartOfAccounts:
    return _chart


def journal_validator() -> JournalValidator:
    return _journal_validator


def posting_service() -> JournalPostingService:
    return _posting_service


def currency_policy() -> CurrencyPolicy:
    return _currency_policy


async def ensure_accounting_indexes() -> dict:
    result = await _store.ensure_indexes()
    result["journal_indexes"] = await _journal_store.ensure_indexes()
    result["period_indexes"] = await _period_store.ensure_indexes()
    result["currency_indexes"] = await _currency_settings_store.ensure_indexes()
    result["fx_rate_indexes"] = await _fx_rate_store.ensure_indexes()
    return result


def actor_label(user: dict) -> str:
    return user.get("email") or str(user.get("_id") or "system")


async def resolve_entity(user: dict, requested: Optional[str] = None) -> str:
    """Map a Meraaj request onto exactly one accounting entity.

    A non-super-admin can never address an entity other than the platform entity, so a
    crafted `entity_id` query parameter cannot read another entity's chart.
    """
    if requested and str(requested).strip():
        requested = str(requested).strip()
        if user.get("role") != "super_admin" and requested != PLATFORM_ENTITY:
            raise HTTPException(403, "لا تملك صلاحية الوصول إلى جهة محاسبية أخرى")
        return requested
    return PLATFORM_ENTITY


def accounting_perm(key: str):
    """Real permission gate (not UI hiding): a revoked `accounting.*` returns 403."""
    async def dep(user: dict = Depends(get_current_user)) -> dict:
        from rbac import has_perm, PERMISSIONS as P
        if not await has_perm(user, key):
            raise HTTPException(403, f"لا تملك صلاحية: {P.get(key, key)}")
        return user
    return dep
