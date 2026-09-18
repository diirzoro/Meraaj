# Test Credentials — Meraaj Network

## Super Admin (Target Media)
- Email: `abuzay84@gmail.com`
- Password: `Meraaj@2026`
- Role: `super_admin`

## Test Office accounts
- Seller office: `seller@test.com` / `Test@1234` (role: office, has packages)
- Buyer office: `buyer@test.com` / `Test@1234` (role: office, funded)

## Individual / Marketer
- `user1@qa-example.com` / `Test@1234` (role: individual, marketer)

## Rahal SSO (embedded store)
- Shared secret (HS256): `rahal_meraaj_shared_secret_key_2026` (env `RAHAL_SHARED_SECRET`)
- MERAAJ_STORE_URL: `https://umrah-exchange.preview.emergentagent.com/embed/market?token=<SIGNED_JWT>&lang=ar`
- SSO exchange: `POST /api/integrations/rahal/sso` body `{ "token": "<SIGNED_JWT>" }` → returns Meraaj `access_token`.
- JWT claims: office_ref, email, office_name, (owner_name/phone/governorate optional), exp.
- Auto-provisions/links a Meraaj office (source=rahal, rahal_office_ref). Seeded test office via SSO: `rahal_office1@qa-example.com` (office_ref RHL-OFF-77001).

## Auth
JWT via httpOnly cookie `access_token` + `access_token` in body (Bearer fallback, localStorage `meraaj_token`).

## Wallet model (dual-currency — updated June 2026)
Wallets are now TRUE multi-currency: `wallet = { SAR:{available,pending,total}, USD:{available,pending,total} }`.
- Top-ups keep their own currency (no conversion). Program bookings are denominated in the program's currency.
- Buyer debit takes from the program-currency balance first; any shortfall is covered from the other currency at the FIXED rate SAR_PER_USD=3.77.
- Escrow/settlement/refunds/marketer-commissions/platform-revenue all stay in the program's currency (NO merging to USD). Admin dashboard reports liquidity + revenue split per currency.
- Legacy balances were migrated into the USD bucket via `backend/migrate_dual_wallet.py`.

## Meraaj TEST server accounts (https://meraaj-test.targetmediagrp.com — separate DB, NOT preview)
- Office Owner: `owner@gmail.com` / `123456` — role: `office`, office "مكتب معراج التجريبي". Created via public /api/auth/register. Login verified ✓. As a normal (non-Rahal) office it is UNRESTRICTED = full office permissions.
- Office User:  `taha@gmail.com`  / `123456` — role: `office`. Pre-existing (office "زاد المشاعر", has wallet). Login verified ✓.
- PENDING (needs Test server RAHAL_SHARED_SECRET / MERAAJ_SHARED_SECRET, unknown to agent): apply reduced `rahal_permissions` to taha and unify office via signed POST /api/integrations/rahal/offices/link. The preview secret `rahal_meraaj_shared_secret_key_2026` is NOT accepted by the Test server (401).
- Same-origin: Test frontend calls /api on same domain via nginx proxy → NO CORS / env / cookie changes needed.

## Meraaj TEST server — standalone staff account (path B, 2026-09-01)
- Staff: `staff@gmail.com` / `123456` — role: `office`, office_name "مكتب معراج التجريبي". Created via public /api/auth/register. Login verified ✓. Independent Test office (own _id/wallet), used for current permission testing.
- taha@gmail.com is kept UNCHANGED as independent Test office "زاد المشاعر" (has real test wallet/bookings — do NOT modify).
- Reduced permissions on staff/taha still require Test-server RAHAL_SHARED_SECRET (agent has no shell/DB access to Test); not applied. See memory/DEV_NOTES.md for the Office/Staff model limitation.

## Batch 2 notes (2026-09-01)
- No new accounts created. Super Admin `abuzay84@gmail.com / Meraaj@2026` (login field: `access_token`).
- Test data left in preview DB: booking `6a97252cd99f0d8ab7be0fd1` (buyer@test.com, SAR 1020,
  created to verify the commission snapshot + freeze block) and package `TEST_باكج_bdaab8`.
- All credit limits reset to 0 / status active; all TEST_ commission rules deleted.

## Batch 3–5 QA (2026-09-01, iteration_12)
- SECOND Super Admin (for Maker–Checker): `qa.checker@qa-example.com` / `Checker@2026` (role super_admin, created via tests/_mk_second_admin.py). Keep for future dual-control tests.
- Suite: `cd /app/backend && python -m pytest tests/test_admin_enterprise_b345.py -n 0` (run SERIALLY).
- Test data left in preview DB: TEST_ offices/packages/bookings created by the suite; 3 gzip backups in /app/backups. No suspended accounts, no force-logout flags, no credit limits, no extra commission rules, 2FA disabled.

## Batches 3-5 notes (2026-09-01)
- No new login accounts created by the main agent. Super Admin: abuzay84@gmail.com / Meraaj@2026
- The testing agent may have created a second super_admin for Maker–Checker — see iteration_12.json.
- Suspended-login guard verified with buyer@test.com then reset to status=active.
- All credit limits remain 0/active; no account left suspended or force-logged-out.
- Backups written to /app/backups (unencrypted until BACKUP_PASSPHRASE is set); ALLOW_RESTORE unset.

## جلسة الإصلاح النهائية (2026-06)
- لم يُنشأ أي حساب جديد. المستخدم: `abuzay84@gmail.com` / `Meraaj@2026` (super_admin).
- المعتمد الثاني (Maker–Checker) المستخدم في التحقق: `qa.checker@qa-example.com` / `Checker@2026`.
- سجل مؤقت واحد أُنشئ للتحقق وموثّق: إعلان "إعلان تحقق مؤقت" (advertisements) —
  مسودة ← بانتظار الاعتماد ← رُفض الاعتماد من نفس المنشئ (403) ← اعتُمد من qa.checker ← ظهر عاماً.
  يمكن حذفه/أرشفته من `/admin/ads` عند رغبتكم (لم أحذف أي بيان).

## تحقق فواتير الإعلانات (2026-06)
- أُضيف `commercial_license: CR-TEST-1010101010` لحسابي `seller@test.com` و`buyer@test.com` (مطلوب لإطلاق إعلان تجاري).
- بيانات التحقق المؤقتة (باقات/إعلانات TEST_) حُذفت بعد الاختبار. بقيت حركات محفظة `buyer@test.com` (خصم 25 ريال لإعلان مُعتمد) في السجل المالي.

## Batch 2 — المحاسبة (2026-06)
- لا حسابات دائمة جديدة: سكربت `backend/tests/batch2_rbac_qa.py` يُنشئ حسابات `qa-b2-<role>-<tag>@qa-example.com` بكلمة `QaTest@2026` ويحذفها بالكامل في نهاية التشغيل (حتى لو فشل).
- إسناد الأدوار المحاسبية للموظفين يتم من: الصلاحيات والأمان → الأدوار / الصلاحيات / نطاق الحسابات.

## Meraaj Mobile (2026-06)
- التطبيق يستخدم **نفس** مصادقة معراج: `POST /api/auth/login`.
- للاختبار على الجوال: `buyer@test.com` / `Test@1234` (مكتب) و`user1@qa-example.com` / `Test@1234` (فرد).
- حسابات `super_admin` تُحوَّل تلقائياً إلى لوحة الويب `/admin` ولا تدخل قشرة التطبيق.

## جلسة الإغلاق النهائية (2026-06)
- **الإدارة تدخل التطبيق الآن**: `abuzay84@gmail.com` / `Meraaj@2026` → يفتح `/m/home` بتجربة إدارة الجوال (وليس `/admin`).
- المكتب: `buyer@test.com` / `Test@1234` · الفرد: `user1@qa-example.com` / `Test@1234`.
- سكربتات QA تُنشئ وتحذف حساباتها: `qa-b2-*` و`qa-mob-*@qa-example.com` بكلمة `QaTest@2026`.
- إعادة تعيين كلمة المرور: الرمز يُنشأ في `db.password_reset_tokens` (هاش فقط) ويُسلَّم عبر الإدارة — لا يوجد مزوّد بريد/SMS مُهيّأ.
