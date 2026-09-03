"""Traveler documents + cancellation evidence read APIs. Multiple attachments per
traveler per doc_type. Private storage, ownership-scoped authorization, audit trail."""
import time
import uuid
import base64
import mimetypes
import os
import hmac
import hashlib
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Response
from pydantic import BaseModel
from db import db, serialize, oid, now_iso, audit
from security import get_current_user
from storage import get_storage, MAX_FILE_BYTES, ALLOWED_MIME

PER_FILE_BYTES = min(MAX_FILE_BYTES, 10 * 1024 * 1024)
BATCH_BYTES = 20 * 1024 * 1024
from integration import notify_rahal

router = APIRouter(prefix="/api", tags=["documents"])

DOC_TYPES = {"passport", "visa", "photo", "ticket", "other"}


async def _booking_party(booking_id: str, user: dict) -> dict:
    """Load a booking only if the caller is its buyer or seller (tenant isolation)."""
    b = await db.bookings.find_one({"_id": oid(booking_id)})
    if not b or str(user["_id"]) not in (b.get("buyer_id"), b.get("seller_id")):
        raise HTTPException(404, "الحجز غير موجود")
    return b


async def _authorized_doc(doc_id: str, user: dict):
    d = await db.traveler_documents.find_one({"_id": oid(doc_id)})
    if not d:
        raise HTTPException(404, "المستند غير موجود")
    b = await db.bookings.find_one({"_id": oid(d["booking_id"])})
    if not b or (user.get("role") != "super_admin"
                 and str(user["_id"]) not in (b.get("buyer_id"), b.get("seller_id"))):
        raise HTTPException(404, "المستند غير موجود")
    return d, b


def _doc_signing_secret():
    return (
        os.getenv("JWT_SECRET")
        or os.getenv("MERAAJ_SHARED_SECRET")
        or os.getenv("RAHAL_SHARED_SECRET")
        or ""
    )


def _signed_document_url(doc_id: str, expires_in: int = 72 * 3600) -> str:
    base = (
        os.getenv("MERAAJ_PUBLIC_BASE_URL")
        or os.getenv("FRONTEND_URL")
        or ""
    ).rstrip("/")

    secret = _doc_signing_secret()
    if not base or not secret:
        return ""

    exp = int(time.time()) + expires_in
    msg = f"doc:{doc_id}:{exp}".encode()
    sig = hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()

    return f"{base}/api/documents/{doc_id}/signed?exp={exp}&sig={sig}"


async def _notify_docs(b: dict):
    """Push the full per-registrant document set to Rahal using the REAL booking_ref."""
    docs = await db.traveler_documents.find({"booking_id": str(b["_id"])}).to_list(2000)
    by_idx = {}
    for d in docs:
        idx = d["registrant_index"]
        reg = (b.get("registrants") or [])[idx] if idx < len(b.get("registrants") or []) else {}
        by_idx.setdefault(idx, []).append({
            "type": d["doc_type"],
            "file_ref": str(d["_id"]),
            "label": d["filename"],
            "filename": d["filename"],
            "url": _signed_document_url(str(d["_id"])),
            "passport_no": d.get("passport_no") or reg.get("passport_no"),
            "registrant_name": reg.get("name"),
            "download_ref": f"/api/documents/{d['_id']}/download"
        })
    registrants = [{"index": i, "documents": by_idx.get(i, [])}
                   for i in range(len(b.get("registrants", [])))]
    await notify_rahal("meraaj.booking.documents_updated", {}, envelope={
        "id": str(uuid.uuid4()), "type": "meraaj.booking.documents_updated",
        "timestamp": int(time.time()),
        "data": {"package_ref": b.get("rahal_ref"), "booking_ref": str(b["_id"]),
                 "registrants": registrants}})


class DocIn(BaseModel):
    registrant_index: int
    doc_type: str
    filename: str
    content_base64: str
    passport_no: Optional[str] = None
    batch_total_bytes: Optional[int] = None


@router.post("/bookings/{booking_id}/documents")
async def upload_document(booking_id: str, payload: DocIn, user: dict = Depends(get_current_user)):
    b = await _booking_party(booking_id, user)
    if payload.doc_type not in DOC_TYPES:
        raise HTTPException(400, "نوع مستند غير صالح")
    regs = b.get("registrants", [])
    if payload.registrant_index < 0 or payload.registrant_index >= len(regs):
        raise HTTPException(400, "المسافر غير موجود")
    try:
        raw = base64.b64decode(payload.content_base64.split(",")[-1])
    except Exception:
        raise HTTPException(400, "محتوى الملف غير صالح")
    if len(raw) == 0 or len(raw) > PER_FILE_BYTES:
        raise HTTPException(400, "حجم الملف يتجاوز 10 ميجابايت للملف الواحد أو أنه فارغ")
    if payload.batch_total_bytes and payload.batch_total_bytes > BATCH_BYTES:
        raise HTTPException(400, "حجم الدفعة يتجاوز 20 ميجابايت")
    ct = mimetypes.guess_type(payload.filename)[0] or "application/octet-stream"
    if ct not in ALLOWED_MIME:
        raise HTTPException(400, "نوع الملف غير مدعوم (PDF أو صورة فقط)")
    tenant = b.get("rahal_office_ref") or b.get("seller_id") or "meraaj"
    key = await get_storage().put(raw, ct, prefix=f"docs/{tenant}")
    rec = {
        "booking_id": booking_id, "rahal_ref": b.get("rahal_ref"),
        "registrant_index": payload.registrant_index,
        "registrant_name": regs[payload.registrant_index].get("name"),
        "doc_type": payload.doc_type, "filename": payload.filename,
        "passport_no": payload.passport_no,
        "object_key": key, "mime": ct, "size": len(raw),
        "tenant_office_id": b.get("seller_id"), "buyer_id": b.get("buyer_id"),
        "uploaded_by": str(user["_id"]), "created_at": now_iso(),
    }
    res = await db.traveler_documents.insert_one(rec)
    rec["_id"] = res.inserted_id
    await audit(booking_id, "document_uploaded", user.get("role", "user"), actor_id=str(user["_id"]),
                meta={"doc_type": payload.doc_type, "registrant_index": payload.registrant_index})
    if b.get("rahal_ref"):
        await _notify_docs(b)
    return serialize(rec)


@router.get("/bookings/{booking_id}/documents")
async def list_documents(booking_id: str, registrant_index: Optional[int] = None,
                         user: dict = Depends(get_current_user)):
    await _booking_party(booking_id, user)
    q = {"booking_id": booking_id}
    if registrant_index is not None:
        q["registrant_index"] = registrant_index
    docs = await db.traveler_documents.find(q).sort("created_at", 1).to_list(2000)
    return serialize(docs)


@router.get("/documents/{doc_id}/signed")
async def download_document_signed(doc_id: str, exp: int, sig: str):
    if exp < int(time.time()):
        raise HTTPException(410, "انتهت صلاحية رابط المستند")

    secret = _doc_signing_secret()
    if not secret:
        raise HTTPException(503, "خدمة مشاركة المستندات غير مهيأة")

    expected = hmac.new(
        secret.encode(),
        f"doc:{doc_id}:{exp}".encode(),
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected, sig):
        raise HTTPException(401, "رابط المستند غير صالح")

    d = await db.traveler_documents.find_one({"_id": oid(doc_id)})
    if not d:
        raise HTTPException(404, "المستند غير موجود")

    try:
        data, ct = await get_storage().get(d["object_key"])
    except FileNotFoundError:
        raise HTTPException(404, "الملف غير متوفر في وحدة التخزين")

    await audit(
        d["booking_id"],
        "document_read_signed",
        "rahal",
        meta={"doc_id": doc_id}
    )

    return Response(
        content=data,
        media_type=ct,
        headers={
            "Content-Disposition": f'inline; filename="{d.get("filename", "file")}"',
            "Cache-Control": "private, no-store"
        }
    )


@router.get("/documents/{doc_id}/download")
async def download_document(doc_id: str, user: dict = Depends(get_current_user)):
    d, _ = await _authorized_doc(doc_id, user)
    try:
        data, ct = await get_storage().get(d["object_key"])
    except FileNotFoundError:
        raise HTTPException(404, "الملف غير متوفر في وحدة التخزين")
    await audit(d["booking_id"], "document_read", user.get("role", "user"),
                actor_id=str(user["_id"]), meta={"doc_id": doc_id})
    return Response(content=data, media_type=ct,
                    headers={"Content-Disposition": f'inline; filename="{d.get("filename", "file")}"'})


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, user: dict = Depends(get_current_user)):
    d, b = await _authorized_doc(doc_id, user)
    await get_storage().delete(d["object_key"])
    await db.traveler_documents.delete_one({"_id": d["_id"]})
    await audit(d["booking_id"], "document_deleted", user.get("role", "user"),
                actor_id=str(user["_id"]), meta={"doc_id": doc_id})
    if b.get("rahal_ref"):
        await _notify_docs(b)
    return {"ok": True}


@router.get("/bookings/{booking_id}/cancellation-evidence")
async def list_cancellation_evidence(booking_id: str, user: dict = Depends(get_current_user)):
    b = await db.bookings.find_one({"_id": oid(booking_id)})
    if not b or (user.get("role") != "super_admin"
                 and str(user["_id"]) not in (b.get("buyer_id"), b.get("seller_id"))):
        raise HTTPException(404, "الحجز غير موجود")
    ev = await db.cancellation_evidence.find({"booking_id": booking_id}).sort("created_at", 1).to_list(500)
    return serialize(ev)
