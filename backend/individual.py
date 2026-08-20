import os
import secrets
from fastapi import APIRouter, HTTPException, Depends
from db import db, serialize
from security import get_current_user

router = APIRouter(prefix="/api/individual", tags=["individual"])


async def require_individual(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "individual":
        raise HTTPException(status_code=403, detail="هذه الميزة متاحة للأفراد فقط")
    return user


def _gen_code() -> str:
    return secrets.token_hex(4).upper()


@router.post("/become-marketer")
async def become_marketer(user: dict = Depends(require_individual)):
    fresh = await db.users.find_one({"_id": user["_id"]})
    if fresh.get("is_marketer") and fresh.get("affiliate_code"):
        return {"is_marketer": True, "affiliate_code": fresh["affiliate_code"]}
    code = _gen_code()
    while await db.users.find_one({"affiliate_code": code}):
        code = _gen_code()
    await db.users.update_one({"_id": user["_id"]},
                              {"$set": {"is_marketer": True, "affiliate_code": code}})
    return {"is_marketer": True, "affiliate_code": code}


@router.get("/affiliate")
async def affiliate(user: dict = Depends(require_individual)):
    fresh = await db.users.find_one({"_id": user["_id"]})
    code = fresh.get("affiliate_code")
    base = os.environ.get("FRONTEND_URL", "")
    link = f"{base}/?ref={code}" if code else None
    txns = await db.transactions.find(
        {"office_id": str(user["_id"]), "type": "marketer_commission"}
    ).sort("created_at", -1).to_list(200)
    total_earned = round(sum(t["amount"] for t in txns), 2)
    return {
        "is_marketer": bool(fresh.get("is_marketer")),
        "affiliate_code": code,
        "link": link,
        "total_earned": total_earned,
        "transactions": serialize(txns),
    }
