"""Executive analytics for the Super Admin dashboard. Pure read/aggregation — ADDITIVE."""
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends

from db import db, serialize
from security import require_admin

router = APIRouter(prefix="/api/admin", tags=["admin-analytics"])

CCY = ("SAR", "USD")
RELEASED_TXN = ("settlement", "dispute_release", "seller_compensation")
REFUND_TXN = ("cancel_refund", "dispute_refund", "hold_release")


def _z():
    return {"SAR": 0.0, "USD": 0.0}


def _now():
    return datetime.now(timezone.utc)


def _day(d: datetime) -> str:
    return d.date().isoformat()


def _range(date_from: Optional[str], date_to: Optional[str], period: str):
    now = _now()
    if date_from and date_to:
        return date_from, date_to
    span = {"day": 1, "week": 7, "month": 30, "year": 365}.get(period, 30)
    return _day(now - timedelta(days=span - 1)), _day(now)


def _created_filter(df: str, dt: str) -> dict:
    return {"created_at": {"$gte": df, "$lte": dt + "T23:59:59.999999+00:00"}}


def _bucket(iso: str, period: str) -> str:
    if period == "year":
        return iso[:4]
    if period == "month":
        return iso[:7]
    if period == "week":
        try:
            d = datetime.fromisoformat(iso).date()
        except Exception:
            return iso[:10]
        return (d - timedelta(days=d.weekday())).isoformat()
    return iso[:10]


async def _sum_by_ccy(coll, match: dict, field: str) -> dict:
    out = _z()
    async for r in coll.aggregate([{"$match": match},
                                   {"$group": {"_id": "$currency", "t": {"$sum": f"${field}"}}}]):
        if r["_id"] in out:
            out[r["_id"]] = round(r["t"], 2)
    return out


@router.get("/analytics")
async def analytics(date_from: Optional[str] = None, date_to: Optional[str] = None,
                    period: str = "month", currency: Optional[str] = None,
                    seller_id: Optional[str] = None, buyer_id: Optional[str] = None,
                    package_id: Optional[str] = None, status: Optional[str] = None,
                    admin: dict = Depends(require_admin)):
    df, dt = _range(date_from, date_to, period)
    base = dict(_created_filter(df, dt))
    if currency in CCY:
        base["currency"] = currency
    if seller_id:
        base["seller_id"] = seller_id
    if buyer_id:
        base["buyer_id"] = buyer_id
    if package_id:
        base["package_id"] = package_id
    if status:
        base["status"] = status

    # ---- sales / revenue ----
    gross = await _sum_by_ccy(db.bookings, base, "amount_charged")
    seller_net = await _sum_by_ccy(db.bookings, base, "net_cost_total")
    plat_fee = await _sum_by_ccy(db.bookings, base, "platform_fee")
    plat_profit = await _sum_by_ccy(db.bookings, base, "platform_profit")
    marketer = await _sum_by_ccy(db.bookings, base, "marketer_commission")
    buyer_comm = await _sum_by_ccy(db.bookings, base, "buyer_commission_total")
    bookings_count = await db.bookings.count_documents(base)
    platform_total = {c: round(plat_fee[c] + plat_profit[c], 2) for c in CCY}
    net_profit = {c: round(platform_total[c] - marketer[c], 2) for c in CCY}

    # ---- statuses / approvals ----
    by_status = {}
    async for r in db.bookings.aggregate([{"$match": base},
                                          {"$group": {"_id": "$status", "n": {"$sum": 1}}}]):
        by_status[r["_id"] or "unknown"] = r["n"]
    by_approval = {}
    async for r in db.bookings.aggregate([{"$match": base},
                                          {"$group": {"_id": "$approval_status", "n": {"$sum": 1}}}]):
        by_approval[r["_id"] or "legacy"] = r["n"]
    # "Awaiting seller decision" = explicit pending OR a legacy new booking with no decision yet.
    awaiting_seller = await db.bookings.count_documents({**base, "$or": [
        {"approval_status": "pending"},
        {"approval_status": {"$in": [None, ""]}, "status": "blue"},
    ]})
    by_approval["awaiting_seller"] = awaiting_seller
    status_sum = sum(by_status.values())

    # ---- escrow / money movement (transaction ledger, whole platform) ----
    txn_range = _created_filter(df, dt)
    released = await _sum_by_ccy(db.transactions, {**txn_range, "type": {"$in": list(RELEASED_TXN)}}, "amount")
    refunded = await _sum_by_ccy(db.transactions, {**txn_range, "type": {"$in": list(REFUND_TXN)}}, "amount")

    liq = {c: {"available": 0.0, "pending": 0.0, "total": 0.0} for c in CCY}
    seller_dues = _z()
    exposure = _z()
    negative_wallets = []
    users = await db.users.find({"role": {"$in": ["office", "individual"]}}).to_list(5000)
    for u in users:
        w = u.get("wallet") or {}
        for c in CCY:
            cw = w.get(c) or {}
            for k in ("available", "pending", "total"):
                liq[c][k] += float(cw.get(k) or 0)
            av = float(cw.get("available") or 0)
            seller_dues[c] += float(cw.get("pending") or 0)
            if av < -0.01:
                exposure[c] += -av
                negative_wallets.append({"id": str(u["_id"]),
                                         "name": u.get("office_name") or u.get("name"),
                                         "currency": c, "amount": round(av, 2)})
    for c in CCY:
        liq[c] = {k: round(v, 2) for k, v in liq[c].items()}
        seller_dues[c] = round(seller_dues[c], 2)
        exposure[c] = round(exposure[c], 2)

    # ---- withdrawals / settlements ----
    wd_pending = await _sum_by_ccy(db.withdrawals, {"status": "pending"}, "amount")
    wd_done = await _sum_by_ccy(db.withdrawals, {"status": "approved"}, "amount")
    withdrawals = {
        "pending_count": await db.withdrawals.count_documents({"status": "pending"}),
        "pending_amount": wd_pending,
        "approved_amount": wd_done,
        "settled_bookings": await db.bookings.count_documents({**base, "settled": True}),
    }

    # ---- attention queue ----
    now_iso_s = _now().isoformat()
    attention = {
        "overdue_approvals": await db.bookings.count_documents(
            {"approval_status": "pending", "approval_expires_at": {"$lte": now_iso_s}}),
        "pending_approvals": await db.bookings.count_documents({"approval_status": "pending"}),
        "cancellation_requests": await db.bookings.count_documents({"cancellation_status": "requested"}),
        "open_disputes": await db.bookings.count_documents({"dispute.status": "open"}),
        "escalated": await db.bookings.count_documents({"escalated": True}),
        "pending_topups": await db.topups.count_documents({"status": "pending"}),
        "pending_transfers": await db.transfers.count_documents({"status": "pending"}),
        "pending_withdrawals": await db.withdrawals.count_documents({"status": "pending"}),
        "failed_outbox": await db.rahal_outbox.count_documents({"status": {"$in": ["pending", "failed"]}}),
        "open_tasks": await db.admin_tasks.count_documents({"status": {"$in": ["open", "in_progress"]}}),
    }

    # ---- programs ----
    today = _day(_now())
    programs = {
        "active": await db.packages.count_documents(
            {"status": {"$ne": "unlisted"}, "departure_date": {"$gte": today}}),
        "expired": await db.packages.count_documents({"departure_date": {"$lt": today}}),
        "unlisted": await db.packages.count_documents({"status": "unlisted"}),
        "total": await db.packages.count_documents({}),
        "rahal": await db.packages.count_documents({"source": "rahal"}),
    }

    # ---- parties ----
    parties = {
        "offices": await db.users.count_documents({"role": "office"}),
        "individuals": await db.users.count_documents({"role": "individual"}),
        "marketers": await db.users.count_documents({"role": "individual", "is_marketer": True}),
        "suspended": await db.users.count_documents({"status": "suspended"}),
        "active_sellers": len(await db.bookings.distinct("seller_id", base)),
        "active_buyers": len(await db.bookings.distinct("buyer_id", base)),
    }

    # ---- time series ----
    raw = await db.bookings.find(base, {"created_at": 1, "amount_charged": 1,
                                        "platform_fee": 1, "platform_profit": 1}).to_list(20000)
    series_map = {}
    for b in raw:
        k = _bucket(str(b.get("created_at") or ""), period)
        s = series_map.setdefault(k, {"bucket": k, "gross": 0.0, "revenue": 0.0, "bookings": 0})
        s["gross"] += float(b.get("amount_charged") or 0)
        s["revenue"] += float(b.get("platform_fee") or 0) + float(b.get("platform_profit") or 0)
        s["bookings"] += 1
    series = [{**v, "gross": round(v["gross"], 2), "revenue": round(v["revenue"], 2)}
              for v in sorted(series_map.values(), key=lambda x: x["bucket"])]

    # ---- comparison with the previous equal-length window ----
    try:
        d1 = datetime.fromisoformat(df).date()
        d2 = datetime.fromisoformat(dt).date()
        span = (d2 - d1).days + 1
        prev = dict(base)
        prev.update(_created_filter((d1 - timedelta(days=span)).isoformat(),
                                    (d1 - timedelta(days=1)).isoformat()))
        prev_gross = await _sum_by_ccy(db.bookings, prev, "amount_charged")
        prev_count = await db.bookings.count_documents(prev)
    except Exception:
        prev_gross, prev_count = _z(), 0

    # ---- risk alerts (deduplicated: identical warnings must never repeat) ----
    alerts, seen_alerts = [], set()

    def add_alert(level, atype, message):
        key = (atype, message)
        if key in seen_alerts:
            return
        seen_alerts.add(key)
        alerts.append({"level": level, "type": atype, "message": message})

    for nw in negative_wallets[:10]:
        add_alert("critical", "negative_balance",
                  f"رصيد سالب لـ {nw['name']}: {nw['amount']} {nw['currency']}")
    if attention["overdue_approvals"]:
        add_alert("critical", "overdue_approval",
                  f"{attention['overdue_approvals']} طلب تجاوز مهلة اعتماد البائع")
    if attention["failed_outbox"]:
        add_alert("warning", "integration",
                  f"{attention['failed_outbox']} حدث لم يُسلَّم إلى رحّال")
    if attention["open_disputes"]:
        add_alert("warning", "dispute", f"{attention['open_disputes']} نزاع مفتوح")
    if attention["cancellation_requests"]:
        add_alert("warning", "cancellation",
                  f"{attention['cancellation_requests']} طلب إلغاء بانتظار القرار")
    big = await db.bookings.find({**base, "amount_charged": {"$gte": 50000}},
                                 {"package_title": 1, "amount_charged": 1, "currency": 1}
                                 ).sort("amount_charged", -1).to_list(3)
    for b in big:
        add_alert("info", "high_value",
                  f"عملية بقيمة مرتفعة: {b.get('package_title')} — "
                  f"{round(b.get('amount_charged', 0), 2)} {b.get('currency')}")

    return {
        "range": {"from": df, "to": dt, "period": period},
        "sales": {"gross": gross, "seller_net": seller_net, "buyer_commission": buyer_comm,
                  "platform_commission": platform_total, "marketer_commission": marketer,
                  "net_profit": net_profit, "bookings_count": bookings_count},
        "escrow": {"pending": seller_dues, "released": released, "refunded": refunded},
        "liquidity": liq, "seller_dues": seller_dues, "exposure": exposure,
        "credit": {"enabled": False, "limits_total": _z(), "used": exposure},
        "withdrawals": withdrawals,
        "bookings_by_status": by_status, "bookings_by_approval": by_approval,
        "counts_check": {"bookings_count": bookings_count, "status_sum": status_sum,
                         "matches": bookings_count == status_sum},
        "attention": attention, "programs": programs, "parties": parties,
        "series": series,
        "comparison": {"previous_gross": prev_gross, "previous_bookings": prev_count},
        "alerts": alerts,
    }


@router.get("/attention")
async def attention_queue(limit: int = 20, admin: dict = Depends(require_admin)):
    """Top bookings that need management intervention (overdue / disputed / escalated)."""
    now_iso_s = _now().isoformat()
    f = {"$or": [
        {"approval_status": "pending", "approval_expires_at": {"$lte": now_iso_s}},
        {"cancellation_status": "requested"},
        {"dispute.status": "open"},
        {"escalated": True},
        {"delivery_status": "failed"},
    ]}
    docs = await db.bookings.find(f).sort("created_at", -1).limit(limit).to_list(limit)
    from admin_orders import _decorate
    return [_decorate(d) for d in docs]
