"""Platform cron endpoints (Batch 6): daily encrypted DB backup + daily alert scan.
Both ack immediately and run the work in a background task.
"""
import hmac
import os
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from db import db, now_iso

router = APIRouter(prefix="/api/cron", tags=["cron"])


def _auth(authorization: str):
    secret = os.environ.get("WEBHOOK_CRON_SECRET")
    if not secret:
        raise HTTPException(401, "cron secret not configured")
    token = (authorization or "").removeprefix("Bearer ").strip()
    if not token or not hmac.compare_digest(token, secret):
        raise HTTPException(401, "unauthorized")


async def _seen(run_id: str, job: str) -> bool:
    if not run_id:
        return False
    res = await db.cron_runs.update_one({"_id": f"{job}:{run_id}"},
                                        {"$setOnInsert": {"at": now_iso(), "job": job}},
                                        upsert=True)
    return res.upserted_id is None


async def _do_backup():
    from enterprise import run_backup, BackupIn
    admin = await db.users.find_one({"role": "super_admin"})
    try:
        await run_backup(BackupIn(reason="نسخة احتياطية يومية مجدولة (Cron)"), admin)
    except Exception as e:
        await db.backups.insert_one({"file": None, "result": "failed", "error": str(e)[:300],
                                     "by": "cron", "reason": "نسخة يومية مجدولة",
                                     "size": 0, "encrypted": False, "at": now_iso()})


async def _do_alerts():
    from orgs import scan_alerts
    admin = await db.users.find_one({"role": "super_admin"})
    try:
        await scan_alerts(admin)
    except Exception:
        pass


@router.post("/backup")
async def cron_backup(request: Request, bg: BackgroundTasks, authorization: str = Header(default=""),
                      x_webhook_id: str = Header(default="")):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    _auth(authorization)
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    run_id = x_webhook_id or (body or {}).get("run_id") or ""
    if await _seen(run_id, "backup"):
        return {"ok": True, "duplicate": True}
    bg.add_task(_do_backup)
    return {"ok": True, "queued": "backup"}


@router.post("/alerts")
async def cron_alerts(request: Request, bg: BackgroundTasks, authorization: str = Header(default=""),
                      x_webhook_id: str = Header(default="")):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    _auth(authorization)
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    run_id = x_webhook_id or (body or {}).get("run_id") or ""
    if await _seen(run_id, "alerts"):
        return {"ok": True, "duplicate": True}
    bg.add_task(_do_alerts)
    return {"ok": True, "queued": "alerts"}
