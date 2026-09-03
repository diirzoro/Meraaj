"""Arabic RTL PDF generation (reports + vouchers) using reportlab with proper
shaping and bidi reordering. Fonts are taken from the system (FreeSans has Arabic coverage).
"""
import glob
import io

import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

FONT = "MeraajAr"
_registered = False


def _font_path():
    for pat in ("/usr/share/fonts/**/Amiri-Regular.ttf", "/usr/share/fonts/**/NotoNaskh*.ttf",
                "/usr/share/fonts/**/*Arabic*.ttf", "/usr/share/fonts/**/FreeSans.ttf"):
        hits = glob.glob(pat, recursive=True)
        if hits:
            return hits[0]
    raise RuntimeError("لا يوجد خط عربي مثبّت على الخادم")


def _ensure_font():
    global _registered
    if not _registered:
        pdfmetrics.registerFont(TTFont(FONT, _font_path()))
        _registered = True


def ar(text) -> str:
    """Shape + bidi-reorder so Arabic renders connected and right-to-left in the PDF."""
    s = "" if text is None else str(text)
    if not s:
        return ""
    try:
        return get_display(arabic_reshaper.reshape(s))
    except Exception:
        return s


def build_table_pdf(title: str, columns: list, rows: list, meta: str = "") -> bytes:
    _ensure_font()
    buf = io.BytesIO()
    wide = len(columns) > 6
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4) if wide else A4,
                            rightMargin=12 * mm, leftMargin=12 * mm,
                            topMargin=14 * mm, bottomMargin=12 * mm)
    h = ParagraphStyle("h", fontName=FONT, fontSize=15, alignment=2, leading=20,
                       textColor=colors.HexColor("#0A2540"))
    sub = ParagraphStyle("s", fontName=FONT, fontSize=8.5, alignment=2, leading=12,
                         textColor=colors.HexColor("#64748B"))
    story = [Paragraph(ar(title), h)]
    if meta:
        story.append(Paragraph(ar(meta), sub))
    story.append(Spacer(1, 6 * mm))

    head = [ar(c) for c in reversed(columns)]
    data = [head] + [[ar(c) for c in reversed(r)] for r in rows[:400]]
    t = Table(data, repeatRows=1, hAlign="RIGHT")
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0A2540")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E2E8F0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F6F8")]),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(t)
    if len(rows) > 400:
        story.append(Spacer(1, 4 * mm))
        story.append(Paragraph(ar(f"معروض 400 من {len(rows)} سجل — استخدم تصدير Excel للكل"), sub))
    doc.build(story)
    return buf.getvalue()


def build_report_pdf(ds: dict) -> bytes:
    """Official Meraaj report: brand header, report identity, financial summary, RTL table,
    page numbers, footer and a TEST watermark in the test environment.
    All numbers come from the shared dataset — nothing is recomputed here."""
    from reportlab.lib.pagesizes import A4 as _A4
    _ensure_font()
    buf = io.BytesIO()
    wide = len(ds["columns"]) > 6
    size = landscape(_A4) if wide else _A4
    doc = SimpleDocTemplate(buf, pagesize=size, rightMargin=12 * mm, leftMargin=12 * mm,
                            topMargin=26 * mm, bottomMargin=16 * mm,
                            title=ds["title"], author="Meraaj Network")
    h = ParagraphStyle("h", fontName=FONT, fontSize=14, alignment=2, leading=19,
                       textColor=colors.HexColor("#0A2540"))
    sub = ParagraphStyle("s", fontName=FONT, fontSize=8.5, alignment=2, leading=12,
                         textColor=colors.HexColor("#64748B"))
    story = [Paragraph(ar(ds["title"]), h),
             Paragraph(ar(f"رقم التقرير: {ds['report_no']} • {ds['filters_label']} • "
                          f"عدد السجلات: {ds['row_count']} • "
                          f"تاريخ الإنشاء: {ds['generated_at'][:19].replace('T', ' ')}"), sub),
             Paragraph(ar(ds["period_note"]), sub), Spacer(1, 5 * mm)]

    summary = ds.get("summary") or []
    if summary:
        story.append(Paragraph(ar("الملخص المالي"), sub))
        st = Table([[ar(f"{v:,.2f}"), ar(str(k))] for k, v in summary],
                   colWidths=[45 * mm, 75 * mm], hAlign="RIGHT")
        st.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), FONT), ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
            ("BACKGROUND", (1, 0), (1, -1), colors.HexColor("#F4F6F8")),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E2E8F0")),
        ]))
        story += [st, Spacer(1, 5 * mm)]

    head = [ar(c) for c in reversed(ds["columns"])]
    body = [[ar(f"{c:,.2f}") if isinstance(c, float) else ar(c)
             for c in reversed(r)] for r in ds["rows"][:400]]
    t = Table([head] + body, repeatRows=1, hAlign="RIGHT")
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0A2540")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E2E8F0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F6F8")]),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(t)
    if len(ds["rows"]) > 400:
        story += [Spacer(1, 4 * mm),
                  Paragraph(ar(f"معروض 400 من {ds['row_count']} سجل — "
                               "استخدم تصدير Excel لكل السجلات"), sub)]

    watermark = str(ds.get("environment", "")).lower() in ("test", "staging")

    def decorate(canvas, _doc):
        canvas.saveState()
        w, hgt = size
        canvas.setFillColor(colors.HexColor("#0A2540"))
        canvas.rect(0, hgt - 18 * mm, w, 18 * mm, stroke=0, fill=1)
        canvas.setFillColor(colors.white)
        canvas.setFont(FONT, 11)
        canvas.drawRightString(w - 12 * mm, hgt - 9 * mm,
                               ar("شبكة معراج — Meraaj Network"))
        canvas.setFillColor(colors.HexColor("#D4AF37"))
        canvas.setFont(FONT, 8)
        canvas.drawRightString(w - 12 * mm, hgt - 14.5 * mm, ar("Target Media — تارجت ميديا"))
        canvas.setFillColor(colors.HexColor("#D4AF37"))
        canvas.circle(16 * mm, hgt - 9 * mm, 5 * mm, stroke=0, fill=1)
        canvas.setFillColor(colors.HexColor("#0A2540"))
        canvas.setFont(FONT, 10)
        canvas.drawCentredString(16 * mm, hgt - 11 * mm, ar("م"))
        canvas.setFillColor(colors.HexColor("#64748B"))
        canvas.setFont(FONT, 7.5)
        canvas.drawRightString(w - 12 * mm, 9 * mm,
                               ar("تقرير رسمي صادر من نظام معراج نتورك — للاستخدام الداخلي"))
        canvas.drawString(12 * mm, 9 * mm, ar(f"صفحة {canvas.getPageNumber()}"))
        if watermark:
            canvas.saveState()
            canvas.setFont(FONT, 58)
            canvas.setFillColor(colors.Color(0.72, 0.11, 0.11, alpha=0.12))
            canvas.translate(w / 2, hgt / 2)
            canvas.rotate(32)
            canvas.drawCentredString(0, 0, "TEST ENVIRONMENT")
            canvas.restoreState()
        canvas.restoreState()

    doc.build(story, onFirstPage=decorate, onLaterPages=decorate)
    return buf.getvalue()


def build_voucher_pdf(v: dict) -> bytes:
    _ensure_font()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
                            topMargin=20 * mm, bottomMargin=18 * mm)
    h = ParagraphStyle("h", fontName=FONT, fontSize=17, alignment=2, leading=24,
                       textColor=colors.HexColor("#0A2540"))
    sub = ParagraphStyle("s", fontName=FONT, fontSize=9, alignment=2, leading=13,
                         textColor=colors.HexColor("#64748B"))
    story = [Paragraph(ar("شبكة معراج — Meraaj Network"), h),
             Paragraph(ar(f"{v.get('kind_label')} رقم {v.get('voucher_no')}"), sub),
             Spacer(1, 8 * mm)]
    pairs = [
        ("التاريخ", str(v.get("date"))[:19]), ("الطرف", (v.get("party") or {}).get("name")),
        ("البريد", (v.get("party") or {}).get("email")),
        ("الهاتف", (v.get("party") or {}).get("phone")),
        ("نوع الحركة", v.get("type_label")), ("البيان", v.get("description")),
        ("المرجع", v.get("ref") or "—"),
        ("المبلغ", f"{v.get('amount')} {v.get('currency')}"),
        ("أصدره", v.get("issued_by")), ("وقت الإصدار", str(v.get("issued_at"))[:19]),
    ]
    data = [[ar(str(val)), ar(k)] for k, val in pairs]
    t = Table(data, colWidths=[110 * mm, 45 * mm], hAlign="RIGHT")
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), FONT), ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("BACKGROUND", (1, 0), (1, -1), colors.HexColor("#F4F6F8")),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E2E8F0")),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story += [t, Spacer(1, 14 * mm),
              Paragraph(ar("التوقيع: ____________________     الختم: ____________________"), sub)]
    doc.build(story)
    return buf.getvalue()
