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
