from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from db import db, serialize, oid, now_iso, adjust_wallet, log_txn, wallet_available, CurrencyField
from security import require_buyer
from datetime import datetime, timezone

router = APIRouter(prefix="/api/wallet", tags=["wallet"])


@router.get("")
async def get_wallet(user: dict = Depends(require_buyer)):
    fresh = await db.users.find_one({"_id": user["_id"]})
    return fresh["wallet"]


@router.get("/transactions")
async def transactions(user: dict = Depends(require_buyer)):
    docs = await db.transactions.find({"office_id": str(user["_id"])}).sort("created_at", -1).to_list(300)
    return serialize(docs)


class TopupInput(BaseModel):
    amount: float = Field(gt=0)
    currency: CurrencyField = "SAR"  # SAR | USD
    method: str
    receipt_url: str


@router.post("/topups")
async def create_topup(payload: TopupInput, user: dict = Depends(require_buyer)):
    currency = payload.currency
    # Guard against duplicate submissions (flaky network / repeated clicks):
    # reject an identical pending topup (same amount+currency) created within the last 2 minutes.
    recent = await db.topups.find_one(
        {"office_id": str(user["_id"]), "amount": round(payload.amount, 2),
         "currency": currency, "status": "pending"},
        sort=[("created_at", -1)])
    if recent and recent.get("created_at"):
        try:
            prev = datetime.fromisoformat(recent["created_at"])
            if prev.tzinfo is None:
                prev = prev.replace(tzinfo=timezone.utc)
            within = (datetime.now(timezone.utc) - prev).total_seconds() < 120
        except (ValueError, TypeError):
            within = True
        if within:
            raise HTTPException(409, "لديك طلب شحن بنفس المبلغ قيد المعالجة")
    doc = {
        "office_id": str(user["_id"]),
        "office_name": user["office_name"],
        "amount": round(payload.amount, 2),   # credited in its own currency on approval
        "currency": currency,
        "method": payload.method,
        "receipt_url": payload.receipt_url,
        "status": "pending",
        "created_at": now_iso(),
    }
    res = await db.topups.insert_one(doc)
    doc["_id"] = res.inserted_id
    return serialize(doc)


@router.get("/topups")
async def my_topups(user: dict = Depends(require_buyer)):
    docs = await db.topups.find({"office_id": str(user["_id"])}).sort("created_at", -1).to_list(200)
    return serialize(docs)


class TransferInput(BaseModel):
    to_email: str
    amount: float = Field(gt=0)
    currency: CurrencyField = "USD"  # SAR | USD
    note: str = ""


@router.post("/transfers")
async def create_transfer(payload: TransferInput, user: dict = Depends(require_buyer)):
    currency = payload.currency
    target = await db.users.find_one({"email": payload.to_email.lower(), "role": {"$in": ["office", "individual"]}})
    if not target:
        raise HTTPException(404, "المكتب المستلم غير موجود")
    if str(target["_id"]) == str(user["_id"]):
        raise HTTPException(400, "لا يمكن التحويل لنفس الحساب")
    fresh = await db.users.find_one({"_id": user["_id"]})
    if wallet_available(fresh["wallet"], currency) < payload.amount:
        raise HTTPException(400, f"الرصيد المتاح غير كافٍ ({currency})")
    doc = {
        "from_office_id": str(user["_id"]),
        "from_office_name": user["office_name"],
        "to_office_id": str(target["_id"]),
        "to_office_name": target["office_name"],
        "amount": round(payload.amount, 2),
        "currency": currency,
        "note": payload.note,
        "status": "pending",
        "created_at": now_iso(),
    }
    res = await db.transfers.insert_one(doc)
    doc["_id"] = res.inserted_id
    return serialize(doc)


@router.get("/transfers")
async def my_transfers(user: dict = Depends(require_buyer)):
    uid = str(user["_id"])
    docs = await db.transfers.find({"$or": [{"from_office_id": uid}, {"to_office_id": uid}]}).sort("created_at", -1).to_list(200)
    return serialize(docs)


class WithdrawalInput(BaseModel):
    amount: float = Field(gt=0)
    currency: CurrencyField = "USD"  # SAR | USD
    method: str
    details: str


@router.post("/withdrawals")
async def create_withdrawal(payload: WithdrawalInput, user: dict = Depends(require_buyer)):
    currency = payload.currency
    fresh = await db.users.find_one({"_id": user["_id"]})
    if wallet_available(fresh["wallet"], currency) < payload.amount:
        raise HTTPException(400, f"الرصيد المتاح غير كافٍ ({currency})")
    doc = {
        "office_id": str(user["_id"]),
        "office_name": user["office_name"],
        "amount": round(payload.amount, 2),
        "currency": currency,
        "method": payload.method,
        "details": payload.details,
        "status": "pending",
        "created_at": now_iso(),
    }
    res = await db.withdrawals.insert_one(doc)
    doc["_id"] = res.inserted_id
    return serialize(doc)


@router.get("/withdrawals")
async def my_withdrawals(user: dict = Depends(require_buyer)):
    docs = await db.withdrawals.find({"office_id": str(user["_id"])}).sort("created_at", -1).to_list(200)
    return serialize(docs)
