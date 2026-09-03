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
