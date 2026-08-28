"""
Tests for the login flow and the public contact form. Shares the same
in-memory-DB / TestClient setup pattern as test_agents_and_isolation.py.
Email sending is mocked so these run offline.
"""
import os
from unittest.mock import patch

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-real")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LOOM_ADMIN_KEYS", "test-admin-key")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app  # noqa: E402
from app.database import Base, get_db  # noqa: E402

engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)
ADMIN_HEADERS = {"X-Admin-Key": "test-admin-key"}


def _make_tenant_and_user(tenant_name: str, email: str, password: str) -> dict:
    tenant = client.post("/admin/tenants", json={"name": tenant_name}, headers=ADMIN_HEADERS).json()
    client.post(
        f"/admin/tenants/{tenant['id']}/users",
        json={"email": email, "password": password, "role": "admin"},
        headers=ADMIN_HEADERS,
    )
    return tenant


# ---------- Login ----------

def test_login_succeeds_with_correct_credentials():
    _make_tenant_and_user("Login Test Co", "user@logintest.com", "correct-password")
    resp = client.post("/auth/login", json={"email": "user@logintest.com", "password": "correct-password"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["token"].startswith("loom_sess_")
    assert body["user_email"] == "user@logintest.com"


def test_login_rejects_wrong_password():
    _make_tenant_and_user("Login Fail Co", "user2@logintest.com", "correct-password")
    resp = client.post("/auth/login", json={"email": "user2@logintest.com", "password": "wrong-password"})
    assert resp.status_code == 401


def test_login_rejects_unknown_email():
    resp = client.post("/auth/login", json={"email": "nobody@nowhere.com", "password": "whatever"})
    assert resp.status_code == 401


def test_session_token_from_login_works_as_bearer_token():
    _make_tenant_and_user("Session Use Co", "user3@logintest.com", "correct-password")
    login_resp = client.post("/auth/login", json={"email": "user3@logintest.com", "password": "correct-password"})
    token = login_resp.json()["token"]

    resp = client.get("/initiatives", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


def test_logout_invalidates_session_token():
    _make_tenant_and_user("Logout Co", "user4@logintest.com", "correct-password")
    login_resp = client.post("/auth/login", json={"email": "user4@logintest.com", "password": "correct-password"})
    token = login_resp.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get("/initiatives", headers=headers).status_code == 200
    assert client.post("/auth/logout", headers=headers).status_code == 200
    assert client.get("/initiatives", headers=headers).status_code == 401


def test_duplicate_user_email_rejected():
    _make_tenant_and_user("Dup Co", "dup@logintest.com", "password123")
    tenant2 = client.post("/admin/tenants", json={"name": "Dup Co 2"}, headers=ADMIN_HEADERS).json()
    resp = client.post(
        f"/admin/tenants/{tenant2['id']}/users",
        json={"email": "dup@logintest.com", "password": "password123"},
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 409


# ---------- Contact form ----------

def test_contact_form_submission_is_stored_and_acked():
    with patch("app.routers.contact.send_email", return_value=True) as mock_send:
        resp = client.post(
            "/contact",
            json={
                "full_name": "Jamie Prospect",
                "work_email": "jamie@prospect.com",
                "company": "Prospect Co",
                "role": "VP Product",
                "interest": "Full Suite",
                "message": "Interested in Loom Prioritize and Loom Sustain.",
            },
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "received"
    mock_send.assert_called_once()
    call_kwargs = mock_send.call_args.kwargs
    assert call_kwargs["to"] == "saileshathreya@autostrat.net"
    assert "Jamie Prospect" in call_kwargs["body"]


def test_contact_form_still_acks_when_email_fails():
    with patch("app.routers.contact.send_email", return_value=False):
        resp = client.post(
            "/contact",
            json={
                "full_name": "Alex Prospect",
                "work_email": "alex@prospect.com",
                "message": "Hello.",
            },
        )
    # A public form submitter shouldn't see internal SMTP failures.
    assert resp.status_code == 200
    assert resp.json()["status"] == "received"


def test_contact_form_requires_no_auth():
    # No Authorization header at all — this must still work, unlike every
    # tenant-data endpoint.
    with patch("app.routers.contact.send_email", return_value=True):
        resp = client.post(
            "/contact",
            json={"full_name": "No Auth Person", "work_email": "x@y.com", "message": "hi"},
        )
    assert resp.status_code == 200
