# Database Change Manifest — Meraaj Network
(يُقدَّم قبل أي دمج مستقبلي — لا يُنفَّذ أي إجراء نشر من هذا الملف)

## 1) مجموعات جديدة (تُنشأ تلقائياً عند أول كتابة، لا تحتاج ترحيل)
orgs, org_branches, rbac_roles, credit_limits, credit_events, commission_rules,
notification_templates, notifications, admin_notes, admin_tasks, audit_log,
saved_reports, report_exports, backups, backup_drills, maintenance_runs,
rahal_outbox, rahal_inbox, package_events, sessions, withdrawals,
trip_passports, traveler_documents, cancellation_evidence.

## 2) فهارس جديدة (كلها تُنشأ عند بدء التشغيل، Idempotent)
- server.py::startup
  - users.email (unique)
  - packages.rahal_ref
  - trip_passports (package_id, passport_norm) unique
  - traveler_documents (booking_id, registrant_index)
  - cancellation_evidence.booking_id
- admin_ops.py::ensure_indexes
  - credit_limits (office_id, currency) unique
  - audit_log (at desc), notifications (user_id, at desc), sessions (jti),
    package_events (package_id, at desc)
`create_index` في MongoDB عملية Idempotent ولا تحذف أو تعدّل أي بيانات.

## 3) حقول جديدة على مجموعات قائمة
- bookings: platform_fee, platform_profit, marketer_commission, buyer_commission_total,
  net_cost_total, approval_status, dispute{}, settled, debit_split, registrants[]
  (كلها تُكتب فقط عند إنشاء/تحديث الطلب؛ الطلبات القديمة تُعرض كـ legacy دون تعديل).
- users: wallet{SAR,USD}, status, extra_permissions[], org_id, rahal_office_ref.
- transactions: type, ref, office_id, currency, description.
لا يوجد أي سكربت يكتب هذه الحقول بأثر رجعي على السجلات القائمة.

## 4) كل ترحيل/تلقين (seed) قد يعمل عند بدء التشغيل
1. `security.seed_admin()` — يُنشئ حساب المدير من `ADMIN_EMAIL`/`ADMIN_PASSWORD` إن لم يوجد،
   وإن وُجد يُحدّث كلمة المرور/الدور فقط لنفس السجل. لا يحذف أي مستخدم. Idempotent.
2. `admin_ops.ensure_indexes()` — فهارس فقط. Idempotent.
3. `orgs.seed_notification_templates()` — `upsert` بـ `$setOnInsert` فقط،
   فلا يستبدل تعديلات الإدارة على القوالب. Idempotent.
لا يوجد أي ترحيل آخر، ولا أي سكربت حذف أو كتابة جماعية يعمل عند بدء التشغيل.

## 5) تأكيدات ما قبل الدمج
- **لا تُنسخ بيانات Test ولا نسخ Test الاحتياطية إلى Live أبداً**: لا يوجد في أي Workflow
  أمر `mongodump` أو `mongorestore` أو أي نقل بيانات بين البيئتين (تحقّق: لا نتائج
  لـ mongorestore/mongodump/MONGO في `.github/workflows/*.yml`).
- **Live لا يستخدم أي حسابات تجريبية**: لا يوجد أي كود يقرأ `SEED_TEST_ACCOUNTS`
  ولا أي تلقين لحسابات تجريبية في التطبيق؛ لذا القيمة الفعلية على Live = لا تلقين تجريبي
  (`SEED_TEST_ACCOUNTS=false` سلوكياً)، وقاعدة بيانات Live تأتي من `MONGO_URL`/`DB_NAME`
  الخاصة ببيئة Live فقط دون أي إشارة إلى قاعدة Test.
- **كل ترحيلات Live إضافية وIdempotent** ولا يمكنها استبدال أو حذف بيانات قائمة
  (فهارس + `$setOnInsert` + إنشاء حساب المدير إن لم يوجد).
- **استعادة القاعدة العاملة محميّة**: معطّلة افتراضياً (`ALLOW_RESTORE`) ومرفوضة على Live،
  والاستعادة المعزولة تعمل على قاعدة مؤقتة فقط.

## تحديث (جلسة الإصلاح النهائية 2026-06)
### مجموعة جديدة واحدة
- `advertisements` — الإعلانات والعروض (الحقول: kind, title, description_ar, advertiser_name,
  advertiser_type, paid, contract_value, currency, start_date, end_date, image_url, target_url,
  audience, placements[], priority, cta_label, linked_package_id, linked_office_id, status,
  views, clicks, created_by, created_by_id, approved_by, approved_at, rejection_reason,
  created_at, updated_at).
### فهرس جديد واحد
- `advertisements(status, placements, start_date, end_date)` — يُنشأ عند بدء التشغيل، Idempotent.
### حقول جديدة على مجموعات قائمة
- لا شيء. (كل ما أُضيف في هذه الجلسة إما مجموعة جديدة أو حسابات عرض مشتقّة وقت القراءة.)
### Startup writes — القائمة الفعلية الكاملة (كما في `backend/server.py::startup` وبالترتيب)
1. فهارس مباشرة: `users.email` (unique)، `packages.rahal_ref`،
   `trip_passports(package_id, passport_norm)` (unique)،
   `traveler_documents(booking_id, registrant_index)`، `cancellation_evidence.booking_id`،
   و**`advertisements(status, placements, start_date, end_date)`**.
2. `seed_admin()` — ينشئ حساب الإدارة من ENV إن لم يوجد؛ وإن وُجد يحدّث كلمة المرور/الدور
   لنفس السجل فقط ولا يحذف أي مستخدم. Idempotent.
3. `ensure_indexes()` (admin_ops) — فهارس فقط. Idempotent.
4. `seed_notification_templates()` (orgs) — `upsert` بـ`$setOnInsert` فقط، فلا يستبدل تعديلات
   الإدارة على القوالب. Idempotent.
5. `ensure_default_rule()` (commissions) — **السلوك الفعلي في الكود**: يخرج فوراً إذا كان
   `commission_rules.count_documents({}) > 0`، أي أنه **ينشئ القاعدتين الافتراضيتين فقط عندما
   تكون المجموعة فارغة تماماً**، ولا يعدّل ولا يحدّث ولا يحذف أي قاعدة موجودة إطلاقاً
   (لا `update`، لا `upsert`، لا `delete`). عند الفراغ يُنشئ:
   «عمولة المنصة الأساسية — المكاتب» (`mode: percent`, القيمة = `platform_pct()` وهي نفس
   النسبة المستخدمة أصلاً 10%, `charge_side: buyer`, `active: true`) و«قاعدة المشتري الفرد
   (B2C) — معطّلة افتراضياً» (`active: false`). القيمة مطابقة للسلوك القائم فلا يتغيّر أي
   حساب مالي؛ الغرض جعل القاعدة ظاهرة وقابلة للإدارة.

لا يوجد أي ترحيل آخر، ولا أي سكربت حذف أو كتابة جماعية يعمل عند بدء التشغيل.
### مجموعات GridFS لصور الإعلانات
- رفع صور/بانرات الإعلانات يستخدم **GridFS bucket باسم `ad_images`**
  (`AsyncIOMotorGridFSBucket(db, bucket_name="ad_images")` في `backend/ads.py`).
- المجموعات الفعلية التي ينشئها MongoDB/GridFS تلقائياً عند أول رفع:
  - `ad_images.files` (بيانات الملف الوصفية: الاسم، الحجم، `metadata.content_type`,
    `metadata.by`, `metadata.at`)
  - `ad_images.chunks` (محتوى الصورة مقسّماً إلى أجزاء)
- خصائصها: **Additive** بالكامل • **خاصة بملفات صور الإعلانات فقط** •
  **لا تستبدل أي بيانات موجودة** (كل رفع ينشئ ملفاً جديداً بمعرّف جديد) •
  **لا تعدّل المحافظ ولا الطلبات ولا أي معاملة مالية** • لا تُحذف تلقائياً بأي وظيفة صيانة.
- التقديم للقراءة عبر `GET /api/ads/image/{file_id}` (قراءة فقط).

### تأكيدات
- لا drop/dropDatabase/dropCollection ولا deleteMany تلقائي ولا استبدال قاعدة ولا إعادة تعيين
  أرصدة/طلبات/مستخدمين في أي كود أُضيف.
- التقارير والمطابقة وتتبّع التسوية: قراءة فقط 100%.
