"""MERAAJ MOBILE — a thin, VERSIONED read layer for the native app.

Rules this module obeys:
* It creates NO second engine: no wallet, no booking, no pricing, no commission logic here.
  Every write the app performs goes to the EXISTING endpoints (`/api/bookings`,
  `/api/wallet/topups`, ...) so server-side business rules stay the single source of truth.
* It is SERVER-DRIVEN: tabs, service tiles, feature flags, limits and the minimum supported
  app version come from here, so most product changes ship WITHOUT a new store release.
* It is ADDITIVE-ONLY: the app tolerates new fields; breaking changes get a new version
  prefix (`/api/v2/mobile/...`) while `v1` keeps serving older installs.
"""
from typing import Optional

from fastapi import APIRouter, Depends

from db import db, serialize, wallet_available
from rbac import has_perm
from security import get_current_user, get_optional_user

router = APIRouter(prefix="/api/v1/mobile", tags=["mobile"])

API_VERSION = "v1"
#: installs older than this are asked to update (soft gate, evaluated by the app)
MIN_SUPPORTED_APP = "1.0.0"
LATEST_APP = "1.0.0"

SERVICE_CATALOG = [
    {"key": "umrah", "label": "برامج العمرة", "icon": "kaaba", "route": "/m/programs",
     "status": "live", "roles": ["office", "individual"]},
    {"key": "tickets", "label": "التذاكر", "icon": "bus", "route": "/m/tickets",
     "status": "coming_soon", "roles": ["office", "individual"],
     "note": "بانتظار واجهة شركة النقل — لا يوجد تدفق حجز بعد"},
    {"key": "bookings", "label": "حجوزاتي", "icon": "receipt", "route": "/m/bookings",
     "status": "live", "roles": ["office", "individual"]},
    {"key": "topup", "label": "شحن الرصيد", "icon": "plus-circle", "route": "/m/wallet/topup",
     "status": "live", "roles": ["office", "individual"]},
    {"key": "wallet", "label": "المحفظة", "icon": "wallet", "route": "/m/wallet",
     "status": "live", "roles": ["office", "individual"]},
    {"key": "sales", "label": "مبيعاتي", "icon": "trending-up", "route": "/m/sales",
     "status": "live", "roles": ["office"]},
    {"key": "notifications", "label": "الإشعارات", "icon": "bell",
     "route": "/m/notifications", "status": "live", "roles": ["office", "individual"]},
    {"key": "account", "label": "حسابي", "icon": "user", "route": "/m/account",
     "status": "live", "roles": ["office", "individual"]},
    {"key": "office_statement", "label": "كشف حساب المكتب", "icon": "file-text",
     "route": "/m/statement", "status": "live", "roles": ["office"]},
]

TABS = [
    {"key": "home", "label": "الرئيسية", "icon": "home", "route": "/m/home"},
    {"key": "bookings", "label": "حجوزاتي", "icon": "receipt", "route": "/m/bookings"},
    {"key": "wallet", "label": "المحفظة", "icon": "wallet", "route": "/m/wallet"},
    {"key": "notifications", "label": "الإشعارات", "icon": "bell", "route": "/m/notifications"},
    {"key": "account", "label": "حسابي", "icon": "user", "route": "/m/account"},
]


@router.get("/config")
async def public_config(user: Optional[dict] = Depends(get_optional_user)):
    """Reachable BEFORE login (splash screen): version gate + public identity only."""
    return {
        "api_version": API_VERSION,
        "min_supported_app": MIN_SUPPORTED_APP,
        "latest_app": LATEST_APP,
        "brand": {"name_ar": "معراج نتورك", "name_en": "Meraaj Network",
                  "primary": "#0A2540", "accent": "#D4AF37"},
        "locale": {"default": "ar", "dir": "rtl", "currencies": ["SAR", "USD"]},
        "registration_open": True,
        "authenticated": bool(user),
    }


@router.get("/bootstrap")
async def bootstrap(user: dict = Depends(get_current_user)):
    """Everything the shell needs after login, in ONE round trip (weak networks).

    Purely derived from existing collections — it never writes and never recomputes money.
    """
    role = user.get("role")
    fresh = await db.users.find_one({"_id": user["_id"]}) or user
    wallet = fresh.get("wallet") or {}
    own_id = str(fresh.get("parent_office_id") or fresh["_id"])

    services = [s for s in SERVICE_CATALOG if role in s["roles"]]
    if role == "office" and not await has_perm(user, "office.statement.view"):
        # the office owner always sees its own statement; staff need the permission
        services = [s for s in services
                    if s["key"] != "office_statement" or not fresh.get("is_staff_account")]

    unread = await db.notifications.count_documents({"user_id": str(fresh["_id"]),
                                                     "read": False})
    active_bookings = await db.bookings.count_documents(
        {"buyer_id": own_id, "status": {"$nin": ["cancelled", "green", "expired"]}})
    pending_topups = await db.topups.count_documents({"office_id": own_id,
                                                      "status": "pending"})
    return {
        "api_version": API_VERSION,
        "min_supported_app": MIN_SUPPORTED_APP,
        "tabs": TABS,
        "services": services,
        "features": {
            "umrah_booking": True,
            "tickets_booking": False,          # awaits the transport provider contract
            "wallet_topup": True,
            "withdrawals": role == "office",
            "b2b_transfers": role == "office",
            "push_notifications": False,       # architecture ready, transport not wired
        },
        "user": {
            "id": str(fresh["_id"]), "email": fresh.get("email"), "role": role,
            "name": fresh.get("staff_name") or fresh.get("owner_name")
                    or fresh.get("office_name"),
            "office_name": fresh.get("office_name"),
            "is_staff": bool(fresh.get("is_staff_account")),
            "office_id": own_id,
        },
        "wallet": {c: {"available": wallet_available(wallet, c),
                       "pending": round(float((wallet.get(c) or {}).get("pending") or 0), 2),
                       "total": round(float((wallet.get(c) or {}).get("total") or 0), 2)}
                   for c in ("SAR", "USD")},
        "badges": {"notifications": unread, "active_bookings": active_bookings,
                   "pending_topups": pending_topups},
    }


@router.get("/home")
async def home(user: dict = Depends(get_current_user)):
    """Home feed: featured live programs + the user's latest bookings. Read-only."""
    own_id = str(user.get("parent_office_id") or user["_id"])
    pkgs = await db.packages.find(
        {"status": "listed", "available_seats": {"$gt": 0}},
        {"title": 1, "currency": 1, "departure_date": 1, "return_date": 1, "city": 1,
         "hotel_name": 1, "cover_image": 1, "images": 1, "available_seats": 1,
         "final_sale_price": 1, "net_cost_per_seat": 1, "type": 1}
    ).sort("created_at", -1).to_list(8)
    bookings = await db.bookings.find(
        {"buyer_id": own_id},
        {"package_title": 1, "status": 1, "currency": 1, "amount_charged": 1,
         "created_at": 1, "seats": 1}).sort("created_at", -1).to_list(5)
    return {"featured_programs": serialize(pkgs), "recent_bookings": serialize(bookings)}


@router.get("/tickets/providers")
async def ticket_providers(user: dict = Depends(get_current_user)):
    """TICKETS ARCHITECTURE ONLY — the adapter registry is empty until the transport
    company's API contract arrives. No provider is hardcoded and no flow is invented."""
    return {
        "enabled": False,
        "kinds": [{"key": "land_transport", "label": "النقل البري", "status": "pending_api"}],
        "providers": [],
        "required_provider_contract": [
            "search(from, to, date, passengers) → trips[]",
            "trip(trip_id) → segments, seat_map, fare_rules",
            "seat_hold(trip_id, seats[], ttl) → hold_id",
            "price_check(hold_id, passengers[]) → authoritative price breakdown",
            "book(hold_id, passengers[], contact, idempotency_key) → booking_ref",
            "issue(booking_ref) → ticket documents (PDF/QR)",
            "cancel(booking_ref, reason) / refund_quote(booking_ref) → penalty + refundable",
            "webhook: trip changed / cancelled / ticket issued",
        ],
        "note": "الشاشة محفوظة في التطبيق، والتدفق يُبنى على العقد الحقيقي بعد استلامه",
    }
