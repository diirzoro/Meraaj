"""Batch 1 Enterprise Super Admin panel — analytics, attention queue, orders center,
order detail, internal notes, staff tasks, escalation + protected-path regressions."""
import time
import base64
import hmac
import hashlib
import json
import requests
import pytest

from conftest import API, client, RAHAL_SECRET

SELLER = ("seller@test.com", "Test@1234")
BUYER = ("buyer@test.com", "Test@1234")


def _has_objectid_key(obj) -> bool:
    """True if any dict anywhere in the payload still exposes the raw mongo `_id` key."""
    if isinstance(obj, dict):
        if "_id" in obj:
            return True
        return any(_has_objectid_key(v) for v in obj.values())
    if isinstance(obj, list):
        return any(_has_objectid_key(v) for v in obj)
    return False


def login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"login {email} failed {r.status_code}: {r.text[:200]}"
    return client(r.json()["access_token"])


@pytest.fixture(scope="module")
def office():
    return login(*SELLER)


@pytest.fixture(scope="module")
def anon():
    return client()


# ---------------- AUTHORIZATION ----------------
class TestAuthorization:
    ENDPOINTS = [
        ("GET", "/admin/analytics"),
        ("GET", "/admin/attention"),
        ("GET", "/admin/bookings"),
        ("GET", "/admin/tasks"),
    ]

    def test_anonymous_blocked(self, anon):
        for method, path in self.ENDPOINTS:
            r = anon.request(method, f"{API}{path}")
            assert r.status_code in (401, 403), f"{path} anon -> {r.status_code}"

    def test_office_token_blocked(self, office):
        for method, path in self.ENDPOINTS:
            r = office.request(method, f"{API}{path}")
            assert r.status_code in (401, 403), f"{path} office -> {r.status_code}"

    def test_office_blocked_on_mutations(self, office, admin):
        bid = admin.get(f"{API}/admin/bookings", params={"limit": 1}).json()["items"][0]["id"]
        for method, path, body in [
            ("GET", f"/admin/bookings/{bid}/full", None),
            ("POST", f"/admin/bookings/{bid}/notes", {"text": "TEST_hack"}),
            ("POST", f"/admin/bookings/{bid}/tasks", {"title": "TEST_hack"}),
            ("POST", f"/admin/bookings/{bid}/escalate", {"reason": "TEST_hack"}),
            ("POST", f"/admin/bookings/{bid}/de-escalate", {}),
        ]:
            r = office.request(method, f"{API}{path}", json=body)
            assert r.status_code in (401, 403), f"{path} office -> {r.status_code}"


# ---------------- ANALYTICS ----------------
class TestAnalytics:
    def test_analytics_default(self, admin):
        r = admin.get(f"{API}/admin/analytics")
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        for key in ("range", "sales", "escrow", "liquidity", "withdrawals",
                    "bookings_by_status", "bookings_by_approval", "attention",
                    "programs", "parties", "series", "comparison", "alerts"):
            assert key in d, f"missing {key}"
        assert d["range"]["period"] == "month"
        assert set(d["sales"]["gross"].keys()) == {"SAR", "USD"}
        assert isinstance(d["sales"]["bookings_count"], int)
        assert d["programs"]["total"] > 0
        assert d["parties"]["offices"] > 0
        assert isinstance(d["series"], list)

    @pytest.mark.parametrize("period", ["day", "week", "month", "year"])
    def test_analytics_periods(self, admin, period):
        r = admin.get(f"{API}/admin/analytics", params={"period": period})
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["range"]["period"] == period
        assert d["range"]["from"] <= d["range"]["to"]

    def test_analytics_custom_range_and_currency(self, admin):
        r = admin.get(f"{API}/admin/analytics",
                      params={"date_from": "2026-01-01", "date_to": "2026-12-31",
                              "currency": "SAR"})
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["range"]["from"] == "2026-01-01"
        assert d["range"]["to"] == "2026-12-31"
        # currency filter must zero the other bucket
        assert d["sales"]["gross"]["USD"] == 0.0

    def test_analytics_status_filter_consistency(self, admin):
        full = admin.get(f"{API}/admin/analytics", params={"period": "year"}).json()
        by_status = full["bookings_by_status"]
        if not by_status:
            pytest.skip("no bookings in year window")
        st = max(by_status, key=by_status.get)
        f = admin.get(f"{API}/admin/analytics",
                      params={"period": "year", "status": st}).json()
        assert f["sales"]["bookings_count"] == by_status[st]

    def test_attention_queue(self, admin):
        r = admin.get(f"{API}/admin/attention", params={"limit": 5})
        assert r.status_code == 200, r.text[:400]
        items = r.json()
        assert isinstance(items, list)
        assert len(items) <= 5, f"limit not enforced: got {len(items)}"
        for it in items:
            assert "_id" not in it and "id" in it
            assert it["needs_attention"] is True
            assert it["severity"] in ("warning", "critical")


# ---------------- ORDERS CENTER ----------------
class TestOrdersCenter:
    def test_list_shape_and_no_objectid(self, admin):
        r = admin.get(f"{API}/admin/bookings", params={"limit": 5})
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        assert set(["items", "total", "page", "limit", "amount_totals"]) <= set(d)
        assert d["total"] > 0
        assert len(d["items"]) <= 5
        it = d["items"][0]
        assert not _has_objectid_key(it), "raw _id leaked in list item"
        for k in ("id", "attention_reasons", "needs_attention", "severity",
                  "gross_total", "seller_net", "platform_total"):
            assert k in it, f"missing {k}"

    def test_pagination(self, admin):
        p1 = admin.get(f"{API}/admin/bookings", params={"page": 1, "limit": 10}).json()
        p2 = admin.get(f"{API}/admin/bookings", params={"page": 2, "limit": 10}).json()
        assert p1["total"] == p2["total"]
        ids1 = {i["id"] for i in p1["items"]}
        ids2 = {i["id"] for i in p2["items"]}
        assert ids1 and ids2 and not (ids1 & ids2), "pages overlap"

    @pytest.mark.parametrize("status", ["blue", "yellow", "green", "cancelled"])
    def test_status_filter(self, admin, status):
        d = admin.get(f"{API}/admin/bookings", params={"status": status, "limit": 20}).json()
        for i in d["items"]:
            assert i["status"] == status

    @pytest.mark.parametrize("ccy", ["SAR", "USD"])
    def test_currency_filter(self, admin, ccy):
        d = admin.get(f"{API}/admin/bookings", params={"currency": ccy, "limit": 20}).json()
        for i in d["items"]:
            assert i.get("currency") == ccy
        other = "USD" if ccy == "SAR" else "SAR"
        assert d["amount_totals"][other] == 0.0

    def test_approval_filter(self, admin):
        d = admin.get(f"{API}/admin/bookings", params={"approval_status": "pending", "limit": 20}).json()
        for i in d["items"]:
            assert i.get("approval_status") == "pending"

    @pytest.mark.parametrize("source", ["rahal", "meraaj"])
    def test_source_filter(self, admin, source):
        d = admin.get(f"{API}/admin/bookings", params={"source": source, "limit": 20}).json()
        for i in d["items"]:
            if source == "rahal":
                assert i.get("rahal_ref")
            else:
                assert not i.get("rahal_ref")

    @pytest.mark.parametrize("sort", ["newest", "oldest", "amount_desc", "amount_asc", "departure_asc"])
    def test_sorts(self, admin, sort):
        d = admin.get(f"{API}/admin/bookings", params={"sort": sort, "limit": 10})
        assert d.status_code == 200, d.text[:300]
        items = d.json()["items"]
        if sort == "amount_desc":
            amts = [i["gross_total"] for i in items]
            assert amts == sorted(amts, reverse=True)
        if sort == "amount_asc":
            amts = [i["gross_total"] for i in items]
            assert amts == sorted(amts)

    def test_search_by_package_title(self, admin):
        base = admin.get(f"{API}/admin/bookings", params={"limit": 1}).json()["items"][0]
        title = (base.get("package_title") or "")[:8]
        if not title.strip():
            pytest.skip("no package_title to search")
        d = admin.get(f"{API}/admin/bookings", params={"q": title, "limit": 20}).json()
        assert d["total"] >= 1
        for i in d["items"]:
            hay = " ".join(str(i.get(k) or "") for k in
                           ("package_title", "buyer_office_name", "seller_office_name"))
            travelers = " ".join(str(t.get("name") or "") + str(t.get("passport_no") or "")
                                 for t in (i.get("registrants") or []))
            assert title.lower() in (hay + travelers).lower()

    def test_search_by_id(self, admin):
        bid = admin.get(f"{API}/admin/bookings", params={"limit": 1}).json()["items"][0]["id"]
        d = admin.get(f"{API}/admin/bookings", params={"q": bid}).json()
        assert d["total"] == 1 and d["items"][0]["id"] == bid

    def test_date_filters(self, admin):
        d = admin.get(f"{API}/admin/bookings",
                      params={"date_from": "2026-01-01", "date_to": "2026-12-31", "limit": 20})
        assert d.status_code == 200, d.text[:300]
        for i in d.json()["items"]:
            assert str(i["created_at"])[:4] == "2026"

    def test_attention_flag_filter(self, admin):
        d = admin.get(f"{API}/admin/bookings", params={"attention": "true", "limit": 50}).json()
        for i in d["items"]:
            assert i["needs_attention"] is True

    def test_limit_cap(self, admin):
        r = admin.get(f"{API}/admin/bookings", params={"limit": 500})
        assert r.status_code == 422, f"limit>200 should be rejected, got {r.status_code}"

    def test_invalid_id_search_does_not_500(self, admin):
        r = admin.get(f"{API}/admin/bookings", params={"q": "not-an-objectid-@@@"})
        assert r.status_code == 200, r.text[:300]


# ---------------- ORDER DETAIL / NOTES / TASKS / ESCALATION ----------------
@pytest.fixture(scope="module")
def sample_booking(admin):
    return admin.get(f"{API}/admin/bookings", params={"limit": 1}).json()["items"][0]


class TestOrderDetail:
    def test_full_detail(self, admin, sample_booking):
        bid = sample_booking["id"]
        r = admin.get(f"{API}/admin/bookings/{bid}/full")
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        for k in ("booking", "package", "buyer", "seller", "documents",
                  "missing_documents", "timeline", "notes", "tasks",
                  "transactions", "financials"):
            assert k in d, f"missing {k}"
        assert d["booking"]["id"] == bid
        assert not _has_objectid_key(d), "raw _id leaked in detail payload"
        fin = d["financials"]
        for k in ("gross", "seller_net", "buyer_commission", "platform_fee",
                  "platform_profit", "marketer_commission", "settled", "currency"):
            assert k in fin

    def test_full_detail_404(self, admin):
        r = admin.get(f"{API}/admin/bookings/507f1f77bcf86cd799439011/full")
        assert r.status_code == 404, r.status_code

    def test_note_is_internal_only(self, admin, sample_booking):
        bid = sample_booking["id"]
        marker = f"TEST_note_{int(time.time())}"
        r = admin.post(f"{API}/admin/bookings/{bid}/notes", json={"text": marker})
        assert r.status_code == 200, r.text[:400]
        note = r.json()
        assert note["text"] == marker and note["internal"] is True
        # persisted
        d = admin.get(f"{API}/admin/bookings/{bid}/full").json()
        assert any(n["text"] == marker for n in d["notes"])
        # NOT leaked to seller/buyer facing APIs
        for creds in (SELLER, BUYER):
            s = login(*creds)
            lst = s.get(f"{API}/bookings")
            assert lst.status_code == 200, lst.text[:200]
            assert marker not in lst.text, f"internal note leaked in /bookings for {creds[0]}"
            one = s.get(f"{API}/bookings/{bid}")
            if one.status_code == 200:
                assert marker not in one.text, f"internal note leaked in /bookings/{{id}} for {creds[0]}"

    def test_note_validation(self, admin, sample_booking):
        r = admin.post(f"{API}/admin/bookings/{sample_booking['id']}/notes", json={"text": "a"})
        assert r.status_code == 422, r.status_code

    def test_task_lifecycle(self, admin, sample_booking):
        bid = sample_booking["id"]
        title = f"TEST_task_{int(time.time())}"
        r = admin.post(f"{API}/admin/bookings/{bid}/tasks",
                       json={"title": title, "assignee": "QA", "due_date": "2026-08-01",
                             "priority": "high"})
        assert r.status_code == 200, r.text[:400]
        t = r.json()
        tid = t["id"]
        assert t["status"] == "open" and t["priority"] == "high" and t["assignee"] == "QA"
        # patch to in_progress
        p = admin.patch(f"{API}/admin/tasks/{tid}", json={"status": "in_progress"})
        assert p.status_code == 200, p.text[:300]
        assert p.json()["status"] == "in_progress"
        # persisted on reload
        d = admin.get(f"{API}/admin/bookings/{bid}/full").json()
        got = [x for x in d["tasks"] if x["id"] == tid]
        assert got and got[0]["status"] == "in_progress"
        # done sets closed_at
        p2 = admin.patch(f"{API}/admin/tasks/{tid}", json={"status": "done"})
        assert p2.status_code == 200 and p2.json()["status"] == "done"
        assert p2.json().get("closed_at")
        # listing
        lst = admin.get(f"{API}/admin/tasks", params={"status": "done"})
        assert lst.status_code == 200
        assert any(x["id"] == tid for x in lst.json())
        # bad status
        bad = admin.patch(f"{API}/admin/tasks/{tid}", json={"status": "bogus"})
        assert bad.status_code == 400, bad.status_code
        # bad priority
        bp = admin.post(f"{API}/admin/bookings/{bid}/tasks",
                        json={"title": "TEST_bad", "priority": "bogus"})
        assert bp.status_code == 400, bp.status_code

    def test_escalation_is_oversight_only(self, admin, sample_booking):
        bid = sample_booking["id"]
        before = admin.get(f"{API}/admin/bookings/{bid}/full").json()
        b0, f0 = before["booking"], before["financials"]
        r = admin.post(f"{API}/admin/bookings/{bid}/escalate",
                       json={"reason": "TEST_escalation_reason"})
        assert r.status_code == 200, r.text[:400]
        assert r.json()["escalated"] is True
        after = admin.get(f"{API}/admin/bookings/{bid}/full").json()
        b1, f1 = after["booking"], after["financials"]
        assert b1["status"] == b0["status"]
        assert b1.get("approval_status") == b0.get("approval_status")
        assert f1 == f0, "escalation changed financials"
        assert "مُصعَّد إدارياً" in b1["attention_reasons"]
        # appears with attention filter
        lst = admin.get(f"{API}/admin/bookings",
                        params={"q": bid, "attention": "true"}).json()
        assert any(i["id"] == bid for i in lst["items"])
        # de-escalate
        de = admin.post(f"{API}/admin/bookings/{bid}/de-escalate", json={})
        assert de.status_code == 200, de.text[:300]
        assert de.json()["escalated"] is False
        final = admin.get(f"{API}/admin/bookings/{bid}/full").json()["booking"]
        assert final["status"] == b0["status"]

    def test_escalate_requires_reason(self, admin, sample_booking):
        r = admin.post(f"{API}/admin/bookings/{sample_booking['id']}/escalate", json={"reason": "x"})
        assert r.status_code == 422, r.status_code


# ---------------- REGRESSIONS: protected paths ----------------
class TestRegressionRahal:
    @staticmethod
    def _sso_token(secret=RAHAL_SECRET, **over):
        claims = {"iss": "rahaal-erp", "aud": "meraaj-network",
                  "office_ref": "RHL-OFF-77001", "email": "rahal_office1@qa-example.com",
                  "office_name": "مكتب رحال التجريبي", "exp": int(time.time()) + 600}
        claims.update(over)
        raw = json.dumps(claims, ensure_ascii=False, separators=(",", ":")).encode()
        b64 = base64.urlsafe_b64encode(raw).decode().rstrip("=")
        sig = hmac.new(secret.encode(), b64.encode(), hashlib.sha256).hexdigest()
        return f"{b64}.{sig}"

    def test_sso_exchange_no_duplicate_user(self):
        r1 = requests.post(f"{API}/integrations/rahal/sso", json={"token": self._sso_token()})
        assert r1.status_code == 200, r1.text[:300]
        assert r1.json().get("access_token")
        uid1 = (r1.json().get("user") or {}).get("id")
        r2 = requests.post(f"{API}/integrations/rahal/sso",
                           json={"token": self._sso_token(exp=int(time.time()) + 700)})
        assert r2.status_code == 200, r2.text[:300]
        uid2 = (r2.json().get("user") or {}).get("id")
        assert uid1 and uid1 == uid2, "duplicate user created on repeat SSO"

    def test_sso_bad_secret_rejected(self):
        r = requests.post(f"{API}/integrations/rahal/sso",
                          json={"token": self._sso_token(secret="wrong_secret")})
        assert r.status_code in (400, 401, 403), r.status_code

    def test_sso_expired_rejected(self):
        r = requests.post(f"{API}/integrations/rahal/sso",
                          json={"token": self._sso_token(exp=int(time.time()) - 10)})
        assert r.status_code == 401, r.status_code

    def _webhook(self, body_bytes, sig=None):
        h = {"Content-Type": "application/json"}
        if sig is not None:
            h["X-Rahal-Signature"] = sig
        return requests.post(f"{API}/integrations/rahal/webhooks", data=body_bytes, headers=h)

    def test_webhook_hmac_enforced(self):
        body = json.dumps({"event": "ping", "data": {}}).encode()
        good = hmac.new(RAHAL_SECRET.encode(), body, hashlib.sha256).hexdigest()
        r_ok = self._webhook(body, good)
        assert r_ok.status_code == 200, f"valid signature rejected: {r_ok.status_code} {r_ok.text[:200]}"
        assert self._webhook(body, "deadbeef").status_code == 401
        assert self._webhook(body).status_code == 401


class TestRegressionOffice:
    def test_seller_dashboard_and_packages(self, office):
        for path in ("/auth/me", "/packages/mine", "/wallet/transactions"):
            r = office.get(f"{API}{path}")
            assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:200]}"

    def test_wallet_dual_currency(self, office):
        me = office.get(f"{API}/auth/me").json()
        wal = (me.get("user") or me).get("wallet") or {}
        for c in ("SAR", "USD"):
            assert c in wal, f"missing {c} bucket: {list(wal)[:6]}"
            assert set(["available", "pending", "total"]) <= set(wal[c])

    def test_market_browsing_with_filters(self, office):
        r = office.get(f"{API}/packages", params={"limit": 5})
        assert r.status_code == 200, r.text[:300]
        r2 = office.get(f"{API}/packages", params={"currency": "SAR", "limit": 5})
        assert r2.status_code == 200, r2.text[:300]

    def test_bookings_list(self, office):
        r = office.get(f"{API}/bookings")
        assert r.status_code == 200, r.text[:300]


class TestRegressionAdminPages:
    def test_existing_admin_endpoints(self, admin):
        for path in ("/admin/dashboard", "/admin/topups", "/admin/transfers",
                     "/admin/withdrawals", "/admin/offices", "/admin/cancellations",
                     "/admin/disputes"):
            r = admin.get(f"{API}{path}")
            assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:200]}"
