"""Business ↔ Accounting INTEGRATION LAYER (ACC-015). Lives OUTSIDE the Core.

This package is the ONLY place where Meraaj business concepts (wallets, topups,
withdrawals, transfers…) meet the accounting Core. The Core stays 100% business-agnostic:
nothing here is imported by `accounting/core/*`.

DIRECTION OF DEPENDENCY (enforced by review, not by hope):
    business modules → integration → accounting.core
    accounting.core  →  (nothing)
"""
from .account_links import (AccountLinkService, LINK_DEFINITIONS, LinkKey)
from .events import (FINANCIAL_EVENTS, EventSpec, build_source_key, PRODUCER)
from .posting_bridge import AccountingBridge
from .reconciliation import BusinessAccountingReconciliation

__all__ = ["AccountLinkService", "LINK_DEFINITIONS", "LinkKey", "FINANCIAL_EVENTS",
           "EventSpec", "build_source_key", "PRODUCER", "AccountingBridge",
           "BusinessAccountingReconciliation"]
