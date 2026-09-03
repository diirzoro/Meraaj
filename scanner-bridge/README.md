# Meraaj Scan Bridge — Proof of Concept (Windows)

## لماذا نحتاج خدمة محلية؟
لا يوجد متصفح يستطيع الوصول مباشرةً إلى بروتوكولات الماسحات الضوئية (TWAIN / WIA).
`<input type="file" capture="environment">` هو رفع ملف أو كاميرا جوال — وعلى Windows يتجاهله
المتصفح ويفتح File Browser. ولذلك الحل الوحيد الموثوق هو خدمة محلية صغيرة على جهاز الموظف
تتحدث مع المتصفح عبر `https://127.0.0.1:8787`.

## العقد (Contract) الذي تتوقعه واجهة معراج
| الطلب | الوصف | الاستجابة |
|---|---|---|
| `GET /api/scanners` | قائمة الأجهزة المتصلة | `{"devices":[{"id":"wia:0","name":"Canon LiDE 400","duplex":false,"dpi":[150,300,600]}]}` |
| `POST /api/scan` | بدء المسح | `{"pages":[{"page":1,"content_base64":"...","mime":"image/jpeg"}]}` |
| `POST /api/scan/pdf` | دمج الصفحات في PDF | `{"filename":"scan.pdf","content_base64":"..."}` |

خيارات `POST /api/scan`: `device_id`, `dpi`, `color` (`color|gray|bw`), `paper` (`A4|Letter`),
`duplex` (bool), `pages` (multi-page).

## نموذج مرجعي (Python + WIA على Windows)
```python
# pip install pywin32 flask pillow
import base64, io, win32com.client
from flask import Flask, jsonify, request
app = Flask(__name__)
ALLOWED_ORIGIN = "https://<meraaj-domain>"   # لا يُسمح لأي موقع آخر

def _cors(r):
    r.headers["Access-Control-Allow-Origin"] = ALLOWED_ORIGIN
    return r

@app.get("/api/scanners")
def scanners():
    mgr = win32com.client.Dispatch("WIA.DeviceManager")
    out = []
    for i in range(1, mgr.DeviceInfos.Count + 1):
        d = mgr.DeviceInfos(i)
        if d.Type == 1:  # Scanner
            out.append({"id": f"wia:{i}", "name": d.Properties("Name").Value})
    return _cors(jsonify({"devices": out}))

@app.post("/api/scan")
def scan():
    body = request.get_json() or {}
    idx = int(str(body.get("device_id", "wia:1")).split(":")[1])
    mgr = win32com.client.Dispatch("WIA.DeviceManager")
    dev = mgr.DeviceInfos(idx).Connect()
    img = dev.Items(1).Transfer()          # DPI/color/duplex تُضبط عبر WIA properties
    data = bytes(img.FileData.BinaryData)
    return _cors(jsonify({"pages": [{"page": 1, "mime": "image/jpeg",
                                     "content_base64": base64.b64encode(data).decode()}]}))

if __name__ == "__main__":
    # شهادة محلية موقّعة ذاتياً مثبّتة في متجر الجهاز
    app.run(host="127.0.0.1", port=8787, ssl_context=("cert.pem", "key.pem"))
```

## الأمان
- الاستماع على `127.0.0.1` فقط (لا يُسمح بالوصول من الشبكة).
- CORS مقيَّد بنطاق معراج، مع رمز اقتران لمرة واحدة يُخزَّن في الخدمة وفي المتصفح.
- بلا صلاحية قراءة القرص: الخدمة تُصدر الصفحات الممسوحة فقط.
- الملف الناتج يُرفع عبر واجهة معراج نفسها (نفس التحقق: 10MB/ملف، 20MB/دفعة، أنواع مسموحة)،
  ويُسجَّل في `traveler_documents` مرتبطاً بالطلب والمسافر ونوع المستند، مع Audit Log.

## متطلبات التثبيت
مُثبّت MSI صغير مرة واحدة على أجهزة الموظفين (Windows 10/11). لا شيء على الجوال (تُستخدم الكاميرا).

## حالة النموذج الآن
- زر «مسح من Scanner» موجود في واجهة المستندات ويستكشف الخدمة فعلياً على `127.0.0.1:8787`.
- عند عدم وجود الخدمة/الجهاز تظهر رسالة عربية واضحة مع بقاء «رفع ملف» و«تصوير بالكاميرا» كما هما.
- المتبقي لإكمال PoC: بناء خدمة Windows فعلية بالكود أعلاه واختبارها على جهاز به ماسح،
  ثم تفعيل الراية `scanner_bridge` من مركز الإعدادات.
