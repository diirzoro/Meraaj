from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Optional
from db import (db, serialize, oid, now_iso, adjust_wallet, log_txn,
                platform_pct, cancel_fee_pct, marketer_pct, log_platform_revenue,
                plan_debit, wallet_available, CurrencyField)
from security import get_current_user, get_optional_user, require_office, require_buyer
from integration import notify_rahal

router = APIRouter(prefix="/api", tags=["market"])


def _view_package(doc, user):
    """Hide wholesale/net pricing from non-office viewers (individuals & guests)."""
    d = serialize(doc)
    if not user or user.get("role") != "office":
        d.pop("net_cost_per_seat", None)
        d.pop("buyer_office_commission", None)
    return d


# ---------- Packages ----------
class HotelInput(BaseModel):
    city: str
    name: str
    nights: int = 0
    distance_m: Optional[int] = None


class PackageInput(BaseModel):
    type: str  # umrah | tourism
    title: str
    description: str = ""
    departure_date: str
    return_date: str
    departure_city: str = ""
    transport: str = ""
    hotels: List[HotelInput] = []
    images: List[str] = []
    net_cost_per_seat: float
    final_sale_price: float
    buyer_office_commission: float
    currency: CurrencyField = "USD"
    total_seats: int


@router.post("/packages")
async def create_package(payload: PackageInput, user: dict = Depends(require_office)):
    doc = payload.model_dump()
    doc.update({
        "seller_id": str(user["_id"]),
        "seller_office_name": user["office_name"],
        "available_seats": payload.total_seats,
        "status": "listed",
        "source": "manual",
        "rahal_ref": None,
        "created_at": now_iso(),
    })
    res = await db.packages.insert_one(doc)
    doc["_id"] = res.inserted_id
    return serialize(doc)


@router.get("/packages")
async def list_packages(type: Optional[str] = None, q: Optional[str] = None, user=Depends(get_optional_user)):
    query = {"status": "listed"}
    if type:
        query["type"] = type
    if q:
        query["title"] = {"$regex": q, "$options": "i"}
    docs = await db.packages.find(query).sort("created_at", -1).to_list(500)
    return [_view_package(d, user) for d in docs]


@router.get("/packages/mine")
async def my_packages(user: dict = Depends(require_office)):
    docs = await db.packages.find({"seller_id": str(user["_id"])}).sort("created_at", -1).to_list(500)
    return serialize(docs)


@router.get("/packages/{pkg_id}")
async def get_package(pkg_id: str, user=Depends(get_optional_user)):
    doc = await db.packages.find_one({"_id": oid(pkg_id)})
    if not doc:
        raise HTTPException(404, "البرنامج غير موجود")
    return _view_package(doc, user)


@router.patch("/packages/{pkg_id}/toggle")
async def toggle_package(pkg_id: str, user: dict = Depends(require_office)):
    pkg = await db.packages.find_one({"_id": oid(pkg_id), "seller_id": str(user["_id"])})
    if not pkg:
        raise HTTPException(404, "البرنامج غير موجود")
    new_status = "unlisted" if pkg["status"] == "listed" else "listed"
    await db.packages.update_one({"_id": oid(pkg_id)}, {"$set": {"status": new_status}})
    return {"status": new_status}


# ---------- Bookings ----------
class RegistrantInput(BaseModel):
    name: str
    passport_no: str
    age: int


class BookingInput(BaseModel):
    package_id: str
    registrants: List[RegistrantInput]
    ref: Optional[str] = None  # affiliate code


@router.post("/bookings")
async def create_booking(payload: BookingInput, user: dict = Depends(require_buyer)):
    pkg = await db.packages.find_one({"_id": oid(payload.package_id)})
    if not pkg or pkg["status"] != "listed":
        raise HTTPException(404, "البرنامج غير متاح")
    if pkg["seller_id"] == str(user["_id"]):
        raise HTTPException(400, "لا يمكنك حجز البرنامج الخاص بك")
    seats = len(payload.registrants)
    if seats == 0:
        raise HTTPException(400, "يجب إضافة مسجّل واحد على الأقل")
    if seats > pkg["available_seats"]:
        raise HTTPException(400, "المقاعد المتاحة غير كافية")

    cur = pkg.get("currency", "USD")
    cur = "SAR" if cur == "SAR" else "USD"
    net_seat = round(float(pkg["net_cost_per_seat"]), 2)
    comm_seat = round(float(pkg.get("buyer_office_commission", 0)), 2)
    sale_seat = round(float(pkg["final_sale_price"]), 2)
    net_total = round(net_seat * seats, 2)
    is_office = user["role"] == "office"
    marketer_id = None
    marketer_commission = 0.0
    platform_profit = 0.0

    if is_office:
        # B2B: office pays net + platform fee (double commission); keeps margin offline
        buyer_commission_total = round(comm_seat * seats, 2)
        platform_fee = round(buyer_commission_total * platform_pct(), 2)
        required = round(net_total + platform_fee, 2)
    else:
        # B2C: consumer pays full retail; seller gets net; margin => platform (+marketer)
        buyer_commission_total = 0.0
        platform_fee = 0.0
        required = round(sale_seat * seats, 2)
        margin_total = round((sale_seat - net_seat) * seats, 2)
        if payload.ref:
            m = await db.users.find_one({"affiliate_code": payload.ref, "is_marketer": True})
            if m and str(m["_id"]) not in (pkg["seller_id"], str(user["_id"])):
                marketer_id = str(m["_id"])
        if marketer_id:
            marketer_commission = round(margin_total * marketer_pct(), 2)
        platform_profit = round(margin_total - marketer_commission, 2)

    fresh = await db.users.find_one({"_id": user["_id"]})
    split = plan_debit(fresh["wallet"], cur, required)
    if split is None:
        raise HTTPException(400, f"الرصيد المتاح غير كافٍ. المطلوب: {required} {cur}")

    # Debit buyer (program currency first, shortfall covered from the other currency at fixed rate)
    for c, amt in split.items():
        if amt:
            await adjust_wallet(user["_id"], c, available=-amt, total=-amt)
    # Escrow to seller in the program's own currency
    await adjust_wallet(oid(pkg["seller_id"]), cur, pending=net_total, total=net_total)
    await db.packages.update_one({"_id": pkg["_id"]}, {"$inc": {"available_seats": -seats}})

    booking = {
        "package_id": str(pkg["_id"]),
        "package_title": pkg["title"],
        "package_type": pkg["type"],
        "rahal_ref": pkg.get("rahal_ref") if pkg.get("source") == "rahal" else None,
        "buyer_id": str(user["_id"]),
        "buyer_office_name": user["office_name"],
        "buyer_type": user["role"],
        "seller_id": pkg["seller_id"],
        "seller_office_name": pkg["seller_office_name"],
        "departure_date": pkg["departure_date"],
        "seats": seats,
        "registrants": [{**r.model_dump(), "visa_no": None, "visa_file": None} for r in payload.registrants],
        "net_cost_total": net_total,
        "buyer_commission_total": buyer_commission_total,
        "platform_fee": platform_fee,
        "marketer_id": marketer_id,
        "marketer_commission": marketer_commission,
        "platform_profit": platform_profit,
        "amount_charged": required,
        "debit_split": split,
        "currency": cur,
        "status": "blue",
        "dispatched_at": None,
        "dispute": None,
        "cancellation": None,
        "created_at": now_iso(),
    }
    res = await db.bookings.insert_one(booking)
    bid = str(res.inserted_id)
    await log_txn(user["_id"], "booking_debit", -required, f"حجز برنامج: {pkg['title']}", bid, currency=cur)
    await log_txn(pkg["seller_id"], "booking_escrow", net_total, f"إيراد معلق من حجز: {pkg['title']}", bid, currency=cur)
    if is_office and platform_fee:
        await log_platform_revenue(platform_fee, f"عمولة منصة (حجز): {pkg['title']}", bid, currency=cur)
    if not is_office:
        if marketer_id and marketer_commission > 0:
            await adjust_wallet(oid(marketer_id), cur, pending=marketer_commission, total=marketer_commission)
            await log_txn(marketer_id, "marketer_commission", marketer_commission,
                          f"عمولة تسويق (معلّقة): {pkg['title']}", bid, currency=cur)
        if platform_profit:
            await log_platform_revenue(platform_profit, f"أرباح المنصة من حجز مباشر: {pkg['title']}", bid, currency=cur)
    if pkg.get("source") == "rahal" and pkg.get("rahal_ref"):
        await notify_rahal("meraaj.booking.created", {
            "package_ref": pkg["rahal_ref"],
            "meraaj_booking_id": bid,
            "seats_booked": seats,
            "available_seats_now": pkg["available_seats"] - seats,
            "buyer": {"office_name": user["office_name"], "type": user["role"]},
            "registrants": [{"name": r.name, "passport_no": r.passport_no, "age": r.age} for r in payload.registrants],
        })
    booking["_id"] = res.inserted_id
    return serialize(booking)


@router.get("/bookings")
async def list_bookings(role: str = "buyer", user: dict = Depends(require_buyer)):
    key = "buyer_id" if role == "buyer" else "seller_id"
    docs = await db.bookings.find({key: str(user["_id"])}).sort("created_at", -1).to_list(500)
    return serialize(docs)


@router.get("/bookings/{booking_id}")
async def get_booking(booking_id: str, user: dict = Depends(require_buyer)):
    b = await db.bookings.find_one({"_id": oid(booking_id)})
    if not b or str(user["_id"]) not in (b["buyer_id"], b["seller_id"]):
        raise HTTPException(404, "الحجز غير موجود")
    return serialize(b)


class VisaInput(BaseModel):
    visas: List[dict]  # [{index, visa_no, visa_file?}]


@router.post("/bookings/{booking_id}/issue-visas")
async def issue_visas(booking_id: str, payload: VisaInput, user: dict = Depends(require_office)):
    b = await db.bookings.find_one({"_id": oid(booking_id)})
    if not b or b["seller_id"] != str(user["_id"]):
        raise HTTPException(404, "الحجز غير موجود")
    if b["status"] != "blue":
        raise HTTPException(400, "لا يمكن إصدار التأشيرات في هذه الحالة")
    registrants = b["registrants"]
    for v in payload.visas:
        idx = v.get("index")
        if idx is None or idx < 0 or idx >= len(registrants):
            continue
        registrants[idx]["visa_no"] = v.get("visa_no")
        if v.get("visa_file") is not None:
            registrants[idx]["visa_file"] = v.get("visa_file")
    # Validation: every registrant must have a visa number
    if any(not r.get("visa_no") for r in registrants):
        raise HTTPException(400, "يجب إدخال رقم التأشيرة لكل مسجّل قبل تحويل الحالة")
    await db.bookings.update_one({"_id": b["_id"]}, {"$set": {"registrants": registrants, "status": "yellow"}})
    return {"status": "yellow"}


@router.post("/bookings/{booking_id}/dispatch")
async def dispatch_booking(booking_id: str, user: dict = Depends(require_office)):
    b = await db.bookings.find_one({"_id": oid(booking_id)})
    if not b or b["seller_id"] != str(user["_id"]):
        raise HTTPException(404, "الحجز غير موجود")
    if b["status"] != "yellow":
        raise HTTPException(400, "يجب إصدار التأشيرات أولاً")
    await db.bookings.update_one({"_id": b["_id"]},
                                 {"$set": {"status": "green", "dispatched_at": now_iso()}})
    return {"status": "green", "dispatched_at": now_iso(), "grace_hours": 24}


@router.post("/bookings/{booking_id}/settle")
async def settle_booking(booking_id: str, user: dict = Depends(require_office)):
    """Release escrow to seller available after 24h grace with no dispute."""
    b = await db.bookings.find_one({"_id": oid(booking_id)})
    if not b or b["seller_id"] != str(user["_id"]):
        raise HTTPException(404, "الحجز غير موجود")
    if b["status"] != "green":
        raise HTTPException(400, "الحجز غير جاهز للتسوية")
    if b.get("settled"):
        raise HTTPException(400, "تمت التسوية مسبقاً")
    if b.get("dispute"):
        raise HTTPException(400, "يوجد نزاع مفتوح على هذا الحجز")
    from datetime import datetime, timezone
    disp = datetime.fromisoformat(b["dispatched_at"])
    if (datetime.now(timezone.utc) - disp).total_seconds() < 24 * 3600:
        raise HTTPException(400, "لم تنته فترة السماح (24 ساعة) بعد")
    net = b["net_cost_total"]
    fee = b["platform_fee"]
    cur = b.get("currency", "USD")
    await adjust_wallet(user["_id"], cur, pending=-net, available=(net - fee), total=-fee)
    await log_txn(user["_id"], "settlement", net - fee, f"تسوية حجز: {b['package_title']}", booking_id, currency=cur)
    if fee:
        await log_platform_revenue(fee, f"عمولة منصة (تسوية): {b['package_title']}", booking_id, currency=cur)
    if b.get("marketer_id") and b.get("marketer_commission"):
        await adjust_wallet(oid(b["marketer_id"]), cur, pending=-b["marketer_commission"], available=b["marketer_commission"])
        await log_txn(b["marketer_id"], "marketer_commission_release", b["marketer_commission"],
                      f"تحرير عمولة تسويق: {b['package_title']}", booking_id, currency=cur)
    await db.bookings.update_one({"_id": b["_id"]}, {"$set": {"settled": True, "settled_at": now_iso()}})
    return {"ok": True, "released": net - fee}


# ---------- Cancellation ----------
@router.post("/bookings/{booking_id}/cancel-request")
async def cancel_request(booking_id: str, user: dict = Depends(require_buyer)):
    b = await db.bookings.find_one({"_id": oid(booking_id)})
    if not b or b["buyer_id"] != str(user["_id"]):
        raise HTTPException(404, "الحجز غير موجود")
    if b["status"] == "green":
        raise HTTPException(400, "لا يمكن الإلغاء بعد التفويج")
    if b["status"] not in ("blue", "yellow"):
        raise HTTPException(400, "لا يمكن إلغاء هذا الحجز في حالته الحالية")
    if b.get("cancellation"):
        raise HTTPException(400, "يوجد طلب إلغاء قيد المعالجة على هذا الحجز")
    if b["status"] == "yellow" and b.get("buyer_type") == "individual":
        raise HTTPException(400, "لا يمكن الإلغاء بعد إصدار التأشيرات. يرجى التواصل مع الإدارة.")
    if b["status"] == "blue":
        # Full refund minus small admin fee (all in the program's currency)
        cur = b.get("currency", "USD")
        admin_fee = round(b["net_cost_total"] * cancel_fee_pct(), 2)
        refund = round(b["amount_charged"] - admin_fee, 2)
        await adjust_wallet(oid(b["seller_id"]), cur, pending=-b["net_cost_total"], total=-b["net_cost_total"])
        if admin_fee:
            await log_platform_revenue(admin_fee, f"رسوم إلغاء إدارية: {b['package_title']}", booking_id, currency=cur)
        if b.get("buyer_type") != "individual" and b.get("platform_fee"):
            await log_platform_revenue(-b["platform_fee"], f"عكس عمولة منصة (إلغاء): {b['package_title']}", booking_id, currency=cur)
        if b.get("buyer_type") == "individual":
            if b.get("marketer_id") and b.get("marketer_commission"):
                await adjust_wallet(oid(b["marketer_id"]), cur,
                                    pending=-b["marketer_commission"], total=-b["marketer_commission"])
                await log_txn(b["marketer_id"], "marketer_commission_reversal", -b["marketer_commission"],
                              f"عكس عمولة تسويق (إلغاء): {b['package_title']}", booking_id, currency=cur)
            if b.get("platform_profit"):
                await log_platform_revenue(-b["platform_profit"], f"عكس أرباح إلغاء: {b['package_title']}", booking_id, currency=cur)
        await adjust_wallet(user["_id"], cur, available=refund, total=refund)
        await db.packages.update_one({"_id": oid(b["package_id"])}, {"$inc": {"available_seats": b["seats"]}})
        await db.bookings.update_one({"_id": b["_id"]}, {"$set": {"status": "cancelled",
                                     "cancellation": {"type": "auto_blue", "refund": refund, "admin_fee": admin_fee}}})
        await log_txn(user["_id"], "cancel_refund", refund, f"استرداد إلغاء: {b['package_title']}", booking_id, currency=cur)
        if b.get("rahal_ref"):
            await notify_rahal("meraaj.booking.cancelled", {
                "package_ref": b["rahal_ref"], "meraaj_booking_id": booking_id, "seats_released": b["seats"]})
        return {"status": "cancelled", "refund": refund, "admin_fee": admin_fee}
    # Yellow: send to seller to set deduction
    await db.bookings.update_one({"_id": b["_id"]}, {"$set": {"cancellation": {"type": "yellow_pending", "stage": "awaiting_seller"}}})
    return {"status": "yellow", "cancellation": "awaiting_seller"}


class DeductionInput(BaseModel):
    deduction: float = Field(ge=0)  # non-refundable (visa cost); capped at escrowed net


@router.post("/bookings/{booking_id}/cancel-offer")
async def cancel_offer(booking_id: str, payload: DeductionInput, user: dict = Depends(require_office)):
    b = await db.bookings.find_one({"_id": oid(booking_id)})
    if not b or b["seller_id"] != str(user["_id"]):
        raise HTTPException(404, "الحجز غير موجود")
    if not b.get("cancellation") or b["cancellation"].get("stage") != "awaiting_seller":
        raise HTTPException(400, "لا يوجد طلب إلغاء بانتظارك")
    if payload.deduction > b["net_cost_total"]:
        raise HTTPException(400, f"الخصم لا يمكن أن يتجاوز التكلفة الصافية المحجوزة ({b['net_cost_total']} {b.get('currency','USD')})")
    await db.bookings.update_one({"_id": b["_id"]}, {"$set": {
        "cancellation": {"type": "yellow_pending", "stage": "awaiting_buyer", "deduction": payload.deduction}}})
    return {"stage": "awaiting_buyer", "deduction": payload.deduction}


@router.post("/bookings/{booking_id}/cancel-accept")
async def cancel_accept(booking_id: str, user: dict = Depends(require_buyer)):
    b = await db.bookings.find_one({"_id": oid(booking_id)})
    if not b or b["buyer_id"] != str(user["_id"]):
        raise HTTPException(404, "الحجز غير موجود")
    c = b.get("cancellation")
    if not c or c.get("stage") != "awaiting_buyer":
        raise HTTPException(400, "لا يوجد عرض إلغاء لقبوله")
    deduction = c["deduction"]
    cur = b.get("currency", "USD")
    platform_cut = round(deduction * platform_pct(), 2)
    seller_keeps = round(deduction - platform_cut, 2)
    refund = round(b["net_cost_total"] - deduction + b["platform_fee"], 2)
    if refund < 0:
        refund = 0.0
    # seller: remove escrow, keep deduction minus platform cut into available
    await adjust_wallet(oid(b["seller_id"]), cur, pending=-b["net_cost_total"],
                        available=seller_keeps, total=-(b["net_cost_total"] - seller_keeps))
    await adjust_wallet(user["_id"], cur, available=refund, total=refund)
    await db.packages.update_one({"_id": oid(b["package_id"])}, {"$inc": {"available_seats": b["seats"]}})
    await db.bookings.update_one({"_id": b["_id"]}, {"$set": {"status": "cancelled",
                                 "cancellation": {"type": "yellow_settled", "deduction": deduction,
                                                  "seller_keeps": seller_keeps, "platform_cut": platform_cut,
                                                  "refund": refund}}})
    await log_txn(user["_id"], "cancel_refund", refund, f"استرداد إلغاء (أصفر): {b['package_title']}", booking_id, currency=cur)
    await log_txn(b["seller_id"], "cancel_deduction", seller_keeps, f"خصم إلغاء: {b['package_title']}", booking_id, currency=cur)
    if b.get("platform_fee"):
        await log_platform_revenue(-b["platform_fee"], f"عكس عمولة منصة (إلغاء أصفر): {b['package_title']}", booking_id, currency=cur)
    if platform_cut:
        await log_platform_revenue(platform_cut, f"رسوم تشغيلية إلغاء: {b['package_title']}", booking_id, currency=cur)
    if b.get("rahal_ref"):
        await notify_rahal("meraaj.booking.cancelled", {
            "package_ref": b["rahal_ref"], "meraaj_booking_id": booking_id, "seats_released": b["seats"]})
    return {"status": "cancelled", "refund": refund, "seller_keeps": seller_keeps}


@router.post("/bookings/{booking_id}/dispute")
async def open_dispute(booking_id: str, payload: dict, user: dict = Depends(require_buyer)):
    b = await db.bookings.find_one({"_id": oid(booking_id)})
    if not b or b["buyer_id"] != str(user["_id"]):
        raise HTTPException(404, "الحجز غير موجود")
    if b["status"] != "green" or b.get("settled"):
        raise HTTPException(400, "لا يمكن فتح نزاع على هذا الحجز")
    if b.get("dispute"):
        raise HTTPException(400, "يوجد نزاع مفتوح مسبقاً على هذا الحجز")
    from datetime import datetime, timezone
    disp = datetime.fromisoformat(b["dispatched_at"])
    if (datetime.now(timezone.utc) - disp).total_seconds() > 24 * 3600:
        raise HTTPException(400, "انتهت مهلة الاعتراض (24 ساعة)")
    dispute = {"reason": payload.get("reason", ""), "status": "open", "created_at": now_iso(),
               "opener": str(user["_id"])}
    await db.bookings.update_one({"_id": b["_id"]}, {"$set": {"dispute": dispute}})
    return {"ok": True, "dispute": dispute}
