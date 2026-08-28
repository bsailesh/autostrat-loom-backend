"""
Tests run against an isolated in-memory SQLite database and mock every
Claude API call, so they run offline, fast, and without an API key.

Run with: pytest -v

The tenant-isolation tests are the ones that matter most for an enterprise
buyer's review — they assert that tenant A genuinely cannot read or act on
tenant B's data, not just that the UI doesn't happen to show it.
"""
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-real")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LOOM_ADMIN_KEYS", "test-admin-key")

from app.main import app  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.schemas import (  # noqa: E402
    PrioritizeScoreSchema,
    DiscoverExtractionSchema,
    SustainAssessmentSchema,
    AlignDraftSchema,
    BriefDraftSchema,
)

# --- isolated in-memory DB per test session, shared connection so :memory: persists ---
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


def create_tenant(name: str) -> dict:
    resp = client.post("/admin/tenants", json={"name": name}, headers=ADMIN_HEADERS)
    assert resp.status_code == 200, resp.text
    return resp.json()


def auth_headers(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


# ---------- Auth ----------

def test_admin_route_requires_admin_key():
    resp = client.post("/admin/tenants", json={"name": "Nope"})
    assert resp.status_code == 403


def test_admin_route_rejects_wrong_admin_key():
    resp = client.post("/admin/tenants", json={"name": "Nope"}, headers={"X-Admin-Key": "wrong"})
    assert resp.status_code == 403


def test_data_route_requires_bearer_token():
    resp = client.get("/initiatives")
    assert resp.status_code == 401


def test_data_route_rejects_bad_token():
    resp = client.get("/initiatives", headers=auth_headers("not-a-real-key"))
    assert resp.status_code == 401


# ---------- Tenant isolation ----------

def test_tenant_cannot_list_another_tenants_initiatives():
    tenant_a = create_tenant("Tenant A Co")
    tenant_b = create_tenant("Tenant B Co")

    resp = client.post(
        "/initiatives",
        json={"title": "A's secret roadmap item", "category": "growth"},
        headers=auth_headers(tenant_a["api_key"]),
    )
    assert resp.status_code == 200
    a_initiative_id = resp.json()["id"]

    # Tenant B lists initiatives — should see nothing belonging to A.
    resp_b = client.get("/initiatives", headers=auth_headers(tenant_b["api_key"]))
    assert resp_b.status_code == 200
    assert all(i["id"] != a_initiative_id for i in resp_b.json())


def test_tenant_cannot_fetch_another_tenants_initiative_by_id():
    tenant_a = create_tenant("Tenant C Co")
    tenant_b = create_tenant("Tenant D Co")

    resp = client.post(
        "/initiatives",
        json={"title": "C's private item", "category": "irad"},
        headers=auth_headers(tenant_a["api_key"]),
    )
    a_initiative_id = resp.json()["id"]

    # Tenant B tries to fetch it directly by ID — must 404, not 200 or 403.
    resp_b = client.get(f"/initiatives/{a_initiative_id}", headers=auth_headers(tenant_b["api_key"]))
    assert resp_b.status_code == 404


def test_tenant_cannot_run_agent_on_another_tenants_asset():
    tenant_a = create_tenant("Tenant E Co")
    tenant_b = create_tenant("Tenant F Co")

    resp = client.post(
        "/assets",
        json={"name": "A's proprietary sensor", "asset_type": "part", "criticality": "high"},
        headers=auth_headers(tenant_a["api_key"]),
    )
    a_asset_id = resp.json()["id"]

    resp_b = client.post(f"/assets/{a_asset_id}/assess", headers=auth_headers(tenant_b["api_key"]))
    assert resp_b.status_code == 404


def test_audit_log_is_tenant_scoped():
    tenant_a = create_tenant("Tenant G Co")
    tenant_b = create_tenant("Tenant H Co")

    with patch(
        "app.agents.base.BaseAgent.call_claude_structured",
        return_value=PrioritizeScoreSchema(reach=5, impact=5, confidence=5, effort=2, rationale="mocked"),
    ):
        init_resp = client.post(
            "/initiatives",
            json={"title": "G's initiative", "category": "growth"},
            headers=auth_headers(tenant_a["api_key"]),
        )
        init_id = init_resp.json()["id"]
        client.post(f"/initiatives/{init_id}/prioritize", headers=auth_headers(tenant_a["api_key"]))

    log_a = client.get("/audit-log", headers=auth_headers(tenant_a["api_key"])).json()
    log_b = client.get("/audit-log", headers=auth_headers(tenant_b["api_key"])).json()

    assert any("G's initiative" in entry["action"] for entry in log_a)
    assert not any("G's initiative" in entry["action"] for entry in log_b)


# ---------- Agents (mocked Claude calls) ----------

def test_prioritize_agent_computes_composite_and_logs():
    tenant = create_tenant("Prioritize Test Co")
    init_resp = client.post(
        "/initiatives",
        json={"title": "Test initiative", "category": "growth", "description": "desc"},
        headers=auth_headers(tenant["api_key"]),
    )
    initiative_id = init_resp.json()["id"]

    with patch(
        "app.agents.base.BaseAgent.call_claude_structured",
        return_value=PrioritizeScoreSchema(reach=8, impact=6, confidence=7, effort=2, rationale="Clear win, low effort."),
    ):
        resp = client.post(f"/initiatives/{initiative_id}/prioritize", headers=auth_headers(tenant["api_key"]))

    assert resp.status_code == 200
    body = resp.json()
    assert body["composite_score"] == round((8 * 6 * 7) / 2, 2)

    # status should flip to "scored"
    init_after = client.get(f"/initiatives/{initiative_id}", headers=auth_headers(tenant["api_key"])).json()
    assert init_after["status"] == "scored"


def test_discover_agent_creates_signal():
    tenant = create_tenant("Discover Test Co")
    with patch(
        "app.agents.base.BaseAgent.call_claude_structured",
        return_value=DiscoverExtractionSchema(
            is_validated_problem=True,
            extracted_problem="Users can't export reports as CSV.",
            suggested_category="growth",
            confidence=8,
        ),
    ):
        resp = client.post(
            "/signals/discover",
            json={"source_type": "support_ticket", "raw_text": "please let me export as csv!!"},
            headers=auth_headers(tenant["api_key"]),
        )
    assert resp.status_code == 200
    assert resp.json()["is_validated"] is True


def test_sustain_agent_creates_assessment():
    tenant = create_tenant("Sustain Test Co")
    asset_resp = client.post(
        "/assets",
        json={"name": "Legacy gateway", "asset_type": "platform", "criticality": "high"},
        headers=auth_headers(tenant["api_key"]),
    )
    asset_id = asset_resp.json()["id"]

    with patch(
        "app.agents.base.BaseAgent.call_claude_structured",
        return_value=SustainAssessmentSchema(
            risk_level="high",
            recommended_action="Identify a replacement gateway vendor this quarter.",
            rationale="High criticality with no known successor.",
        ),
    ):
        resp = client.post(f"/assets/{asset_id}/assess", headers=auth_headers(tenant["api_key"]))
    assert resp.status_code == 200
    assert resp.json()["risk_level"] == "high"


def test_align_agent_rejects_foreign_initiative_ids():
    tenant_a = create_tenant("Align A Co")
    tenant_b = create_tenant("Align B Co")

    init_resp = client.post(
        "/initiatives",
        json={"title": "A's item", "category": "growth"},
        headers=auth_headers(tenant_a["api_key"]),
    )
    a_id = init_resp.json()["id"]

    resp = client.post(
        "/roadmaps",
        json={"title": "B's roadmap", "initiative_ids": [a_id]},
        headers=auth_headers(tenant_b["api_key"]),
    )
    assert resp.status_code == 404


def test_align_agent_drafts_roadmap():
    tenant = create_tenant("Align Test Co")
    init_resp = client.post(
        "/initiatives",
        json={"title": "Roadmap item", "category": "growth"},
        headers=auth_headers(tenant["api_key"]),
    )
    init_id = init_resp.json()["id"]

    with patch(
        "app.agents.base.BaseAgent.call_claude_structured",
        return_value=AlignDraftSchema(exec_summary="Summary.", narrative="# Roadmap\n\n- Roadmap item"),
    ):
        resp = client.post(
            "/roadmaps",
            json={"title": "Q3 Roadmap", "initiative_ids": [init_id]},
            headers=auth_headers(tenant["api_key"]),
        )
    assert resp.status_code == 200
    assert resp.json()["exec_summary"] == "Summary."


def test_brief_agent_generates_report():
    tenant = create_tenant("Brief Test Co")
    with patch(
        "app.agents.base.BaseAgent.call_claude_structured",
        return_value=BriefDraftSchema(content="# Portfolio Brief\n\nAll clear."),
    ):
        resp = client.post(
            "/briefs",
            json={"title": "Q3 Board Update", "notes": ""},
            headers=auth_headers(tenant["api_key"]),
        )
    assert resp.status_code == 200
    assert "Portfolio Brief" in resp.json()["content"]
