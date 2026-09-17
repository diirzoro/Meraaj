# MERAAJ MOBILE — تقرير فحص (Inspection Only) — يونيو 2026
لا تعديلات في هذه الخطوة. لا PDF. لا تغيير Backend/Accounting.

## 0) طبيعة البنية الحالية (من الكود، لا افتراض)
- **ليست WebView لموقع**: لا يوجد أي مكوّن يفتح URL الموقع داخل التطبيق.
- **ليست PWA**: لا `public/manifest.json` ولا Service Worker (لا وجود لأي تسجيل SW).
- **البنية الفعلية**: React SPA واحدة (CRA/craco) + **Capacitor 7 native shell**:
  - `frontend/capacitor.config.json` (appId `network.meraaj.app`، `webDir: build`، SplashScreen/StatusBar/Keyboard)
  - مجلد `frontend/android/` (مشروع Gradle حقيقي) + `@capacitor/android`, `@capacitor/app`, `@capacitor/status-bar`, `@capacitor/splash-screen`, `@capacitor/keyboard` في package.json
  - `src/native/NativeBridge.jsx` + `useNativeChrome.js` (StatusBar/Splash) + `useAndroidBackButton.js` (زر الرجوع)
  - `App.js`: `IS_NATIVE` → عند التنصيب الأصلي الجذر `/` يذهب إلى `/m` (لا يفتح الموقع أبداً)
- **الخلاصة**: Native App Shell (Capacitor) يعرض مسارات `/m/*` فقط، ويشترك مع الويب في نفس الكود والـ Backend. المشكلة إذن **ليست بنيوية بل بصرية/تفاعلية (UX polish)**.
- **ملاحظة مهمة**: زر الرجوع الأندرويدي في `useAndroidBackButton.js` يعتبر جذور التطبيق `["/", "/dashboard", "/admin", "/login"]` — أي **لا يعرف `/m/home`**، فالرجوع من الرئيسية في التطبيق لا يسلك سلوك "اضغط مرتين للخروج" بل يحاول العودة/الذهاب إلى `/dashboard` (خطأ فعلي، يحتاج إصلاح).

## 1) جميع مسارات /m/* الموجودة ووظيفة كل شاشة
| المسار | الملف | الوظيفة | الحالة البصرية |
|---|---|---|---|
| `/m` | MSplash.js | Splash + بوابة إصدار (`min_supported_app`) + استعادة الجلسة → home/login | **Native-like** |
| `/m/login` | MLogin.js | دخول بحساب معراج نفسه (كل الأدوار) | **Native-like** |
| `/m/register` | MRegister.js | إنشاء حساب فرد/مكتب على `/api/auth/register` | متوسط (نموذج طويل بلا خطوات) |
| `/m/forgot` | MForgot.js | استعادة كلمة المرور (request → token → confirm) — التسليم يدوي من الإدارة | متوسط (يعرض نصاً تشغيلياً طويلاً) |
| `/m/home` | App.js → MHome / MAdminHome | رئيسية تتبدّل حسب `bootstrap.experience` | **Native-like (مستخدم)** / قائمة إدارية طويلة (أدمن) |
| `/m/programs` | MPrograms.js | تصفح برامج العمرة + بحث + Bottom Sheet للتصفية (`GET /api/packages`) | **Native-like** |
| `/m/programs/:id` | MProgramDetail.js | تفاصيل البرنامج، الغرف، السعر، زر متابعة | متوسط (بلا صور/بطل بصري) |
| `/m/programs/:id/book` | MBookingFlow.js | خطوتان: المسافرون → المراجعة → تأكيد (Idempotency-Key) | **Native-like** |
| `/m/bookings` | MBookings.js | مركز الحجوزات الموحّد (`kind` مهيّأ للتذاكر لاحقاً) + تبويب مشتري/بائع للمكتب | جيد (بلا فلترة حالة) |
| `/m/bookings/:id` | MBookingDetail.js | تفاصيل الحجز + المسافرون + المسار الزمني | جيد |
| `/m/wallet` | MWallet.js | أرصدة SAR/USD + تبويبات الحركات/الشحن/السحوبات | جيد (تبويبات Pills، بلا رسم بياني) |
| `/m/wallet/topup` | MTopup.js | طلب شحن + رفع صورة الإيصال (`capture="environment"`) + طلباتي | **web-like**: `<input type="file">` خام بدل زر كاميرا/معرض |
| `/m/statement` | MStatement.js | كشف حساب المكتب (`/api/office-statement`) | web-like (صفوف كشف مضغوطة) |
| `/m/sales` | MSales.js | مبيعات المكتب (`/api/bookings?role=seller`) | جيد |
| `/m/notifications` | MNotifications.js | الإشعارات + تعليم كمقروء / الكل | **Native-like** |
| `/m/account` | MAccount.js | الهوية، روابط، نص أمان، الإصدار، خروج | متوسط (لا تعديل بيانات، لا إعدادات، لا تغيير كلمة مرور) |
| `/m/tickets` | MTickets.js | **Placeholder فقط** + عرض متطلبات عقد المزوّد | متوسط (يعرض متطلبات تقنية للمستخدم النهائي — غير مناسب) |
| `/m/accounting` | MAccountingHub.js | لوحة محاسبة للأدمن فقط + AccountingGate على كل مسار | قائمة إدارية (مقبولة للأدمن) |
| `/m/accounting/{chart,vouchers,journals,ledger,reports,periods,audit}` | MAcc*.js | نفس Batch 2 endpoints عبر `mobile/api/accounting.js` | **web/desktop-like**: جداول/أرقام كثيفة |
| `/m/admin/operations` و `/m/admin/orders` | MAdminOrders.js | متابعة الطلبات + تبويبات حالة | جيد |
| `/m/admin/topups` | MAdminTopups.js | مراجعة طلبات الشحن (اعتماد/رفض في Sheet) | **Native-like** |

**البنية الداعمة**: `MobileShell.js` (Server-driven: tabs/services/features/badges من `/api/v1/mobile/bootstrap`) · `MobileLayout.js` (Bottom Nav من ٥ عناصر) · `ui/kit.js` (Screen, TopBar, Card, Sheet, Skeleton, Empty/Error, PrimaryButton/GoldButton, StatusPill, Money, useAsync) · `api/client.js` (طبقة API واحدة + إعادة محاولة للقراءات فقط) · `push.js`.

## 2) ما يبدو Mobile-Native فعلاً الآن
- Bottom Tab Bar حقيقي (٥ عناصر + Badges + safe-area) — **لا Sidebar إطلاقاً** في `/m/*`.
- Bottom Sheets بدل الـ Dialogs (تصفية البرامج، مراجعة الشحن).
- Splash + بوابة تحديث إلزامي + StatusBar/Keyboard أصلية عبر Capacitor.
- Skeletons و Empty/Error States في كل شاشة، و`active:scale` على اللمس، و`env(safe-area-inset-*)`.
- Home المستخدم: هيدر داكن بانحناء سفلي + بطاقة رصيد + شبكة أيقونات خدمات 3×N (App-style فعلاً).
- رفع الإيصال بالكاميرا، و`inputMode` مناسب للأرقام، وRTL بالكامل.

## 3) ما ما زال Web/Desktop-like (سبب إحساسك "موقع داخل تطبيق")
1. **لا انتقالات بين الشاشات**: التنقل قفزة فورية بلا push/pop أو fade — أقوى سبب للإحساس بأنه ويب.
2. **لا Pull-to-Refresh**: التحديث زر نصي في الـ TopBar (`m-wallet-refresh`).
3. **TopBar ثابت غير أصلي**: نفس الشكل في كل شاشة، بلا Large Title يتقلّص، ولا Header شفاف يتلوّن عند التمرير.
4. **عناصر HTML خام**: `<select>` في كل النماذج (Programs filter, Topup, Register, Statement) يفتح قائمة المتصفح؛ الأصلي = Bottom Sheet Picker. و`<input type="file">` الخام في الشحن.
5. **شاشات المحاسبة (MAcc*)**: صفوف/أعمدة كثيفة = تصغير Dashboard، وهي النقطة الأقرب لوصفك (مقبولة للأدمن لكنها ليست Mobile-first).
6. **Home الأدمن**: قوائم روابط طويلة (Group → children) = Sidebar الويب معاد رسمه رأسياً، بلا بطاقات KPI أو إجراءات سريعة.
7. **لا صور/بصريات**: البرامج بلا صورة غلاف؛ كل شيء نص + بطاقات بيضاء متشابهة → إحساس "جدول ويب".
8. **`/m/tickets`** يعرض متطلبات API تقنية بالإنجليزية للمستخدم — محتوى داخلي في واجهة عملاء.
9. **زر الرجوع الأندرويدي لا يعرف `/m/home`** (خطأ سلوكي أصلي).
10. **لا Haptics، لا Toast بموضع أصلي (الحالي top-center عام)، لا Skeleton Shimmer، لا Empty Illustrations، لا Swipe Actions، لا Tab-state memory** (العودة لتبويب تعيد التحميل من الصفر).
11. **الخطوط والمقاسات**: كثير من النصوص `text-[10px]/[11px]` = كثافة ويب أكثر من إيقاع تطبيق.
12. **Register صفحة نموذج واحدة طويلة** بدل Stepper، و**Account** بلا إعدادات/تعديل/تغيير كلمة مرور.

## 4) REUSE / REDESIGN / NEW UI
**REUSE كما هو (بلا لمس)**
- `api/client.js`, `api/accounting.js`, `MobileShell.js`, `push.js` — كل طبقة الاتصال والحالة.
- منطق `MBookingFlow` (Idempotency, server-authoritative pricing), `MTopup` (single-shot), `AccountingGate`, `MobileHome` experience switch.
- كل `data-testid` الحالية (أساس الـ 58 اختبار) — يجب **عدم تغيير أي testid** لإبقاء الـ regression baseline صالحاً.
- `Backend`: `mobile_api.py` SERVICE_CATALOG/TABS/ADMIN_SECTIONS كما هي.

**REDESIGN (نفس الوظيفة، واجهة أصلية)**
- `ui/kit.js` → نظام تصميم أصلي: Large/Collapsing TopBar، Screen بانتقالات، SheetSelect بدل `<select>`، PullToRefresh، Shimmer، Haptics، أزرار Pill.
- `MHome` (إيقاع بطاقات + Quick Actions + Stories/Carousel للبرامج) · `MAdminHome` (KPI Cards + إجراءات سريعة بدل قائمة روابط) · `MWallet` (بطاقة محفظة قابلة للتبديل + Timeline للحركات) · `MTopup` (خطوات + زر كاميرا/معرض + معاينة الإيصال) · `MProgramDetail` (Hero + Sticky Price Bar) · `MPrograms` (بطاقات بصورة + Segmented filters) · `MBookings` (فلترة حالة + Segmented + Swipe) · `MStatement` (بطاقات حركة بدل صفوف كشف) · `MRegister` (Stepper) · `MForgot` (خطوات واضحة، نص أقصر) · `MAcc*` (بطاقات/Accordion + Sheet تفاصيل بدل جداول).
- `useAndroidBackButton.js` → إضافة `/m/home` كجذر (إصلاح سلوكي).

**NEW UI فقط (لا Backend جديد)**
- انتقالات الصفحات (push/pop) + Route Transition Wrapper.
- PullToRefresh generic + Skeleton Shimmer + Empty Illustrations.
- SheetSelect / SheetDatePicker / FilePickerButton.
- `More` Screen (خدمات إضافية) + Profile Settings Sections (بدون endpoints جديدة).
- `/m/tickets` إعادة كتابة كشاشة "قريباً" موجّهة للعميل + تسجيل اهتمام بصري فقط (بلا Flow وهمي).

## 5) Navigation: الحالي والمقترح
**الحالي (Server-driven من bootstrap)**
- مستخدم: `الرئيسية | حجوزاتي | المحفظة | الإشعارات | حسابي`
- أدمن: `الرئيسية | العمليات | الحسابات | الإشعارات | حسابي`
- كل شيء آخر من Home/Account. Bottom Nav موجود بالفعل ✅ لكن بلا انتقالات ولا حفظ حالة.

**المقترح**
- إبقاء نفس الخمسة (مطابق لطلبك حرفياً) + **حفظ حالة كل تبويب** (لا إعادة تحميل عند التبديل).
- الخدمات الأقل تكراراً (مبيعاتي، كشف الحساب، التذاكر) في **Home + شاشة `More`** بدل حشو التبويبات.
- إضافة FAB سياقي في المحفظة (شحن) وفي البرامج (بحث).
- زر الرجوع الأندرويدي: `/m/home` = جذر (ضغط مزدوج للخروج).

## 6) Home architecture المقترحة (المستخدم)
1. Header داكن: تحية + اسم + جرس إشعارات (Badge).
2. **بطاقة المحفظة** (رصيد + شحن + تنبيه طلبات معلّقة) — موجودة، تُطوّر بصرياً.
3. **شبكة الخدمات** من `bootstrap.services` حصراً (الموجود فعلاً): برامج العمرة · التذاكر (قريباً) · حجوزاتي · شحن الرصيد · المحفظة · مبيعاتي (مكتب) · الإشعارات · كشف حساب المكتب (مكتب) · حسابي.
4. **Carousel برامج مميزة** (من `/v1/mobile/home`) ببطاقات أفقية.
5. **أحدث حجوزاتي** (٣ عناصر) + "عرض الكل".
6. (أدمن) بدلاً منها: KPI Cards + أقسام مسموحة من `admin_sections` كبطاقات.

## 7) User Journey (Login → حجز/محفظة/حساب)
`/m` Splash → (بلا جلسة) `/m/login` → `/m/home` ← bootstrap يحدد التجربة.
- **حجز**: Home/Services → `/m/programs` → بحث/تصفية (Sheet) → `/m/programs/:id` → "متابعة الحجز" → `/m/programs/:id/book` (مسافرون → مراجعة → تأكيد بـ Idempotency-Key) → شاشة نجاح → `/m/bookings/:id`.
- **محفظة**: Tab المحفظة → أرصدة → "شحن الرصيد" → `/m/wallet/topup` (مبلغ/عملة/طريقة/إيصال) → طلب `pending` → يُعتمد من الإدارة (`/m/admin/topups`) → الرصيد يُضاف في السيرفر.
- **حساب**: Tab حسابي → الهوية/الروابط/الإصدار → خروج → `/m/login`.
- **أدمن**: Login → `/m/home` (MAdminHome) → العمليات/الطلبات/الشحن/الحسابات (AccountingGate + RBAC + Scope).

## 8) هل إعادة التصميم ممكنة بلا تغيير Backend APIs؟
**نعم — ٩٥٪ منها UI خالص.** الاستثناءات الحقيقية (اختيارية وصغيرة، وكلها في `mobile_api.py` فقط، بلا مساس بـ Accounting/RBAC/Batch1/Batch2):
1. **صور البرامج**: إن لم يكن `image_url` موجوداً في `GET /api/packages` سنحتاج تمريره في `/v1/mobile/home` (حقل قراءة فقط) — وإلا نستخدم Placeholder بصري بلا تغيير.
2. **KPI الأدمن على الجوال**: عرض أرقام سريعة يتطلب إما `/api/admin/dashboard` الموجود (مفضّل، بلا تغيير) أو حقول إضافية في `bootstrap.badges`.
3. **`More`/تصنيف الخدمات**: يفضّل إضافة `group` اختياري لعناصر `SERVICE_CATALOG` (سطر بيانات ثابت، لا منطق).
4. **التذاكر**: `/v1/mobile/tickets/providers` حالياً يرجع متطلبات تقنية؛ نص العرض للعميل يُعاد كتابته في الواجهة (بلا تغيير Endpoint).
لا شيء من ذلك يمسّ المال أو الصلاحيات، ولا يتطلب Migration.

## 9) المخاطر وضوابط التنفيذ المقترحة (عند الموافقة)
- **عدم تغيير أي `data-testid`** → الـ 58 اختبار Mobile تبقى Regression baseline صالحاً.
- عدم لمس `mobile/api/*`, `MobileShell.js`, `AccountingGate`, أو أي مسار من `/m/*` (نفس المسارات، واجهة جديدة).
- عدم لمس `accounting/`, `wallet.py`, `security.py`, RBAC، أو أي endpoint مستقر.
- بعد التنفيذ: تشغيل الخمسة سكربتات + فحص بصري 390×844 لكل شاشة.

## STOP — لا تنفيذ قبل رسالة التنفيذ الواحدة منك.
