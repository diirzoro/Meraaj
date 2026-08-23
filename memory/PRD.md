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

## Room selection drives booking price (Option b) — DONE Aug 2026
Per user: booking must charge the **selected room's** customer price dynamically (not display-only).
- **Frontend `PackageDetail.js`**: radio selector on each row of "أسعار الغرف" (`room-select-<type>`, row clickable, first room selected by default). Main sidebar price, tier box, per-traveler charges, and booking total all recompute from the selected room. Selected room shown in booking dialog ("نوع الغرفة المختارة"). Sends `room_type` to `POST /bookings`.
- **Backend `market.py` booking engine**: `BookingInput.room_type` (optional). New `_find_room`, `_room_customer_price`, `_booking_prices` — when a room is selected, B2C sale = room `customer[category]` (obj {adult,child,infant}) with fallback to room adult; office net/commission = room net/commission; falls back to package-level tier pricing when no room. Unknown `room_type` → 400. `room_type` stored on the booking. Wallet/escrow logic otherwise UNCHANGED.
- **Child/infant from Rahal**: `RoomPricingInput.customer` relaxed to `Union[float, Dict[str,float]]` so object pricing (adult/child/infant) is accepted on the manual endpoint too; Rahal adapter already stores it raw. Room table + booking now consume child/infant prices accurately.
- Verified: unit test of `_booking_prices` (double 1500/1300/700, quad 1100/900/300, office net/comm 700/150, scalar+child-fallback 900); UI screenshot (double 1500 → quad 1100 dynamic in main price + booking total); real E2E booking (quad, 1 adult) → amount_charged 1100 SAR, room_type=quad persisted.

## Professional market filters & sorting — DONE Aug 2026
Rebuilt the market search bar (`Market.js`) + backend `list_packages` filtering/sorting.
- **Filters**: price range (`min_price`/`max_price` on "starts-from" adult price), departure date range (`date_from`/`date_to`), trip-duration quick chips (short ≤7 / mid 8–14 / long 15+ via `min_days`/`max_days`, computed from departure→return), quick-feature toggles (breakfast / near_haram / vip_transport / wifi — matched via `FEATURE_SYNONYMS` fuzzy AND), type tabs, and text search.
- **Sort By** (`sort`): newest (default), price_asc, price_desc, date_asc (soonest departure), duration_asc, best_selling.
- **Seller rating = Option (b) proxy**: `best_selling` sorts by completed-deals count per seller (bookings with status `green`, via `_seller_deals_map`); each card shows a gold "X صفقة" badge (`pkg-deals-<id>`). Real star ratings deferred.
- Backend returns computed `start_price`, `duration_days`, `seller_deals` per package. Debounced (350ms) auto-apply on the frontend; result count shown; reset button clears all.
- Verified: curl (price_asc/desc ordering, min/max range all-in-range, best_selling desc, features=breakfast returns only matching) + UI screenshot (40→1 result after price+duration+feature+sort; filter bar renders cleanly, public/guest accessible).

## Admin offices — WhatsApp contact column — DONE Aug 2026
- `AdminOffices.js`: added a **"واتساب"** column showing each office's normalized number + a green direct-contact button (`whatsapp-<id>`) that opens `https://wa.me/<number>?text=<greeting>` in a new tab. Number normalized (digits only, strips leading zeros/+); offices without a valid number show "—". No backend change (office `phone` already returned by `GET /admin/offices`).
- Verified (screenshot as super_admin): column renders, buttons present, href correct with prefilled Arabic greeting.
- Note: test offices store `0770000000` → shown as `770000000`. Real international numbers (e.g. 967781115482) render as-is once an office saves them.

## Idle auto-lock + hard-refresh navigation — DONE Aug 2026
Files: NEW `frontend/src/config.js`, NEW `frontend/src/components/SessionManager.js`; edited `App.js` (mount SessionManager inside BrowserRouter), `Login.js` (route restore), `Layout.js` (clear resume on manual logout). No backend/auth/SSO/booking/pricing/wallet/image changes.
- **Idle auto-lock**: `SessionManager` (inside router) resets a timer on mousemove/mousedown/keydown/scroll/touchstart/click; on expiry it saves the current deep route to `localStorage.meraaj_resume_route`, calls the existing `logout()`, and routes to `/login`. Timeout centralized in `config.js` → `IDLE_TIMEOUT_MS = 15*60*1000`. QA override: `localStorage.meraaj_idle_ms`. Skips `/embed` (Rahaal SSO) and `/login`,`/register`.
- **Route restore**: `Login.js` after login uses `?next=` (booking guard) → else `meraaj_resume_route` → else home (`/admin` or `/dashboard`), with role-sanity check; clears the key after use. Manual logout (`Layout.doLogout`) removes the key so a normal logout does NOT restore.
- **Hard refresh**: on document `navigation.type === "reload"`, an authenticated user is sent to their home (`/dashboard` or `/admin`); guests keep public deep links (preserves shareable market links). SPA nav, deep links, back/forward, login redirects and SSO ("navigate"/"back_forward") are untouched.
- Verified (Playwright): deep route + reload → /dashboard; idle (2.5s QA) → /login with resume saved → re-login → restored exact deep route; SSO embed excluded.

## Automatic image optimization + consistent card ratios — DONE Aug 2026
Files: NEW `frontend/src/lib/imageOptimizer.js`; edited `CreatePackage.js` (image upload UI), `Market.js`/`Landing.js`/`EmbedMarket.js` (card aspect ratio). No backend/schema/contract/HMAC/auth/booking/pricing/wallet change.
- **Client-side optimizer** (`optimizeImage`): validates JPG/PNG/WebP → canvas resize to max 1200px longest side (aspect ratio preserved, only downscales) → `toDataURL("image/webp", 0.82)` with JPEG fallback. Runs once at upload; the STORED data URL is already small (real payload reduction, not CSS).
- **CreatePackage**: new optional multi-image upload (`pkg-images-file`) with previews + remove; optimized data URLs stored in `images` (max 6); falls back to default stock image per type when none uploaded.
- **Cards**: consistent responsive `aspect-[4/3]` + `object-cover` across Market/Landing/Embed cards (no stretch, uniform desktop/tablet/mobile). PackageDetail hero already object-cover.
- **Rahaal**: images arrive as external URLs — untouched, still displayed (contract unchanged).
- Verified (Playwright): 5.1 MB JPEG upload → optimized **WebP ~588 KB (~89% smaller)**, `data:image/webp` confirmed; create form renders; large landscape resized. Portrait/small handled by the same ratio logic.

## Full responsive pass + image fallback — DONE Aug 2026 (testing iteration_9: 100%)
Smallest compatible fixes (no redesign, no backend/contract/HMAC/booking/pricing/wallet change):
- `dialog.jsx`: DialogContent now `w-[calc(100%-2rem)] max-w-lg max-h-[90vh] overflow-y-auto rounded-lg` → every modal fits inside the viewport (gutters + internal scroll + visible close) down to 320px.
- `index.css`: global `html,body,#root { max-width:100%; overflow-x:hidden }` + `img { max-width:100% }` → no accidental horizontal overflow.
- Cards already `aspect-[4/3]` + `object-cover` (Market/Landing/Embed); PackageDetail hero unchanged.
- NEW `components/PkgImage.js`: package image with graceful fallback — shows placeholder when src is missing OR the image fails to load (fixes dead external Rahaal image URLs rendering a broken-image glyph). Used in Market/Landing/PackageDetail/Embed.
- Verified by testing agent (real Playwright viewport emulation) at 320/360/375/390/412/430 mobile + 1024/1280/1440/1920 desktop across all major screens: no horizontal overflow anywhere; booking & topup dialogs fit at 360 & 320; cards/images responsive; RTL correct; market filters work at mobile & desktop; room-pricing (double 1500 / quad 1100) correct; guest browsing + booking→login guard; **regressions all green**: idle auto-lock + resume, hard-refresh→dashboard, manual-logout no-restore, admin WhatsApp column. Post-fix: 0 broken card images.
- Note (from testing): mobile sidebar nav is off-canvas — open via `menu-open-btn` before nav-* links at <1024px (existing behavior, not a bug). Office-role booking total is intentionally net+10% commission.

## FIX: Rahal unified pricing schema (NaN / 0.00 / child-infant) — DONE Aug 2026
Root cause: Rahal unified its pricing UI so `room_pricing[].net`, `.commission` AND `.customer` are now per-category OBJECTS `{adult, child, infant}` (previously net/commission were scalars). Meraaj passed the object straight into `money()` → "NaN" in net/commission columns, and the booking engine's `float(room["net"])` would break / yield 0.00; child/infant prices weren't read.
- **Frontend** `format.js`: `roomCustomer(value, cat)` now guards NaN and falls back to `.adult`; reused for net/commission/customer (object OR scalar). `PackageDetail.js`: room-table net/commission cells extract adult via `roomCustomer` (show "—" if absent, never NaN); `chargeOf` uses `roomCustomer` for net/commission/customer per category with NaN-safe fallbacks. (Also fixed missing `PkgImage` import in PackageDetail.)
- **Backend** `market.py`: new `_room_num(field, cat)` (object→cat else adult; scalar→all; never raises); `_booking_prices` uses it for net & commission + `_room_customer_price` for sale, all falling back to package tier pricing. `RoomPricingInput.net/commission` relaxed to `Union[float, Dict]`. `integration.py` base-room derivation extracts `.adult` from object net/commission so flat `net_cost_per_seat`/`buyer_office_commission` stay numeric.
- Verified E2E (signed share of unified-object package + real bookings): B2C quad adult+child+infant = **2,300** (1100+900+300); office quad adult total **715**; office room table shows 1,000/200 & 700/150 with child/infant 1,300/700 & 900/300; **no "NaN" anywhere**; guest view still strips net/commission and keeps customer object.

## Backlog (P1/P2)
- P1 (mobile next): Firebase FCM push (needs Firebase project + `google-services.json`; add `device_tokens` model + triggers on booking/wallet events) — Phase 3. Capgo OTA updates (needs Capgo account/key) — Phase 4.
- P1: Real Rahal SSO + embedded signed-iframe (awaiting Rahal APIs). Atomic booking debit (transactions/optimistic locking) to prevent oversell/overdraw under concurrency.
- P2: Object storage for receipt/visa uploads (currently URL/base64 fields). Email/notifications. Phone OTP. Debounced market search. Split market.py. Rewrite/delete obsolete single-USD pytest suites. Clean stale TEST_* accounts.

## Test Credentials
See /app/memory/test_credentials.md — Admin abuzay84@gmail.com / Meraaj@2026; seller@test.com & buyer@test.com / Test@1234; individual+marketer user1@qa-example.com / Test@1234.
