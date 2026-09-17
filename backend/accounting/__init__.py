"""Accounting Module — Phase 1 (Chart of Accounts foundation).

Layering (enforced by convention and reviewed on every change):

    accounting/core/      → Generic Accounting Core. MUST NOT import anything from Meraaj
                            (no db.py, no rbac.py, no security.py, no business modules).
    accounting/templates/ → Chart-of-Accounts templates (data only, no engine logic).
    accounting/adapters/  → Project-specific glue (entity resolution, permissions, chart
                            profile). This is the ONLY layer that knows Meraaj exists.
    accounting/api.py     → HTTP surface for Meraaj (read + chart administration).

Phase 1 scope is the Account model + the Chart of Accounts only. No journal, no posting,
no ledger, no reports, no currency engine, no account linking, no business integration.
"""
