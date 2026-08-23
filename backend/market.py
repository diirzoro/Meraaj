from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Optional, Union, Dict
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
        d.pop("child_net_cost", None)
        d.pop("child_commission", None)
        d.pop("infant_net_cost", None)
        d.pop("infant_commission", None)
        if isinstance(d.get("room_pricing"), list):
            d["room_pricing"] = [{"room_type": r.get("room_type"), "customer": r.get("customer")}
                                 for r in d["room_pricing"]]
    return d


# ---------- Packages ----------
class HotelInput(BaseModel):
    city: str
    name: str
    nights: int = 0
    distance_m: Optional[int] = None


class RoomPricingInput(BaseModel):
    room_type: str  # double | triple | quad | quint | single
    net: Optional[float] = None
    commission: Optional[float] = None
    customer: Union[float, Dict[str, float]]  # scalar (adult) OR {adult, child, infant}


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
    features: List[str] = []
    room_pricing: List[RoomPricingInput] = []
    net_cost_per_seat: float
    final_sale_price: float
    buyer_office_commission: float
    child_net_cost: Optional[float] = None
    child_sale_price: Optional[float] = None
    child_commission: Optional[float] = None
    infant_net_cost: Optional[float] = None
    infant_sale_price: Optional[float] = None
    infant_commission: Optional[float] = None
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
    pkg_id = str(res.inserted_id)
    # Sync the newly published program to the Meraaj Network (reliable outbox → Rahal)
    await notify_rahal("package.published", {
        "package_ref": pkg_id,
        "source_office_ref": user.get("rahal_office_ref"),
        "office_name": user["office_name"],
        "title": doc["title"],
        "type": doc.get("type"),
        "departure_date": doc.get("departure_date"),
        "return_date": doc.get("return_date"),
        "images": doc.get("images", []),
        "features": doc.get("features", []),
        "hotels": doc.get("hotels", []),
        "available_seats": doc.get("available_seats", 0),
        "pricing": {
            "net_cost_per_seat": doc.get("net_cost_per_seat", 0),
            "final_sale_price": doc.get("final_sale_price", 0),
            "buyer_office_commission": doc.get("buyer_office_commission", 0),
            "currency": doc.get("currency", "USD"),
        },
        "status": "listed",
    })
    return serialize(doc)


FEATURE_SYNONYMS = {
    "breakfast": ["فطور", "افطار", "إفطار", "بوفيه", "breakfast"],
    "near_haram": ["الحرم", "حرم", "قريب من الحرم", "haram"],
    "vip_transport": ["vip", "في اي بي", "فاخر", "نقل vip", "مواصلات vip"],
    "wifi": ["واي فاي", "wifi", "wi-fi", "انترنت", "إنترنت"],
}


def _start_price(doc):
    adults = []
    for r in (doc.get("room_pricing") or []):
        v = _room_customer_price(r.get("customer"), "adult")
        if v is not None and v > 0:
            adults.append(v)
    if adults:
        return round(min(adults), 2)
    try:
        return round(float(doc.get("final_sale_price") or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def _duration_days(doc):
    from datetime import date as _date
    try:
        d1 = _date.fromisoformat(str(doc.get("departure_date"))[:10])
        d2 = _date.fromisoformat(str(doc.get("return_date"))[:10])
        return max((d2 - d1).days, 0)
    except (ValueError, TypeError):
        return None


def _match_features(doc, selected_keys):
    blob = " ".join(str(f).lower() for f in (doc.get("features") or []))
    for key in selected_keys:
        syns = FEATURE_SYNONYMS.get(key, [key])
        if not any(s.lower() in blob for s in syns):
            return False
    return True


async def _seller_deals_map():
    """Completed-deals count per seller (proxy for reliability / best-selling)."""
    out = {}
    async for row in db.bookings.aggregate(
        [{"$match": {"status": "green"}}, {"$group": {"_id": "$seller_id", "n": {"$sum": 1}}}]):
        out[row["_id"]] = row["n"]
    return out


@router.get("/packages")
async def list_packages(type: Optional[str] = None, q: Optional[str] = None,
                        min_price: Optional[float] = None, max_price: Optional[float] = None,
                        date_from: Optional[str] = None, date_to: Optional[str] = None,
                        min_days: Optional[int] = None, max_days: Optional[int] = None,
                        features: Optional[str] = None, sort: str = "newest",
                        user=Depends(get_optional_user)):
    query = {"status": "listed"}
    if type:
        query["type"] = type
    if q:
        query["title"] = {"$regex": q, "$options": "i"}
    if date_from or date_to:
        dr = {}
        if date_from:
            dr["$gte"] = date_from
        if date_to:
            dr["$lte"] = date_to
        query["departure_date"] = dr
    docs = await db.packages.find(query).sort("created_at", -1).to_list(500)

    selected_features = [f.strip() for f in (features or "").split(",") if f.strip()]
    deals = await _seller_deals_map()

    rows = []
    for d in docs:
        start = _start_price(d)
        dur = _duration_days(d)
        if min_price is not None and start < min_price:
            continue
        if max_price is not None and start > max_price:
            continue
        if min_days is not None and (dur is None or dur < min_days):
            continue
        if max_days is not None and (dur is None or dur > max_days):
            continue
        if selected_features and not _match_features(d, selected_features):
            continue
        view = _view_package(d, user)
        view["start_price"] = start
        view["duration_days"] = dur
        view["seller_deals"] = deals.get(str(d.get("seller_id")), 0)
        rows.append(view)

    if sort == "price_asc":
        rows.sort(key=lambda r: r.get("start_price") or 0)
    elif sort == "price_desc":
        rows.sort(key=lambda r: r.get("start_price") or 0, reverse=True)
    elif sort == "date_asc":
        rows.sort(key=lambda r: r.get("departure_date") or "")
    elif sort == "duration_asc":
        rows.sort(key=lambda r: (r.get("duration_days") is None, r.get("duration_days") or 0))
    elif sort == "best_selling":
        rows.sort(key=lambda r: r.get("seller_deals") or 0, reverse=True)
    return rows


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
    # Keep the Meraaj Network in sync when an office lists/unlists a manual program
    if pkg.get("source") != "rahal":
        await notify_rahal(
            "package.activated" if new_status == "listed" else "package.deactivated",
            {"package_ref": pkg_id, "status": new_status})
    return {"status": new_status}


# ---------- Bookings ----------
class RegistrantInput(BaseModel):
    name: str
    passport_no: str
    age: int
    category: str = "adult"  # adult | child | infant
    photo: Optional[str] = None


class BookingInput(BaseModel):
    package_id: str
    registrants: List[RegistrantInput]
    room_type: Optional[str] = None  # selected room drives per-traveler pricing when set
    ref: Optional[str] = None  # affiliate code


def _tier_prices(pkg: dict, category: str):
    """Return (net, sale, commission) for a traveler category. Child/Infant fall back
    to adult pricing when the seller did not define a special price for that tier."""
    adult = (round(float(pkg["net_cost_per_seat"]), 2),
             round(float(pkg["final_sale_price"]), 2),
             round(float(pkg.get("buyer_office_commission") or 0), 2))
    if category == "child":
        n, s, c = pkg.get("child_net_cost"), pkg.get("child_sale_price"), pkg.get("child_commission")
    elif category == "infant":
        n, s, c = pkg.get("infant_net_cost"), pkg.get("infant_sale_price"), pkg.get("infant_commission")
    else:
        return adult
    return (round(float(n), 2) if n is not None else adult[0],
            round(float(s), 2) if s is not None else adult[1],
            round(float(c), 2) if c is not None else adult[2])


def _room_customer_price(customer, category):
    """A room's customer price for a traveler category. `customer` may be an object
    {adult, child, infant} (Rahal) or a scalar (manual programs → adult only)."""
    if customer is None:
        return None
    if isinstance(customer, dict):
        v = customer.get(category)
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None
    try:
        return float(customer) if category == "adult" else None
    except (TypeError, ValueError):
        return None


def _find_room(pkg: dict, room_type):
    if not room_type:
        return None
    for r in (pkg.get("room_pricing") or []):
        if r.get("room_type") == room_type:
            return r
    return None


def _booking_prices(pkg: dict, category: str, room: dict = None):
    """(net, sale, commission) per traveler. When a room is selected, the customer sale
    price comes from that room per category (falling back to the room's adult price), and
    net/commission come from the room when provided; otherwise package-level tier pricing."""
    n, s, c = _tier_prices(pkg, category)
    if room:
        if room.get("net") is not None:
            n = round(float(room["net"]), 2)
        if room.get("commission") is not None:
            c = round(float(room["commission"]), 2)
        rc = _room_customer_price(room.get("customer"), category)
        if rc is None:
            rc = _room_customer_price(room.get("customer"), "adult")
        if rc is not None:
            s = round(float(rc), 2)
    return n, s, c


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
    # Resolve the selected room (drives per-traveler pricing); reject an unknown room type
    room = _find_room(pkg, payload.room_type)
    if payload.room_type and room is None:
        raise HTTPException(400, "نوع الغرفة المختار غير متاح لهذا البرنامج")
    # Sum prices per traveler category (adult / child / infant) using the selected room
    net_total = 0.0
    sale_total = 0.0
    comm_total = 0.0
    for r in payload.registrants:
        n, s, c = _booking_prices(pkg, r.category, room)
        net_total += n
        sale_total += s
        comm_total += c
    net_total = round(net_total, 2)
    sale_total = round(sale_total, 2)
    comm_total = round(comm_total, 2)
    is_office = user["role"] == "office"
    marketer_id = None
    marketer_commission = 0.0
    platform_profit = 0.0

    if is_office:
        # B2B: office pays net + platform fee (double commission); keeps margin offline
        buyer_commission_total = comm_total
        platform_fee = round(buyer_commission_total * platform_pct(), 2)
        required = round(net_total + platform_fee, 2)
    else:
        # B2C: consumer pays full retail; seller gets net; margin => platform (+marketer)
        buyer_commission_total = 0.0
        platform_fee = 0.0
        required = sale_total
        margin_total = round(sale_total - net_total, 2)
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
        "room_type": payload.room_type,
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
