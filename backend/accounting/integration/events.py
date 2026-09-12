"""FINANCIAL EVENT MAP — which business moments carry an accounting effect, and which do not.

TRACEABILITY
  event map            ← Rahaal per-route ad-hoc journal building        ADAPT (declared map)
  status→journal per step ← Rahaal (a journal per status change)          LEAVE (refused)
  source_key builder   ← Rahaal `meraaj_booking_ref` (one key per object) PORT + HARDEN (per EVENT)

NOT EVERY STATUS IS A FINANCIAL EVENT. `pending → approved → executed` produces ONE effect,
at the moment the money actually moves. Events declared here with `posts_journal=False`
exist precisely so that "no journal" is a documented decision instead of an omission.
"""
from dataclasses import dataclass, field
from typing import Optional, Tuple

PRODUCER = "meraaj"


@dataclass(frozen=True)
class EventSpec:
    event: str
    label_ar: str
    business_object: str
    trigger: str
    posts_journal: bool
    links: Tuple[str, ...] = field(default_factory=tuple)
    note: str = ""
    implemented: bool = False


def build_source_key(entity_id: str, business_object: str, event: str,
                     event_id: str, producer: str = PRODUCER) -> str:
    """`{producer}:{entity_id}:{business_object}:{financial_event}:{event_id}`

    Deterministic and stable: built only from identifiers that already exist on the
    business document. No `now()`, no `uuid4()`, no attempt counter — so a retry produces
    the SAME key and the posting gateway replays instead of duplicating.
    """
    for name, value in (("business_object", business_object), ("event", event),
                        ("event_id", event_id), ("entity_id", entity_id)):
        if not value or not str(value).strip():
            raise ValueError(f"source_key segment '{name}' is required")
    return ":".join([producer, str(entity_id).strip(), str(business_object).strip(),
                     str(event).strip(), str(event_id).strip()])


_E = EventSpec
FINANCIAL_EVENTS = {e.event: e for e in (
    # ---------------------------------------------------------------- implemented (P1)
    _E("wallet_topup", "شحن محفظة المكتب", "topup",
       "admin approves the topup (money received) — NOT at request creation", True,
       (("cash", "office_wallet_liability")), implemented=True,
       note="مدين نقدية/بنك · دائن التزام المحفظة — الشحن ليس إيراداً"),
    _E("wallet_withdrawal", "سحب من محفظة المكتب", "withdrawal",
       "admin approves the withdrawal (money paid out)", True,
       (("office_wallet_liability", "cash")), implemented=True,
       note="مدين التزام المحفظة · دائن نقدية/بنك — تخفيض التزام لا مصروف"),
    _E("b2b_transfer", "تحويل بين مكتبين", "transfer",
       "admin approves the transfer", True,
       (("office_wallet_liability",)), implemented=True,
       note="نقل التزام بين طرفين داخل نفس حساب الالتزام — لا إيراد ولا مصروف؛ "
            "القيد يوثّق الحركة بمرجع واحد ورصيد الالتزام الكلي لا يتغير"),
    # ------------------------------------------------------------- declared, next phase
    _E("booking_debit", "خصم حجز من المشتري", "booking",
       "buyer confirms a booking (wallet debited, seller amount held)", True,
       (("office_wallet_liability", "seller_payable", "deferred_platform_revenue")),
       implemented=True,
       note="PD-1: مدين التزام المشتري · دائن مستحقات البائع · دائن إيراد مؤجّل "
            "لحصة المنصة — لا إيراد نهائي عند الحجز"),
    _E("booking_settlement", "تسوية حجز + استحقاق حصة المنصة", "booking",
       "settlement/earning point — deferred share becomes revenue", True,
       (("seller_payable", "office_wallet_liability", "commission_revenue",
         "deferred_platform_revenue")), implemented=True,
       note="PD-1A: الإيراد المؤجّل → إيراد؛ وعمولة جانب البائع تُعترف هنا؛ وعمولة "
            "المسوّق تُحرَّر كالتزام له"),
    _E("booking_cancel_blue", "إلغاء أزرق (استرداد شبه كامل)", "booking",
       "blue cancellation executed", True,
       (("seller_payable", "office_wallet_liability", "deferred_platform_revenue",
         "cancellation_fee_revenue")), implemented=True,
       note="PD-3/PD-5A: الإيراد المؤجّل يُفرَج عنه (لا إيراد سالب)، ورسوم الإلغاء "
            "إيراد مستحق"),
    _E("booking_cancel_yellow", "إلغاء أصفر (خصم مقسوم)", "booking",
       "yellow cancellation accepted by the buyer", True,
       (("seller_payable", "office_wallet_liability", "deferred_platform_revenue",
         "cancellation_fee_revenue")), implemented=True,
       note="PD-5: platform_cut إيراد إلغاء للمنصة · seller_keeps مستحق للبائع · "
            "الباقي يعود للمشتري والإيراد المؤجّل يُفرَج عنه"),
    _E("ads_capture", "تحصيل إعلان", "ad",
       "ad price CAPTURED (admin approval) — the ONLY ads revenue moment", True,
       (("office_wallet_liability", "ads_revenue")), implemented=True,
       note="PD-4A/PD-4D: اعتراف واحد عند التحصيل، بلا اعتراف زمني وبلا استرداد تلقائي"),
    _E("ads_refund", "استرداد إعلان بعد التحصيل", "ad",
       "explicit admin-approved refund after capture (never automatic)", True,
       (("ads_revenue", "office_wallet_liability")),
       note="PD-4B/PD-4C: يدوي بقرار إداري صريح بمبلغ محدد — لا يُنفَّذ آلياً"),
    _E("marketer_commission", "عمولة مسوّق", "booking",
       "commission granted/released to the marketer", True,
       (("seller_payable", "office_wallet_liability"))),
    _E("booking_cancel_refund", "استرداد إلغاء", "booking",
       "cancellation refund executed", False,
       (),
       note="مغطى بـ booking_cancel_blue / booking_cancel_yellow"),
    _E("dispute_resolution", "تسوية نزاع", "booking",
       "admin resolves a dispute (refund buyer or release seller)", True,
       (("seller_payable", "office_wallet_liability", "commission_revenue"))),
    _E("ads_capture", "تحصيل إعلان", "ad",
       "ad price CAPTURED (service consumed) — the ONLY ads revenue moment", True,
       (("office_wallet_liability", "ads_revenue")),
       note="الإيراد عند التحصيل فقط"),
    _E("finance_adjustment", "تسوية مالية إدارية", "adjustment",
       "admin posts a reconciliation adjustment", True,
       (("office_wallet_liability", "adjustment_expense"))),
    # ------------------------------------------------ explicitly NO journal (documented)
    _E("ads_hold", "تجنيب مبلغ إعلان", "ad",
       "ad price moved available → pending inside the SAME wallet", False, (),
       note="لا قيد: تجنيب داخلي في نفس الالتزام ولا يغيّر الأصول ولا الالتزامات"),
    _E("ads_release", "فك تجنيب إعلان", "ad",
       "ad hold released back to available", False, (),
       note="لا قيد: عكس تجنيب داخلي"),
    _E("booking_escrow", "إيراد معلّق للبائع", "booking",
       "seller amount moved into pending", False, (),
       note="لا قيد مستقل: مغطى داخل قيد الحجز/التسوية"),
    _E("topup_request", "طلب شحن", "topup", "office submits a topup request", False, (),
       note="لا قيد: طلب وليس حركة مالية"),
    _E("withdrawal_request", "طلب سحب", "withdrawal",
       "office submits a withdrawal request", False, (),
       note="لا قيد: طلب وليس حركة مالية"),
    _E("credit_ceiling_change", "تعديل السقف الائتماني", "office",
       "admin changes a credit ceiling", False, (),
       note="لا قيد: حدّ تسهيل وليس حركة مالية"),
)}


def spec(event: str) -> Optional[EventSpec]:
    return FINANCIAL_EVENTS.get(event)


def event_map_public() -> dict:
    return {
        "producer": PRODUCER,
        "source_key_shape": "{producer}:{entity_id}:{business_object}:"
                            "{financial_event}:{event_id}",
        "rule": "one financial EFFECT = one stable key; the same business object with "
                "several effects yields several keys",
        "events": [{"event": e.event, "label_ar": e.label_ar,
                    "business_object": e.business_object, "trigger": e.trigger,
                    "posts_journal": e.posts_journal, "links": list(e.links),
                    "implemented": e.implemented, "note": e.note}
                   for e in FINANCIAL_EVENTS.values()],
    }
