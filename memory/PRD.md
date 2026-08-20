# PRD — معراج نتورك (Meraaj Network)

## Original Problem Statement
Build a B2B marketplace ("Meraaj Network" by Target Media) connecting travel/Umrah offices to buy & sell packages (Umrah, tourism) using prepaid wallets + escrow. Two roles: Super Admin (Target Media) and Office (acts as both seller & buyer via one wallet). Includes wallet engine (total/pending/available), colored booking lifecycle (blue→yellow→green), cancellations, P2P transfers, settlements/withdrawals, disputes, and a technical integration layer with the external "Rahal" system. Also produce a technical integration requirements document (APIs/Webhooks/Endpoints) for the Rahal dev team.

## User Choices
- Deliver integration requirements doc FIRST, then build the MVP.
- Meraaj is a standalone platform + a ready integration layer for Rahal (manual package entry works independently).
- Auth: custom JWT (email + password + mandatory phone; OTP deferred).
- Wallet top-up: manual, admin approves uploaded bank-transfer receipts (no payment gateway).
- UI: Arabic RTL only.
- Admin/owner account: abuzay84@gmail.com

## Architecture
- Backend: FastAPI (modular: server.py, security.py, db.py, market.py, wallet.py, admin.py, integration.py), MongoDB (motor). All routes under `/api`.
- Auth: JWT (httpOnly cookie + Bearer fallback in localStorage), bcrypt, idempotent admin seed, brute-force lockout (5 attempts / 15 min).
- Frontend: React (CRA) + Tailwind + shadcn/ui + sonner + lucide, RTL. `@/` alias. Fonts: Alexandria/Cairo/IBM Plex Sans Arabic. Colors: navy #0A2540 + gold #D4AF37.

## Implemented (2026-06)
- Auth: register office (office_name, owner_name, email, phone, governorate, address), login, logout, /me, admin seed, brute-force lockout.
- Wallet engine: total/pending/available with escrow; ledger transactions.
- Marketplace: create/list/toggle packages (umrah/tourism), search & filter, package detail.
- Booking lifecycle: blue (registrants w/ passport) → yellow (mandatory per-registrant visa numbers + optional visa file) → green (dispatch + 24h grace → settle releases escrow). Double platform commission (buyer at booking, seller at settlement) per PRD.
- Cancellations: blue auto-refund (minus admin fee); yellow seller-deduction → buyer accept; green blocked. Idempotency guards on all money moves.
- P2P transfers (admin-approved), withdrawals/settlements (admin-approved), top-ups via receipt upload (admin-approved).
- Disputes: buyer opens within 24h of dispatch; admin resolves (refund_buyer / release_seller), idempotent.
- Admin: dashboard (system liquidity + pending counts), finance center, offices management (activate/suspend), disputes.
- Rahal integration layer: `/api/integrations/rahal/status`, `/packages/share` (X-Rahal-Api-Key), `/webhooks` (HMAC-SHA256). Reverse inventory webhooks documented.
- Integration requirements doc: `/app/memory/RAHAL_INTEGRATION_REQUIREMENTS.md`.

## Verified
- Iteration 2 testing: backend 40/41 tests pass; all money-safety guards confirmed; layout & mobile drawer verified geometrically; brute-force lockout (429) and bad-id (404) confirmed via curl.

## Backlog (P1/P2)
- P1: Real Rahal SSO handoff + embedded signed-iframe (awaiting Rahal APIs).
- P1: Atomic booking debit (conditional findOneAndUpdate) to prevent concurrency oversell.
- P2: Object storage for receipt/visa file uploads (currently URL fields).
- P2: Debounced market search; admin offices pagination; phone OTP; email notifications.

## Test Credentials
See /app/memory/test_credentials.md
