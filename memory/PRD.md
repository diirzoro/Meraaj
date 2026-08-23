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

## Real bidirectional E2E — Rahaal Test ↔ Meraaj Preview (June 2026)
- Shared TEMPORARY HMAC secret set in Preview `backend/.env` MERAAJ_SHARED_SECRET (fingerprint len67/d812…0168); Rahaal Test holds the same. RAHAL_WEBHOOK_URL (outbound Meraaj→Rahaal) pointed at Rahaal Test: https://visa-booking-5.preview.emergentagent.com/api/meraaj/webhooks (that endpoint is live and enforces HMAC — 401 on unsigned ping).
- testing_agent iteration_8: **E2E 15/15 PASS** — inbound SHARE (v2: package_type, 3 room types w/ net+commission+customer, 2 buses, 2 hotels, components, features, images, dates, currency → DB + UI) and package.updated (partial no-blank, no-duplicate, match by rahal_ref/meraaj_package_id not name, idempotency via event id, 401 on bad signature). CRITICAL image check: stored image URLs fetched → HTTP 200 and rendered (hero naturalWidth=1200).
- NOTE: temporary secret is for Preview E2E only; real production secret to be set via the platform Secrets (deployment) at Production time. No production deploy done. No further code changes per user directive.
- Deploy order pending: docs → Backup → Rahaal Test → Production Backup → Production Deploy → Prod verify + set prod Secrets.

## Rahaal Contract v2 Adapter (June 2026) — Preview/Test only (NOT deployed)
- `integration.py._adapt_package(body)` normalizes Rahaal Contract v2 AND legacy flat payloads into Meraaj canonical fields: `package_type→type`, `name→title`, `start_date→departure_date`, `end_date→return_date`, `pricing.currency|currency→currency`, stores `room_pricing[]` ({room_type,net,commission,customer}), `package_transports[]→transports`, `components[]`, `hotels[]`, `features[]`, `image_url|images→images[]`. Flat pricing derived from the base (double) room for backward-compatible booking math.
- `share_package` matches by `meraaj_package_id → rahal_ref` (never title) and mirrors the raw payload + v2 fields into `rahal_packages`.
- `rahal_webhook`: `package.updated` routes through `_adapt_partial(data)` — updates ONLY keys present in the delta (no blanking of description/city/transport); refreshes the `rahal_packages` mirror; matching precedence id→ref; Idempotency via `event.id`/`event_id` (dup delivery ACKed once); `handled=false` when a targeted event matches nothing.
- `_view_package` sanitizes for non-office: hides net/commission (incl. child/infant) and strips `room_pricing` to `{room_type,customer}` only.
- Frontend `PackageDetail.js`: renders أسعار الغرف (office sees net+commission), النقل والمواصلات, مكونات البرنامج, hotels, features, gallery; Arabic labels for room_type (ثنائية/ثلاثية/رباعية) and transport (باص/طيران).
- Verified: testing_agent iteration_7 (20/20 v2 + 27/27 regression + UI); local 47/47 pytest + 4/4 partial-update/idempotency/mirror/unmatched checks. Deploy order pending user: review → publish v2 in Rahaal → E2E → backup → test server → production.

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

## Manual room pricing & features in CreatePackage — DONE Aug 2026
- Per user request (Option a: display-only, no booking-engine impact): offices can now add **room pricing** (نوع الغرفة double/triple/quad/quint/single + net + commission + customer) and **program features** (نصية) directly in `CreatePackage.js` (previously these only arrived via Rahal). Dynamic add/remove rows.
- Backend `PackageInput` gained `room_pricing: List[RoomPricingInput]` ({room_type, net?, commission?, customer}) and `features: List[str]`; persisted via `payload.model_dump()`. Booking/wallet engine UNCHANGED (still adult/child/infant tier pricing).
- Display already existed: `PackageDetail.js` renders أسعار الغرف table + مميزات checklist; Market card computes "يبدأ من" from lowest room `customer`. `_view_package` hides net/commission from non-office & strips room_pricing to {room_type,customer}.
- Verified: curl (create with 2 rooms + 3 features → stored & returned; guest GET hides net/commission, keeps customer+features) + create-form screenshot (both sections render, layout intact).

## Production-verified pricing + webhook fixes — DONE Aug 2026
- **Room pricing NaN fix (frontend)**: Rahal now sends `room_pricing[].customer` as an OBJECT `{adult, child, infant}` (not a scalar). Added `roomCustomer(customer, cat)` helper in `format.js` (handles BOTH object=Rahal and scalar=manual Meraaj programs). `PackageDetail.js` room table shows سعر البالغ/الطفل/الرضيع columns; main sidebar price = `roomCustomer(room_pricing[0].customer,'adult') || Number(final_sale_price) || 0`. `Market.js` "يبدأ من" = min adult across rooms, fallback `final_sale_price`. Booking engine UNCHANGED.
- **Backend safety**: `_adapt_package` base-room derivation now extracts `.adult` when `customer` is an object, so `final_sale_price`/net/comm remain valid scalars (booking/admin math intact). `room_pricing` still stored RAW (object customer preserved for FE).
- **Webhook event type (backend)**: `rahal_webhook` reads `event.get("event") or event.get("type")` — Rahal envelope `{id, type, timestamp, data}` now yields handled:true / matched_count:1 (was event:null / handled:false).
- **Activation/Deactivation**: already implemented (package.activated→listed, package.deactivated/deleted/removed/disabled→unlisted); confirmed preserved E2E.
- Items NOT in Meraaj repo (Rahal ERP-side): professional confirmation dialogs (askConfirm/ConfirmHost), Delete Package action — no Meraaj changes. **IMAGE ISSUE LEFT OPEN per user (not touched).**
- Verified E2E via signed HMAC curl: SHARE(object customer)→stored, guest sees customer object + scalar final_sale_price + net hidden; UPDATE(type-envelope)→handled 1; DEACTIVATE→hidden; ACTIVATE→visible. Frontend screenshot: 1,600/1,250/550 render, no literal NaN.

## Image receiving hardening — DONE Aug 2026
- `_adapt_package` already accepts `images[]` and normalizes a single `image_url` string → `[image_url]` (also handles `image_url` as list).
- **Anti-wipe guard added**: `_adapt_partial` now only sets `images` when the incoming list is non-empty (`has(...) and m["images"]`); `share_package` re-share preserves `existing.images` when the incoming payload has no images. Prevents an empty payload from wiping a valid stored image. Mirror `rahal_packages.images` uses the preserved `doc["images"]`.
- Frontend renders the Rahal URL `https://rahaal.targetmediagrp.com/api/meraaj/packages/<id>/image` directly as `<img src>` (Market/PackageDetail/EmbedMarket). Verified src is set correctly (image only appears broken inside the preview sandbox because that external prod domain is unreachable there; loads in production).
- Verified E2E (signed HMAC curl): share(image_url string)→[url]; update(no images)→preserved; re-share(no images)→preserved; share(images[])→stored as-is. No frontend NaN.

## Prominent topup popup + duplicate guard + public browsing — DONE Aug 2026
**1. Wallet topup UX (`Wallet.js` TopupDialog + `wallet.py`):**
- Success now shows a **centered popup dialog** (`topup-success-dialog`) with a large green check + reassurance message + "تمام" button, instead of a small toast.
- Submit button disabled immediately with "جارٍ الإرسال..." loading state (`busy` guard) to prevent double-submit on click.
- **Backend duplicate guard** in `create_topup`: rejects an identical pending topup (same office+amount+currency) created within the last 120s → HTTP 409 "لديك طلب شحن بنفس المبلغ قيد المعالجة". Verified: 200 → 409(identical) → 200(different amount).

**2. Public browsing before login:**
- Landing page now fetches `GET /api/packages` and renders a **"أحدث البرامج المتاحة"** section (6 newest cards, `landing-programs`) with "تصفّح كل البرامج" → `/market`. No login required.
- `/market` and `/market/:id` moved out of `<Protected>` into `PublicOrMember` wrapper: authenticated users get the app `Layout`; guests get new `PublicLayout` shell (header with login/register + market link).
- Booking is still gated: guest clicking "احجز الآن" (`open-booking-btn`) → redirect to `/login?next=/market/:id`; `Login.js` now honors `?next=` after successful login (non-admin).
- Backend `GET /packages(/{id})` already anonymous via `get_optional_user`; `_view_package` hides net/commission from guests.
- Verified (screenshots): landing 6 cards render (no NaN), public market 39 cards + guest header, book→login redirect, topup success popup.

## Backlog (P1/P2)
- P1 (mobile next): Firebase FCM push (needs Firebase project + `google-services.json`; add `device_tokens` model + triggers on booking/wallet events) — Phase 3. Capgo OTA updates (needs Capgo account/key) — Phase 4.
- P1: Real Rahal SSO + embedded signed-iframe (awaiting Rahal APIs). Atomic booking debit (transactions/optimistic locking) to prevent oversell/overdraw under concurrency.
- P2: Object storage for receipt/visa uploads (currently URL/base64 fields). Email/notifications. Phone OTP. Debounced market search. Split market.py. Rewrite/delete obsolete single-USD pytest suites. Clean stale TEST_* accounts.

## Test Credentials
See /app/memory/test_credentials.md — Admin abuzay84@gmail.com / Meraaj@2026; seller@test.com & buyer@test.com / Test@1234; individual+marketer user1@qa-example.com / Test@1234.
