import os
import uuid
import jwt
import bcrypt
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Request, Response, Depends
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from db import db, serialize, oid, now_iso, empty_wallet

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
    now = datetime.now(timezone.utc)
    payload = {"sub": user_id, "email": email, "role": role, "iat": int(now.timestamp()),
               "jti": uuid.uuid4().hex, "exp": now + timedelta(days=7), "type": "access"}
    return jwt.encode(payload, _secret(), algorithm=JWT_ALGORITHM)


def token_jti(token: str) -> Optional[str]:
    try:
        return jwt.decode(token, _secret(), algorithms=[JWT_ALGORITHM]).get("jti")
    except jwt.InvalidTokenError:
        return None


async def record_session(user: dict, request: Optional[Request] = None,
                         source: str = "password", token: Optional[str] = None):
    """Session bookkeeping for the admin security screen. Never blocks a login.
    The token's `jti` is stored so an admin force-logout can revoke that exact token."""
    try:
        ip = ua = ""
        if request is not None:
            ip = request.headers.get("x-forwarded-for", "") or (request.client.host if request.client else "")
            ua = request.headers.get("user-agent", "")[:250]
        await db.sessions.insert_one({
            "user_id": str(user["_id"]), "email": user.get("email"),
            "role": user.get("role"), "source": source, "ip": ip, "user_agent": ua,
            "jti": token_jti(token) if token else None,
            "revoked": False, "created_at": now_iso(), "last_seen": now_iso()})
    except Exception:
        pass


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
        forced = user.get("force_logout_at")
        if payload.get("jti"):
            # Exact-token revocation (admin force-logout / suspend revokes the session rows),
            # so a NEW login right after a force-logout is immediately valid.
            revoked = await db.sessions.find_one({"jti": payload["jti"], "revoked": True},
                                                 {"_id": 1})
            if revoked:
                raise HTTPException(status_code=401, detail="تم إنهاء الجلسة من الإدارة")
        elif forced and payload.get("iat"):
            # Legacy tokens issued before `jti` existed: fall back to the timestamp epoch.
            try:
                if datetime.fromisoformat(forced).timestamp() > float(payload["iat"]):
                    raise HTTPException(status_code=401, detail="تم إنهاء الجلسة من الإدارة")
            except (ValueError, TypeError):
                pass
        if user.get("parent_office_id"):
            # Staff account: acts INSIDE the office identity, so it shares the office wallet,
            # ledger and bookings. No separate wallet is ever created for staff.
            if user.get("status") != "active":
                raise HTTPException(status_code=403, detail="حساب الموظف معطّل")
            parent = await db.users.find_one({"_id": oid(user["parent_office_id"])})
            if not parent:
                raise HTTPException(status_code=401, detail="المكتب المرتبط غير موجود")
            if parent.get("status") == "suspended":
                raise HTTPException(status_code=403, detail="حساب المكتب معلَّق")
            parent["_acting_staff"] = {
                "id": str(user["_id"]), "email": user.get("email"),
                "name": user.get("staff_name") or user.get("email"),
                "roles": user.get("staff_roles") or [],
            }
            return parent
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


async def require_buyer(user: dict = Depends(get_current_user)) -> dict:
    """Buyer actions are allowed for offices AND individuals."""
    if user.get("role") not in ("office", "individual"):
        raise HTTPException(status_code=403, detail="هذه العملية متاحة للمكاتب والأفراد فقط")
    if user.get("status") != "active":
        raise HTTPException(status_code=403, detail="الحساب غير مفعّل أو موقوف")
    return user


# ---- Rahal-linked office permissions (server-side enforcement) ----
RAHAL_PERMISSIONS = {"manage_packages", "manage_bookings", "approve_reject",
                     "can_refund", "manage_settings"}


def is_rahal_office(user: dict) -> bool:
    return user.get("source") == "rahal" or bool(user.get("rahal_office_ref"))


def require_permission(permission: str):
    """Server-side gate for Rahal-linked offices. A normal Meraaj office is unrestricted
    (backward compatible). A Rahal office with an explicit `rahal_permissions` set is
    enforced strictly; a legacy Rahal office WITHOUT a set (auto-provisioned via share)
    keeps full access until Rahal pushes its permissions."""
    async def dep(user: dict = Depends(require_office)) -> dict:
        if is_rahal_office(user):
            perms = user.get("rahal_permissions")
            if perms is not None and permission not in perms:
                raise HTTPException(status_code=403,
                                    detail="هذه العملية غير مصرّح بها لحساب مكتب رحّال الخاص بك")
        return user
    return dep


async def get_optional_user(request: Request):
    try:
        return await get_current_user(request)
    except HTTPException:
        return None


class RegisterInput(BaseModel):
    account_type: str = "office"  # office | individual
    email: EmailStr
    password: str = Field(min_length=6)
    phone: str
    governorate: str
    # office fields
    office_name: Optional[str] = None
    owner_name: Optional[str] = None
    address: Optional[str] = None
    commercial_license: Optional[str] = None
    # individual field
    name: Optional[str] = None


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
    base = {
        "email": email,
        "password_hash": hash_password(payload.password),
        "phone": payload.phone,
        "governorate": payload.governorate,
        "status": "active",
        "wallet": empty_wallet(),
        "created_at": now_iso(),
    }
    if payload.account_type == "individual":
        if not payload.name:
            raise HTTPException(status_code=400, detail="الاسم مطلوب")
        base.update({
            "role": "individual",
            "office_name": payload.name,   # reused as display name
            "owner_name": payload.name,
            "address": "",
            "is_marketer": False,
            "affiliate_code": None,
        })
        role = "individual"
    else:
        if not (payload.office_name and payload.owner_name):
            raise HTTPException(status_code=400, detail="بيانات المكتب غير مكتملة")
        base.update({
            "role": "office",
            "office_name": payload.office_name,
            "owner_name": payload.owner_name,
            "address": payload.address or "",
            "commercial_license": payload.commercial_license or "",
        })
        role = "office"
    res = await db.users.insert_one(base)
    token = create_access_token(str(res.inserted_id), email, role)
    _set_cookie(response, token)
    base["_id"] = res.inserted_id
    await record_session(base, None, "register", token)
    return {"user": serialize(base), "access_token": token}


@router.post("/login")
async def login(payload: LoginInput, response: Response, request: Request):
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
    if user.get("status") == "suspended":
        raise HTTPException(status_code=403, detail="الحساب معلَّق من إدارة معراج — تواصل مع الدعم")
    token = create_access_token(str(user["_id"]), email, user["role"])
    _set_cookie(response, token)
    await record_session(user, request, "password", token)
    return {"user": serialize(user), "access_token": token}


@router.post("/logout")
async def logout(request: Request, response: Response):
    """Ends the session: the presented token is revoked server-side, so it can never be
    reused even if the cookie/localStorage copy is kept."""
    token = request.cookies.get("access_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else None
    jti = token_jti(token) if token else None
    if jti:
        await db.sessions.update_one({"jti": jti},
                                     {"$set": {"revoked": True, "revoked_at": now_iso()}},
                                     upsert=True)
    response.delete_cookie("access_token", path="/")
    return {"ok": True, "revoked": bool(jti)}


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
            "wallet": empty_wallet(),
            "created_at": now_iso(),
        })
    elif not verify_password(password, existing["password_hash"]):
        await db.users.update_one({"email": email},
                                  {"$set": {"password_hash": hash_password(password), "role": "super_admin"}})
