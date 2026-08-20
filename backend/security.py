import os
import jwt
import bcrypt
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Request, Response, Depends
from pydantic import BaseModel, EmailStr, Field
from db import db, serialize, oid, now_iso

JWT_ALGORITHM = "HS256"
LOCK_THRESHOLD = 5
LOCK_MINUTES = 15
router = APIRouter(prefix="/api/auth", tags=["auth"])


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def _secret() -> str:
    return os.environ["JWT_SECRET"]


def create_access_token(user_id: str, email: str, role: str) -> str:
    payload = {"sub": user_id, "email": email, "role": role,
               "exp": datetime.now(timezone.utc) + timedelta(days=7), "type": "access"}
    return jwt.encode(payload, _secret(), algorithm=JWT_ALGORITHM)


async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="غير مصرح بالدخول")
    try:
        payload = jwt.decode(token, _secret(), algorithms=[JWT_ALGORITHM])
        user = await db.users.find_one({"_id": oid(payload["sub"])})
        if not user:
            raise HTTPException(status_code=401, detail="المستخدم غير موجود")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="انتهت صلاحية الجلسة")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="جلسة غير صالحة")


async def require_office(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "office":
        raise HTTPException(status_code=403, detail="هذه العملية متاحة للمكاتب فقط")
    if user.get("status") != "active":
        raise HTTPException(status_code=403, detail="حساب المكتب غير مفعّل أو موقوف")
    return user


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="صلاحيات الإدارة مطلوبة")
    return user


class RegisterInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    office_name: str
    owner_name: str
    phone: str
    governorate: str
    address: str


class LoginInput(BaseModel):
    email: EmailStr
    password: str


def _set_cookie(response: Response, token: str):
    response.set_cookie(key="access_token", value=token, httponly=True,
                        secure=True, samesite="none", max_age=604800, path="/")


@router.post("/register")
async def register(payload: RegisterInput, response: Response):
    email = payload.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="البريد الإلكتروني مستخدم مسبقاً")
    doc = {
        "email": email,
        "password_hash": hash_password(payload.password),
        "role": "office",
        "office_name": payload.office_name,
        "owner_name": payload.owner_name,
        "phone": payload.phone,
        "governorate": payload.governorate,
        "address": payload.address,
        "status": "active",
        "wallet": {"total": 0.0, "pending": 0.0, "available": 0.0},
        "created_at": now_iso(),
    }
    res = await db.users.insert_one(doc)
    token = create_access_token(str(res.inserted_id), email, "office")
    _set_cookie(response, token)
    doc["_id"] = res.inserted_id
    return {"user": serialize(doc), "access_token": token}


@router.post("/login")
async def login(payload: LoginInput, response: Response):
    email = payload.email.lower()
    now = datetime.now(timezone.utc)
    rec = await db.login_attempts.find_one({"email": email})
    if rec and rec.get("locked_until"):
        if datetime.fromisoformat(rec["locked_until"]) > now:
            raise HTTPException(status_code=429, detail="تم تجاوز عدد المحاولات المسموحة. حاول مجدداً بعد قليل.")
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(payload.password, user["password_hash"]):
        count = (rec.get("count", 0) if rec else 0) + 1
        update = {"count": count, "updated_at": now.isoformat()}
        if count >= LOCK_THRESHOLD:
            update["locked_until"] = (now + timedelta(minutes=LOCK_MINUTES)).isoformat()
            update["count"] = 0
        await db.login_attempts.update_one({"email": email}, {"$set": update}, upsert=True)
        raise HTTPException(status_code=401, detail="بيانات الدخول غير صحيحة")
    if rec:
        await db.login_attempts.delete_one({"email": email})
    token = create_access_token(str(user["_id"]), email, user["role"])
    _set_cookie(response, token)
    return {"user": serialize(user), "access_token": token}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    return {"ok": True}


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    return serialize(user)


async def seed_admin():
    email = os.environ["ADMIN_EMAIL"].lower()
    password = os.environ["ADMIN_PASSWORD"]
    existing = await db.users.find_one({"email": email})
    if existing is None:
        await db.users.insert_one({
            "email": email,
            "password_hash": hash_password(password),
            "role": "super_admin",
            "office_name": "Target Media",
            "owner_name": "الإدارة العليا",
            "phone": "",
            "governorate": "",
            "address": "",
            "status": "active",
            "wallet": {"total": 0.0, "pending": 0.0, "available": 0.0},
            "created_at": now_iso(),
        })
    elif not verify_password(password, existing["password_hash"]):
        await db.users.update_one({"email": email},
                                  {"$set": {"password_hash": hash_password(password), "role": "super_admin"}})
