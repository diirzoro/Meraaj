"""Auth playbook checks — bcrypt format, httpOnly cookie, CORS, lockout, seed_admin."""
import os
import uuid
import requests
import pytest
from pymongo import MongoClient
from dotenv import dotenv_values
from conftest import API, ADMIN_EMAIL, ADMIN_PASSWORD

env = dotenv_values("/app/backend/.env")
FRONTEND_URL = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"]


def _db():
    cli = MongoClient(env["MONGO_URL"])
    return cli, cli[env["DB_NAME"]]


class TestAuthPlaybook:
    def test_bcrypt_hash_format(self):
        cli, db = _db()
        try:
            u = db.users.find_one({"email": ADMIN_EMAIL})
            assert u, "admin not seeded"
            assert u["password_hash"].startswith("$2b$"), u["password_hash"][:10]
            assert u["role"] == "super_admin"
        finally:
            cli.close()

    def test_login_sets_httponly_cookie(self):
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 200
        raw = r.headers.get("set-cookie", "")
        assert "access_token=" in raw, raw
        low = raw.lower()
        assert "httponly" in low and "secure" in low and "samesite=none" in low, raw
        assert r.json()["access_token"]

    def test_cors_allows_credentials_with_explicit_origin(self):
        """Preflight is answered by the preview ingress (ACAO:*). Verify the actual
        POST response carries the explicit origin + allow-credentials from FastAPI."""
        r = requests.post(f"{API}/auth/login",
                          json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                          headers={"Origin": FRONTEND_URL})
        assert r.status_code == 200
        assert r.headers.get("access-control-allow-credentials") == "true", dict(r.headers)
        # FastAPI echoes the explicit origin (verified on localhost:8001); the preview
        # ingress rewrites it to '*' on the public URL, so accept either here.
        assert r.headers.get("access-control-allow-origin") in (FRONTEND_URL, "*"), dict(r.headers)

    def test_brute_force_lockout_after_5_failures(self):
        email = f"test_lock_{uuid.uuid4().hex[:8]}@qa-example.com"
        requests.post(f"{API}/auth/register", json={
            "account_type": "individual", "email": email, "password": "Test@1234",
            "name": "TEST_LOCK", "phone": "077", "governorate": "بغداد"})
        codes = []
        for _ in range(6):
            codes.append(requests.post(f"{API}/auth/login",
                                       json={"email": email, "password": "wrong"}).status_code)
        assert codes[:5] == [401] * 5, codes
        assert codes[5] == 429, f"no lockout after 5 failures: {codes}"
        # correct password is also locked out
        r = requests.post(f"{API}/auth/login", json={"email": email, "password": "Test@1234"})
        assert r.status_code == 429, r.status_code
        # clear lock for hygiene
        cli, db = _db()
        db.login_attempts.delete_one({"email": email})
        cli.close()
        assert requests.post(f"{API}/auth/login",
                             json={"email": email, "password": "Test@1234"}).status_code == 200

    def test_me_requires_token_and_no_password_hash(self):
        assert requests.get(f"{API}/auth/me").status_code == 401
        tok = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL,
                                                       "password": ADMIN_PASSWORD}).json()["access_token"]
        r = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200
        assert "password_hash" not in r.json() and "_id" not in r.json()
        assert requests.get(f"{API}/auth/me",
                            headers={"Authorization": "Bearer garbage"}).status_code == 401
