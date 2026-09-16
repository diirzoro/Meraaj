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

import os

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from accounting.adapters import PLATFORM_ENTITY
from accounting.scope import load_scope
from db import db, serialize, now_iso, wallet_available
from rbac import has_perm
from security import get_current_user, get_optional_user

router = APIRouter(prefix="/api/v1/mobile", tags=["mobile"])

API_VERSION = "v1"
#: installs older than this are asked to update (soft gate, evaluated by the app)
MIN_SUPPORTED_APP = "1.0.0"
LATEST_APP = "1.0.0"
APP_VERSION_HINT = "1.0.0"
#: EXTERNAL CONFIGURATION REQUIRED — no fake provider, no placeholder secrets.
PUSH_CONFIGURED = bool(os.environ.get("FCM_SERVER_KEY") or os.environ.get("APNS_KEY_ID"))

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

ADMIN_TABS = [
    {"key": "home", "label": "الرئيسية", "icon": "home", "route": "/m/home"},
    {"key": "operations", "label": "العمليات", "icon": "receipt", "route": "/m/admin/operations"},
    {"key": "accounting", "label": "الحسابات", "icon": "calculator", "route": "/m/accounting"},
    {"key": "notifications", "label": "الإشعارات", "icon": "bell", "route": "/m/notifications"},
    {"key": "account", "label": "حسابي", "icon": "user", "route": "/m/account"},
]

#: Admin mobile sections. `perm=None` means "super admin only"; every other entry is
#: resolved against the REAL RBAC permission — never against the role name.
ADMIN_SECTIONS = [
    {"group": "operations", "label": "العمليات", "icon": "receipt", "children": [
        {"key": "orders", "label": "مركز الطلبات", "route": "/m/admin/orders", "perm": "orders.view"},
    ]},
    {"group": "money", "label": "المالية والمحافظ", "icon": "wallet", "children": [
        {"key": "topups", "label": "طلبات شحن الرصيد", "route": "/m/admin/topups", "perm": "funds.release"},
        {"key": "office_statement", "label": "كشف حساب مكتب", "route": "/m/statement", "perm": "office.statement.view"},
    ]},
    {"group": "accounting", "label": "الحسابات", "icon": "calculator", "children": [
        {"key": "acc_hub", "label": "لوحة المحاسبة", "route": "/m/accounting", "perm": "accounting.journals.view"},
        {"key": "acc_chart", "label": "الدليل المحاسبي", "route": "/m/accounting/chart", "perm": "accounting.accounts.view"},
        {"key": "acc_vouchers", "label": "السندات", "route": "/m/accounting/vouchers", "perm": "accounting.vouchers.view"},
        {"key": "acc_journals", "label": "القيود اليومية", "route": "/m/accounting/journals", "perm": "accounting.journals.view"},
        {"key": "acc_ledger", "label": "الأستاذ وكشف الحساب", "route": "/m/accounting/ledger", "perm": "accounting.ledger.view"},
        {"key": "acc_reports", "label": "التقارير المالية", "route": "/m/accounting/reports", "perm": "accounting.reports.view"},
        {"key": "acc_periods", "label": "الفترات والإقفال", "route": "/m/accounting/periods", "perm": "accounting.periods.view"},
        {"key": "acc_audit", "label": "المطابقة والتدقيق الذاتي", "route": "/m/accounting/audit", "perm": "accounting.reconciliation.view"},
    ]},
    {"group": "reports", "label": "التقارير", "icon": "file-text", "children": [
        {"key": "acc_reports_shortcut", "label": "التقارير المالية", "route": "/m/accounting/reports", "perm": "accounting.reports.view"},
    ]},
]

#: Mobile-usable accounting capabilities, each gated by its own Batch 2 permission.
ACCOUNTING_CAPABILITIES = {
    "chart_view": "accounting.accounts.view",
    "vouchers_view": "accounting.vouchers.view",
    "voucher_receipt": "accounting.vouchers.receipt",
    "voucher_payment": "accounting.vouchers.payment",
    "voucher_approve": "accounting.vouchers.approve",
    "voucher_cancel": "accounting.vouchers.cancel",
    "journals_view": "accounting.journals.view",
    "journal_create": "accounting.journals.create",
    "journal_post": "accounting.journals.post",
    "journal_reverse": "accounting.journals.reverse",
    "ledger_view": "accounting.ledger.view",
    "statement_view": "accounting.statement.view",
    "reports_view": "accounting.reports.view",
    "periods_view": "accounting.periods.view",
    "period_close": "accounting.periods.close",
    "period_reopen": "accounting.periods.reopen",
    "year_close": "accounting.year.close",
    "year_reopen": "accounting.year.reopen",
    "reconciliation_view": "accounting.reconciliation.view",
    "self_audit": "accounting.selfaudit.run",
}


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

    The EXPERIENCE is decided from the authenticated identity + RBAC only — never from a
    value the client sends. Purely derived from existing collections: it never writes and
    never recomputes money.
    """
    role = user.get("role")
    fresh = await db.users.find_one({"_id": user["_id"]}) or user
    wallet = fresh.get("wallet") or {}
    own_id = str(fresh.get("parent_office_id") or fresh["_id"])
    is_admin = role == "super_admin" or bool(fresh.get("is_admin_staff"))
    experience = "admin" if is_admin else ("individual" if role == "individual" else "office")

    unread = await db.notifications.count_documents(
        {"$or": [{"user_id": str(fresh["_id"])},
                 *([{"audience": "admin"}] if is_admin else [])], "read": False})

    if experience == "admin":
        sections, section_count = [], 0
        for group in ADMIN_SECTIONS:
            children = [c for c in group["children"]
                        if await has_perm(user, c["perm"])]
            if children:
                sections.append({**group, "children": children})
                section_count += len(children)
        caps = {name: await has_perm(user, perm)
                for name, perm in ACCOUNTING_CAPABILITIES.items()}
        scope = (await load_scope(user)).public()
        accounting_enabled = any(caps.values())
        return {
            "api_version": API_VERSION, "min_supported_app": MIN_SUPPORTED_APP,
            "experience": experience,
            "tabs": [t for t in ADMIN_TABS
                     if t["key"] != "accounting" or accounting_enabled],
            "services": [], "admin_sections": sections,
            "accounting": {"enabled": accounting_enabled, "capabilities": caps,
                           "account_scope": scope, "entity_id": PLATFORM_ENTITY},
            "features": {"umrah_booking": False, "tickets_booking": False,
                         "wallet_topup": False, "withdrawals": False,
                         "b2b_transfers": False,
                         "push_notifications": PUSH_CONFIGURED,
                         "admin_console": True},
            "user": {"id": str(fresh["_id"]), "email": fresh.get("email"), "role": role,
                     "name": fresh.get("staff_name") or fresh.get("owner_name")
                             or fresh.get("office_name") or "إدارة معراج",
                     "is_staff": bool(fresh.get("is_staff_account")), "office_id": own_id},
            "wallet": {}, "badges": {"notifications": unread, "admin_sections": section_count},
            "maintenance": await _maintenance_state(),
        }

    services = [s for s in SERVICE_CATALOG if role in s["roles"]]
    if role == "office" and fresh.get("is_staff_account") \
            and not await has_perm(user, "office.statement.view"):
        services = [s for s in services if s["key"] != "office_statement"]

    active_bookings = await db.bookings.count_documents(
        {"buyer_id": own_id, "status": {"$nin": ["cancelled", "green", "expired"]}})
    pending_topups = await db.topups.count_documents({"office_id": own_id,
                                                      "status": "pending"})
    return {
        "api_version": API_VERSION,
        "min_supported_app": MIN_SUPPORTED_APP,
        "experience": experience,
        "tabs": TABS,
        "services": services,
        "admin_sections": [],
        # ACCOUNTING IS ADMIN-ONLY ON MOBILE: an office/individual never sees it.
        "accounting": {"enabled": False, "capabilities": {}, "account_scope": None},
        "features": {
            "umrah_booking": True,
            "tickets_booking": False,          # awaits the transport provider contract
            "wallet_topup": True,
            "withdrawals": role == "office",
            "b2b_transfers": role == "office",
            "push_notifications": PUSH_CONFIGURED,
            "admin_console": False,
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
        "maintenance": await _maintenance_state(),
    }


async def _maintenance_state() -> dict:
    doc = await db.settings.find_one({"_id": "maintenance"}) or {}
    return {"active": bool(doc.get("active")), "message": doc.get("message") or "",
            "update_required": False}


class DeviceTokenIn(BaseModel):
    token: str = Field(min_length=10, max_length=512)
    platform: str = Field(default="android", max_length=16)
    app_version: str = Field(default=APP_VERSION_HINT, max_length=24)


@router.post("/devices")
async def register_device(payload: DeviceTokenIn, user: dict = Depends(get_current_user)):
    """Push ARCHITECTURE: device tokens are stored against the authenticated user so the
    existing notification events can be fanned out once FCM/APNs credentials are supplied
    (EXTERNAL CONFIGURATION REQUIRED). Nothing is sent from here and no fake provider is
    used — in-app notifications keep working regardless."""
    await db.device_tokens.update_one(
        {"token": payload.token},
        {"$set": {"user_id": str(user["_id"]), "platform": payload.platform,
                  "app_version": payload.app_version, "active": True,
                  "updated_at": now_iso()},
         "$setOnInsert": {"created_at": now_iso()}}, upsert=True)
    return {"ok": True, "push_configured": PUSH_CONFIGURED,
            "note": "التوكن مسجّل — الإرسال الفعلي يتطلب إعداد FCM/APNs"
                    if not PUSH_CONFIGURED else "التوكن مسجّل"}


@router.delete("/devices")
async def unregister_device(token: str, user: dict = Depends(get_current_user)):
    await db.device_tokens.update_one({"token": token, "user_id": str(user["_id"])},
                                      {"$set": {"active": False, "updated_at": now_iso()}})
    return {"ok": True}


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
