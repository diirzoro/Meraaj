# PRD — معراج نتورك (Meraaj Network)

## Original Problem Statement
B2B marketplace ("Meraaj Network" by Target Media) connecting travel/Umrah offices to buy & sell packages using prepaid wallets + escrow. Expanded to also be a B2C direct-sales channel for individuals (consumers & marketers). Roles: Super Admin (Target Media), Office (seller+buyer, one wallet), Individual (consumer; can toggle Marketer). Includes wallet engine (total/pending/available), colored booking lifecycle (blue→yellow→green), cancellations, P2P transfers, settlements/withdrawals, disputes, affiliate program, and a technical integration layer for the external "Rahal" system.

## User Choices
- Deliver Rahal integration requirements doc first, then build MVP (done).
- Standalone platform + ready Rahal integration layer (manual package entry works independently).
- Auth: custom JWT (email + password + mandatory phone; OTP deferred). Smart dynamic registration by account type.
- Wallet top-up: manual, admin approves uploaded bank-transfer receipts (no payment gateway).
- UI: Arabic RTL only. Admin/owner: abuzay84@gmail.com

## Architecture
- Backend: FastAPI (server.py, security.py, db.py, market.py, wallet.py, admin.py, integration.py, individual.py), MongoDB (motor). All routes /api.
- Auth: JWT (httpOnly cookie + Bearer localStorage), bcrypt, idempotent admin seed, brute-force lockout (5/15min). Roles: super_admin, office, individual. require_office / require_buyer / require_admin / require_individual gates.
- Frontend: React (CRA) + Tailwind + shadcn/ui + sonner + lucide, RTL, `@/` alias. Navy #0A2540 + gold #D4AF37. Fonts Alexandria/Cairo/IBM Plex Sans Arabic.

## Implemented
- Landing page (B2B + B2C/marketer messaging, captures ?ref= affiliate code).
- Smart dynamic registration: Office (office_name, owner_name, address, governorate, phone, email, commercial_license) OR Individual (name, governorate, phone, email).
- Unified dashboards by role (office full tools; individual simplified) with role-based sidebar.
- Marketplace with role-aware pricing: offices see net cost + commission; individuals see only final sale price (backend strips wholesale fields).
- Booking lifecycle blue→yellow(mandatory per-registrant visa numbers)→green(dispatch+24h grace→settle). B2B: double platform commission (buyer at booking, seller at settlement), both logged to platform_revenue. B2C: consumer pays full retail, seller gets net escrow, margin → platform profit.
- Affiliate/marketer: individual toggles marketer → affiliate code + link; bookings via a DIFFERENT marketer's ref credit commission (20% of margin) held in PENDING until settlement, then released to available; reversed on blue cancel (never negative). No self-referral. Full ledger entries.
- Cancellations (blue auto-refund w/ admin fee recorded; yellow seller-deduction→buyer-accept w/ platform_cut recorded; green blocked; B2C yellow blocked). All money-conserving & idempotent.
- P2P transfers (office or individual recipient, admin-approved), withdrawals (admin-approved), top-ups via receipt upload (admin-approved).
- Disputes: buyer opens within 24h of dispatch; admin resolves (refund_buyer/release_seller), idempotent.
- Admin dashboard: system liquidity, platform revenue, offices/individuals/marketers counts, pending approvals, disputes; finance center; offices management (activate/suspend); disputes.
- Rahal integration layer: /api/integrations/rahal/status, /packages/share (X-Rahal-Api-Key), /webhooks (HMAC-SHA256). Doc at /app/memory/RAHAL_INTEGRATION_REQUIREMENTS.md.

## Verified (iteration 4)
- 80/80 pytest pass; all money-safety fixes confirmed (marketer escrow no-overdraft, ledger reconciliation, no self-referral, cancellation fees recorded, individual P2P, B2B platform fee logged). Frontend flows all pass.

## Backlog (P1/P2)
- P1: Real Rahal SSO + embedded signed-iframe (awaiting Rahal APIs). Atomic booking debit (transactions/optimistic locking) to prevent oversell/overdraw under concurrency.
- P2: Object storage for receipt/visa uploads (currently URL fields). Email/notifications. Phone OTP. Debounced market search. Split market.py into packages/bookings modules. Clean stale negative-wallet test accounts.

## Test Credentials
See /app/memory/test_credentials.md — Admin abuzay84@gmail.com / Meraaj@2026; seller@test.com & buyer@test.com / Test@1234; individual+marketer user1@qa-example.com / Test@1234.
