"""
Phase 2: self-serve signup, tenant invites, and the Market Insights agent
endpoints — plus the tenant-isolation checks the kickoff briefing calls the
single most important thing to verify.

Same offline pattern as the other test modules: isolated in-memory SQLite,
every Claude call mocked. The Market Insights agent (the Phase 1 module) is
replaced wholesale with a fake so no real research/synthesis runs.
"""
import os
from unittest.mock import patch

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-real")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LOOM_ADMIN_KEYS", "test-admin-key")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.main import app  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.models import SignupAllowlist  # noqa: E402

# StaticPool keeps a single shared connection so the :memory: DB created by
# create_all() below is the same one the app sees through the request thread.
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


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _allow(email: str) -> None:
    """
    Pre-authorize an email for signup. Since the Pre-Phase 6 addendum, signup
    is gated on the allowlist; every test that signs up seeds it first, exactly
    as an operator would with `manage_allowlist.py add`.
    """
    db = TestingSessionLocal()
    try:
        if not db.query(SignupAllowlist).filter(SignupAllowlist.email == email.strip().lower()).first():
            db.add(SignupAllowlist(email=email.strip().lower()))
            db.commit()
    finally:
        db.close()


# --------------------------------------------------------------------------
# Fake Market Insights agent
# --------------------------------------------------------------------------

class _FakeReport:
    def __init__(self, n: int):
        self.report_number = n
        self.title = f"Report {n} title"
        self.content = f"# Report {n}\n\nBody for report {n}."
        self.confidence_summary = f"Confidence summary {n}."


class _FakeResult:
    def __init__(self):
        self.reports = [_FakeReport(i) for i in range(1, 10)]


class _FakeAgent:
    last_subject = None

    def __init__(self, *args, **kwargs):
        pass

    def run(self, subject, **kwargs):
        _FakeAgent.last_subject = subject
        return _FakeResult()


def _run_agent_patches():
    return (
        patch("app.routers.market_insights.MarketInsightsAgent", _FakeAgent),
        patch("app.routers.market_insights.SessionFactory", TestingSessionLocal),
    )


def set_scope(token: str, product_line: str = "electric ferries", **extra) -> dict:
    body = {"product_line": product_line, **extra}
    resp = client.put("/agents/market-insights/scope", json=body, headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    return resp.json()


def start_run(token: str, product_line: str = "electric ferries") -> dict:
    set_scope(token, product_line)
    p1, p2 = _run_agent_patches()
    with p1, p2:
        resp = client.post(
            "/agents/market-insights/run",
            json={},
            headers=auth_headers(token),
        )
    assert resp.status_code == 202, resp.text
    return resp.json()


# --------------------------------------------------------------------------
# Signup
# --------------------------------------------------------------------------

def test_signup_creates_tenant_and_owner_and_returns_working_token():
    _allow("founder@acme.test")
    resp = client.post(
        "/auth/signup",
        json={"email": "founder@acme.test", "password": "supersecret1", "tenant_name": "Acme"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["role"] == "owner"
    assert body["tenant_name"] == "Acme"
    assert body["token"].startswith("loom_sess_")

    me = client.get("/auth/me", headers=auth_headers(body["token"]))
    assert me.status_code == 200
    assert me.json()["email"] == "founder@acme.test"
    assert me.json()["tenant_id"] == body["tenant_id"]


def test_signup_defaults_tenant_name_and_lowercases_email():
    _allow("Solo.Person@Example.test")
    resp = client.post(
        "/auth/signup",
        json={"email": "Solo.Person@Example.test", "password": "supersecret1"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["user_email"] == "solo.person@example.test"
    assert "workspace" in body["tenant_name"]


def test_signup_rejects_duplicate_email():
    _allow("dup@acme.test")
    client.post("/auth/signup", json={"email": "dup@acme.test", "password": "supersecret1"})
    resp = client.post("/auth/signup", json={"email": "dup@acme.test", "password": "supersecret1"})
    assert resp.status_code == 409


def test_signup_rejected_when_email_not_on_allowlist():
    resp = client.post("/auth/signup", json={"email": "stranger@nope.test", "password": "supersecret1"})
    assert resp.status_code == 403
    # No tenant or user was created: the email cannot then log in.
    login = client.post("/auth/login", json={"email": "stranger@nope.test", "password": "supersecret1"})
    assert login.status_code == 401


def test_signup_allowed_once_email_is_on_allowlist():
    _allow("invited@welcome.test")
    resp = client.post("/auth/signup", json={"email": "invited@welcome.test", "password": "supersecret1"})
    assert resp.status_code == 201, resp.text
    assert resp.json()["role"] == "owner"


def test_signup_then_login_roundtrip_uses_bcrypt():
    _allow("bcrypt@acme.test")
    client.post("/auth/signup", json={"email": "bcrypt@acme.test", "password": "hunter2hunter2"})
    resp = client.post("/auth/login", json={"email": "bcrypt@acme.test", "password": "hunter2hunter2"})
    assert resp.status_code == 200
    assert resp.json()["token"].startswith("loom_sess_")
    # wrong password still rejected
    bad = client.post("/auth/login", json={"email": "bcrypt@acme.test", "password": "nope"})
    assert bad.status_code == 401


# --------------------------------------------------------------------------
# Invites
# --------------------------------------------------------------------------

def _signup(email: str, password: str = "supersecret1", tenant_name: str = "") -> dict:
    _allow(email)
    resp = client.post(
        "/auth/signup",
        json={"email": email, "password": password, "tenant_name": tenant_name},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_invite_flow_attaches_second_user_to_existing_tenant():
    owner = _signup("owner1@team.test", tenant_name="Team One")

    inv = client.post(
        "/invites",
        json={"email": "colleague@team.test", "role": "member"},
        headers=auth_headers(owner["token"]),
    )
    assert inv.status_code == 201, inv.text
    invite = inv.json()
    assert invite["tenant_id"] == owner["tenant_id"]
    assert invite["token"].startswith("loom_inv_")

    accept = client.post(
        "/invites/accept",
        json={"token": invite["token"], "password": "colleaguepass1"},
    )
    assert accept.status_code == 201, accept.text
    accepted = accept.json()
    # Same tenant, not a new one.
    assert accepted["tenant_id"] == owner["tenant_id"]
    assert accepted["role"] == "member"

    # The second user can log in independently and lands in the same tenant.
    login = client.post(
        "/auth/login", json={"email": "colleague@team.test", "password": "colleaguepass1"}
    )
    assert login.status_code == 200
    assert login.json()["tenant_id"] == owner["tenant_id"]


def test_invite_cannot_be_reused():
    owner = _signup("owner2@team.test")
    invite = client.post(
        "/invites",
        json={"email": "second@team.test"},
        headers=auth_headers(owner["token"]),
    ).json()

    first = client.post("/invites/accept", json={"token": invite["token"], "password": "password12"})
    assert first.status_code == 201
    second = client.post("/invites/accept", json={"token": invite["token"], "password": "password12"})
    assert second.status_code == 404


def test_member_cannot_invite():
    owner = _signup("owner3@team.test")
    invite = client.post(
        "/invites", json={"email": "member3@team.test"}, headers=auth_headers(owner["token"])
    ).json()
    member_login = client.post(
        "/invites/accept", json={"token": invite["token"], "password": "memberpass1"}
    ).json()

    resp = client.post(
        "/invites",
        json={"email": "someone-else@team.test"},
        headers=auth_headers(member_login["token"]),
    )
    assert resp.status_code == 403


def test_invite_accept_rejects_unknown_token():
    resp = client.post("/invites/accept", json={"token": "loom_inv_nope", "password": "whatever12"})
    assert resp.status_code == 404


# --------------------------------------------------------------------------
# Agent run lifecycle
# --------------------------------------------------------------------------

def test_run_completes_and_produces_nine_reports():
    owner = _signup("runner@agent.test")
    run = start_run(owner["token"], "electric ferries")
    assert run["status"] == "pending"
    assert run["agent_type"] == "market-insights"

    # Background task runs synchronously under TestClient, so it's done now.
    listed = client.get("/agents/market-insights/runs", headers=auth_headers(owner["token"]))
    assert listed.status_code == 200
    runs = listed.json()
    assert len(runs) == 1
    assert runs[0]["id"] == run["id"]
    assert runs[0]["status"] == "succeeded"

    reports = client.get(
        f"/agents/market-insights/runs/{run['id']}/reports",
        headers=auth_headers(owner["token"]),
    )
    assert reports.status_code == 200
    body = reports.json()
    assert [r["report_number"] for r in body] == list(range(1, 10))
    assert "content" not in body[0]  # summary list is lighter

    one = client.get(
        f"/agents/market-insights/reports/{body[0]['id']}",
        headers=auth_headers(owner["token"]),
    )
    assert one.status_code == 200
    assert one.json()["content"].startswith("# Report 1")


def test_run_records_failure_on_agent_error():
    owner = _signup("failrunner@agent.test")
    set_scope(owner["token"], "doomed product line")

    class _BoomAgent:
        def __init__(self, *a, **k):
            pass

        def run(self, subject, **kw):
            raise RuntimeError("research API exploded")

    with patch("app.routers.market_insights.MarketInsightsAgent", _BoomAgent), \
         patch("app.routers.market_insights.SessionFactory", TestingSessionLocal):
        resp = client.post(
            "/agents/market-insights/run",
            json={},
            headers=auth_headers(owner["token"]),
        )
    assert resp.status_code == 202
    run_id = resp.json()["id"]

    got = client.get(
        f"/agents/market-insights/runs/{run_id}", headers=auth_headers(owner["token"])
    ).json()
    assert got["status"] == "failed"
    assert "research API exploded" in got["error"]


def test_run_requires_auth():
    assert client.post("/agents/market-insights/run", json={}).status_code == 401


# --------------------------------------------------------------------------
# Tenant isolation — the stop-everything checks
# --------------------------------------------------------------------------

def test_other_tenant_cannot_see_runs_in_list():
    a = _signup("iso-a@corp.test", tenant_name="Corp A")
    b = _signup("iso-b@corp.test", tenant_name="Corp B")

    a_run = start_run(a["token"], "A's confidential market")

    b_runs = client.get("/agents/market-insights/runs", headers=auth_headers(b["token"]))
    assert b_runs.status_code == 200
    assert all(r["id"] != a_run["id"] for r in b_runs.json())
    assert b_runs.json() == []


def test_other_tenant_cannot_fetch_run_by_id():
    a = _signup("iso-c@corp.test")
    b = _signup("iso-d@corp.test")
    a_run = start_run(a["token"], "A's market")

    resp = client.get(
        f"/agents/market-insights/runs/{a_run['id']}", headers=auth_headers(b["token"])
    )
    assert resp.status_code == 404


def test_other_tenant_cannot_list_run_reports():
    a = _signup("iso-e@corp.test")
    b = _signup("iso-f@corp.test")
    a_run = start_run(a["token"], "A's market")

    resp = client.get(
        f"/agents/market-insights/runs/{a_run['id']}/reports", headers=auth_headers(b["token"])
    )
    assert resp.status_code == 404


def test_other_tenant_cannot_fetch_report_by_id_even_guessing():
    a = _signup("iso-g@corp.test")
    b = _signup("iso-h@corp.test")
    a_run = start_run(a["token"], "A's market")

    a_reports = client.get(
        f"/agents/market-insights/runs/{a_run['id']}/reports", headers=auth_headers(a["token"])
    ).json()
    assert len(a_reports) == 9

    for r in a_reports:
        resp = client.get(
            f"/agents/market-insights/reports/{r['id']}", headers=auth_headers(b["token"])
        )
        assert resp.status_code == 404, f"tenant B fetched report {r['id']}"


def test_other_tenant_cannot_read_via_auth_me_cross_wiring():
    a = _signup("iso-i@corp.test", tenant_name="Corp I")
    b = _signup("iso-j@corp.test", tenant_name="Corp J")
    assert client.get("/auth/me", headers=auth_headers(a["token"])).json()["tenant_id"] != \
        client.get("/auth/me", headers=auth_headers(b["token"])).json()["tenant_id"]


# --------------------------------------------------------------------------
# Phase 2 addendum — agent scope
# --------------------------------------------------------------------------

def test_run_without_scope_configured_is_rejected():
    owner = _signup("noscope@scope.test")
    with patch("app.routers.market_insights.MarketInsightsAgent", _FakeAgent), \
         patch("app.routers.market_insights.SessionFactory", TestingSessionLocal):
        resp = client.post("/agents/market-insights/run", json={}, headers=auth_headers(owner["token"]))
    assert resp.status_code == 409
    assert "product line" in resp.json()["detail"].lower()
    # ...and no run row was created
    runs = client.get("/agents/market-insights/runs", headers=auth_headers(owner["token"])).json()
    assert runs == []


def test_put_scope_rejects_empty_or_missing_product_line():
    owner = _signup("emptyscope@scope.test")
    empty = client.put(
        "/agents/market-insights/scope",
        json={"product_line": "   "},
        headers=auth_headers(owner["token"]),
    )
    assert empty.status_code == 400
    missing = client.put(
        "/agents/market-insights/scope", json={}, headers=auth_headers(owner["token"])
    )
    assert missing.status_code == 400


def test_get_scope_before_and_after_configuration():
    owner = _signup("getscope@scope.test")

    before = client.get("/agents/market-insights/scope", headers=auth_headers(owner["token"]))
    assert before.status_code == 200
    assert before.json()["configured"] is False
    assert before.json()["product_line"] is None

    put = client.put(
        "/agents/market-insights/scope",
        json={"product_line": "hydrogen fuel cells", "competitors": "Ballard, Plug Power", "geography": "EU"},
        headers=auth_headers(owner["token"]),
    )
    assert put.status_code == 200
    assert put.json()["configured"] is True

    after = client.get("/agents/market-insights/scope", headers=auth_headers(owner["token"])).json()
    assert after["configured"] is True
    assert after["product_line"] == "hydrogen fuel cells"
    assert after["competitors"] == "Ballard, Plug Power"
    assert after["geography"] == "EU"


def test_put_scope_updates_in_place_not_duplicates():
    owner = _signup("updscope@scope.test")
    set_scope(owner["token"], "first line")
    set_scope(owner["token"], "second line", competitors="Acme")
    got = client.get("/agents/market-insights/scope", headers=auth_headers(owner["token"])).json()
    assert got["product_line"] == "second line"
    assert got["competitors"] == "Acme"


def test_run_feeds_configured_scope_to_the_agent():
    owner = _signup("feedscope@scope.test")
    client.put(
        "/agents/market-insights/scope",
        json={
            "product_line": "shipboard battery systems",
            "competitors": "Corvus Energy, Leclanché",
            "geography": "Northern Europe",
        },
        headers=auth_headers(owner["token"]),
    )

    _FakeAgent.last_subject = None
    with patch("app.routers.market_insights.MarketInsightsAgent", _FakeAgent), \
         patch("app.routers.market_insights.SessionFactory", TestingSessionLocal):
        resp = client.post("/agents/market-insights/run", json={}, headers=auth_headers(owner["token"]))
    assert resp.status_code == 202

    subject = _FakeAgent.last_subject
    assert subject is not None
    assert "shipboard battery systems" in subject
    assert "Corvus Energy, Leclanché" in subject
    assert "Northern Europe" in subject

    # the run row records the same composed subject
    run = client.get(
        f"/agents/market-insights/runs/{resp.json()['id']}", headers=auth_headers(owner["token"])
    ).json()
    assert run["subject"] == subject


def test_run_works_with_only_product_line_no_optional_fields():
    owner = _signup("minimalscope@scope.test")
    set_scope(owner["token"], "tugboat propulsion")

    _FakeAgent.last_subject = None
    with patch("app.routers.market_insights.MarketInsightsAgent", _FakeAgent), \
         patch("app.routers.market_insights.SessionFactory", TestingSessionLocal):
        resp = client.post("/agents/market-insights/run", json={}, headers=auth_headers(owner["token"]))
    assert resp.status_code == 202
    assert _FakeAgent.last_subject == "tugboat propulsion"


def test_scope_is_tenant_isolated():
    a = _signup("scope-a@corp.test", tenant_name="Scope Corp A")
    b = _signup("scope-b@corp.test", tenant_name="Scope Corp B")

    set_scope(a["token"], "A's secret product line")

    # B sees nothing configured, and configuring B doesn't touch A.
    assert client.get("/agents/market-insights/scope", headers=auth_headers(b["token"])).json()["configured"] is False
    set_scope(b["token"], "B's own product line")

    a_scope = client.get("/agents/market-insights/scope", headers=auth_headers(a["token"])).json()
    assert a_scope["product_line"] == "A's secret product line"
