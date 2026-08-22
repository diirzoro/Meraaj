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
- Rahal integration layer: /api/integrations/rahal/status, /packages/share, /webhooks. Doc at /app/memory/RAHAL_INTEGRATION_REQUIREMENTS.md.

## Rahal Receiver v1.1 (updated June 2026)
- `POST /api/integrations/rahal/packages/share`: now verifies inbound requests via HMAC-SHA256 with `MERAAJ_SHARED_SECRET` (header `X-Rahal-Signature`/`X-Meraaj-Signature`); legacy `X-Rahal-Api-Key` still accepted. Stores `images[]` + `features[]`, mirrors the raw payload into a dedicated `rahal_packages` collection, and returns `remote_id`.
- `POST /api/integrations/rahal/webhooks`: accepts HMAC via `MERAAJ_SHARED_SECRET` OR `RAHAL_SHARED_SECRET`. `package.deactivated/deleted/removed/disabled` → unlist (soft, preserves booking history) + syncs `rahal_packages` mirror; `package.activated` → relist; `package.updated` passes through images/features. NOTE: "deletion" = unlist/hidden (no physical delete) to protect existing bookings.
- Frontend `PackageDetail.js`: shows an image gallery (hero + up to 4 thumbnails) and a `features` checklist. `_view_package` passes features/images to all viewers while still hiding net cost from non-office.

## Wallet Engine — TRUE Dual-Currency (updated June 2026)
- Wallet shape: `{ SAR:{available,pending,total}, USD:{available,pending,total} }` (was single-USD). Migration script `backend/migrate_dual_wallet.py` moved legacy balances into the USD bucket (run once; idempotent).
- Top-ups keep their own currency (no conversion). Bookings are denominated in the PROGRAM's currency; escrow/settlement/refunds/marketer-commissions/platform-revenue all stay in that currency (NO merge to USD).
- Buyer debit: program-currency balance first, then covers any shortfall from the other currency at FIXED rate SAR_PER_USD=3.77 (the ONLY conversion point). Stored per-booking as `debit_split`. Insufficient total funds → 400.
- P2P transfers & withdrawals carry a `currency`; admin approval moves funds in that currency, checking sender balance in that currency.
- Platform revenue SPLIT per currency; admin dashboard `GET /api/admin/dashboard` returns `liquidity{SAR,USD}` + `platform_revenue{SAR,USD}`.
- Strict currency validation via `CurrencyField` (db.py) on Topup/Transfer/Withdrawal/Package inputs (Literal SAR/USD, case-normalized, rejects others → 422).
- Yellow-cancel `deduction` now bounded `0 <= deduction <= net_cost_total` (fixed 2 critical money-creation leaks).

## Verified (iteration 6 — dual-currency)
- 22/22 new dual-currency pytest pass (core contract 15 + edges 7 incl. the 2 critical fixes + 3 validation gaps). Rahal suites 27/27 pass (no regression). Frontend: Wallet/Dashboard/Admin pages show per-currency balances; compiles clean.
- NOTE (by design, per user): blue-cancel refund is paid in the PROGRAM currency (not per debit_split); value conserved at 3.77.

## Verified (iteration 4)
- 80/80 pytest pass; all money-safety fixes confirmed (marketer escrow no-overdraft, ledger reconciliation, no self-referral, cancellation fees recorded, individual P2P, B2B platform fee logged). Frontend flows all pass.

## Tiered pricing — Adult / Child / Infant (June 2026)
- Programs carry optional per-tier prices: `child_net_cost/child_sale_price/child_commission` and `infant_*` (null = fall back to adult). Set in CreatePackage under "أسعار الفئات (اختياري)".
- Booking (`create_booking`) sums net/sale/commission per registrant `category` (adult|child|infant) via `_tier_prices`. Registrant gains `category` + optional `photo` (infant photo, base64). Card keeps showing adult price; booking dialog has add-buttons (بالغ/طفل/رضيع), per-traveler price, infant photo upload, and a live per-category total.
- `_view_package` also hides child/infant net & commission from non-office viewers. Verified e2e (adult+child+infant total, wallet debit, seller escrow in program currency, categories+photo stored, no net leak). Dual-currency suites 22/22 still pass.

## Meraaj Network outbound sync (June 2026)
- `create_package` now enqueues `package.published` to the reliable outbox (`notify_rahal`) so publishing a program from the app/web auto-syncs to the Meraaj Network/Rahal (includes title, dates, images[], features[], hotels[], pricing, seats).
- `toggle_package` on manual programs enqueues `package.activated`/`package.deactivated`. Rahal-sourced programs are not echoed back. Delivery requires `RAHAL_WEBHOOK_URL`; otherwise events queue for admin retry.
- Verified via curl (publish → pending outbox entry; toggle → deactivate entry). Rahal suites 27/27 still pass.

## Android App — Phase 1 (Capacitor native shell) — DONE June 2026
- Capacitor **v7** stack (Node-20 compatible; v8 CLI needs Node ≥22). Packages: @capacitor/core,app,status-bar,splash-screen,keyboard + dev cli,android,assets. Config `frontend/capacitor.config.json` (appId `network.meraaj.app`, appName «معراج نتورك», webDir `build`).
- Native code under `frontend/src/native/` (all guarded by `Capacitor.isNativePlatform()` → zero effect on web): `useAndroidBackButton.js` (router-aware back, double-back-to-exit on root routes), `useNativeChrome.js` (status bar navy #0A2540 + light icons, splash hide, sets `cap-native` body class), `NativeBridge.jsx` (mounted once inside BrowserRouter).
- Touch/native feel in `src/index.css`: tap-highlight off, `touch-action: manipulation`, overscroll off, user-select off (except inputs), safe-area insets. `index.html` viewport → `viewport-fit=cover, maximum-scale=1`.
- Icon+splash generated (navy/gold brand) from `frontend/assets/` → 56 Android resources. Android project scaffolded at `frontend/android/`. Web build unaffected (verified 200 + clean console + landing screenshot).
- Local build steps documented in `frontend/ANDROID_BUILD.md` (yarn build → cap sync → cap open android; gradlew assembleDebug/bundleRelease). APK/AAB built on user's machine (no Android SDK in server env).

## Backlog (P1/P2)
- P1 (mobile next): Firebase FCM push (needs Firebase project + `google-services.json`; add `device_tokens` model + triggers on booking/wallet events) — Phase 3. Capgo OTA updates (needs Capgo account/key) — Phase 4.
- P1: Real Rahal SSO + embedded signed-iframe (awaiting Rahal APIs). Atomic booking debit (transactions/optimistic locking) to prevent oversell/overdraw under concurrency.
- P2: Object storage for receipt/visa uploads (currently URL/base64 fields). Email/notifications. Phone OTP. Debounced market search. Split market.py. Rewrite/delete obsolete single-USD pytest suites. Clean stale TEST_* accounts.

## Test Credentials
See /app/memory/test_credentials.md — Admin abuzay84@gmail.com / Meraaj@2026; seller@test.com & buyer@test.com / Test@1234; individual+marketer user1@qa-example.com / Test@1234.
