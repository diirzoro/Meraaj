# معراج نتورك — دليل بناء تطبيق أندرويد (Capacitor)

نسخة الأندرويد جاهزة داخل المشروع (المرحلة 1: القشرة الأصلية). البناء النهائي (APK/AAB)
يتم على جهازك لأن بيئة الخادم لا تحتوي على Android SDK.

## المتطلبات على جهازك
- Node.js ‏18 أو 20 (الحزم مثبّتة على إصدار Capacitor **v7**)
- Android Studio + Android SDK (Platform API 24+)
- Java JDK 17

## خطوات البناء
```bash
cd frontend
yarn install
yarn build              # يبني ملفات الويب في مجلد build/
npx cap sync android    # ينسخ build/ إلى مشروع أندرويد ويحدّث الإضافات
npx cap open android    # يفتح المشروع في Android Studio
```
ثم من Android Studio: اختر جهازاً/محاكياً واضغط Run.

### بناء APK للتجربة عبر الطرفية
```bash
cd frontend/android
./gradlew assembleDebug
# الناتج: android/app/build/outputs/apk/debug/app-debug.apk
```

### بناء نسخة إصدار للمتجر (AAB)
```bash
cd frontend/android
./gradlew bundleRelease   # يتطلب إعداد توقيع (keystore) في Android Studio
```

## ما تم إعداده في المرحلة 1
- **appId:** `network.meraaj.app` — **اسم التطبيق:** «معراج نتورك»
- **زر الرجوع (Back):** يتنقّل صفحة-بصفحة عبر React Router؛ في الصفحة الرئيسية يطلب ضغطة ثانية خلال 1.8 ثانية للخروج (`src/native/useAndroidBackButton.js`).
- **شريط الحالة + شاشة كاملة:** شريط حالة كحلي (#0A2540) بأيقونات فاتحة، إخفاء السبلاش بعد تجهيز الواجهة (`src/native/useNativeChrome.js`).
- **سلاسة اللمس:** إلغاء وميض اللمس، `touch-action: manipulation` (إزالة تأخير 300ms)، منع الارتداد الزائد (overscroll)، منع تحديد النص إلا في الحقول، ودعم `safe-area` (index.css + الكلاس `cap-native`).
- **الأيقونة وشاشة البداية:** مولّدة من `assets/icon-only.png` و`assets/splash.png` (بالهوية الكحلي/الذهبي). لإعادة التوليد: `npx capacitor-assets generate --android`.
- كل الكود الأصلي محميّ بـ `Capacitor.isNativePlatform()` فلا يؤثّر إطلاقاً على نسخة الويب.

## ملاحظات
- التطبيق يستدعي الـ backend عبر `REACT_APP_BACKEND_URL` (HTTPS). لا تضع أي أسرار في الواجهة.
- المراحل القادمة: إشعارات Firebase FCM (تحتاج مشروع Firebase + `google-services.json`) وتحديثات OTA عبر Capgo (تحتاج حساب Capgo + مفتاح).
