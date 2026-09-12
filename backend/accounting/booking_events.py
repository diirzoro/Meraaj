"""Booking / settlement / cancellation / ads accounting emitters (Batch 1, PD-1..PD-6).

REVENUE RECOGNITION (PD-1): the platform's share collected at booking is a LIABILITY
(deferred/unearned) until the earning point. It becomes revenue exactly once, at settlement
(PD-1A). Nothing here posts a negative revenue amount (PD-3): a cancellation RELEASES the
deferred liability and, where revenue was already earned, the correction goes through the
reversal engine.

Accounting Actor for an auto-generated entry = System / Integration Service (never an
accountant who did not act). The Business Actor is always the real user.
"""
from .adapters import accounting_bridge
from .business_events import actor_from_user
from .integration.account_links import LinkKey as K

SYSTEM = {"id": "system", "label": "System / Integration Service", "kind": "system"}


def _round(v) -> float:
    return round(float(v or 0), 2)


async def emit_booking_created(booking: dict, booking_id: str, buyer: dict) -> dict:
    """DEBIT buyer wallet liability (amount_charged) · CREDIT seller payable (net_total)
    · CREDIT deferred platform revenue (the rest). No revenue at booking."""
    charged = _round(booking.get("amount_charged"))
    net = _round(booking.get("net_cost_total"))
    deferred = _round(charged - net)
    lines = [(K.OFFICE_WALLET_LIABILITY, "debit", charged),
             (K.SELLER_PAYABLE, "credit", net)]
    if deferred > 0:
        lines.append((K.DEFERRED_PLATFORM_REVENUE, "credit", deferred))
    elif deferred < 0:
        lines.append((K.SELLER_PAYABLE, "debit", -deferred))
    return await accounting_bridge().post_event(
        "booking_debit", event_id=booking_id,
        currency=booking.get("currency", "USD"), amount=charged, lines=lines,
        business_actor=actor_from_user(buyer), accounting_actor=SYSTEM,
        description=f"حجز: {booking.get('package_title', '')}",
        business_ref={"seller_id": booking.get("seller_id"),
                      "buyer_type": booking.get("buyer_type"),
                      "is_rahal": bool(booking.get("rahal_ref")),
                      "deferred_platform_share": deferred})


async def emit_booking_settlement(booking: dict, booking_id: str,
                                  seller: dict) -> dict:
    """Earning point (PD-1A): the deferred share becomes revenue, the seller-side fee is
    recognised, and the marketer commission is released as a liability to the marketer."""
    net = _round(booking.get("net_cost_total"))
    fee = _round(booking.get("platform_fee"))
    charged = _round(booking.get("amount_charged"))
    deferred = _round(charged - net)
    marketer = _round(booking.get("marketer_commission"))
    lines = [(K.SELLER_PAYABLE, "debit", net),
             (K.OFFICE_WALLET_LIABILITY, "credit", _round(net - fee))]
    if fee > 0:
        lines.append((K.COMMISSION_REVENUE, "credit", fee))
    if deferred > 0:
        lines.append((K.DEFERRED_PLATFORM_REVENUE, "debit", deferred))
        platform_share = _round(deferred - marketer)
        if platform_share > 0:
            lines.append((K.COMMISSION_REVENUE, "credit", platform_share))
        if marketer > 0:
            lines.append((K.OFFICE_WALLET_LIABILITY, "credit", marketer))
    return await accounting_bridge().post_event(
        "booking_settlement", event_id=booking_id,
        currency=booking.get("currency", "USD"), amount=net, lines=lines,
        business_actor=actor_from_user(seller), accounting_actor=SYSTEM,
        description=f"تسوية حجز: {booking.get('package_title', '')}",
        business_ref={"platform_fee": fee, "recognized_deferred": deferred,
                      "marketer_commission": marketer})


async def emit_cancel_blue(booking: dict, booking_id: str, refund: float,
                           admin_fee: float, buyer: dict) -> dict:
    """Blue cancellation: release the seller payable and the deferred share, keep the
    administrative fee as EARNED cancellation revenue, refund the rest to the buyer."""
    net = _round(booking.get("net_cost_total"))
    charged = _round(booking.get("amount_charged"))
    deferred = _round(charged - net)
    refund, admin_fee = _round(refund), _round(admin_fee)
    lines = [(K.SELLER_PAYABLE, "debit", net)]
    if deferred > 0:
        lines.append((K.DEFERRED_PLATFORM_REVENUE, "debit", deferred))
    lines.append((K.OFFICE_WALLET_LIABILITY, "credit", refund))
    if admin_fee > 0:
        lines.append((K.CANCELLATION_FEE_REVENUE, "credit", admin_fee))
    residual = _round(net + max(deferred, 0) - refund - admin_fee)
    if residual > 0:
        lines.append((K.SELLER_PAYABLE, "credit", residual))
    elif residual < 0:
        lines.append((K.SELLER_PAYABLE, "debit", -residual))
    return await accounting_bridge().post_event(
        "booking_cancel_blue", event_id=booking_id,
        currency=booking.get("currency", "USD"), amount=refund, lines=lines,
        business_actor=actor_from_user(buyer), accounting_actor=SYSTEM,
        description=f"إلغاء أزرق: {booking.get('package_title', '')}",
        business_ref={"refund": refund, "admin_fee": admin_fee,
                      "released_deferred": deferred})


async def emit_cancel_yellow(booking: dict, booking_id: str, deduction: float,
                             platform_cut: float, seller_keeps: float,
                             refund: float, buyer: dict) -> dict:
    """Yellow cancellation (PD-5): `platform_cut` = earned cancellation revenue,
    `seller_keeps` = seller payable (NOT platform revenue), the rest returns to the buyer
    and the deferred share is released (PD-5A)."""
    net = _round(booking.get("net_cost_total"))
    charged = _round(booking.get("amount_charged"))
    deferred = _round(charged - net)
    platform_cut, seller_keeps, refund = (_round(platform_cut), _round(seller_keeps),
                                          _round(refund))
    lines = [(K.SELLER_PAYABLE, "debit", net)]
    if deferred > 0:
        lines.append((K.DEFERRED_PLATFORM_REVENUE, "debit", deferred))
    if seller_keeps > 0:
        lines.append((K.SELLER_PAYABLE, "credit", seller_keeps))
    if platform_cut > 0:
        lines.append((K.CANCELLATION_FEE_REVENUE, "credit", platform_cut))
    lines.append((K.OFFICE_WALLET_LIABILITY, "credit", refund))
    residual = _round(net + max(deferred, 0) - seller_keeps - platform_cut - refund)
    if residual > 0:
        lines.append((K.SELLER_PAYABLE, "credit", residual))
    elif residual < 0:
        lines.append((K.SELLER_PAYABLE, "debit", -residual))
    return await accounting_bridge().post_event(
        "booking_cancel_yellow", event_id=booking_id,
        currency=booking.get("currency", "USD"), amount=deduction, lines=lines,
        business_actor=actor_from_user(buyer), accounting_actor=SYSTEM,
        description=f"إلغاء أصفر: {booking.get('package_title', '')}",
        business_ref={"deduction": deduction, "platform_cut": platform_cut,
                      "seller_keeps": seller_keeps, "refund": refund,
                      "released_deferred": deferred})


async def emit_ads_capture(ad: dict, ad_id: str, price: float, currency: str,
                           payer: dict, admin: dict = None) -> dict:
    """PD-4A: CAPTURE is the single ads revenue moment. HOLD and RELEASE post nothing."""
    price = _round(price)
    return await accounting_bridge().post_event(
        "ads_capture", event_id=ad_id, currency=currency, amount=price,
        lines=[(K.OFFICE_WALLET_LIABILITY, "debit", price),
               (K.ADS_REVENUE, "credit", price)],
        business_actor=actor_from_user(payer),
        accounting_actor=actor_from_user(admin) if admin else SYSTEM,
        description=f"تحصيل باقة إعلانية: {ad.get('title') or ''}",
        business_ref={"advertisement_id": ad_id, "kind": ad.get("kind")})


async def emit_ads_refund(ad: dict, ad_id: str, amount: float, currency: str,
                          payer: dict, admin: dict, reason: str) -> dict:
    """PD-4C: explicit administrative refund after capture only — never automatic, and only
    for the approved amount."""
    amount = _round(amount)
    return await accounting_bridge().post_event(
        "ads_refund", event_id=f"{ad_id}:{amount}", currency=currency, amount=amount,
        lines=[(K.ADS_REVENUE, "debit", amount),
               (K.OFFICE_WALLET_LIABILITY, "credit", amount)],
        business_actor=actor_from_user(admin),
        accounting_actor=actor_from_user(admin),
        description=f"استرداد إعلان بقرار إداري: {ad.get('title') or ''} — {reason}",
        business_ref={"advertisement_id": ad_id, "reason": reason,
                      "approved_by": (admin or {}).get("name")})
