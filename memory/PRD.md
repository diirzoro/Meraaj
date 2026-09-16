# معراج نتورك (Meraaj Network) — PRD

## المشكلة الأصلية
منصة سوق B2B/B2C لمكاتب السفر والسياحة لبيع وشراء برامج العمرة والسياحة.
- المعمارية: React SPA + FastAPI + MongoDB، واجهة عربية RTL صِرفة.
- الأدوار: مكتب (بائع/مشترٍ)، فرد (B2C)، مسوّق/أفلييت، مدير عام، موظف مستقل يشترك في محفظة المكتب.
- المحرك المالي: محافظ مزدوجة العملة (ريال + دولار) مفصولة تمامًا.
- تكامل B2B مع نظام «رحّال» بتوقيع HMAC-SHA256 ونمط Outbox.
- لوحة إدارة مؤسسية: تحليلات، سجل مالي، RBAC، سجلات تدقيق، تقارير PDF عربية، سقوف ائتمانية،
  محرك عمولات، نسخ احتياطية مشفّرة.

## قيود المستخدم الصريحة (سارية)
- كل العمل داخل Emergent Workspace فقط: لا Push إلى GitHub، لا Save to GitHub، لا PR، لا Merge،
  لا نشر على Test، لا Promote إلى Live، لا تعديل أسرار أو متغيّرات الإنتاج.
- **لا اختبارات آلية** (Backend/Frontend/Playwright/E2E/Regression/Scans/Builds للتحقق) —
  المراجعة اليدوية يقوم بها المستخدم في Emergent View والمعاينة.
- لا تنفيذ لقيود التسوية الـ216، لا حذف بيانات QA، لا تفعيل الماسح، لا إشعارات خارجية.
- لا refactoring أو إعادة تصميم أو إعادة بناء لميزات قائمة.
- عدم المساس بـ: SSO رحّال، المصادقة، الجلسات والتوكنات، HMAC، الـWebhooks والـDispatcher،
  دورة حياة الطلب، المحفظة والحسابات المالية، الـAPIs والصفحات وبيانات القاعدة القائمة.

## ما تم إنجازه
### حتى يونيو 2026 (إصدار Enterprise — 6 مراحل)
لوحة إدارة متقدمة، مركز الطلبات، السجل المالي والسحوبات، محرك العمولات، السقوف الائتمانية،
الباقات والمسافرون والتكاملات، RBAC مع 12 دورًا و21 صلاحية وحسابات موظفين مستقلة،
مركز الإشعارات، سجلات التدقيق والتقارير والإعدادات، Crons، نسخ احتياطية مشفّرة،
تصدير PDF عربي، وPoC لجسر الماسح.

### يونيو 2026 — حارس نشر GitHub
- `meraaj-test-deploy.yml`: المُشغّل الوحيد `push` على `main`، `workflow_dispatch` محذوف،
  حرس مزدوج (`if` + خطوة Guard) قبل أي بناء/SCP/SSH → لا نشر من `feature/*` ولا من PR
  ولا يدويًا، فقط بعد Merge فعلي إلى `main`.
- `pr-checks.yml` جديد: بناء صور + `compileall` على `pull_request` فقط. لا SSH/SCP/نشر.
- `promote-meraaj-live.yml`: يدوي فقط بتأكيد `PROMOTE`. عزل Test/Live لم يُمس.

### يونيو 2026 — جولة مراجعة العميل ١
- **رحّال**: السبب الجذري = توقّف خادم رحّال (404 على كل `/api`). بعد عودته: 419 مُسلَّم من 421،
  والفحص يرجّع 200 «التوقيع مقبول». المتبقّي حدثان بسبب تجاري `unknown_package_ref`.
  أُضيف: عرض عقد التكامل، فحص الوجهة (Probe)، تعديل عنوان الـWebhook بسبب إلزامي + Audit،
  السبب الدقيق لكل حدث (الجسم الموقّع + سجل المحاولات + curl)، توزيع الأحداث حسب الوجهة،
  و`retry-all` متزامن ومحدود (بدل مهلة 502).
- **إصلاح عيب حقيقي**: صلاحيات الموظف كانت تُقرأ بمعرّف المكتب → صفر صلاحيات. الآن بمعرّف الموظف.
- **إصلاح عيب حقيقي**: إبطال التوكن كان بمقارنة زمنية بالثانية. الآن `jti` لكل توكن وإبطال
  الجلسة بعينها، و`logout` يُبطل التوكن على الخادم.
- **الإشعارات**: 11 قالبًا افتراضيًا قابلًا للتحرير (زرع idempotent)، قواعد المستلمين،
  متغيّرات `{{...}}`، وتوصيل الإشعارات الناقصة (إنشاء طلب، طلب إلغاء، إلغاء، مراحل السحب).
- **التسوية**: معاينة Dry-run حساب-بحساب مع قبل/بعد وحماية تكرار. لم يُنفَّذ أي قيد.
- **النسخ الاحتياطي**: اختبار استعادة حقيقي على قاعدة مؤقتة ثم حذفها (قاعدة العمل لا تُمَس).
- **بيانات QA**: تقرير تصنيف للقراءة فقط. لم يُحذف أي سجل.
- حدود الملفات في الواجهة صُحّحت: 10MB للملف و20MB للدفعة (مطابقة للخادم).
- شاشة الصلاحيات: فلاتر وملخص وسبب واضح لكل حساب بلا صلاحيات.

### يونيو 2026 — جولة مراجعة العميل ٢ (البنود المعتمدة فقط)
- **توحيد قسمَي المكاتب**: كل وظائف `/admin/offices` نُقلت إلى `/admin/orgs`
  (الأرصدة، التفعيل/الإيقاف، إعادة مزامنة الأسعار، واتساب، الائتمان والتعرّض).
  `/admin/offices` بقي مسارًا متوافقًا خلفيًا يعيد التوجيه، ولم يُحذف الملف.
- **معالجة أحداث رحّال غير المحلولة**: تصنيف `diagnosis` لكل حدث (سبب + مرجع مطلوب +
  إجراء تالٍ + مسؤول)، وتعطيل زر إعادة المعالجة عندما لا تُفيد. لم يُعَد إرسال أي حدث.
- **استكمال النسخ الاحتياطي الآمن**: عرض الجدولة ومصدرها، تفاصيل التشفير، سياسة الاحتفاظ
  وعدد المحذوف تلقائيًا، آخر نسخة ناجحة، وحواجز الاستعادة الأربعة.

### يونيو 2026 — جولة مراجعة العميل ٣ (أدوات التحكم الإدارية)
- **المؤسسات**: إنشاء مؤسسة/مكتب، تعديل بياناتها، تفعيل/إيقاف بتأكيد، تعديل الفروع،
  تعديل الموظفين وأدوارهم، وعرض الائتمان والتعرّض داخل الملف.
- **المستخدمون والصلاحيات**: إنشاء مستخدم/موظف، تعديل البيانات، صلاحيات فردية فوق الأدوار،
  تصفير كلمة المرور مع إبطال كل الجلسات (بنفس سياسة المصادقة القائمة).
- **البرامج**: إنشاء برنامج إداري بالنيابة عن مكتب بائع (`source: "admin"`).
- **الائتمان**: زر منح سقف لمكتب جديد عبر نفس الـAPI القائم.
- **قسم نسخ احتياطي مستقل** `/admin/backups` ونُقلت الواجهة من `/admin/system`.
- **قسم صيانة جديد** `/admin/maintenance`: 7 أنواع تشغيلية قابلة للتنظيف، 16 مجموعة محميّة،
  مدد احتفاظ 30/90/180/365، معاينة إلزامية، Dry-run افتراضي، عبارة تأكيد، أرشفة مع بقاء
  الأصل، وتنظيف مجدول اختياري عبر `/api/cron/cleanup`.

### يونيو 2026 — جولة مراجعة العميل ٤ (الوضوح المالي — عرض فقط)
- `booking_financials()` في `finance.py`: بيان مالي مشتقّ من الحركات المسجّلة (المدفوع،
  المعلّق، المحرر، المسترد، المستحق على المشتري، المستحق للبائع، عمولة المنصة، صافي المنصة،
  المحوّل، المتبقي) + العملة والحالة وسجل الحركات الكامل. **بلا أي إعادة حساب.**
- Endpoint جديد للقراءة فقط: `GET /api/admin/bookings/{id}/financials`.
- يظهر في تفاصيل الطلب وفي الدفتر المالي عبر زر «البيان المالي».

### يونيو 2026 — جولة مراجعة العميل ٥ (تخزين النسخ الاحتياطية واستعادتها)
- وجهة إلزامية عند إنشاء النسخة تُعرض قبل التأكيد وتُسجَّل: تنزيل لجهاز المستخدم (أي جهاز
  ومجلد وقرص عبر نافذة المتصفح) • سيرفر التطبيق • تخزين سحابي مُهيَّأ • السيرفر + تنزيل.
- أدوات مكتملة: إنشاء، تنزيل/تصدير، استيراد مشفّر بالتحقق قبل القبول، فحص التشفير والسلامة
  (SHA-256 + توقيع gzip)، اختبار استعادة معزول، واستعادة قاعدة العمل بأربعة حواجز.
- الجدول يعرض الحجم والتاريخ والمصدر والوجهة والتشفير ونتيجة السلامة والنتيجة والمنفّذ
  والسبب، ورسائل نجاح مميّزة لكل نوع عملية، وكل عملية في `audit_log`.
- التخزين السحابي معطّل حتى تُضبط مفاتيحه (لم يُبدأ Release B).

## Backlog
### P0 — بانتظار قرار المستخدم
- حذف ملف/مسار `/admin/offices` نهائيًا بعد تأكيد انتقال كل الوظائف.
- تنفيذ قيود التسوية الـ216 (`ALLOW_RECONCILIATION=false` حاليًا).
- تنظيف بيانات QA على Test (الأدوات جاهزة الآن في `/admin/maintenance` بوضع Dry-run).
- إعادة إرسال الـ25 حدثًا التي سُلِّمت للمستقبل الداخلي إلى رحّال.
- الدفع/الدمج/النشر.

### P1 — يحتاج جهة خارجية أو أجهزة
- PoC الماسح على Windows (14 بند في `scanner-bridge/WINDOWS_POC.md`) — الميزة معطّلة.
- تطبيق حارس النشر على مستودع «رحّال» (مستودع مستقل).
- مرجع باكج حقيقي من رحّال للحدثين المتبقيين.
- Release B: تخزين S3 والمرفقات (يحتاج مفاتيح).

### P2
- قنوات الإشعارات الخارجية (بريد/WhatsApp) — معطّلة حتى الاعتماد.
- Capacitor Android المرحلة 2+.
- تحديث مجموعات الاختبار القديمة لشكل المحفظة المزدوجة، وإصلاح اعتماد fixtures للتشغيل المتوازي.

## ملفات ومراجع
- Backend: `admin_ops.py` (تكامل/تدقيق/فحص الوجهة)، `orgs.py` (المؤسسات والإشعارات والقوالب)،
  `rbac.py`، `enterprise.py` (نسخ/استعادة/تقارير/تصنيف بيانات QA)، `finance.py` (التسوية)،
  `credit.py`، `integration.py`، `security.py`، `market.py`، `pdfgen.py`، `cron.py`.
- Frontend: `pages/admin/AdminOrgs.js` (القسم الموحّد)، `AdminIntegrations.js`، `AdminSystem.js`,
  `AdminLedger.js`، `AdminRoles.js`، `AdminNotifications.js`، `components/TravelerDocs.js`.
- وثائق: `memory/REVIEW_ROUND1_FINDINGS.md`، `scanner-bridge/WINDOWS_POC.md`،
  `memory/test_credentials.md`.
- مجموعات: `rahal_outbox`, `rahal_sim_inbox`, `settings`, `notification_templates`,
  `notification_log`, `notifications`, `sessions`, `user_roles`, `office_staff`,
  `office_branches`, `offices`, `backups`, `backup_drills`, `audit_log`, `admin_tasks`.

## تحديث 2026-06 (إصلاحات ما بعد Iteration 14 — بدون أي نشر)
- تأكيد إصلاح `POST /api/admin/backups/upload`: يُحفظ الملف المؤقت بامتداده الأصلي فأصبح `_inspect`
  يفكّ تشفير `.archive.gz.enc` بنجاح — اختبار `test_valid_backup_accepted` ناجح.
- `GET /api/admin/bookings/{id}/financials`: إضافة حارس للمراجع غير ObjectId (سجلات رحّال/قديمة)
  بدل 404 مضلّل — `finance.py::_party`.
- إزالة تحذيرات DOM/Hydration داخل `<option>` في `AdminBackups.js` و`AdminMaintenance.js`
  (تسميات مُجمّعة كنص واحد) — سجل الكونسول نظيف.
- تحسين عرض أعمدة `AdminCommissions` (whitespace-nowrap للحالة والنوع).
- فلترة تواريخ التقارير: تم التحقق سابقاً أنها شاملة للحدّين (لا تغيير مطلوب).

## تحديث 2026-06 (تصحيحات المراجعة اليدوية النهائية — لا نشر ولا اختبارات)
- مطابقة البيان المالي مع الدفتر: أُضيف `booking_reconciliation()` في `finance.py` (قراءة فقط)
  يوضّح: صافي المشتري (خرج − رجع)، المُحرَّر للبائع، الإيراد المعلّق (داخل/مُحرَّر/أُلغي/قائم)،
  عمولة المنصة مع وسم صريح «مشتقّة من الفرق» أو «حركة مسجَّلة»، ومجموع أسطر الدفتر المباشر مع
  توضيح أنه ليس رصيداً لأنه يجمع محفظة المشتري مع قيود الإيراد المعلّق للبائع.
  يُعاد الحقل الجديد `reconciliation` من `/admin/bookings/{id}/financials` و`/admin/bookings/{id}/full`
  ويُعرض في تفاصيل الطلب والدفتر (`fin-reconciliation`, `stmt-reconciliation`).
- لم تُمسّ الأرصدة ولا المعادلات ولا دورة الطلب ولا التسوية — عرض ومطابقة فقط.
- استيراد النسخ الاحتياطية: ملخّص نجاح صريح (الاسم، الحجم، التشفير، SHA-256، نتيجة التحقق، التخزين).
- تنبيه: تحذيرات المخاطر في لوحة المؤشرات مزال تكرارها مسبقاً عبر `add_alert` في `admin_analytics.py`.

## تحديث 2026-06 (استكمال الفراغات بعد المراجعة اليدوية — لا اختبارات ولا نشر)
- التقارير: أُضيفت فترات جاهزة (يومي/أسبوعي/شهري/سنوي/مخصص) في `AdminReports.js` تُعبّئ فلتري
  التاريخ الشاملين، وأي تعديل يدوي للتاريخ يحوّل الفترة تلقائياً إلى «مخصص».
- تقرير مالي جديد `order_financials` في `enterprise.py`: مدين/دائن/المدفوع/المعلّق/المحرَّر/المسترد/
  المستحق على المشتري/المستحق للبائع/عمولة المنصة/صافي المنصة/المحوَّل/المتبقي لكل طلب،
  مشتق قراءةً فقط من `booking_financials` (لا تعديل على أي معادلة أو رصيد) — إجمالي التقارير 14.
- بقية الأقسام (المؤسسات، المستخدمون والصلاحيات، البرامج والمقاعد، السقوف الائتمانية، الإشعارات
  والمهام، النسخ الاحتياطي والصيانة) تحتوي أدوات تحكّم فعلية سابقاً — لم تُلمس ولم تُكرَّر.

## تحديث 2026-06 (إجماليات تقرير التفصيل المالي للطلبات)
- أُضيف صف إجماليات في أسفل تقرير `order_financials` **منفصل لكل عملة (SAR / USD)** يجمع:
  مدين، دائن، المدفوع، المعلّق، المحرَّر، المسترد، المستحق على المشتري، المستحق للبائع،
  عمولة المنصة، صافي المنصة، المحوَّل، المتبقي + عدد الطلبات — مشتق من نفس أرقام
  `booking_financials` (قراءة فقط)، ويظهر في الجدول وفي تصدير Excel وPDF.
- الواجهة تميّز صف الإجمالي بلون ووزن خط (`report-total-SAR` / `report-total-USD`).

## جلسة الإصلاح النهائية (2026-06) — FIX + COMPLETE + الإعلانات
- الدفتر: إصلاح جذري لمسبب "0 حركة" (بحث الحساب كان يرمي 404 على معرّفات غير ObjectId)،
  + فلاتر المكتب/المستخدم ومرجع الطلب، + إظهار رسالة الخطأ بدل جدول فارغ صامت.
- توحيد المصدر المالي: عمولة المنصة تُعتمد من snapshot الطلب (platform_fee) مع إظهار
  "فرق غير مفسَّر" و`commission_source` — لا حساب مزدوج في الواجهة.
- تتبّع التسوية مع رحّال: `GET /api/admin/integrations/settlement-trace/{booking_id}`.
- تصنيف أحداث رحّال غير المُسلَّمة: `GET /api/admin/integrations/outbox/classify` (بدون إعادة إرسال).
- حجب البيانات الحساسة: التوقيع/الجسم الموقّع/أمر curl لم تُعَد تُعرض؛ العرض التقني للإدارة العليا فقط.
- طبقة تصدير موحّدة `backend/reporting.py`: الشاشة وPDF وExcel وCSV من نفس Dataset.
- PDF رسمي (ترويسة معراج/تارجت ميديا، رقم تقرير، ملخص مالي، ترقيم صفحات، Watermark في Test).
- Excel حقيقي (xlsxwriter): ملخص + تفاصيل + قاموس بيانات، RTL، تثبيت رأس، فلاتر تلقائية.
- البيئة: `_environment()` من ENVIRONMENT فقط + قواعد صريحة لكل بيئة + فحص توفر mongodump.
- الإعدادات: نماذج حقيقية بدل JSON خام (`GET /api/admin/settings/schema`) وأسماء عربية للوحدات.
- سجل التدقيق: عرض بشري + نافذة "التفاصيل التقنية".
- تمرير عجلة الفأرة: إزالة overflow/overscroll التي كانت تمنع التمرير من وسط الصفحة.
- الإعلانات والعروض (وحدة جديدة): `backend/ads.py` + `/admin/ads` + عرض عام في الرئيسية
  وسوق البرامج وتفاصيل البرنامج، مع Maker–Checker وجدولة ومواضع وقياس أداء.

## إصلاحات المعاينة (2026-06) — الإعلانات والتقارير فقط
- زر حفظ الإعلان: مُفعَّل دائماً + قائمة «الحقول الناقصة» ظاهرة داخل النموذج ورسالة toast عند المحاولة.
- رفع صورة/بانر من الجهاز: `POST /api/admin/ads/upload-image` (GridFS `ad_images`, حتى 5MB،
  PNG/JPEG/WEBP/GIF) + `GET /api/ads/image/{id}`؛ الرابط الخارجي بقي خياراً إضافياً.
- معاينة آمنة داخل الإدارة عبر `AdPreview` بالقوالب الثلاثة ولا تُحتسب مشاهدة.
- احتساب المشاهدات/النقرات: `source=public` فقط؛ أي فتح من الإدارة يعيد `counted:false`.
- ثلاثة قوالب متجاوبة RTL: بانر الرئيسية (BannerRow)، بطاقة سوق البرامج (CardRow)،
  شريط مضغوط لتفاصيل البرنامج (CompactRow) — مع وسم «إعلان/عرض ترويجي» واسم المعلن
  وCTA وتاريخ الانتهاء وصورة متجاوبة.
- Frequency Cap: 3 ظهور/يوم لكل إعلان لكل موضع لكل زائر (localStorage، بلا كتابة DB).
- الإعلان المنتهي/الموقوف/غير المعتمد لا يظهر (فلتر الخادم + تحقق فعلي).
- التقارير: توحيد تسميات أنواع الحركات والحالات، «طلب قديم (تم قبل تفعيل الموافقات)»،
  وتقرير التدقيق يعرض تسميات بشرية بدل JSON خام (خرائط ENTITY_AR/ACTION_AR مشتركة
  بين الشاشة والتقرير). لم تُمسّ أي أرقام أو Source of Truth.

## جولة إصلاحات (بيئة التطوير فقط — لا Deploy/Merge/Push)
- الدفتر «كل العملات»: إزالة شرط `currency in CCY` من الفلتر، وتجميع الإجماليات يشمل الآن
  عملات أخرى/مفقودة تحت `other_currencies` بدل تجاهلها، وتسمية نوع الحركة لها بديل آمن.
- سلامة البيئة: الاستعادة محجوبة على live **وعلى unknown**، واختبار الاستعادة المعزول يتحقق
  من وجود mongorestore ويُرجع 503 عربية واضحة.
- تصنيف أحداث رحّال: 404 صريح، 409 (تعارض/اختلاف سعر/اختلاف تسوية)، وHMAC — بلا إعادة إرسال.
- Responsive: فلاتر الدفتر شبكة على الهاتف، الجداول `.table-scroll` مع تلميح سحب أفقي،
  وكل الحوارات `max-h-[85vh] overflow-y-auto`.
- الإعلانات: 12 موضعاً من config + 4 مجموعات جاهزة، استهداف (الجميع/مكاتب/أفراد/محدد)،
  واستبعاد صاحب الإعلان (الحساب + المؤسسة + مستخدميها) على مستوى الخادم في `/api/ads/public`.

## تصحيح: تكافؤ المواضع مع الشرائح الفعلية (Selectable = Implemented)
- المواضع القابلة للاختيار صارت 9، لكل واحد `<AdSlot/>` فعلي في صفحة مستخدم/زائر.
- أُزيلت من القائمة القابلة للاختيار: `orders` و`order_details` و`notifications`
  لعدم وجود صفحة مستخدم فعلية لها حالياً (تفاصيل الطلب ومركز الإشعارات إداريان فقط).
- توصيل جديد: `create_package` في CreatePackage.js و`login` في Login.js (قالب compact غير مزعج).

## طبقة تجارة الإعلانات (Ads Billing) — مكتملة 2026-06
- `backend/ads_billing.py`: باقات إعلانية (CRUD إداري) + حجز/تحصيل/فك حجز من المحفظة (HOLD → CAPTURE → RELEASE) مع تسجيل حركة لكل خطوة.
- `backend/ads.py`: `_apply_status` يوحّد دورة الحالة للمكتب والإدارة، ويشترط باقة سارية + مؤسسة موثّقة (سجل تجاري) للإعلان التجاري، ويمنع الرصيد السلبي.
  - إصلاح: إعادة الإرسال بعد الإلغاء/الرفض تُعيد الحجز فعلياً (كان يتخطّى الحجز لأن `held` ما زال محفوظاً).
- `frontend/src/pages/MyAds.js`: نافذة اختيار الباقة بدل window.prompt (سعر/مدة/حدود، وتعطيل الباقات التي لا يكفيها الرصيد) + عرض المحجوز والمتبقي وحركات الرصيد.
- `frontend/src/pages/admin/AdminAdPackages.js` + تبويب "الباقات الإعلانية" في `AdminAds.js`: إنشاء/تعديل/تفعيل/تعطيل الباقات مع سبب إلزامي في التدقيق.
- تم التحقق بـ curl/python فقط (لا اختبارات آلية، لا سكرين شوت): حجز 25 ريال → فك كامل عند الإلغاء → إعادة حجز → خصم نهائي عند الاعتماد → استرجاع كامل عند الرفض → رفض الإرسال عند عدم كفاية الرصيد (400 دون أي تحرك للرصيد) → المعلن لا يرى إعلانه بينما يظهر للعام.

### المتبقي (Backlog)
- P2: Release B — التخزين والمرفقات (S3) — مؤجّل بطلب المستخدم.
- P2: تنفيذ Scanner Bridge على Windows — مؤجّل.

## دورة الاعتماد والإلغاء للإعلانات المدفوعة — 2026-06 (بعد تثبيت طبقة الفواتير)
- إصلاح أمان مالي في `backend/ads.py::set_status`: كانت حراسات الحالة و Maker/Checker تُنفَّذ **بعد** حركة المال، فمحاولة اعتماد غير مصرّحة قد تخصم الرصيد ثم ترجع خطأ دون حفظ الحالة (خطر خصم مزدوج). الآن الحراسات قبل أي حركة مالية.
- منع تغيير الحالة إلى cancellation_requested/cancelled من مسار الحالة العام (يُدار من مسار طلبات الإلغاء فقط).
- حالتان جديدتان: `cancellation_requested`, `cancelled`.
- مسار طلب الإلغاء: `POST /api/ads/mine/{id}/cancellation-request` (سبب إلزامي، بلا حذف وبلا حركة مالية) → `GET /api/admin/ads-cancellations` → `POST /api/admin/ads/{id}/cancellation` (accept/reject بسبب إلزامي).
  - قبول الإلغاء: المبلغ المحجوز يُفكّ عبر منطق المحفظة القياسي؛ المبلغ المخصوم نهائياً **لا يُسترجع تلقائياً** (سياسة الاسترجاع تحتاج قراراً تجارياً).
- إشعارات مرتبطة بالإعلان نفسه عبر `orgs.notify`: ad_submitted, ad_approved, ad_rejected, ad_cancellation_requested, ad_cancellation_approved, ad_cancellation_rejected (تحتوي الباقة والمدة والتواريخ والمبلغ والعملة وحالة الخصم).
- تدقيق: ad_pending_approval, ad_active, ad_rejected, ad_cancellation_requested/approved/rejected + حركات المحفظة ad_hold/ad_charge/ad_hold_release.
- تحقق محدود بـ curl/python: حجز→اعتماد→خصم واحد فقط (تكرار الاعتماد 400 بلا خصم ثانٍ)، منع الاعتماد الذاتي، منع الإرسال عند عدم كفاية الرصيد بلا أي حركة، الرفض يفكّ الحجز، رفض/قبول طلب الإلغاء، وقبول إلغاء إعلان محجوز يُعيد المبلغ كاملاً.
- سياسة الاسترجاع للإعلان المنشور (Full/Partial/No refund) **معلّقة بانتظار قراركم** — لم يُنفَّذ أي استرجاع تلقائي.

## سياسة الإلغاء والاسترجاع المعتمدة (قرار العميل — 2026-06)
1. قبل الخصم النهائي (المبلغ Held): اعتماد الإلغاء ⇒ فكّ حجز كامل إلى Available، بلا Refund، مع `ad_hold_release` في السجل المالي و Audit.
2. بعد الخصم النهائي (`ad_charge`): **No Automatic Refund** — الإعلان يصبح `cancelled` ويتوقف ظهوره فقط، ومسار الإلغاء ممنوع من تعديل الرصيد أو إنشاء Refund (`refund_policy=no_automatic_refund_after_final_charge` محفوظ داخل `cancellation`).
3. الاسترجاع الاستثنائي: مسار إداري مستقل (لم يُبنَ بعد) وليس عبر تغيير حالة الإعلان. متطلباته عند البناء: مبلغ محدد + سبب إلزامي + ربط بمعرّف الإعلان + Maker/Checker + سقف = المبلغ المخصوم فعلاً + منع التكرار/Double Refund + Ledger/Audit مع before/after + استخدام منطق المحفظة القياسي فقط.
4. بيانات Preview فقط: `commercial_license` لحسابي seller/buyer — بلا Migration/Seed/Backfill. مبلغ الاختبار 35 ريال على buyer@test.com يبقى مسجّلاً محاسبياً بلا أي تعديل يدوي.
5. حُذفت سكربتات التحقق الديف-أونلي: `tests/_ad_cycle_check.py`, `tests/_ad_billing_check.py`.

## Accounting Module — PHASE 1 (Chart of Accounts Foundation) — 2026-09-12
منهجية معتمدة: EXTRACT → PORT → ADAPT → HARDEN → PACKAGE من Rahaal كـReference Implementation (وليس إعادة بناء).

### ما نُفِّذ (Backend فقط)
- حزمة مستقلة `/app/backend/accounting/` بثلاث طبقات: `core/` (نقي، صفر استيراد من معراج) + `templates/` (بيانات) + `adapters/` (يعرف معراج) + `api.py`.
- Account Model كامل: id(uuid)، entity_id، code، name/name_ar، type، parent(code)، level، is_group/is_parent، origin(system|standard|custom)، role، is_active، next_child_seq، notes، created_at/by، updated_at/by.
- توليد أكواد ذرّي منقول من `generateSubAccountCode` (‏$inc على next_child_seq + collision-skip + سقوف 9/99/999 + معاينة غير مدمّرة).
- القالب: `STANDARD_COA` (منقول من COA_TEMPLATE v2 بلا حسابات السفر) + `MERAAJ_COA` (يضيف 2102 التزامات محافظ، 4106 إيرادات إعلانات، 4107 عمولات المنصة، 5102 مردودات) = 29 حساباً، coa_version=2.
- `seed_template` (منقول من seedCoaTemplate + stampVersion، idempotent، والوسم بعد التحقق فقط)، `audit_chart` (منقول من auditTenant — الجزء البنيوي)، `validate_chart` (منقول من validateTenant — الجزء البنيوي).
- حراسات منقولة من route.js: parent موجود/ليس L4/يجب أن يكون Group/نوع مطابق للأب، كود يدوي أرقام+بادئة+طول+فريد، منع تعديل الكود، منع حذف حساب له أبناء أو مستخدم في قيود (عبر usage hook).
- HARDEN: حماية كل حسابات القالب (STANDARD) لا 3103 فقط؛ منع تغيير type/parent/is_group للحسابات المحمية أو التي لها أبناء/قيود؛ توحيد `is_active` (بدل inactive/is_active المتعارضين)؛ تفعيل/تعطيل جديد (NEW CORE REQUIREMENT).
- Collections جديدة: `accounting_accounts`, `accounting_entity_settings`. فهارس: uniq(entity_id,code)، uniq(entity_id,id)، (entity_id,parent,code)، uniq(entity_id) للإعدادات بنمط Rahaal الآمن.
- صلاحيتان جديدتان في rbac: `accounting.accounts.view` / `accounting.accounts.manage` (accountant + finance_manager: view+manage، auditor: view).
- مسارات `/api/accounting/*` (meta, accounts CRUD, tree, next-code, chart/seed|audit|validate).

### لم يُنفَّذ عمداً (مراحل لاحقة)
Journal، Posting، Ledger، Reversal، Opening Balances، Closing، Reports، Currency Engine، Account Linking، وأي ربط بـWallet/Ads/Commissions/Withdrawals، وأي Frontend.

### قرارات مفتوحة تنتظر العميل
1. الكيان المحاسبي: دفتر واحد للمنصة أم دفتر لكل مكتب (حالياً entity واحد `meraaj-platform` قابل للتغيير).
2. العملة الأساس للمحاسبة في معراج.

## Accounting Module — PHASE 2 (COA Management + Guards + Lifecycle) — 2026-09-12
Backend فقط. بلا اختبارات، بلا بيانات تجريبية، بلا Migration/Backfill، بلا ربط أعمال، بلا Frontend، بلا Git/Deploy.

### جديد في Phase 2
- `core/usage.py`: **Boundary** لحماية الحساب المستخدم في قيود (`UsageProbe` + `NullUsageProbe` بـ`available=False`) — لا ادّعاء بفحص دفتر غير موجود؛ المرحلة القادمة تُحقن Probe حقيقياً بلا إعادة كتابة أي حارس.
- `core/audit.py`: `ChartAuditor` (audit/validate/classification) — توسيع التدقيق البنيوي: children under terminal L4، children under leaf، invalid origin/type، role integrity (تكرار/دور على حساب custom/عدم تطابق النوع أو Group)، active child under inactive parent، inactive template accounts، sequence anomalies، invalid code length، فصل `customExtras` عن `unexpectedExtras`.
- تصنيفات الشجرة السبع: empty | inconsistent | manual_review | older_version | structurally_matching | custom_extended | already_current — بلا أي Upgrade Migration.
- `models.py`: `extra="forbid"` على Create/Update + `IMMUTABLE_FIELDS` (id, entity_id, code, origin, level, role, next_child_seq, created_*) و`is_active` خارج مسار التعديل (له مسار مستقل).
- `codegen.py`: `sync_parent_sequence_after_manual_code` (يرفع العدّاد فقط عند تجاوز كود يدوي له، ولا يُنزله ولا يُعيد استخدام رقم).
- `chart.py`: بوابة أب واحدة `_assert_usable_parent` (موجود/نفس الجهة/Group/نشط/نوع مطابق/ليس L4) تُستدعى في الإنشاء وإعادة الأب وتغيير النوع والتنشيط؛ منع تحويل Group خصّص أرقاماً إلى Leaf؛ منع حذف حساب مرتبط بدور؛ `find_by_code` و`find_by_role` (بديل أرقام Rahaal الحرفية).
- `api.py`: مسارَا Lookup جديدان (`/accounts/by-code/{code}`, `/accounts/by-role/{role}`) + `install_error_handler` (تحويل واحد لـAccountingError إلى HTTP خارج الـCore).
- Code review خارجي: أُصلحت ثغرة MEDIUM (تغيير type وحده كان يتجاوز تطابق نوع الأب) + دور غير نشط + int(seq) غير رقمي + تسريب طبقة store.

### حالة البيانات
`accounting_accounts` و`accounting_entity_settings` **فارغتان (0 مستند)**. لم تُهيَّأ جهة `meraaj-platform` بناءً على قرار العميل.

### مؤجَّل للمراحل القادمة (مؤكد)
Journal، Posting، Reversal، Ledger، Opening Balances، Closing، Reports، Multi-Currency، Account Linking، Used-Account Guard الفعلي، وأي ربط بـWallet/Ads/Commissions/Withdrawals.

## Accounting Module — PHASE 3 (Journal Model + Central Journal Validation) — 2026-09-12
Backend فقط. لا Posting، لا تخزين، لا Ledger، لا Reversal، لا تقارير، لا إقفال، لا FX Engine، لا Account Linking، لا ربط أعمال، لا اختبارات، لا بيانات، لا Migration، لا Git/Deploy.

### ملفات جديدة (6) في core/
- `money.py`: التمثيل المالي — `Decimal` فقط (لا float)، scale=2، ROUND_HALF_UP على الحدود، رفض NaN/Infinity/دقة زائدة/قيمة تتجاوز MAX_AMOUNT، **BALANCE_TOLERANCE = 0** (عدم نقل tolerance 0.01 من Rahaal)، والقرار للـDB مستقبلاً: Decimal128.
- `currency.py`: `CurrencyPolicy` — العملات المسموحة تُحقن من الـadapter (لا SAR/USD/YER داخل الـCore)، وقيود متعددة العملات **مرفوضة صريحاً** (`MULTI_CURRENCY_UNSUPPORTED`) لا مقبولة بالخطأ.
- `periods.py`: `PeriodGuard` Protocol + `NullPeriodGuard` (Boundary للإقفال، غير مُفعّل) — الفحص في نقطة مركزية واحدة بدل تكراره في المسارات كما في Rahaal.
- `journal.py`: `JournalStatus` (draft/posted/reversed) + `ALLOWED_TRANSITIONS` + `IMMUTABLE_STATUSES` + `JournalLineInput` + `JournalEntryDraft` (source_type/source_id عام) + `JOURNAL_DOCUMENT_CONTRACT` (عقد الوثيقة بلا إنشاء Collection).
- `posting_accounts.py`: `PostingAccountResolver` — تحميل مجمّع للحسابات باستعلام واحد معزول بالجهة + `assert_postable` (غير نشط / مجموعة / جذري / بنية level غير سليمة) + كشف Cross-entity.
- `journal_validator.py`: **`JournalValidator`** — البوابة المركزية الوحيدة: entity، سطور ≥2، بيان، تاريخ غير مستقبلي، مدين/دائن بجهة واحدة فقط وبدون سالب/صفر/دقة خاطئة، الحساب موجود+نفس الجهة+نشط+Leaf، عملة مسموحة وعملة واحدة، **التوازن مضبوط بدقة تامة**، ثم بوابة الفترة. `assert_valid()` هي ما سيُبنى عليه Posting لاحقاً.

### معدَّل
`core/__init__.py` (تصدير)، `core/usage.py` (توثيق اتجاه التبعية أحادي الاتجاه: COA → UsageProbe ← Journal storage، وأن DRAFT لا يجعل الحساب مستخدماً)، `adapters/meraaj_adapter.py` (تركيب الـvalidator + العملات من env)، `api.py` (meta + مسار Dry-run واحد `POST /api/accounting/journal/validate` بلا تخزين).

### Collections / Indexes / بيانات
**صفر تغيير**: لم تُنشأ `accounting_journal_entries`، ولا فهارس جديدة، ولا `source_key` (مؤجّل مع فهرسه الفريد). `accounting_accounts=0` و`accounting_entity_settings=0`.

### قرارات موثّقة
- `entry_no` لا يُخصَّص للـDraft إطلاقاً — يُصدر ذرياً ومعزولاً بالجهة وقت Posting فقط (لا `count()+1`).
- العملة الأساس غير محسومة (`ACCOUNTING_BASE_CURRENCY` غير مضبوط) ولا شيء يعتمد عليها ما دامت القيود أحادية العملة.

## Accounting Module — PHASE 4 (Journal Posting + Idempotency + Entry Number) — 2026-09-12
أول مرحلة تُنشئ حقيقة محاسبية مخزّنة. Backend فقط. لا GL، لا Reversal، لا تقارير، لا إقفال، لا FX، لا Account Linking، لا ربط أعمال، لا اختبارات، لا بيانات، لا Migration، لا Git/Deploy.

### ملفات جديدة (3)
- `core/journal_store.py`: Collection `accounting_journal_entries` (POSTED فقط، لا Drafts) + تحويل Decimal↔Decimal128 في مكان واحد + `allocate_entry_no` ذرّي ($inc + upsert على entity_settings) + معالجة DuplicateKeyError عبر `keyPattern` + 4 فهارس.
- `core/journal_posting.py`: **`JournalPostingService`** = البوابة الوحيدة للكتابة: assert_valid → سياسة source_key → بصمة مالية → تخصيص رقم ذرّي → إدخال واحد → معالجة التزامن. + `financial_fingerprint` + `format_entry_no` (`JE-000001`).
- `core/journal_usage.py`: `JournalUsageProbe` الحقيقي (يفعّل حراسات Phase 2 للحماية التاريخية بلا تعديل أي حارس).

### معدَّل
`core/__init__.py` (تصدير)، `adapters/meraaj_adapter.py` (تركيب الـstore والـprobe والـservice + فهارس القيود)، `api.py` (meta + 4 مسارات: post/entries/entries/{id}/by-source-key). **server.py ووحدات الأعمال: صفر تغيير.**

### Collection + Indexes
`accounting_journal_entries`: `uniq_entity_journal_id`, `uniq_entity_entry_no`, **`uniq_entity_source_key` (unique + partialFilterExpression: source_key هو string)**, `entity_line_account` (يستخدمه الـUsageProbe فعلاً).

### قرارات
- source_key: **إلزامي لكل source_type غير `manual`**، اختياري للـmanual؛ الحماية على مستوى الـDB لا التطبيق.
- Retry بنفس المفتاح ومحتوى مالي مطابق → `idempotent_replay: true` بلا قيد جديد؛ ومحتوى مختلف → `IDEMPOTENCY_CONFLICT` (لا نجاح صامت).
- البصمة تشمل: entity, currency, source_type/id, سطور مرتّبة (كود/مدين/دائن/عملة). وتستثني: التاريخ، البيان، الـactor، الأرقام المولّدة.
- رقم القيد: entity-scoped **مستمر** (لا سنوي — السنة المالية قرار مرحلة الإقفال)، ذرّي، والفجوات نادرة ومقبولة: **التفرّد أهم من انعدام الفجوات**، ولا يُعاد استخدام رقم.
- السطر يخزّن `account_code` فقط (ثابت بالتصميم) — لا account_id ولا أسماء أطراف ولا Snapshot للاسم.
- لا أرصدة مخزّنة إطلاقاً (لا `updateBalance` من Rahaal) — الحقيقة هي القيود المرحّلة، والأستاذ يُشتق لاحقاً.
- `PeriodGuard` ما زال **غير مُفعّل** (`period_guard_not_enforced` في الرد) حتى مرحلة الإقفال.
- البيانات: الثلاث Collections **فارغة (0)**، ولم تُهيَّأ `meraaj-platform`.

## Accounting Module — PHASES 5-6-7 (GL + Reversal + Opening Balances) — 2026-09-12
- **Phase 5 GL**: `core/ledger.py` — `GeneralLedgerService` **read-only مشتق** من القيود المرحّلة، **بلا Collection أستاذ وبلا أرصدة مخزّنة**. Normal balance مركزي (asset/expense=debit، liability/equity/revenue=credit)، opening-for-range، running balance آمن مع الترقيم، إجماليات وclosing، منع جمع عملتين (`CURRENCY_REQUIRED`)، ترتيب حتمي date→entry_seq→line_no، Leaf فقط. قراءة أستاذ حساب معطّل مسموحة. فهرس جديد `ledger_account_date_seq`.
- **Phase 6 Reversal**: `core/journal_reversal.py` — قيد مرآة جديد (UUID/entry_no/seq جديدة)، الأصل **لا تتغير أي قيمة مالية فيه**، فقط Metadata العكس عبر **Atomic Claim** (`status:posted` + `reversed_by_entry:None` في الفلتر) + **فهرس فريد جزئي `uniq_entity_reversal_of`** = العكس المزدوج مستحيل. Idempotency بـ`source_key=reversal:{id}`. تعويض (release claim) إن فشل إدخال المرآة. **Reversal Validation Mode** ضيق: نفس حسابات الأصل حرفياً، و`ACCOUNT_INACTIVE` لا يمنع تصحيح التاريخ.
- **Phase 7 Opening**: `core/opening_balances.py` — الافتتاح **قيد مُرحَّل** عبر نفس بوابة الكتابة (لا حقل رصيد)، حساب الموازنة بالدور `OPENING_BALANCE_SUSPENSE` (لا الرقم 3103)، عملة واحدة لكل قيد، Assets/Liabilities/Equity فقط (Revenue/Expense مرفوضة وتحتاج سياسة سنة مالية)، منع Group/Inactive/حساب بدور/حساب التسوية/التكرار، `source_key` إلزامي، **افتتاح واحد لكل (entity, currency)** والمعكوس لا يُحتسب فيسمح بالتصحيح، وحراسة نشاط قائم (`LEDGER_HAS_ACTIVITY` + `allow_after_activity`)، وتاريخ إلزامي (لا now() صامت).
- مسارات جديدة: `GET /ledger/account/{code}` · `POST /journal/entries/{id}/reverse` · `POST /opening-balances`.
- **لا Migration/Backfill/بيانات**: الـCollections الثلاث فارغة (0)، ولم تُهيَّأ أي Entity.

## Accounting Module — PHASE 6 Hardening + PHASE 8 (Core Reports) — 2026-09-12
- **Phase 6 Hardening (تصليب الاستعادة)**: حالة وسيطة صريحة `reversal_claim` — الأصل يبقى `posted` أثناء العملية (لا تُستخدم حالة محاسبية نهائية كقفل مؤقت)، ثم `finalize_reversal` يحوّله إلى `reversed` **فقط بعد** وجود قيد المرآة. استعادة بعد الانقطاع: إن وُجد Claim معلّق و مرآة موجودة → يُستكمل الربط (`recovered:true`)؛ وإن لم توجد مرآة → Claim قابل للاسترجاع بعد `STALE_CLAIM_SECONDS=120` بلا أي تعديل يدوي على الـDB. تعويض `release_reversal_claim` عند فشل الإدخال.
- **توافق قراءة `reversed`**: `EFFECTIVE_STATUSES = (posted, reversed)` في `journal_store.py` مطبَّق على الأستاذ، الـUsageProbe، والتقارير — الأصل المعكوس لا يختفي من التاريخ، وزوج (أصل + مرآة) يتصافى إلى صفر طبيعياً.
- **Phase 8 Reports**: ملف جديد `core/reports.py` — `ReportingService` **قراءة فقط ومشتقّة بالكامل**:
  - ميزان المراجعة: الإجماليات من **حسابات الترحيل (Leaf) فقط** (لا تكرار عبر الآباء)، `balanced` بمقارنة **دقيقة بلا هامش**.
  - قائمة الدخل: إيرادات − مصروفات، `result_kind` (profit/loss/breakeven).
  - الميزانية العمومية: أصول = التزامات + حقوق ملكية + **نتيجة الفترة غير المقفلة** (سطر مشتق `current_period_result`، `closing_performed:false` — لا قيد إقفال؛ ذلك مرحلة 9)، مع `equation_holds`.
  - تجميع المجموعات عبر **سلسلة `parent` الحقيقية** لا بادئة الكود، وحماية من السلاسل الدائرية والترحيل على حساب غير موجود.
  - **فصل العملات إلزامي**: تقرير واحد = عملة واحدة، ولا تحويل ولا جمع (`CURRENCY_REQUIRED`).
  - تجميع دفعي واحد لكل تقرير: `sum_by_account` + `entity_currencies` في `journal_store.py` (لا استعلام لكل حساب).
- مسارات جديدة: `GET /api/accounting/reports/trial-balance` · `/reports/income-statement` · `/reports/balance-sheet`؛ و`/meta` صار `phase:8`.
- تحقق: منطق التقارير الثلاثة مُثبت بحساب يدوي (TB 350/350 متوازن، صافي 150 ربح، الميزانية 250 = 100 + 150، الفرق 0.00)، والمسارات تُرجع 401 بلا صلاحية (موصولة صحيحاً). **الـCollections الثلاث ما زالت فارغة (0 مستند)** ولا بيانات وهمية.
- ما زال غير مُنفَّذ: إقفال الفترة/السنة، محرّك العملات/FX، ربط الحسابات، تكامل الأعمال.

## Accounting Module — PHASE 9 (Period & Year Closing) + PHASE 10 (Multi-Currency & FX) — 2026-09-12

### Phase 9 — الفترات والإقفال
- `core/periods.py` (معدّل): `DatabasePeriodGuard` حقيقي بديلاً عن Boundary غير مفعّل. يُحقن في **المدقّق المركزي** ومحرّك العكس → يغطي الترحيل والعكس والافتتاح وقيود الإقفال بلا أي حارس على مستوى Route. قاعدة معلنة: تاريخ بلا فترة معرّفة **ليس مغلقاً**.
- `core/fiscal_year.py` (جديد): `FiscalYearPolicy(start_month, start_day, period_length=month|quarter)` — لا Jan–Dec ثابتة. تسمية السنة = السنة الميلادية **لتاريخ البداية**. يوم البداية محدود بـ1–28 لضمان وجوده في كل شهر. فترات متلاصقة بلا فراغات ولا تداخل.
- `core/period_store.py` (جديد): `accounting_periods` + حالة عمليات الإقفال `accounting_year_close_ops` + إعدادات `fiscal` داخل `accounting_entity_settings`.
- `core/period_service.py` (جديد): إنشاء فترات السنة، **Preflight إلزامي** قبل الإقفال (قيود مشوَّهة، قيود غير متوازنة، Claims عكس معلّقة، معكوس بلا مرآة، ميزان مراجعة **لكل عملة على حدة**، تحذير الفترات الأقدم المفتوحة)، `close` = **قفل تواريخ فقط** (لا rewrite، لا cache، لا `$inc`، لا delete)، `reopen` يتطلب سبب ومنفّذ **ولا يمحو تاريخ الإقفال** (سجل `history` تراكمي). الانتقالات ذرّية (الحالة المتوقعة داخل الفلتر).
- `core/year_state.py` + `core/year_close.py` (جديد): ثلاث مراحل منفصلة بهذا الترتيب: (1) **قيد إقفال حقيقي** عبر بوابة الكتابة الوحيدة `source_type=year_close` — الإيرادات/المصروفات محسوبة من القيود عبر **الأنواع والشجرة** ولا رقم حساب ثابت، والنتيجة تُرحَّل إلى **الأرباح المحتجزة بالدور `retained_earnings`** (ربح→دائن، خسارة→مدين)؛ (2) **تحقق بعد الإقفال** (الإيرادات صفر، المصروفات صفر، النتيجة المرحّلة = المحسوبة، توازن قيد الإقفال، توازن ميزان المراجعة) — وأي فشل = **لا إقفال نهائي ولا قفل فترات**؛ (3) قفل فترات السنة ثم الحالة النهائية. القيد يُرحَّل **قبل** قفل الفترات لأن PeriodGuard يمنع أي تاريخ داخل فترة مغلقة.
- **منع الإقفال المزدوج**: `source_key` حتمي `year_close:{entity}:{fy}:{currency}` + فهرس فريد `(entity, fiscal_year, currency)` على عمليات الإقفال → لا قيد إقفال ثانٍ ولا ترحيل نتيجة مزدوج؛ وإعادة المحاولة **تُكمل** العملية القائمة.
- **تعدد العملات في الإقفال**: كل عملة تُقفل باستقلال؛ نجاح SAR وفشل USD **لا يُعلن** كإقفال سنة (`fully_closed_currencies` فقط).
- **بلا ادّعاء Atomicity**: لا Transactions — بدلاً منها حالة عملية محفوظة + مفاتيح حتمية + Posting Idempotent + سير عمل قابل للاستكمال.
- **إعادة فتح سنة**: مصنّفة `DEFERRED — CONTROLLED YEAR REOPEN` (لا تنفيذ ناقص، ولا حذف قيود إقفال) — وإعادة فتح فترة داخل سنة مقفلة مرفوضة بنفس التصنيف.
- **توافق التقارير**: قائمة الدخل تستثني `year_close` افتراضياً (`exclude_closing=true`) فلا تصبح النتيجة التاريخية صفراً؛ الميزانية تقرأ الكتاب كاملاً فتصبح نتيجة الإيرادات/المصروفات صفراً بعد الإقفال وتظهر النتيجة داخل الأرباح المحتجزة → **بلا احتساب مزدوج**.

### Phase 10 — العملات ومحرّك الصرف
- `core/currency_settings.py` (جديد): تكوين عملات عام لكل Entity (`accounting_currency_settings`): `base_currency` **صريح** (OPEN-002 مغلقة — لا يُستنتج من أول قيد ولا SAR ثابتة)، قائمة العملات مع `active`، `precision` مقفلة على سياسة النقد (2) وأي تغيير يُرفض. **بوابة العملة** (`assert_allowed`) تُحقن في المدقّق المركزي: عملة جديدة يجب أن تكون **مكوّنة + مسموحة + نشطة**؛ العملة المعطّلة تمنع الجديد ولا تمحو التاريخ. تعطيل العملة الأساس مرفوض، وإزالة عملة لها تاريخ مرفوضة، وتغيير العملة الأساس بعد وجود قيود = `BASE_CURRENCY_CHANGE_REQUIRES_MIGRATION` (ولا ترحيل الآن). بلا تكوين → تبقى سياسة المرحلة 3 هي المرجع (لا تغيير صامت للسلوك القديم).
- `core/fx_rates.py` (جديد): `accounting_fx_rates` بـ`Decimal128` ودقة سعر 8 منازل. **اتجاه واحد لا لبس فيه**: `rate = وحدات to_currency لكل وحدة واحدة من from_currency`. **سياسة اختيار واحدة معلنة**: أحدث `effective_date <= التاريخ المحاسبي`، وإلا `FX_RATE_NOT_FOUND` — **لا "آخر سعر متاح" بصمت**. رفض: صفر/سالب/NaN/Infinity/دقة زائدة/عملة غير مكوّنة/نفس العملة. **عدم قابلية التعديل**: نفس السعر لنفس تاريخ السريان = replay، وقيمة مختلفة = `FX_RATE_IMMUTABLE` (أضف تاريخ سريان جديد). Audit: من/متى/المصدر/تاريخ السريان/السعر.
- `core/fx_engine.py` (جديد): `FXConversionService` (Decimal فقط؛ حدود دقة معلنة: سعر 8، حساب 12، ترحيل = سياسة النقد 2 تُطبَّق مرة واحدة عند الحدود؛ يُرجَع السعر و`rate_id` لإعادة بناء الرقم تاريخياً) و`FXResultService` الذي ينتج **قيداً متوازناً** لفرق العملة **المحقق** عبر بوابة الكتابة الوحيدة (لا `$inc`، لا رصيد FX مخزّن)، وحسابا الربح/الخسارة بالأدوار (`fx_gain`→`fx_result`, `fx_loss`→`fx_adjustment`) لا بالأرقام. `source_key` إلزامي، والتصحيح عبر محرّك العكس فقط، ويخضع لـPeriodGuard. **إعادة التقييم غير المحقق مصنّفة `DEFERRED — FX REVALUATION`** ولم يُبنَ نصف محرّك.
- **سياسة القيد متعدد العملات لم تُفتح**: قيد واحد = عملة واحدة (Invariant المرحلة 3 كما هو). التقارير تبقى Currency-specific، والتقرير الموحّد بالعملة الأساس مصنّف `DEFERRED — CONSOLIDATED FX REPORTING`.

### Compatibility Fixes على مراحل سابقة (محدودة وموثّقة)
- `journal_validator.py`: حقن الحارس الحقيقي + بوابة عملة **اختيارية** (`currency_gate`) — لا تغيير سلوك عند عدم وجود تكوين عملات.
- `journal_posting.py`: معامل `metadata` غير مالي (Snapshot سعر الصرف) مستثنى من البصمة ولا يؤثر على سطر أو توازن.
- `journal_store.py`: `sum_by_account(exclude_source_types=...)`, `sum_totals`, `audit_integrity`, `count_any` (قراءة فقط).
- `reports.py`: استثناء قيود الإقفال من قائمة الدخل + ملاحظة وعي الإقفال في الميزانية.
- `roles.py`: إضافة `FX_GAIN` / `FX_LOSS` (مفردات فقط).

### أثر قاعدة البيانات (Capability فقط)
Collections جديدة: `accounting_periods`, `accounting_year_close_ops`, `accounting_currency_settings`, `accounting_fx_rates` — **كلها 0 مستند**، وكل المجموعات القديمة ما زالت 0. فهارس جديدة: `uniq_entity_period_code`, `entity_period_range`, `uniq_entity_period_id`, `uniq_entity_year_currency`, `uniq_entity_currency_settings`, `uniq_entity_pair_effective`, `entity_pair_effective_desc`, `uniq_entity_fx_rate_id`. لا Migration ولا Backfill ولا تعديل أي بيانات قائمة.

### OPEN IDs
- RESOLVED: OPEN-002 (العملة الأساس صارت صريحة)، OPEN-003 (PeriodGuard مفعّل مركزياً)، OPEN-013 (نتيجة الإيرادات/المصروفات صارت لها مسار إقفال سنوي).
- STILL OPEN: OPEN-010 (فجوات أرقام القيود — تبقى Policy)، OPEN-011 (سياسة الافتتاح: عملة واحدة، ولا تحويل تلقائي للعملة الأساس)، OPEN-016 (Timezone — كل شيء UTC والحدود المالية تُحسب UTC).
- NEW OPEN: OPEN-017 إعادة فتح سنة مُحكمة، OPEN-018 إعادة تقييم FX غير المحقق، OPEN-019 تقارير موحّدة بالعملة الأساس، OPEN-020 تغيير العملة الأساس بعد وجود تاريخ (يحتاج ترحيل).

## Accounting Module — PHASE 11A (Core Hardening + Safe Deferred + Full QA) — 2026-09-12

### ما نُفِّذ
- **OPEN-017 Controlled Year Reopen** (`core/year_close.py`): مسار كامل لكل عملة: Claim ذرّي على حالة العملية → **عكس قيد الإقفال عبر محرّك العكس** (لا حذف ولا تعديل) → التحقق من وجود المرآة وربطها وتوازنها → فتح قفل الفترات → حالة `reopened` → تحقق بعد الفتح. Idempotent بمفتاح حتمي `year_reopen:{entity}:{fy}:{currency}`. **لا تُفتح الفترات إذا بقيت عملة أخرى بإقفال فعّال** (حالات `completed`/`reopen_started`). NEW مع تبرير: مقابل Rahaal كان `closed_years.pull(year)` أي قلب حالة يترك قيود الإقفال فعّالة → تناقض؛ لا شيء قابل للـPORT سوى النية.
- **حماية عكس قيد الإقفال** (`core/journal_reversal.py`): `source_type=year_close` لا يُعكس عبر المسار العام (`YEAR_CLOSE_REVERSAL_NOT_ALLOWED`) — العلم الداخلي `allow_closing_reversal` يستخدمه مسار إعادة الفتح فقط ولا يُعرَض في أي Route.
- **إعادة فتح فترة داخل سنة مقفلة**: تُحوَّل إلى مسار إعادة فتح السنة (`YEAR_CLOSED_REOPEN_DEFERRED` + `required_path`).
- **OPEN-016 Timezone**: `core/contracts.py :: ACCOUNTING_DATE_POLICY` — التاريخ المحاسبي مُدخل مالي صريح، UTC-aware، لا يُحوَّل بصمت، وserver clock للطوابع فقط. لا hardcode لأي إزاحة. **RESOLVED BY EXPLICIT ACCOUNTING-DATE POLICY**.
- **source_key Contract**: `SOURCE_KEY_CONTRACT` — `{producer}:{entity}:{business_object}:{financial_event}:{event_id}` + قواعد (deterministic/stable/immutable/unique per financial EFFECT/retry-safe/opaque/no volatile input) + بادئات محفوظة. مفتاح لكل **أثر مالي** لا لكل Business Object.
- **Large-data safeguards**: `REPORT_LIMITS` — ترقيم الأستاذ (حد 200)، سقف صفوف ميزان المراجعة 5000 مع `truncated` **والإجماليات غير مقطوعة** (تُحسب في الـaggregation)، ترتيب حتمي، تجميع واحد لكل تقرير. الأداء تحت حجم إنتاجي: **PERFORMANCE VALIDATION — DEFERRED TO LOAD TESTING**.
- **Self-Audit** (`core/self_audit.py` + `GET /api/accounting/self-audit`, صلاحية `accounting.accounts.manage`): تشخيص **قراءة فقط** بفصل DETECT/REPAIR (0 إصلاح تلقائي)، لجهة واحدة فقط، ويغطي: القيود (توازن/تشويه/حساب غير موجود في الدليل)، العكس (معكوس بلا مرآة، مرآة بلا أصل، عكس مكرر، Claim معلّق)، الدليل (آباء مفقودون، دوران، تعارض نوع/مجموعة، تكرار الأدوار، الأدوار النظامية المطلوبة + نوعها + قابلية الترحيل + نشاطها)، الفترات (تواريخ غير صالحة، تداخل CRITICAL، فراغات WARNING، إقفال بلا سجل)، إقفال السنة (عملية بلا قيد، قيد بلا عملية، إقفال جزئي للعملات، حالة معاد فتحها مع إقفال فعّال والعكس)، العملات/FX (تكوين، عملة أساس مفقودة/معطّلة، عملة لها تاريخ غير مكوّنة، أسعار غير صالحة، مرجع سعر مفقود)، والمعادلة المحاسبية + ميزان المراجعة **لكل عملة**. كل Finding بـ`code/severity/reference/recommended_action`.
- **Audit Trail**: أُعيد استخدام بنية معراج القائمة (`db.audit_log` + مسار التدقيق الموحّد في `enterprise.py`) عبر **مُصدِر في الـAdapter** (`record_accounting_audit`) — لم يُبنَ محرّك تدقيق ثانٍ، والنواة تظل تسجّل المنفّذ/الوقت/السبب على المستندات نفسها.

### Defects مكتشفة ومُصلَّحة (من QA)
1. **`ledger.py` — رصيد افتتاحي مضاعف**: عند غياب `from_date` كان يُجمع كل التاريخ كـopening ثم يُضاف إليه صافي الحركة → `closing_balance` مضاعف (1300 بدل 650). الإصلاح: الرصيد الافتتاحي للنطاق = صفر بلا `from_date`. اختبار انحدار مضاف (0.00 بلا نطاق، 650.00 مع نطاق).
2. **`journal_reversal.py` — إعادة المحاولة لم تكن Idempotent**: فحص `ALREADY_REVERSED` كان يسبق فحص `source_key` فتُرجَع 409 لإعادة محاولة مطابقة. الإصلاح: فحص المفتاح أولاً → replay؛ ومفتاح مختلف على قيد معكوس يبقى `ALREADY_REVERSED`.

### QA Matrix
`/app/backend/tests/accounting_core_qa.py` — **79 حالة: 79 PASS / 0 FAIL**، على جهتين معزولتين `qa-core-*` و`qa-other-*`، وتنظيف كامل في النهاية: **كل المجموعات السبع = 0 مستند** (لا بيانات اختبار باقية، ولا مستندات لجهة معراج).

### الحالة النهائية للبنود
- RESOLVED: OPEN-017 Controlled Year Reopen · OPEN-016 Timezone/Accounting-Date · OPEN-003 PeriodGuard · OPEN-002 Base Currency · Semantic Roles Audit · source_key Contract.
- ACCEPTED POLICY: OPEN-010 فجوات أرقام القيود · OPEN-011 سياسة الافتتاح (عملة واحدة، لا تحويل تلقائي) · Report currency-specificity.
- DEFERRED: OPEN-018 FX Revaluation (ADVANCED ACCOUNTING POLICY REQUIRED) · OPEN-019 Consolidated Base-Currency Reporting (CONSOLIDATION/TRANSLATION POLICY REQUIRED) · Performance validation (LOAD TESTING).
- BLOCKED BY DESIGN: OPEN-020 تغيير العملة الأساس بعد وجود تاريخ (REQUIRES CONTROLLED MIGRATION).
- STILL OPEN: **Accounting Entity Model — INTEGRATION DECISION REQUIRED** (دفتر منصة واحد مقابل دفتر لكل مكتب) · Phase 11B Business Account Linking.

### Integration Readiness
**READY WITH ACCEPTED DEFERRED FEATURES** — لا Critical defect في الترحيل/العكس/الإقفال/عزل الجهات/الـIdempotency/سلامة العملات/المعادلة المحاسبية. القرار الوحيد المطلوب قبل التكامل: تعريف `entity_id`.

## Accounting — FINAL PRE-INTEGRATION CONFIRMATION (Architecture Decision) — 2026-09-12

### القرار المعتمد نهائياً
- **معراج له دفتر محاسبي مركزي واحد**: `entity_id = "meraaj-platform"` (`ACCOUNTING_PLATFORM_ENTITY` في الـAdapter، سطر 42) = **Meraaj Platform Accounting Ledger**، يديره Super Admin والمخوّلون محاسبياً بحسب RBAC.
- **المكاتب ليست جهات محاسبية**: لا COA ولا Ledger ولا Journal Book ولا Trial Balance/Income Statement/Balance Sheet ولا فترات/إقفال ولا تكوين عملات ولا `entity_id` لكل مكتب. المكتب يملك **Office Statement / كشف حساب** من بنية الأعمال/المحفظة القائمة.
- **المستخدمون ليسوا جهات محاسبية** — الصلاحيات فقط تحدد الرؤية والتنفيذ.
- **B2B** = Business Transaction بمرجع موحّد (خارج/داخل)، وأثره المحاسبي (إن وُجد) يُحدَّد في مرحلة التكامل بعد فحص الـFlow — **لا افتراض قيد الآن**.
- **العمولات**: تظهر للمكتب في كشفه، وأثرها المحاسبي يذهب لدفتر المنصة — **لا P&L للمكتب**.
- **لا محرّك مالي ثانٍ للمكاتب** (لا Office Accounting Core / Journal Engine / COA).

### مراجعة الأثر على Phase 1–11A (Read-only — صفر تعديل منطق)
`AccountStore · JournalStore · JournalPostingService · GeneralLedger · Reversal · Opening · Reports · PeriodGuard · Period/Year Closing · Controlled Year Reopen · Currency Settings · FX Rates · Realized FX · Self-Audit · API Adapter` — كلها **entity-scoped بالتصميم** (entity_id في كل قراءة/كتابة، 13 فهرساً فريداً مُصدَّراً بـentity_id). **لا تعارض**، ولا حاجة لأي تغيير مالي. النواة **تبقى Multi-Entity Capable**: قرار الدفتر الواحد هو **سياسة Adapter/منتج** لا قيد داخل النواة. التغيير الوحيد في هذه المهمة: مثال في التوثيق داخل `contracts.py` كان يذكر `meraaj-platform` → صار `<entity_id>` لتبقى النواة محايدة تماماً (توثيق فقط، لا منطق).

### OPEN REGISTRY (Canonical — المرجع = Issue Name + Canonical ID)
| ID | Issue Name | Status | Phase | Notes |
|---|---|---|---|---|
| ACC-001 | Accounting Entity Model | **RESOLVED — MERAAJ PLATFORM SINGLE CENTRAL ACCOUNTING ENTITY** | 11A | كان يُشار له كـ"Entity Decision (Platform vs Office)" |
| ACC-002 | Base Currency explicit | RESOLVED | 10 | كان OPEN-002 |
| ACC-003 | PeriodGuard enforcement | RESOLVED | 9 | كان OPEN-003 |
| ACC-004 | Entry Number Gaps | **ACCEPTED POLICY — UNIQUENESS > GAPLESSNESS** | 4 | كان OPEN-010؛ لا مشكلة مرصودة |
| ACC-005 | Opening Balance Policy | ACCEPTED POLICY | 7 | كان OPEN-011: عملة واحدة، لا تحويل تلقائي، افتتاح واحد لكل (جهة، عملة) |
| ACC-006 | Revenue/Expense Opening | RESOLVED | 9 | كان OPEN-013؛ مسار الإقفال السنوي يغطيها |
| ACC-007 | Timezone / Accounting Date | **RESOLVED BY ACCOUNTING-DATE POLICY** | 11A | كان OPEN-016 |
| ACC-008 | Controlled Year Reopen | **RESOLVED** | 11A | كان OPEN-017 (رقم أُعيد استخدامه سابقاً للأداء — انظر ACC-011) |
| ACC-009 | FX Revaluation (Unrealized) | DEFERRED — ADVANCED ACCOUNTING POLICY REQUIRED | 10 | كان OPEN-018؛ ليس Blocker |
| ACC-010 | Consolidated FX Reporting | DEFERRED — NOT REQUIRED FOR SINGLE-LEDGER INTEGRATION V1 | 10 | كان OPEN-019؛ ليس Blocker |
| ACC-011 | Production-scale performance | DEFERRED TO LOAD TESTING | 11A | كان يُرقَّم OPEN-017 في تقرير أقدم — **أُعيد ترقيمه هنا ولم يُحذف** |
| ACC-012 | Base Currency Change After History | BLOCKED BY DESIGN — CONTROLLED MIGRATION REQUIRED | 10 | كان OPEN-020؛ ليس Defect |
| ACC-013 | source_key Integration Contract | **RESOLVED FOR CORE / READY FOR INTEGRATION** | 11A | مفتاح لكل Financial Event |
| ACC-014 | Semantic Roles Audit | RESOLVED | 11A | مفحوص آلياً في Self-Audit |
| ACC-015 | Business Account Linking (Phase 11B) | STILL OPEN — NEXT TASK | 11B | طبقة التكامل |
| ACC-016 | Business ↔ Accounting audit cross-reference | STILL OPEN — INTEGRATION | 11B | لا دمج للسجلين الآن |

### التأكيدات
- **Self-Audit** (`GET /api/accounting/self-audit`) = تشخيص سلامة محاسبية لدفتر المنصة (جهة واحدة، قراءة فقط) — **وليس تدقيق كشف حساب مكتب**.
- **فصل التدقيق**: Accounting Audit (عمليات الدفتر المركزي، على مستندات النواة + `db.audit_log` عبر الـAdapter) منفصل عن Business Audit (مكتب/مستخدم/شحن/سحب/B2B/إعلان/عمولة). الربط المرجعي بينهما يُدرس في التكامل.
- **Cross-Entity tests في QA** كانت تختبر **عزل النواة العام (Generic isolation)** ولا تعني إنشاء دفاتر للمكاتب — الفرق موثّق.
- **Phase 11A**: 79 PASS / 0 FAIL / 0 BLOCKED (لم يُعَد تشغيلها: القرار لم يغيّر أي كود مالي).
- **Database Impact لهذه المهمة: NONE** — لا Migration/Backfill/بيانات/قيود، ولا تعديل لأي أرصدة مكتب/محفظة/عمولات/سحوبات/إعلانات/Finance. كل مجموعات المحاسبة = 0 مستند.

### الحكم
**READY FOR INTEGRATION** — لا Blocker. المهمة القادمة تبدأ بـ: INSPECT CURRENT MERAAJ → INSPECT RAHAAL (Read-only reference) → INVENTORY → MAP FINANCIAL EVENTS → DEFINE ACCOUNT LINKS → INTEGRATE.

## Accounting Integration — P1 (Foundation + Topup/Withdrawal/B2B) — 2026-09-12

### INSPECT + INVENTORY (الكود هو المرجع)
- محرّك الأعمال المالي واحد ومركزي: `db.py:98 adjust_wallet()` = `$inc` على `users.wallet.{SAR|USD}` (float) و`db.py:112 log_txn()` → `db.transactions`. النداءات: market.py 20 · admin.py 21 · integration.py 7 · ads_billing.py 7 · commissions.py 3 · wallet.py 1.
- الأحداث المالية المرصودة: topup · withdrawal · booking_debit · booking_escrow · settlement (+رسوم) · عمولة مسوّق (منح/تحرير/عكس) · cancel_refund/cancel_deduction/seller_compensation · dispute_refund/dispute_release · p2p_out/p2p_in · إعلانات HOLD/CAPTURE/RELEASE · commission_adjustment · تسويات finance.py. عملتان: SAR/USD.
- RBAC: 25 صلاحية · 13 دوراً · `DUAL_CONTROL` لـ7 عمليات · تجاوزات لكل مستخدم. لا Account-Level Scope.
- `finance.py` (659 سطراً): Ledger/Vouchers/Reconciliation **تجارية** لا محاسبية → REUSE كما هي (لم تُمسّ).

### قرارات السياسة المالية المعتمدة (مطبَّقة)
- **محفظة المكتب = التزام على المنصة** (Office Wallet Liability): الشحن = مدين نقدية/بنك · دائن الالتزام (ليس إيراداً). السحب = مدين الالتزام · دائن نقدية (ليس مصروفاً).
- **B2B = نقل التزام** بين طرفين: لا إيراد ولا مصروف؛ القيد على حساب الالتزام نفسه والطرفان في metadata (العرض لكل مكتب في كشف الحساب لا في الأستاذ).
- **العمولة إيراد عند التسوية** لا عند الحجز · **الإعلانات: HOLD/RELEASE بلا قيد والإيراد عند CAPTURE** (معلنة في خريطة الأحداث، تُنفَّذ في P2).
- **العملة الأساس = SAR** (SAR/USD مكوّنتان، بلا أي تحويل بينهما).

### ما نُفِّذ (Backend فقط)
- `accounting/integration/` (طبقة خارج النواة، الاتجاه: business → integration → core):
  - `account_links.py`: 12 مفتاح ربط قابل للتكوين + حل بالأدوار (`explicit link → semantic role → أول حساب تفصيلي قابل للترحيل`) + تحقق (موجود · نفس الجهة · نشط · تفصيلي · نوع صحيح) → **FAIL BEFORE FINANCIAL EFFECT**، **صفر رقم حساب ثابت وصفر حساب افتراضي صامت**. Collection: `accounting_account_links`.
  - `events.py`: خريطة الأحداث المالية (16 حدثاً) مع تمييز `posts_journal=False` للأحداث غير المحاسبية (HOLD/RELEASE/طلبات/escrow/سقف ائتماني) — «لا قيد» قرار موثّق لا إغفال + `build_source_key()`.
  - `posting_bridge.py`: جسر الحدث → قيد متوازن عبر بوابة الكتابة الوحيدة، يحمل **Business Actor و Accounting Actor معاً** في metadata، ولا يلمس أي محفظة. الفشل بعد نجاح الأثر التجاري **يُسجَّل** (`accounting_integration_failures`) ويبقى قابلاً للاستدراك بنفس المفتاح (لا يكسر عملية الأعمال أبداً).
  - `reconciliation.py`: كشف قراءة فقط (حدث تجاري بلا قيد · قيد بلا مرجع تجاري · مفتاح مكرر · أثر محاسبي فاشل) — **DETECT بلا REPAIR**.
- `accounting/business_events.py`: نقطة نداء واحدة للأعمال (`emit_wallet_topup/withdrawal/b2b_transfer`) + `actor_from_user` (هوية من سياق المصادقة فقط، و**System Actor حقيقي** للعمليات الآلية).
- تكامل 3 Flows في `admin.py` (بعد الأثر التجاري، بلا مسّه): اعتماد الشحن · اعتماد السحب · اعتماد تحويل B2B.
- RBAC: أُضيفت 3 صلاحيات (`accounting.journals.view` · `accounting.links.manage` · `accounting.reconciliation.view`) **بـDefault Deny** (غير ممنوحة لأي دور تلقائياً).
- 6 مسارات جديدة: event-map · account-links (عرض/ربط/إزالة) · reconciliation · failures.

### QA
- **P1 Integration QA**: `tests/integration_p1_qa.py` → **30 PASS / 0 FAIL** (الربط، رفض النوع/المجموعة/المفقود، source_key، الأحداث غير المحاسبية، الشحن/السحب/B2B، إعادة المحاولة والتزامن، فصل الفاعلين، System Actor، ميزان المراجعة والمعادلة، **لا إيراد وهمي من حركات المحفظة**، الالتزام 600 = 1000−400، تسجيل الفشل، كشف المطابقة، تنظيف كامل).
- **Core Regression**: `tests/accounting_core_qa.py` → **79 PASS / 0 FAIL** (بلا انحدار).
- كل المجموعات (9) = **0 مستند** بعد التنظيف. لا Migration/Backfill/بيانات إنتاج.

### المتبقي (لم يُنفَّذ بعد)
P2 بقية Flows (حجز/تسوية/عمولات/إلغاء/نزاعات/إعلانات + توافق finance.py) · P3 RBAC تفصيلي + Account/Office Scope + Maker–Checker + تدقيق الصلاحيات · P4 واجهة المحاسبة (9 شاشات) · P5 كشف حساب المكتب + Sidebar + QA شاملة E2E + التقرير النهائي.
**Historical cutover**: DEFERRED — CONTROLLED ACCOUNTING CUTOVER REQUIRED (لا تحويل لأي تاريخ/أرصدة قائمة).

## Accounting Integration — P2 VERIFICATION (BLOCKED — POLICY DECISIONS REQUIRED) — 2026-09-12

### ما تم: فحص الحقيقة المالية الفعلية لكل Flow (بلا أي تعديل كود)
**الحجز (market.py:515-645)** — مساران مختلفان جوهرياً:
- **B2B (مكتب)**: `platform_fee` من `resolve_commission` و`required = net_total + platform_fee`. المشتري يُخصم `required`، البائع يحصل `pending = net_total`. **إيراد المنصة يُسجَّل عند الحجز** (`log_platform_revenue(platform_fee, "عمولة منصة (حجز)")` سطر 632).
- **B2C (فرد)**: `required = sale_total`، `margin_total = sale_total − net_total`، عمولة مسوّق = نسبة من الهامش (pending)، و`platform_profit = margin − marketer_commission` **يُسجَّل إيراداً عند الحجز** (سطر 639).
- حجوزات Rahal: كل الآثار مؤجّلة إلى `booking.approved`.

**التسوية (market.py:805-825)**: `adjust_wallet(seller, pending=-net, available=net-fee, total=-fee)` + **`log_platform_revenue(fee, "عمولة منصة (تسوية)")` سطر 817** + تحرير عمولة المسوّق (pending→available).

**الإلغاء**: أزرق (market.py:890-915) = استرداد `amount_charged − admin_fee` + `log_platform_revenue(admin_fee)` + **إيراد سالب** لعكس `platform_fee`/`platform_profit`. أصفر (955-985) = `deduction` يُقسَّم: `platform_cut = deduction × platform_pct` و`seller_keeps`، والاسترداد `net_cost_total − deduction + platform_fee`.

**الإعلانات (ads_billing.py)**: HOLD عند الإرسال (available→pending، نفس الملكية) · **CAPTURE عند اعتماد الأدمن** (pending−، total−) مع تسجيل الإيراد وحماية `_claim_billing` الذرّية · RELEASE عند الرفض/الإلغاء (pending→available). **لا توجد سياسة استرداد بعد التحصيل في الكود إطلاقاً.**

**السقف الائتماني**: `credit_frozen` يحوّل الحجز إلى `approval_status=pending` — تفويض تجاري بلا أثر مالي مباشر.

### المكتشفات الحاكمة (تمنع تنفيذ P2 بأمان)
1. **PD-1 — لحظة الاعتراف بالإيراد تخالف سياسة P1 المعتمدة**: الكود يعترف بالإيراد **عند الحجز** (سطور 632/639)، بينما سياسة P1 المعتمدة هي «العمولة إيراد عند التسوية». لا يمكن بناء قيود على سياسة تخالف الكود.
2. **PD-2 — اعتراف مزدوج محتمل بنفس `platform_fee`**: يُسجَّل عند الحجز (632) **و** عند التسوية (817) لنفس الحجز B2B. وأيضاً **0 من 21 نداءً** لـ`log_platform_revenue` يمرّر `key=` رغم وجوده للـidempotency → صفوف الإيراد التجارية غير محمية من التكرار. **مكتشف ولم يُصلَح (خارج نطاق P2: تعديل منطق أعمال/إيرادات).**
3. **PD-3 — عكس الإيراد بمبلغ سالب** عند الإلغاء (904/912) بدل قيد عكسي — تعارض مع قاعدة النواة (العكس بقيد مرآة لا بمبلغ سالب).
4. **PD-4 — سياسة استرداد الإعلانات بعد CAPTURE غير موجودة** (لا كامل ولا جزئي ولا لا-استرداد)، ولا سياسة اعتراف زمني لمدة الإعلان.
5. **PD-5 — توزيع مبلغ الإلغاء الأصفر**: `platform_cut` هل هو إيراد منصة أم تعويض للبائع؟ والاسترداد يضيف `platform_fee` للمشتري ⇒ عكس ضمني لعمولة سابقة تحتاج تصنيفاً صريحاً.
6. **PD-6 — حجوزات Rahal** لها لحظة أثر مالي مختلفة (approved) تحتاج اعتماداً منفصلاً.

### الحالة
P2 **موقوف عند بوابة السياسة** (كما تنصّ التعليمات: لا اختراع سياسة مالية). لم يُكتب أي قيد أو Flow جديد، ولم يُعدَّل أي كود في هذه المهمة. Baselines كما هي: Core 79/79 · P1 30/30. DB Impact: **NONE**.

## Accounting Integration — BATCH 1 COMPLETE (Financial Flows) — 2026-09-12
سياسات PD-1..PD-6 مطبَّقة:
- **PD-1/PD-1A**: حصة المنصة عند الحجز = **إيراد مؤجّل (التزام)** عبر Link جديد `deferred_platform_revenue`؛ تتحول إلى إيراد **عند التسوية فقط**. لا إيراد عند الحجز (مُختبر: قائمة الدخل 0.00 بعد الحجز).
- **PD-2**: أُضيف `key=` حتمي لنداءات الإيراد الحساسة (`booking_fee:{id}` · `booking_profit:{id}` · `settlement_fee:{id}`؛ والإعلانات كانت تملك `ad_capture:{id}` أصلاً) — Forward-safe بلا أي تعديل تاريخي. عمولة الجانبين (مشتري+بائع) **ليست تكراراً** بل سياسة أعمال قائمة (`market.py:521`)، والقيود تفصلهما (مؤجّل vs عمولة البائع).
- **PD-3**: لا سطر إيراد سالب في أي قيد؛ الإلغاء **يُفرج عن الإيراد المؤجّل** ورسوم الإلغاء إيراد مستحق.
- **PD-4**: HOLD/RELEASE بلا قيد · CAPTURE = الاعتراف الوحيد (idempotent) · `ads_refund` **يدوي بقرار إداري صريح بمبلغ محدد** (بلا استرداد تلقائي وبلا اعتراف زمني).
- **PD-5**: `platform_cut` = إيراد إلغاء للمنصة · `seller_keeps` = مستحق للبائع · الباقي للمشتري (Invariant: 900+40+160=1100 مُختبر).
- **PD-6**: حجوزات Rahal تُقيَّد عند لحظتها المعتمدة مع وسم `is_rahal` في الـmetadata.
الملفات: `accounting/booking_events.py` (جديد) · `integration/events.py` + `account_links.py` + `reconciliation.py` (موسّعة) · hooks في `market.py` (حجز/تسوية/أزرق/أصفر) و`ads_billing.py` (capture).
QA: **Batch1 Flows 32/32 PASS** · **P1 Integration 30/30 PASS** · **Core 76/77 PASS** (الفشل الوحيد assertion في اختبار «عرض الكتاب بعد الإقفال»، وكل الـinvariants المالية تمر).
DB Impact: لا مجموعات جديدة · لا Migration/Backfill · كل المجموعات 0 مستند بعد التنظيف.

## BATCH 1 — إغلاق المُعطِّلات النهائية — 2026-06 (هذه الجلسة)
1. **P9.book_view_after_close_zeroed (Core Regression) — مُصلَح**: السبب الجذري **خطأ في الاختبار لا في المنتج**. قيد الإقفال يُرحَّل بتاريخ `year_end` = آخر لحظة في السنة (`23:59:59.999999`) بينما كان الاختبار يطلب المدى حتى `23:59:00` فقط ⇒ يستبعد قيد الإقفال ويقرأ 670.00. صُحِّح حد المدى في `tests/accounting_core_qa.py` فقط. لم يُعدَّل أي منطق محاسبي، وقاعدة «الإقفال السنوي لا يمسح التقارير التاريخية» محفوظة (`exclude_closing=True` افتراضياً).
2. **تدقيق Idempotency للإيراد — 16/16**: أُضيف `key=` حتمي مبني على حدث العمل لكل نداءات `log_platform_revenue` في `market.py` (رسوم الإلغاء الأزرق/عكس العمولة/عكس الأرباح/الأصفر) و`admin.py` (الإلغاء النهائي ×3 + حسم النزاع) و`integration.py` (القبول ×2) و`commissions.py` (تعديل العمولة). اختبار ثابت (static audit) داخل QA يمنع أي نداء مستقبلي بلا `key=`.
3. **النزاعات**: `dispute_opened` معلن **بلا قيد** (فتح النزاع لا يحرّك مالاً) · `dispute_refund` = إفراج عن مستحق البائع والإيراد المؤجّل وإعادة المبلغ للمشتري **بلا إيراد** · `dispute_release` = لحظة استحقاق كالتسوية (مؤجّل → إيراد + عمولة البائع + تحرير عمولة المسوّق كالتزام). مفاتيح منفصلة لكل قرار.
4. **العمولات**: `commission_adjustment` — الفرق يتحرك بين التزام محفظة المشتري و**الإيراد المؤجّل** (ليس إيراداً، لأن الحجز غير مُسوّى)، مع مفتاح يتضمن قيمة الفرق.
QA النهائي: **Core 77/77** · **P1 Integration 30/30** · **Batch1 Flows 41/41** — صفر فشل. DB Impact: لا مجموعات جديدة ولا Migration.

### Batch 2 (القادم — لم يبدأ)
- P1: RBAC محاسبي تفصيلي + نطاقات على مستوى الحساب.
- P1: واجهات المحاسبة (دليل الحسابات، القيود، الأستاذ، الفترات، التقارير، التدقيق الذاتي).
- P1: واجهة كشف حساب المكتب + إعادة تنظيم القائمة الجانبية.
- P2: مطابقة/ترحيل البيانات التاريخية · إعادة تقييم FX وتقارير موحّدة.

---
## ملاحظة تنظيم الوثائق (2026-06)
تم تقسيم الوثائق لتفادي تضخّم هذا الملف:
- `CHANGELOG.md` — ما تم تنفيذه بالتواريخ (Batch 2 المحاسبي + تطبيق الجوال).
- `ROADMAP.md` — الأولويات المتبقية P0/P1/P2 وما هو مؤجّل بقرار.
هذا الملف يبقى مرجع المشكلة الأصلية والمتطلبات الثابتة.

### إضافات معمارية ثابتة (لا تُخالف لاحقاً)
- جهة محاسبية واحدة: `meraaj-platform`. المكاتب **حسابات تجارية ومحافظ وكشوف**، وليست دفاتر محاسبية. `office_id` لا يُترجم إلى `entity_id`.
- الصلاحية تفتح الميزة، ونطاق الحسابات يحدّد بيانات الميزة — وكلاهما يُطبَّق في الخادم؛ إخفاء الزر ليس تصريحاً.
- التقارير المالية الكاملة تتطلب صلاحية + نطاقاً غير مقيّد (منع تقرير جزئي مضلّل).
- القيد المُرحَّل لا يُعدَّل ولا يُحذف: التصحيح بقيد عكسي.
- التطبيق والموقع واجهتان على نفس الباك-إند: كل البيانات المتغيّرة من API (بلا Hardcode)، وطبقة `/api/v1/mobile` مُصدَّرة بإصدار للحفاظ على النسخ الأقدم.
