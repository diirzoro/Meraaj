"""Commission engine (Batch 2) — replaces the hard-coded platform percentage with
manageable rules, WITHOUT changing current behaviour: when no active rule matches,
the engine falls back to PLATFORM_COMMISSION_PCT exactly as before.

Every booking stores a snapshot of the applied rule so historic bookings never change
when rules are edited later.
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from db import (db, serialize, oid, now_iso, platform_pct, adjust_wallet, log_txn,
                log_platform_revenue, audit, wallet_available, CurrencyField)
from security import require_admin

router = APIRouter(prefix="/api/admin", tags=["admin-commissions"])

MODES = ("percent", "fixed")
SIDES = ("buyer", "seller", "split")


# ---------------- resolution (used by the booking flow) ----------------
def _matches(rule: dict, *, buyer_type: str, currency: str, package: dict, seller_id: str) -> bool:
    sc = rule.get("scope") or {}
    if sc.get("buyer_type") not in (None, "", "any", buyer_type):
        return False
    if sc.get("currency") not in (None, "", "any", currency):
        return False
    if sc.get("package_type") not in (None, "", "any", package.get("type")):
        return False
    if sc.get("seller_id") and sc["seller_id"] != str(seller_id):
        return False
    if sc.get("package_id") and sc["package_id"] != str(package.get("_id")):
        return False
    if sc.get("source") not in (None, "", "any", package.get("source") or "meraaj"):
        return False
    return True


async def resolve_commission(*, buyer_type: str, currency: str, package: dict,
                             seller_id: str, base_amount: float,
                             per_category: Optional[dict] = None) -> dict:
    """Returns the commission snapshot to be embedded in the booking.
    `base_amount` = the amount the platform commission is computed on (buyer commission total).
    """
    default = {
        "rule_id": None, "rule_name": "القاعدة الافتراضية (10%)",
        "mode": "percent", "value": platform_pct(), "charge_side": "buyer",
        "amount": round(base_amount * platform_pct(), 2),
        "per_category": None, "resolved_at": now_iso(), "source": "default",
    }
    rules = await db.commission_rules.find({"active": True}).sort("priority", -1).to_list(200)
    for r in rules:
        if not _matches(r, buyer_type=buyer_type, currency=currency,
                        package=package, seller_id=seller_id):
            continue
        mode = r.get("mode", "percent")
        value = float(r.get("value") or 0)
        cats = r.get("per_category") or None
        if mode == "fixed":
            amount = round(value * float((per_category or {}).get("seats") or 1), 2)
        else:
            amount = round(base_amount * value, 2)
        if cats and per_category:
            amount = 0.0
            for cat in ("adult", "child", "infant"):
                n = int((per_category or {}).get(cat) or 0)
                if not n:
                    continue
                cv = cats.get(cat)
                if cv is None:
                    cv = value
                amount += (float(cv) * n) if mode == "fixed" else 0.0
            if mode == "percent":
                amount = round(base_amount * value, 2)
            amount = round(amount, 2)
        return {
            "rule_id": str(r["_id"]), "rule_name": r.get("name"), "mode": mode,
            "value": value, "charge_side": r.get("charge_side", "buyer"),
            "amount": amount, "per_category": cats,
            "resolved_at": now_iso(), "source": "rule",
        }
    return default


# ---------------- CRUD ----------------
class Scope(BaseModel):
    buyer_type: str = "any"       # office | individual | any
    currency: str = "any"         # SAR | USD | any
    package_type: str = "any"     # umrah | tourism | any
    source: str = "any"           # meraaj | rahal | any
    seller_id: str = ""
    package_id: str = ""


class RuleIn(BaseModel):
    name: str = Field(min_length=2)
    mode: str = "percent"         # percent | fixed
    value: float = Field(ge=0)
    charge_side: str = "buyer"    # buyer | seller | split
    per_category: Optional[dict] = None   # {"adult":..,"child":..,"infant":..}
    scope: Scope = Scope()
    priority: int = 0
    active: bool = True
    note: str = ""


@router.get("/commission-rules")
async def list_rules(admin: dict = Depends(require_admin)):
    docs = await db.commission_rules.find({}).sort("priority", -1).to_list(500)
    return {"default_pct": platform_pct(), "rules": serialize(docs)}


@router.post("/commission-rules")
async def create_rule(payload: RuleIn, admin: dict = Depends(require_admin)):
    if payload.mode not in MODES:
        raise HTTPException(400, "نوع العمولة غير صالح")
    if payload.charge_side not in SIDES:
        raise HTTPException(400, "جهة الخصم غير صالحة")
    if payload.mode == "percent" and payload.value > 1:
        raise HTTPException(400, "النسبة يجب أن تكون كسراً (مثال 0.10 = 10%)")
    doc = payload.model_dump()
    doc["scope"] = payload.scope.model_dump()
    doc.update({"created_by": str(admin["_id"]), "created_at": now_iso(), "updated_at": now_iso()})
    res = await db.commission_rules.insert_one(doc)
    doc["_id"] = res.inserted_id
    await db.commission_events.insert_one({
        "rule_id": str(res.inserted_id), "action": "created", "by": admin.get("email"),
        "snapshot": {k: v for k, v in doc.items() if k != "_id"}, "at": now_iso()})
    return serialize(doc)


@router.patch("/commission-rules/{rule_id}")
async def update_rule(rule_id: str, payload: RuleIn, admin: dict = Depends(require_admin)):
    old = await db.commission_rules.find_one({"_id": oid(rule_id)})
    if not old:
        raise HTTPException(404, "القاعدة غير موجودة")
    doc = payload.model_dump()
    doc["scope"] = payload.scope.model_dump()
    doc["updated_at"] = now_iso()
    await db.commission_rules.update_one({"_id": old["_id"]}, {"$set": doc})
    await db.commission_events.insert_one({
        "rule_id": rule_id, "action": "updated", "by": admin.get("email"),
        "before": {k: old.get(k) for k in ("name", "mode", "value", "charge_side", "active", "scope", "priority")},
        "after": {k: doc.get(k) for k in ("name", "mode", "value", "charge_side", "active", "scope", "priority")},
        "at": now_iso()})
    return serialize(await db.commission_rules.find_one({"_id": old["_id"]}))


@router.delete("/commission-rules/{rule_id}")
async def delete_rule(rule_id: str, admin: dict = Depends(require_admin)):
    r = await db.commission_rules.find_one_and_update(
        {"_id": oid(rule_id)}, {"$set": {"active": False, "archived_at": now_iso()}}, return_document=True)
    if not r:
        raise HTTPException(404, "القاعدة غير موجودة")
    await db.commission_events.insert_one({
        "rule_id": rule_id, "action": "deactivated", "by": admin.get("email"), "at": now_iso()})
    return {"ok": True}


@router.get("/commission-events")
async def rule_events(rule_id: Optional[str] = None, admin: dict = Depends(require_admin)):
    f = {"rule_id": rule_id} if rule_id else {}
    docs = await db.commission_events.find(f).sort("at", -1).to_list(500)
    return serialize(docs)


class PreviewIn(BaseModel):
    buyer_type: str = "office"
    currency: CurrencyField = "SAR"
    package_type: str = "umrah"
    source: str = "meraaj"
    base_amount: float = 1000.0
    seats: int = 1


@router.post("/commission-rules/preview")
async def preview(payload: PreviewIn, admin: dict = Depends(require_admin)):
    snap = await resolve_commission(
        buyer_type=payload.buyer_type, currency=payload.currency,
        package={"type": payload.package_type, "source": payload.source, "_id": None},
        seller_id="", base_amount=payload.base_amount,
        per_category={"seats": payload.seats})
    return snap


# ---------------- manual override on a live booking ----------------
class OverrideIn(BaseModel):
    new_platform_fee: float = Field(ge=0)
    reason: str = Field(min_length=5)


@router.post("/bookings/{booking_id}/commission-override")
async def override_commission(booking_id: str, payload: OverrideIn, admin: dict = Depends(require_admin)):
    """Manual commission adjustment: requires a reason, writes an audit entry and a real
    ledger movement (the difference is charged to / refunded from the buyer's wallet).
    Blocked for settled, cancelled or B2C bookings."""
    b = await db.bookings.find_one({"_id": oid(booking_id)})
    if not b:
        raise HTTPException(404, "الحجز غير موجود")
    if b.get("settled") or b.get("status") == "cancelled":
        raise HTTPException(400, "لا يمكن تعديل عمولة حجز مُسوّى أو ملغى")
    if b.get("buyer_type") != "office":
        raise HTTPException(400, "التعديل اليدوي متاح لحجوزات المكاتب فقط")
    cur = b.get("currency", "USD")
    old_fee = round(float(b.get("platform_fee") or 0), 2)
    new_fee = round(payload.new_platform_fee, 2)
    delta = round(new_fee - old_fee, 2)
    if abs(delta) < 0.01:
        raise HTTPException(400, "لا يوجد فرق في العمولة")
    buyer = await db.users.find_one({"_id": oid(b["buyer_id"])})
    if delta > 0 and wallet_available(buyer.get("wallet") or {}, cur) < delta:
        raise HTTPException(400, "رصيد المشتري غير كافٍ لتحمّل الزيادة")
    await adjust_wallet(oid(b["buyer_id"]), cur, available=-delta, total=-delta)
    await log_txn(b["buyer_id"], "commission_adjustment", -delta,
                  f"تعديل عمولة المنصة: {b['package_title']}", booking_id, currency=cur)
    await log_platform_revenue(delta, f"تعديل يدوي لعمولة المنصة: {b['package_title']}",
                               booking_id, currency=cur)
    await db.bookings.update_one({"_id": b["_id"]}, {"$set": {
        "platform_fee": new_fee,
        "amount_charged": round(float(b.get("amount_charged") or 0) + delta, 2),
        "commission_override": {"old": old_fee, "new": new_fee, "delta": delta,
                                "reason": payload.reason.strip(),
                                "by": admin.get("email"), "at": now_iso()}}})
    await audit(booking_id, "commission_override", "super_admin", actor_id=str(admin["_id"]),
                reason=payload.reason.strip(), meta={"old": old_fee, "new": new_fee, "delta": delta})
    return {"ok": True, "old": old_fee, "new": new_fee, "delta": delta}
