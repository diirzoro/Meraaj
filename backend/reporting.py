"""Single source of truth for every report export.

Screen, PDF, Excel and CSV all call `build_dataset()` — the numbers, filters, labels and
status mapping are computed ONCE here, so no exporter can ever produce a different figure.
Read-only: nothing in this module writes to the database.
"""
import csv
import io
import os
from datetime import datetime, timezone

CCY_AR = {"SAR": "ريال سعودي", "USD": "دولار أمريكي", "YER": "ريال يمني"}

# Internal code → Arabic label shown to users (DB values are never changed).
VALUE_LABELS = {
    # booking status
    "active": "نشط", "cancelled": "ملغي", "completed": "مكتمل", "pending": "قيد الانتظار",
    "requested": "مطلوب", "approved": "معتمد", "rejected": "مرفوض", "expired": "منتهي",
    "legacy": "قديم (قبل نظام الموافقات)", "draft": "مسودة", "listed": "معروض",
    "archived": "مؤرشف", "suspended": "موقوف", "paid": "مدفوع", "closed": "مغلق",
    "under_review": "قيد المراجعة", "approved_internal": "اعتماد داخلي",
    "sent_to_accounting": "أُحيل للمحاسبة", "executed": "منفّذ",
    # program lifecycle colours used by the marketplace
    "blue": "قيد التسجيل", "yellow": "صدرت التأشيرات", "green": "تم التفويج",
    # roles
    "office": "مكتب", "individual": "فرد", "marketer": "مسوّق", "staff": "موظف",
    "super_admin": "الإدارة العليا", "admin": "إدارة",
    # sources / misc
    "rahal": "رحّال", "meraaj": "معراج", "manual": "يدوي", "uploaded": "مستوردة",
    "success": "ناجحة", "failed": "فاشلة", "valid": "سليمة", "invalid": "غير سليمة",
    "percent": "نسبة", "fixed": "قيمة ثابتة", "true": "نعم", "false": "لا",
    "delivered": "مُسلَّم",
    "pending_approval": "بانتظار الاعتماد", "paused": "موقوف مؤقتاً",
    "ad": "إعلان", "promotion": "عرض ترويجي", "preview": "بيئة المعاينة",
    "test": "بيئة الاختبار", "live": "البيئة الحقيقية", "unknown": "غير محددة",
}

# Common technical field names → Arabic, used by the audit-log human view.
FIELD_LABELS = {
    "status": "الحالة", "title": "العنوان", "amount": "المبلغ", "currency": "العملة",
    "limit": "السقف", "email": "البريد", "role": "الدور", "reason": "السبب",
    "file": "الملف", "result": "النتيجة", "integrity": "سلامة الملف",
    "encrypted": "مشفّر", "destination": "الوجهة", "webhook_url": "عنوان الـWebhook",
    "ledger_total": "مجموع الدفتر", "wallet_total": "رصيد المحفظة", "seats": "المقاعد",
    "http_status": "رمز الاستجابة", "attempts": "المحاولات", "url": "العنوان",
}


def label(value):
    """Arabic label for a raw internal value; the value itself is returned when unknown."""
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "نعم" if value else "لا"
    key = str(value).strip()
    return VALUE_LABELS.get(key, key)


def environment() -> str:
    """Explicit environment. Never guessed: it is read from ENVIRONMENT only."""
    return (os.environ.get("ENVIRONMENT") or "").strip().lower() or "unknown"


def is_test_env() -> bool:
    return environment() in ("test", "staging")


def humanize_rows(columns, rows):
    """Applies the Arabic value mapping to every non-numeric cell, once, for all exporters."""
    out = []
    for r in rows:
        out.append([c if isinstance(c, (int, float)) else label(c) for c in r])
    return out


async def build_dataset(report: str, filters: dict) -> dict:
    """THE dataset. Every export format must use this and nothing else."""
    from enterprise import REPORTS, SNAPSHOT_REPORTS, _run
    if report not in REPORTS:
        from fastapi import HTTPException
        raise HTTPException(400, "تقرير غير معروف")
    res = await _run(report, filters.get("date_from"), filters.get("date_to"),
                     filters.get("currency"), filters.get("office_id"))
    rows = humanize_rows(res["columns"], res["rows"])
    snapshot = report in SNAPSHOT_REPORTS
    generated = datetime.now(timezone.utc)
    return {
        "report": report,
        "title": REPORTS[report],
        "columns": res["columns"],
        "rows": rows,
        "row_count": len(rows),
        "snapshot": snapshot,
        "filters": {**filters, "date_inclusive": True},
        "filters_label": filters_label(filters),
        "currency_label": CCY_AR.get(filters.get("currency") or "", "جميع العملات"),
        "generated_at": generated.isoformat(),
        "report_no": f"MRJ-RPT-{generated.strftime('%Y%m%d-%H%M%S')}",
        "environment": environment(),
        "period_note": ("تقرير لحظي يعرض الحالة الحالية (الأرصدة/السقوف/الانكشاف) — "
                        "فلتر التاريخ لا ينطبق عليه" if snapshot else
                        "الفترة شاملة لليومين المحددين (من بداية يوم البداية حتى نهاية "
                        "يوم النهاية)"),
    }


def filters_label(f: dict) -> str:
    parts = []
    if f.get("date_from") or f.get("date_to"):
        parts.append(f"الفترة: {f.get('date_from') or 'البداية'} ← {f.get('date_to') or 'اليوم'}")
    else:
        parts.append("الفترة: كل التواريخ")
    parts.append(f"العملة: {CCY_AR.get(f.get('currency') or '', 'جميع العملات')}")
    if f.get("office_id"):
        parts.append("مقيّد بمؤسسة محددة")
    return " • ".join(parts)


def summary_rows(ds: dict) -> list:
    """Numeric totals per numeric column — the same figures the screen shows.
    Rows that are themselves a totals row are skipped so nothing is counted twice."""
    cols = ds["columns"]
    rows = [r for r in ds["rows"] if "إجمالي" not in [str(c) for c in r]]
    out = []
    for i, c in enumerate(cols):
        vals = [r[i] for r in rows if isinstance(r[i], (int, float))]
        if len(vals) >= 2 and any(v for v in vals):
            out.append([c, round(sum(vals), 2)])
    return out


def to_csv(ds: dict) -> bytes:
    """Data export only: UTF-8 BOM, Arabic headers, raw numbers, no formatting."""
    buf = io.StringIO()
    buf.write("\ufeff")
    w = csv.writer(buf)
    w.writerow(ds["columns"])
    for r in ds["rows"]:
        w.writerow(["" if c is None else c for c in r])
    return buf.getvalue().encode("utf-8")


def to_xlsx(ds: dict) -> bytes:
    """Real workbook: summary + details + data dictionary, RTL, frozen header, filters."""
    import xlsxwriter
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True})
    brand = wb.add_format({"bold": True, "font_size": 15, "font_color": "#0A2540",
                           "align": "right", "reading_order": 2})
    h2 = wb.add_format({"bold": True, "font_size": 11, "font_color": "#0A2540",
                        "align": "right", "reading_order": 2})
    txt = wb.add_format({"align": "right", "reading_order": 2, "font_size": 10})
    head = wb.add_format({"bold": True, "bg_color": "#0A2540", "font_color": "white",
                          "align": "right", "reading_order": 2, "border": 1, "font_size": 10})
    num = wb.add_format({"num_format": "#,##0.00", "align": "right", "font_size": 10})
    tot = wb.add_format({"bold": True, "num_format": "#,##0.00", "align": "right",
                         "bg_color": "#F0FDF4", "font_size": 10})
    totlbl = wb.add_format({"bold": True, "align": "right", "reading_order": 2,
                            "bg_color": "#F0FDF4", "font_size": 10})

    s = wb.add_worksheet("الملخص")
    s.right_to_left()
    s.set_column(0, 0, 34)
    s.set_column(1, 1, 60)
    s.write(0, 0, "شبكة معراج — Meraaj Network / Target Media", brand)
    meta = [("اسم التقرير", ds["title"]), ("رقم التقرير", ds["report_no"]),
            ("الفلاتر", ds["filters_label"]), ("العملة", ds["currency_label"]),
            ("عدد السجلات", ds["row_count"]),
            ("تاريخ الإنشاء", ds["generated_at"][:19].replace("T", " ")),
            ("البيئة", ds["environment"]), ("ملاحظة الفترة", ds["period_note"])]
    for i, (k, v) in enumerate(meta, start=2):
        s.write(i, 0, k, h2)
        s.write(i, 1, v, txt)
    srow = len(meta) + 4
    s.write(srow, 0, "ملخص مالي (مجاميع الأعمدة الرقمية)", h2)
    for i, (k, v) in enumerate(summary_rows(ds), start=srow + 1):
        s.write(i, 0, k, totlbl)
        s.write_number(i, 1, v, tot)

    d = wb.add_worksheet("التفاصيل")
    d.right_to_left()
    d.freeze_panes(1, 0)
    for j, c in enumerate(ds["columns"]):
        d.write(0, j, c, head)
        d.set_column(j, j, max(12, min(34, len(str(c)) + 10)))
    for i, r in enumerate(ds["rows"], start=1):
        for j, c in enumerate(r):
            if isinstance(c, (int, float)):
                d.write_number(i, j, c, num)
            else:
                d.write(i, j, "" if c is None else str(c), txt)
    if ds["rows"]:
        d.autofilter(0, 0, len(ds["rows"]), len(ds["columns"]) - 1)

    g = wb.add_worksheet("قاموس البيانات")
    g.right_to_left()
    g.set_column(0, 0, 30)
    g.set_column(1, 1, 70)
    g.write(0, 0, "العمود", head)
    g.write(0, 1, "المعنى", head)
    for i, c in enumerate(ds["columns"], start=1):
        g.write(i, 0, c, txt)
        g.write(i, 1, DATA_DICTIONARY.get(c, "قيمة كما تظهر في الشاشة ونفس مصدر الحساب"), txt)
    wb.close()
    return buf.getvalue()


DATA_DICTIONARY = {
    "المدفوع": "ما خرج فعلياً من محفظة المشتري لهذا الطلب",
    "المعلّق": "إيراد البائع المحجوز ولم يُحرَّر بعد",
    "المحرَّر": "ما حُرِّر للبائع فعلياً",
    "المسترد": "ما أُعيد للمشتري",
    "عمولة المنصة": "عمولة معراج المسجّلة على الطلب وقت التسعير",
    "صافي المنصة": "عمولة المنصة بعد خصم عمولة المسوّق",
    "المستحق على المشتري": "الفرق بين قيمة الطلب وما دُفع فعلياً",
    "المستحق للبائع": "صافي البائع ناقص ما حُرِّر وما خُصم",
    "المحوَّل": "المبلغ المحوّل للبائع فعلياً",
    "المتبقي": "ما زال محتجزاً في الضمان",
    "مدين (خصم)": "مجموع الحركات السالبة للطلب",
    "دائن (استرداد)": "مجموع الحركات الموجبة للطلب",
    "العملة": "عملة الطلب (رمز قياسي مع اسمها العربي في العرض)",
}
