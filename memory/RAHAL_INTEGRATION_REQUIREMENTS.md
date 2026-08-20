# وثيقة المتطلبات التقنية للتكامل بين "معراج نتورك" و "رحال"
## (Meraaj Network ⇄ Rahal — Technical Integration Requirements)

**الإصدار:** 1.0
**التاريخ:** يونيو 2026
**الجهة المُصدِرة:** فريق هندسة منصة معراج نتورك (Target Media)
**الجهة المستقبِلة:** فريق تطوير نظام "رحال"

---

## 0. مقدمة ومبادئ عامة

هذه الوثيقة تحدد العقد التقني (Technical Contract) المطلوب بين النظامين لتحقيق:
1. **الدخول الموحد (SSO)** — دخول مستخدم رحال إلى معراج بضغطة زر دون إعادة تسجيل.
2. **مشاركة الباكج (Package Sharing)** — نشر باكج من رحال إلى سوق معراج.
3. **تزامن المخزون اللحظي (Real-time Inventory Sync)** — منع البيع المزدوج (Overbooking).
4. **عرض السوق داخل رحال (Embedded Marketplace)**.

**مبادئ عامة:**
- كل الاتصالات عبر **HTTPS** فقط.
- تنسيق البيانات: **JSON** (UTF-8).
- المصادقة بين الخوادم (Server-to-Server): **API Key ثابت** في الترويسة `X-Meraaj-Api-Key` / `X-Rahal-Api-Key` + توقيع **HMAC-SHA256** لكل Webhook.
- التوقيت: **ISO 8601 UTC**.
- كل عملية حجز/مشاركة تحمل مُعرّف **idempotency_key** لمنع التكرار.

---

# القسم الأول: ما تحتاجه "معراج" مـن "رحال"
## (APIs & Webhooks that Rahal must provide)

### 1.1 مصادقة الدخول الموحد (SSO)

الطريقة المعتمدة: **OAuth 2.0 Authorization Code Flow** (أو بديل مبسّط: Signed JWT Handoff).

#### أ) نقطة تفويض الدخول (Rahal → Meraaj redirect)
عند ضغط المكتب على زر "الانضمام / الدخول إلى معراج نتورك" داخل رحال، يوجّه رحال المستخدم إلى معراج مع رمز مؤقت.

**API #1 — تبادل الرمز (Token Exchange):**
```
POST https://api.rahal.example/v1/oauth/token
Headers: X-Meraaj-Api-Key: <shared_secret>
Body:
{
  "grant_type": "authorization_code",
  "code": "<one_time_code>",
  "redirect_uri": "https://api.meraaj.network/api/integrations/rahal/callback"
}
Response 200:
{
  "access_token": "<jwt>",
  "expires_in": 3600,
  "office_ref": "RHL-OFF-10231"
}
```

#### ب) جلب ملف المكتب (Office Profile)
**API #2 — بيانات المكتب:** تُستخدم لإنشاء/مطابقة حساب المكتب في معراج تلقائياً.
```
GET https://api.rahal.example/v1/office/me
Headers: Authorization: Bearer <access_token>
Response 200:
{
  "office_ref": "RHL-OFF-10231",
  "office_name": "مكتب النور للسياحة",
  "owner_name": "أحمد صالح",
  "email": "office@example.com",
  "phone": "+967770000000",
  "governorate": "صنعاء",
  "address": "شارع الزبيري",
  "commercial_license": "CR-88213",
  "status": "active"
}
```

### 1.2 سحب بيانات الباكجات (Package Data APIs)

**API #3 — قائمة باكجات المكتب (للاختيار عند المشاركة):**
```
GET https://api.rahal.example/v1/office/{office_ref}/packages?type=umrah|tourism&status=active
Headers: Authorization: Bearer <access_token>
Response 200: [ { PackageObject }, ... ]
```

**API #4 — تفاصيل باكج مفرد (Package Details) — المصدر الرسمي للحقيقة:**
```
GET https://api.rahal.example/v1/packages/{package_ref}
Response 200:
{
  "package_ref": "RHL-PKG-55021",
  "office_ref": "RHL-OFF-10231",
  "type": "umrah",
  "title": "عمرة رمضان - 15 يوم",
  "description": "...",
  "departure_date": "2026-03-10",
  "return_date": "2026-03-25",
  "departure_city": "صنعاء",
  "hotels": [ { "city": "مكة", "name": "...", "distance_m": 300, "nights": 7 } ],
  "transport": "طيران مباشر",
  "net_cost_per_seat": 1200.00,          // التكلفة الصافية (سرية - أساس الحساب)
  "currency": "USD",
  "total_seats": 40,
  "available_seats": 28,                  // ← حقل حرج لتزامن المخزون
  "included_services": ["...", "..."],
  "images": ["https://...", "..."],
  "updated_at": "2026-06-01T10:00:00Z"
}
```

### 1.3 الـ Webhooks المطلوبة من "رحال" (Rahal → Meraaj)

يرسل رحال هذه الأحداث فوراً إلى نقطة استقبال موحدة في معراج مع توقيع HMAC في الترويسة `X-Rahal-Signature`.

**نقطة الاستقبال في معراج (سيوفرها فريق معراج — انظر القسم الثاني):**
`POST https://api.meraaj.network/api/integrations/rahal/webhooks`

الأحداث المطلوبة:

| # | الحدث (event) | الغرض | الحمولة الأساسية |
|---|---|---|---|
| W1 | `inventory.updated` | تحديث المقاعد المتاحة عند أي حجز/إلغاء داخل رحال (تجنّب Overbooking) | `package_ref`, `available_seats`, `updated_at` |
| W2 | `package.updated` | تعديل سعر/تفاصيل/تواريخ الباكج | `package_ref`, الحقول المتغيرة |
| W3 | `package.deactivated` | إيقاف/حذف الباكج → إخفاؤه من سوق معراج | `package_ref`, `reason` |
| W4 | `booking.status_changed` | تغيّر حالة حجز داخل رحال (إن وُجد) | `booking_ref`, `status` |
| W5 | `office.status_changed` | تعليق/تفعيل المكتب في رحال | `office_ref`, `status` |

**مثال حمولة W1 (الأهم لمنع البيع المزدوج):**
```
POST /api/integrations/rahal/webhooks
Headers:
  X-Rahal-Signature: sha256=<hmac>
  Content-Type: application/json
Body:
{
  "event": "inventory.updated",
  "event_id": "evt_9f2c...",              // للـ idempotency
  "package_ref": "RHL-PKG-55021",
  "available_seats": 25,
  "occurred_at": "2026-06-01T10:05:22Z"
}
```
**المتوقع من رحال:** إعادة المحاولة (Retry مع Exponential Backoff) إذا لم يستلم `200 OK` خلال 10 ثوانٍ.

---

# القسم الثاني: ما ستوفره "معراج" لـ "رحال"
## (Endpoints & Components that Meraaj will provide)

### 2.1 نقطة استقبال مشاركة الباكج (Share Button Endpoint)

عند ضغط المكتب على زر "مشاركة إلى معراج نتورك" داخل رحال، وبعد أن يُدخل (سعر البيع النهائي + عمولة المكتب المشتري)، يرسل رحال البيانات إلى:

**Endpoint #1 — استقبال/مزامنة الباكج:**
```
POST https://api.meraaj.network/api/integrations/rahal/packages/share
Headers:
  X-Rahal-Api-Key: <shared_secret>
  Content-Type: application/json
Body:
{
  "package_ref": "RHL-PKG-55021",        // مرجع رحال (للربط والمزامنة)
  "office_ref": "RHL-OFF-10231",
  "type": "umrah",
  "title": "عمرة رمضان - 15 يوم",
  "departure_date": "2026-03-10",
  "return_date": "2026-03-25",
  "available_seats": 28,
  "hotels": [ ... ],
  "images": [ ... ],
  "pricing": {
    "net_cost_per_seat": 1200.00,        // التكلفة الصافية (لا تُعرض للمشتري)
    "final_sale_price": 1450.00,         // سعر البيع النهائي للزبون (يحدده البائع)
    "buyer_office_commission": 100.00,   // عمولة المكتب المشتري (يحددها البائع)
    "currency": "USD"
  }
}
Response 201:
{
  "meraaj_package_id": "MRJ-PKG-abc123",
  "status": "listed",
  "market_url": "https://app.meraaj.network/market/MRJ-PKG-abc123"
}
```
**ملاحظة:** معراج تحتسب تلقائياً عمولة المنصة (نسبة مئوية من عمولة المشتري) وتخزّن الربط `package_ref ⇄ meraaj_package_id`.

**Endpoint #2 — تحديث/إلغاء مشاركة باكج:**
```
PUT    https://api.meraaj.network/api/integrations/rahal/packages/{package_ref}   (تحديث السعر/التفاصيل)
DELETE https://api.meraaj.network/api/integrations/rahal/packages/{package_ref}   (إلغاء المشاركة)
```

### 2.2 نقطة استقبال الـ Webhooks من رحال
موضحة في القسم 1.3:
`POST https://api.meraaj.network/api/integrations/rahal/webhooks` (تتحقق من توقيع HMAC).

### 2.3 Webhooks من معراج إلى رحال (Meraaj → Rahal) — لمزامنة المخزون العكسية

عند إتمام حجز في سوق معراج، يجب خصم المقاعد من رحال فوراً. توفّر معراج هذه الأحداث ويجب أن يوفّر رحال نقطة استقبال لها:

**نقطة الاستقبال المطلوبة من رحال:** `POST https://api.rahal.example/v1/webhooks/meraaj`

| # | الحدث | الغرض | الحمولة |
|---|---|---|---|
| M1 | `meraaj.booking.created` | خصم مقاعد من رحال عند حجز في معراج | `package_ref`, `seats_booked`, `available_seats_now` |
| M2 | `meraaj.booking.cancelled` | إرجاع المقاعد عند إلغاء الحجز | `package_ref`, `seats_released` |
| M3 | `meraaj.booking.status_changed` | مزامنة الحالة (أزرق/أصفر/أخضر) | `package_ref`, `booking_id`, `status` |

### 2.4 آلية عرض السوق داخل رحال (Embedded Marketplace)

**القرار الهندسي المعتمد: نوفّر Iframe URL موقّع (Signed Iframe) — وليس Component.**

**السبب:** يفصل قواعد النظامين، ولا يفرض على رحال إطار عمل React، ويضمن أن منطق المحفظة/الضمان يبقى داخل معراج بأمان، ويسهّل التحديثات دون نشر جديد من طرف رحال.

```
https://app.meraaj.network/embed/market?token=<signed_jwt>&office_ref=RHL-OFF-10231&lang=ar
```
- الـ `token` هو JWT موقّع من رحال (بنفس السر المشترك) يحوي `office_ref` وصلاحية زمنية.
- يدعم الـ iframe الاتصال عبر `postMessage` لإعلام رحال بأحداث (فتح باكج، إتمام حجز، تغيير ارتفاع الإطار).
- اتجاه RTL ولغة عربية افتراضياً.

**(اختياري مستقبلاً):** توفير Web Component / SDK مبسّط `<meraaj-market>` يغلّف الـ iframe إذا رغب فريق رحال بذلك.

---

## 3. ملخص جدول المسؤوليات

| البند | يوفّره رحال | يوفّره معراج |
|---|---|---|
| SSO Token Exchange | ✅ API #1, #2 | يستهلكه |
| بيانات الباكجات | ✅ API #3, #4 | يستهلكه |
| Webhooks المخزون (رحال→معراج) | ✅ W1–W5 (إرسال) | ✅ نقطة استقبال + HMAC |
| Endpoint مشاركة الباكج | يرسل إليه | ✅ Endpoint #1, #2 |
| Webhooks المخزون العكسي (معراج→رحال) | ✅ نقطة استقبال | ✅ M1–M3 (إرسال) |
| عرض السوق | يضمّن الـ iframe | ✅ Signed Iframe URL |

## 4. الأمان (Security Checklist)
- API Keys مشتركة تُخزّن كـ Environment Variables (لا تُكتب في الكود).
- كل Webhook موقّع بـ HMAC-SHA256 ويُتحقق منه قبل المعالجة.
- كل حدث يحمل `event_id` لمنع المعالجة المكررة (Idempotency).
- صلاحية رموز SSO قصيرة (≤ 5 دقائق للـ code، ≤ 60 دقيقة للـ access_token).
- تسجيل كامل (Audit Log) لكل عملية مالية أو تغيير مخزون.

---

**الخلاصة للبدء:** فريق رحال يبدأ فوراً بتجهيز (SSO API #1/#2، Package API #3/#4، وإرسال Webhooks W1–W5). وفريق معراج يجهّز (Endpoints المشاركة #1/#2، نقطة استقبال الـ Webhooks، Signed Iframe URL، وإرسال Webhooks M1–M3).
