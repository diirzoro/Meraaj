from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from db import db, serialize, oid, now_iso, adjust_wallet, log_txn
from security import require_office

router = APIRouter(prefix="/api/wallet", tags=["wallet"])


@router.get("")
async def get_wallet(user: dict = Depends(require_office)):
    fresh = await db.users.find_one({"_id": user["_id"]})
    return fresh["wallet"]


@router.get("/transactions")
async def transactions(user: dict = Depends(require_office)):
    docs = await db.transactions.find({"office_id": str(user["_id"])}).sort("created_at", -1).to_list(300)
    return serialize(docs)


class TopupInput(BaseModel):
    amount: float = Field(gt=0)
    method: str
    receipt_url: str


@router.post("/topups")
async def create_topup(payload: TopupInput, user: dict = Depends(require_office)):
    doc = {
        "office_id": str(user["_id"]),
        "office_name": user["office_name"],
        "amount": payload.amount,
        "method": payload.method,
        "receipt_url": payload.receipt_url,
        "status": "pending",
        "created_at": now_iso(),
    }
    res = await db.topups.insert_one(doc)
    doc["_id"] = res.inserted_id
    return serialize(doc)


@router.get("/topups")
async def my_topups(user: dict = Depends(require_office)):
    docs = await db.topups.find({"office_id": str(user["_id"])}).sort("created_at", -1).to_list(200)
    return serialize(docs)


class TransferInput(BaseModel):
    to_email: str
    amount: float = Field(gt=0)
    note: str = ""


@router.post("/transfers")
async def create_transfer(payload: TransferInput, user: dict = Depends(require_office)):
    target = await db.users.find_one({"email": payload.to_email.lower(), "role": "office"})
    if not target:
        raise HTTPException(404, "المكتب المستلم غير موجود")
    if str(target["_id"]) == str(user["_id"]):
        raise HTTPException(400, "لا يمكن التحويل لنفس الحساب")
    fresh = await db.users.find_one({"_id": user["_id"]})
    if fresh["wallet"]["available"] < payload.amount:
        raise HTTPException(400, "الرصيد المتاح غير كافٍ")
    doc = {
        "from_office_id": str(user["_id"]),
        "from_office_name": user["office_name"],
        "to_office_id": str(target["_id"]),
        "to_office_name": target["office_name"],
        "amount": payload.amount,
        "note": payload.note,
        "status": "pending",
        "created_at": now_iso(),
    }
    res = await db.transfers.insert_one(doc)
    doc["_id"] = res.inserted_id
    return serialize(doc)


@router.get("/transfers")
async def my_transfers(user: dict = Depends(require_office)):
    uid = str(user["_id"])
    docs = await db.transfers.find({"$or": [{"from_office_id": uid}, {"to_office_id": uid}]}).sort("created_at", -1).to_list(200)
    return serialize(docs)


class WithdrawalInput(BaseModel):
    amount: float = Field(gt=0)
    method: str
    details: str


@router.post("/withdrawals")
async def create_withdrawal(payload: WithdrawalInput, user: dict = Depends(require_office)):
    fresh = await db.users.find_one({"_id": user["_id"]})
    if fresh["wallet"]["available"] < payload.amount:
        raise HTTPException(400, "الرصيد المتاح غير كافٍ")
    doc = {
        "office_id": str(user["_id"]),
        "office_name": user["office_name"],
        "amount": payload.amount,
        "method": payload.method,
        "details": payload.details,
        "status": "pending",
        "created_at": now_iso(),
    }
    res = await db.withdrawals.insert_one(doc)
    doc["_id"] = res.inserted_id
    return serialize(doc)


@router.get("/withdrawals")
async def my_withdrawals(user: dict = Depends(require_office)):
    docs = await db.withdrawals.find({"office_id": str(user["_id"])}).sort("created_at", -1).to_list(200)
    return serialize(docs)
