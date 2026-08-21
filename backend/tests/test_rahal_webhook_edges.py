"""Edge/robustness probes for the Rahal inbound webhook (diagnosability + error handling)."""
import json
import uuid

import requests
import pytest
from pymongo import MongoClient
from dotenv import dotenv_values

from conftest import API, RAHAL_SECRET
from test_rahal_inbound_sync import sign, post_webhook, share_pkg, WEBHOOK, db_status

backend_env = dotenv_values("/app/backend/.env")
mongo_client = MongoClient(backend_env.get("MONGO_URL"))
mdb = mongo_client[backend_env.get("DB_NAME")]


def test_duplicate_body_log_handled_flag():
    """Same exact body delivered twice (Rahal retry) — both log rows should reflect handled state."""
    ref = f"TEST-QA-DUP-{uuid.uuid4().hex[:8]}"
    share_pkg(ref)
    body = {"event": "package.deleted", "package_ref": ref, "occurred_at": "2026-07-01T00:00:00Z"}
    try:
        post_webhook(body)
        post_webhook(body)
        logs = list(mdb.rahal_inbound_log.find({"package_ref": ref}))
        assert len(logs) == 2, f"expected 2 log rows, got {len(logs)}"
        unhandled = [l for l in logs if not l.get("handled")]
        assert not unhandled, ("duplicate delivery left a log row with handled=false although it was "
                               "processed (update_one matches by body, hitting only the first row)")
    finally:
        mdb.packages.delete_many({"rahal_ref": ref})
        mdb.rahal_inbound_log.delete_many({"package_ref": ref})


def test_malformed_json_body():
    raw = b"{not-json"
    r = requests.post(WEBHOOK, data=raw,
                      headers={"Content-Type": "application/json", "X-Rahal-Signature": sign(raw)})
    assert r.status_code in (400, 422), f"malformed JSON returned {r.status_code}: {r.text[:200]}"


def test_event_without_package_ref():
    raw_body = {"event": "package.deleted", "occurred_at": "x"}
    r = post_webhook(raw_body)
    assert r.status_code in (200, 400), r.text[:200]
    mdb.rahal_inbound_log.delete_many({"event": "package.deleted", "package_ref": None})
