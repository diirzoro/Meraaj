"""Batch 3 — Unified traveler & document center (Super Admin).
Read/oversight + guarded delete. Travelers are aggregated from bookings by passport number,
so nothing in the booking schema changes.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from db import db, serialize, oid, now_iso, audit
from security import require_admin
from storage import get_storage

router = APIRouter(prefix="/api/admin", tags=["admin-travelers"])

REQUIRED_DOCS = ("passport", "visa")
DOC_LABEL = {"passport": "جواز", "visa": "تأشيرة", "ticket": "تذكرة",
             "authorization": "تفويض", "receipt": "إيصال", "voucher": "سند",
             "photo": "صورة", "other": "أخرى"}


def _today():
    return datetime.now(timezone.utc).date()


def _passport_state(expiry: Optional[str]) -> dict:
    if not expiry:
        return {"level": "unknown", "label": "تاريخ الانتهاء غير مسجّل", "days": None}
    try:
        d = datetime.fromisoformat(str(expiry)[:10]).date()
    except Exception:
        return {"level": "unknown", "label": "تاريخ غير صالح", "days": None}
    days = (d - _today()).days
    if days < 0:
        return {"level": "expired", "label": "الجواز منتهي", "days": days}
    if days < 180:
        return {"level": "warning", "label": "أقل من 6 أشهر للانتهاء", "days": days}
    return {"level": "ok", "label": "سليم", "days": days}


@router.get("/travelers")
async def travelers(q: Optional[str] = None, missing_only: bool = False,
                    passport_issue: bool = False, duplicates_only: bool = False,
                    page: int = 1, limit: int = Query(25, le=100),
                    admin: dict = Depends(require_admin)):
    match = {}
    if q:
        match["$or"] = [{"registrants.name": {"$regex": q, "$options": "i"}},
                        {"registrants.passport_no": {"$regex": q, "$options": "i"}},
                        {"package_title": {"$regex": q, "$options": "i"}}]
    bookings = await db.bookings.find(match, {
        "registrants": 1, "package_id": 1, "package_title": 1, "status": 1, "currency": 1,
        "buyer_office_name": 1, "seller_office_name": 1, "departure_date": 1,
        "created_at": 1}).sort("created_at", -1).to_list(3000)

    docs_by_booking = {}
    async for d in db.traveler_documents.find({}, {"booking_id": 1, "registrant_index": 1,
                                                   "doc_type": 1, "filename": 1, "size": 1,
                                                   "created_at": 1}):
        docs_by_booking.setdefault(d["booking_id"], []).append(d)

    people = {}
    for b in bookings:
        bid = str(b["_id"])
        for i, r in enumerate(b.get("registrants") or []):
            pno = (r.get("passport_no") or "").strip().upper()
            key = pno or f"NOPASS::{(r.get('name') or '').strip()}::{bid}::{i}"
            docs = [x for x in docs_by_booking.get(bid, []) if x.get("registrant_index") == i]
            have = {x["doc_type"] for x in docs}
            missing = [t for t in REQUIRED_DOCS if t not in have]
            entry = people.setdefault(key, {
                "key": key, "passport_no": pno or None, "name": r.get("name"),
                "nationality": r.get("nationality"), "category": r.get("category") or "adult",
                "passport_expiry": r.get("passport_expiry") or r.get("passport_expiry_date"),
                "bookings": [], "documents_count": 0, "missing_documents": [],
            })
            entry["bookings"].append({
                "booking_id": bid, "package_title": b.get("package_title"),
                "package_id": b.get("package_id"), "status": b.get("status"),
                "buyer": b.get("buyer_office_name"), "seller": b.get("seller_office_name"),
                "departure_date": b.get("departure_date"), "registrant_index": i,
                "documents": [{"id": str(x["_id"]), "doc_type": x["doc_type"],
                               "label": DOC_LABEL.get(x["doc_type"], x["doc_type"]),
                               "filename": x.get("filename"), "size": x.get("size")} for x in docs],
                "missing": missing,
            })
            entry["documents_count"] += len(docs)
            for m in missing:
                if m not in entry["missing_documents"]:
                    entry["missing_documents"].append(m)
            if not entry.get("passport_expiry") and r.get("passport_expiry"):
                entry["passport_expiry"] = r.get("passport_expiry")

    out = []
    for e in people.values():
        e["passport_status"] = _passport_state(e.get("passport_expiry"))
        e["bookings_count"] = len(e["bookings"])
        e["is_duplicate"] = bool(e["passport_no"]) and len(e["bookings"]) > 1
        e["missing_labels"] = [DOC_LABEL.get(m, m) for m in e["missing_documents"]]
        out.append(e)

    if missing_only:
        out = [e for e in out if e["missing_documents"]]
    if passport_issue:
        out = [e for e in out if e["passport_status"]["level"] in ("expired", "warning", "unknown")]
    if duplicates_only:
        out = [e for e in out if e["is_duplicate"]]

    out.sort(key=lambda x: (-len(x["missing_documents"]), x["name"] or ""))
    total = len(out)
    start = max(0, (page - 1) * limit)
    return {
        "items": out[start:start + limit], "total": total, "page": page, "limit": limit,
        "stats": {
            "travelers": total,
            "with_missing_docs": sum(1 for e in out if e["missing_documents"]),
            "expired_passports": sum(1 for e in out if e["passport_status"]["level"] == "expired"),
            "expiring_passports": sum(1 for e in out if e["passport_status"]["level"] == "warning"),
            "duplicates": sum(1 for e in out if e["is_duplicate"]),
        },
        "doc_labels": DOC_LABEL,
        "limits": {"per_file_mb": 10, "per_batch_mb": 20},
    }


@router.get("/documents")
async def all_documents(q: Optional[str] = None, doc_type: Optional[str] = None,
                        page: int = 1, limit: int = Query(50, le=200),
                        admin: dict = Depends(require_admin)):
    f = {}
    if doc_type:
        f["doc_type"] = doc_type
    if q:
        f["$or"] = [{"registrant_name": {"$regex": q, "$options": "i"}},
                    {"passport_no": {"$regex": q, "$options": "i"}},
                    {"filename": {"$regex": q, "$options": "i"}}]
    total = await db.traveler_documents.count_documents(f)
    docs = await db.traveler_documents.find(f).sort("created_at", -1) \
        .skip(max(0, (page - 1) * limit)).limit(limit).to_list(limit)
    items = serialize(docs)
    for d in items:
        d["label"] = DOC_LABEL.get(d.get("doc_type"), d.get("doc_type"))
    return {"items": items, "total": total, "page": page, "limit": limit, "doc_labels": DOC_LABEL}


class DocDeleteIn(BaseModel):
    reason: str = Field(min_length=5)


@router.post("/documents/{doc_id}/delete")
async def admin_delete_document(doc_id: str, payload: DocDeleteIn,
                                admin: dict = Depends(require_admin)):
    """Permanent delete requires a reason and always writes an audit entry."""
    d = await db.traveler_documents.find_one({"_id": oid(doc_id)})
    if not d:
        raise HTTPException(404, "المستند غير موجود")
    try:
        await get_storage().delete(d["object_key"])
    except Exception:
        pass
    await db.traveler_documents.delete_one({"_id": d["_id"]})
    await db.audit_log.insert_one({
        "entity": "document", "entity_id": doc_id, "action": "document_deleted",
        "actor": admin.get("email"), "actor_id": str(admin["_id"]),
        "reason": payload.reason.strip(),
        "before": {"filename": d.get("filename"), "doc_type": d.get("doc_type"),
                   "booking_id": d.get("booking_id"), "passport_no": d.get("passport_no")},
        "at": now_iso()})
    await audit(d.get("booking_id"), "document_deleted_by_admin", "super_admin",
                actor_id=str(admin["_id"]), reason=payload.reason.strip(),
                meta={"doc_type": d.get("doc_type"), "filename": d.get("filename")})
    return {"ok": True}


@router.get("/passport-alerts")
async def passport_alerts(days: int = 180, admin: dict = Depends(require_admin)):
    limit_date = (_today() + timedelta(days=days)).isoformat()
    out = []
    async for b in db.bookings.find({"status": {"$ne": "cancelled"}},
                                    {"registrants": 1, "package_title": 1, "departure_date": 1}):
        for i, r in enumerate(b.get("registrants") or []):
            exp = r.get("passport_expiry")
            if exp and str(exp)[:10] <= limit_date:
                st = _passport_state(exp)
                out.append({"booking_id": str(b["_id"]), "package_title": b.get("package_title"),
                            "name": r.get("name"), "passport_no": r.get("passport_no"),
                            "passport_expiry": exp, "status": st,
                            "departure_date": b.get("departure_date")})
    out.sort(key=lambda x: str(x["passport_expiry"]))
    return {"items": out[:300], "total": len(out), "threshold_days": days}
