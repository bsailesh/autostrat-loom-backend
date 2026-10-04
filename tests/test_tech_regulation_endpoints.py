"""
Endpoint and persistence tests for Agent 3 (Technology & Regulatory
Intelligence): the eight scope dimensions, /scope/state, runs, reports,
export, and candidate-work triage including DELETE.

Isolated per conftest.py's convention: this module defines `override_get_db`
and lets the autouse fixture pin it, rather than assigning
app.dependency_overrides at import time.

No real Anthropic calls -- `TechRegulationAgent.run` is patched.
"""
import io
import os
import zipfile
from unittest.mock import patch

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-real")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LOOM_ADMIN_KEYS", "test-admin-key")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.tech_regulation_service as tech_regulation_service
from app.database import Base, get_db
from app.main import app
from app.models import AgentRun, Tenant, TrCandidateWork
from tech_regulation.agent import AgentRunResult, Report
from tech_regulation.schemas import CandidateWorkItem

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


# execute_run's background task opens its own session via SessionFactory,
# since the request-scoped one is closed by the time the task runs -- point
# it at the test engine or it silently hits the real ./loom.db.
tech_regulation_service.SessionFactory = TestingSessionLocal
client = TestClient(app)

ADMIN_HEADERS = {"X-Admin-Key": "test-admin-key"}
BASE = "/agents/tech-regulation"


def create_tenant(name: str) -> dict:
    resp = client.post("/admin/tenants", json={"name": name}, headers=ADMIN_HEADERS)
    assert resp.status_code == 200, resp.text
    return resp.json()


def auth_headers(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


def _item(**overrides) -> CandidateWorkItem:
    payload = {
        "candidate_key": "TR-01",
        "driver": "RTCA DO-160G Section 21 revision, effective 14 Mar 2028",
        "work_date": "2028-03-14",
        "date_basis": "effective",
        "date_absent_reason": "",
        "applicability": {
            "categories": ["EMA-UTIL"],
            "certification_bases": ["TSO-C196b"],
            "platforms": [],
            "note": "",
        },
        "work_implied": "requalification",
        "work_implied_description": "Requalification of affected articles",
        "platform_relationship": None,
        "classification": "FACT",
        "confidence": "High",
        "source": "EUROCAE",
        "source_date": "2027-02-11",
    }
    payload.update(overrides)
    return CandidateWorkItem.model_validate(payload)


def _fake_result(items=None, reports=None) -> AgentRunResult:
    return AgentRunResult(
        operating_state="scoped",
        operating_state_line="**Operating state: SCOPED.**",
        generated_at="2026-10-03T00:00:00Z",
        model="claude-opus-5",
        web_search_queries=[],
        research_sources=[],
        research_brief="brief",
        candidate_work=items if items is not None else [_item()],
        candidate_work_dropped=[],
        reports=reports
        or [
            Report(report_number=n, title=f"Report {n}", content=f"# body {n}", confidence_summary="")
            for n in (1, 2, 3, 4, 5, 6, 7, 8, 11)
        ],
    )


def _seed_full_envelope(headers) -> None:
    assert client.put(
        f"{BASE}/scope/categories",
        json=[{"category_key": "EMA-UTIL", "category_name": "Utility actuation"}],
        headers=headers,
    ).status_code == 200
    assert client.put(
        f"{BASE}/scope/jurisdictions",
        json=[{"jurisdiction": "European Union", "role": "primary"}],
        headers=headers,
    ).status_code == 200
    assert client.put(
        f"{BASE}/scope/certification-basis",
        json=[{
            "category_key": "EMA-UTIL", "basis_type": "TSO",
            "basis_identifier": "TSO-C196b", "status": "approved", "held_since": "2019",
        }],
        headers=headers,
    ).status_code == 200
    assert client.put(
        f"{BASE}/scope/platforms",
        json=[{
            "platform": "Narrowbody commercial", "platform_class": "Part 25 transport",
            "relationship": "pursuing", "programme_status": "design-in window",
        }],
        headers=headers,
    ).status_code == 200
    assert client.put(
        f"{BASE}/scope/standards",
        json=[{"standard_id": "DO-160", "revision": "G", "status": "compliant"}],
        headers=headers,
    ).status_code == 200
    assert client.put(
        f"{BASE}/scope/suppliers",
        json=[{"supplier": "Vendor A", "what_they_supply": "GaN power devices",
               "criticality": "single_source"}],
        headers=headers,
    ).status_code == 200
    assert client.put(
        f"{BASE}/scope/domains", json=[{"domain": "Electrification"}], headers=headers
    ).status_code == 200
    assert client.put(
        f"{BASE}/scope/exclusions",
        json=[{"exclusion_type": "jurisdiction", "value": "China", "reason": "no sales intent"}],
        headers=headers,
    ).status_code == 200


# ---------------------------------------------------------------------------
# Scope dimensions
# ---------------------------------------------------------------------------


def test_scope_dimensions_round_trip():
    tenant = create_tenant("Scope Round Trip Co")
    headers = auth_headers(tenant["api_key"])
    _seed_full_envelope(headers)

    assert client.get(f"{BASE}/scope/categories", headers=headers).json() == [
        {"category_key": "EMA-UTIL", "category_name": "Utility actuation", "description": ""}
    ]
    platforms = client.get(f"{BASE}/scope/platforms", headers=headers).json()
    assert platforms[0]["relationship"] == "pursuing"


def test_put_replaces_a_dimension_wholesale():
    tenant = create_tenant("Replace Co")
    headers = auth_headers(tenant["api_key"])
    client.put(f"{BASE}/scope/domains", json=[{"domain": "A"}, {"domain": "B"}], headers=headers)
    client.put(f"{BASE}/scope/domains", json=[{"domain": "C"}], headers=headers)
    assert [d["domain"] for d in client.get(f"{BASE}/scope/domains", headers=headers).json()] == ["C"]


def test_one_category_may_hold_several_certification_bases():
    tenant = create_tenant("Multi Basis Co")
    headers = auth_headers(tenant["api_key"])
    resp = client.put(
        f"{BASE}/scope/certification-basis",
        json=[
            {"category_key": "EMA-UTIL", "basis_type": "TSO", "basis_identifier": "TSO-C196b"},
            {"category_key": "EMA-UTIL", "basis_type": "Part", "basis_identifier": "14 CFR Part 25"},
        ],
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()) == 2


def test_duplicate_rows_within_a_put_are_rejected():
    tenant = create_tenant("Dup Co")
    headers = auth_headers(tenant["api_key"])
    resp = client.put(
        f"{BASE}/scope/categories",
        json=[
            {"category_key": "X", "category_name": "One"},
            {"category_key": "X", "category_name": "Two"},
        ],
        headers=headers,
    )
    assert resp.status_code == 422


def test_certification_basis_vocabulary_is_enforced():
    tenant = create_tenant("Vocab Co")
    headers = auth_headers(tenant["api_key"])
    resp = client.put(
        f"{BASE}/scope/certification-basis",
        json=[{"category_key": "X", "basis_type": "TSO-ish", "basis_identifier": "Y"}],
        headers=headers,
    )
    assert resp.status_code == 422


def test_scope_is_tenant_isolated():
    a = create_tenant("Isolation A")
    b = create_tenant("Isolation B")
    client.put(
        f"{BASE}/scope/domains", json=[{"domain": "Electrification"}], headers=auth_headers(a["api_key"])
    )
    assert client.get(f"{BASE}/scope/domains", headers=auth_headers(b["api_key"])).json() == []


# ---------------------------------------------------------------------------
# /scope/state -- the b4f3282 bug must not recur
# ---------------------------------------------------------------------------


def test_scope_state_returns_empty_consequence_for_items_that_are_set():
    """The exact bug fixed in b4f3282 on Agent 5's /readiness: every section
    showed its missing-case warning regardless of status."""
    tenant = create_tenant("Consequence Co")
    headers = auth_headers(tenant["api_key"])
    _seed_full_envelope(headers)

    body = client.get(f"{BASE}/scope/state", headers=headers).json()
    assert body["operating_state"] == "scoped"
    assert len(body["items"]) == 8
    for item in body["items"]:
        assert item["status"] == "set", item
        assert item["consequence"] == "", item


def test_scope_state_returns_consequence_only_for_missing_items():
    tenant = create_tenant("Partial Consequence Co")
    headers = auth_headers(tenant["api_key"])
    client.put(
        f"{BASE}/scope/categories",
        json=[{"category_key": "EMA-UTIL", "category_name": "Utility actuation"}],
        headers=headers,
    )

    body = client.get(f"{BASE}/scope/state", headers=headers).json()
    assert body["operating_state"] == "partially_scoped"
    by_key = {i["key"]: i for i in body["items"]}
    assert by_key["product_categories"]["status"] == "set"
    assert by_key["product_categories"]["consequence"] == ""
    assert by_key["certification_basis"]["status"] == "missing"
    assert "most consequential" in by_key["certification_basis"]["consequence"]


def test_scope_state_on_an_empty_envelope_is_unscoped_and_says_so():
    tenant = create_tenant("Unscoped State Co")
    headers = auth_headers(tenant["api_key"])
    body = client.get(f"{BASE}/scope/state", headers=headers).json()
    assert body["operating_state"] == "unscoped"
    assert "industry survey" in body["statement"]
    assert all(i["consequence"] for i in body["items"])


def test_scope_state_reports_counts():
    tenant = create_tenant("Counts Co")
    headers = auth_headers(tenant["api_key"])
    client.put(
        f"{BASE}/scope/domains",
        json=[{"domain": "A"}, {"domain": "B"}, {"domain": "C"}],
        headers=headers,
    )
    body = client.get(f"{BASE}/scope/state", headers=headers).json()
    assert {i["key"]: i["count"] for i in body["items"]}["domains"] == 3


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------


def test_post_runs_persists_nine_reports_and_candidate_work():
    tenant = create_tenant("Nine Reports Co")
    headers = auth_headers(tenant["api_key"])
    _seed_full_envelope(headers)

    with patch("app.tech_regulation_service.TechRegulationAgent") as agent_cls:
        agent_cls.return_value.run.return_value = _fake_result()
        resp = client.post(f"{BASE}/runs", json={}, headers=headers)

    assert resp.status_code == 202, resp.text
    run_id = resp.json()["id"]
    assert client.get(f"{BASE}/runs/{run_id}", headers=headers).json()["status"] == "succeeded"

    reports = client.get(f"{BASE}/runs/{run_id}/reports", headers=headers).json()
    assert [r["report_number"] for r in reports] == [1, 2, 3, 4, 5, 6, 7, 8, 11]

    work = client.get(f"{BASE}/candidate-work", headers=headers).json()
    assert [w["candidate_key"] for w in work] == ["TR-01"]
    assert work[0]["status"] == "new"
    assert work[0]["work_date"] == "2028-03-14"
    assert work[0]["applicability"]["certification_bases"] == ["TSO-C196b"]


def test_a_run_is_never_blocked_by_incomplete_scoping():
    """Unlike Market Insights, which 409s without a product line. This agent
    degrades and states its operating state instead."""
    tenant = create_tenant("Unscoped Run Co")
    headers = auth_headers(tenant["api_key"])

    with patch("app.tech_regulation_service.TechRegulationAgent") as agent_cls:
        agent_cls.return_value.run.return_value = _fake_result()
        resp = client.post(f"{BASE}/runs", json={}, headers=headers)

    assert resp.status_code == 202, resp.text
    assert "unscoped" in resp.json()["subject"]


def test_a_failing_run_lands_its_error_on_the_run_row():
    tenant = create_tenant("Failing Run Co")
    headers = auth_headers(tenant["api_key"])

    with patch("app.tech_regulation_service.TechRegulationAgent") as agent_cls:
        agent_cls.return_value.run.side_effect = RuntimeError("boom")
        resp = client.post(f"{BASE}/runs", json={}, headers=headers)

    run = client.get(f"{BASE}/runs/{resp.json()['id']}", headers=headers).json()
    assert run["status"] == "failed"
    assert "RuntimeError: boom" in run["error"]


def test_runs_are_tenant_isolated_with_404_not_403():
    a = create_tenant("Run Isolation A")
    b = create_tenant("Run Isolation B")
    with patch("app.tech_regulation_service.TechRegulationAgent") as agent_cls:
        agent_cls.return_value.run.return_value = _fake_result()
        run_id = client.post(f"{BASE}/runs", json={}, headers=auth_headers(a["api_key"])).json()["id"]

    resp = client.get(f"{BASE}/runs/{run_id}", headers=auth_headers(b["api_key"]))
    assert resp.status_code == 404
    assert client.get(f"{BASE}/runs", headers=auth_headers(b["api_key"])).json() == []


def test_only_this_agents_runs_are_listed():
    tenant = create_tenant("Agent Filter Co")
    headers = auth_headers(tenant["api_key"])
    db = TestingSessionLocal()
    db.add(AgentRun(tenant_id=tenant["id"], agent_type="market-insights", subject="other", status="succeeded"))
    db.commit()
    db.close()

    with patch("app.tech_regulation_service.TechRegulationAgent") as agent_cls:
        agent_cls.return_value.run.return_value = _fake_result()
        client.post(f"{BASE}/runs", json={}, headers=headers)

    runs = client.get(f"{BASE}/runs", headers=headers).json()
    assert [r["agent_type"] for r in runs] == ["tech-regulation"]


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def test_export_carries_the_technology_regulation_cover_label():
    tenant = create_tenant("Export Co")
    headers = auth_headers(tenant["api_key"])
    _seed_full_envelope(headers)

    with patch("app.tech_regulation_service.TechRegulationAgent") as agent_cls:
        agent_cls.return_value.run.return_value = _fake_result()
        run_id = client.post(f"{BASE}/runs", json={}, headers=headers).json()["id"]

    resp = client.get(f"{BASE}/runs/{run_id}/export.docx", headers=headers)
    assert resp.status_code == 200
    assert "Technology_Regulation" in resp.headers["content-disposition"]

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        document = zf.read("word/document.xml").decode("utf-8")
    assert "Technology &amp; Regulation" in document or "Technology & Regulation" in document


def test_export_404s_before_any_reports_exist():
    tenant = create_tenant("Empty Export Co")
    headers = auth_headers(tenant["api_key"])
    db = TestingSessionLocal()
    run = AgentRun(tenant_id=tenant["id"], agent_type="tech-regulation", subject="x", status="pending")
    db.add(run)
    db.commit()
    run_id = run.id
    db.close()

    assert client.get(f"{BASE}/runs/{run_id}/export.docx", headers=headers).status_code == 404


# ---------------------------------------------------------------------------
# Candidate work persistence and triage
# ---------------------------------------------------------------------------


def test_a_dismissed_item_rediscovered_later_keeps_its_status_and_reason():
    """The never-resurrect rule. A re-run refreshes the evidence fields --
    which is how a corrected date propagates -- but must not reset triage."""
    tenant = create_tenant("Dismissal Co")
    headers = auth_headers(tenant["api_key"])
    _seed_full_envelope(headers)

    with patch("app.tech_regulation_service.TechRegulationAgent") as agent_cls:
        agent_cls.return_value.run.return_value = _fake_result()
        client.post(f"{BASE}/runs", json={}, headers=headers)

    patched = client.patch(
        f"{BASE}/candidate-work/TR-01",
        json={"status": "dismissed", "dismissal_reason": "handled under an existing programme"},
        headers=headers,
    )
    assert patched.status_code == 200, patched.text

    # a later run re-surfaces the same key with a corrected date
    with patch("app.tech_regulation_service.TechRegulationAgent") as agent_cls:
        agent_cls.return_value.run.return_value = _fake_result(items=[_item(work_date="2028-09-01")])
        client.post(f"{BASE}/runs", json={}, headers=headers)

    work = client.get(f"{BASE}/candidate-work", headers=headers).json()
    assert len(work) == 1
    assert work[0]["status"] == "dismissed"
    assert work[0]["dismissal_reason"] == "handled under an existing programme"
    assert work[0]["work_date"] == "2028-09-01", "evidence fields must still refresh"


def test_only_genuinely_new_keys_get_status_new():
    tenant = create_tenant("New Keys Co")
    headers = auth_headers(tenant["api_key"])

    with patch("app.tech_regulation_service.TechRegulationAgent") as agent_cls:
        agent_cls.return_value.run.return_value = _fake_result()
        client.post(f"{BASE}/runs", json={}, headers=headers)
    client.patch(
        f"{BASE}/candidate-work/TR-01",
        json={"status": "accepted", "dismissal_reason": ""},
        headers=headers,
    )

    with patch("app.tech_regulation_service.TechRegulationAgent") as agent_cls:
        agent_cls.return_value.run.return_value = _fake_result(
            items=[_item(), _item(candidate_key="TR-02")]
        )
        client.post(f"{BASE}/runs", json={}, headers=headers)

    work = {w["candidate_key"]: w for w in client.get(f"{BASE}/candidate-work", headers=headers).json()}
    assert work["TR-01"]["status"] == "accepted"
    assert work["TR-02"]["status"] == "new"


def test_candidate_work_can_be_filtered_to_one_run():
    """Including items an earlier run found and this one re-confirmed -- the
    same set Agent 5 reads for a pinned upstream run."""
    tenant = create_tenant("Per Run Co")
    headers = auth_headers(tenant["api_key"])

    with patch("app.tech_regulation_service.TechRegulationAgent") as agent_cls:
        agent_cls.return_value.run.return_value = _fake_result()
        first = client.post(f"{BASE}/runs", json={}, headers=headers).json()["id"]
    with patch("app.tech_regulation_service.TechRegulationAgent") as agent_cls:
        agent_cls.return_value.run.return_value = _fake_result(
            items=[_item(), _item(candidate_key="TR-02")]
        )
        second = client.post(f"{BASE}/runs", json={}, headers=headers).json()["id"]

    first_set = client.get(f"{BASE}/candidate-work?run_id={first}", headers=headers).json()
    second_set = client.get(f"{BASE}/candidate-work?run_id={second}", headers=headers).json()
    assert [w["candidate_key"] for w in first_set] == []
    assert [w["candidate_key"] for w in second_set] == ["TR-01", "TR-02"]


def test_dismissing_without_a_reason_is_rejected():
    tenant = create_tenant("Reasonless Co")
    headers = auth_headers(tenant["api_key"])
    with patch("app.tech_regulation_service.TechRegulationAgent") as agent_cls:
        agent_cls.return_value.run.return_value = _fake_result()
        client.post(f"{BASE}/runs", json={}, headers=headers)

    resp = client.patch(
        f"{BASE}/candidate-work/TR-01",
        json={"status": "dismissed", "dismissal_reason": "   "},
        headers=headers,
    )
    assert resp.status_code == 422


def test_candidate_work_delete_exists_and_removes_the_row():
    """Present from the start, unlike DiscoveredCandidate's missing delete
    path (logged as a known gap in app/routers/strategy_synthesis.py)."""
    tenant = create_tenant("Delete Co")
    headers = auth_headers(tenant["api_key"])
    with patch("app.tech_regulation_service.TechRegulationAgent") as agent_cls:
        agent_cls.return_value.run.return_value = _fake_result()
        client.post(f"{BASE}/runs", json={}, headers=headers)

    assert client.delete(f"{BASE}/candidate-work/TR-01", headers=headers).status_code == 204
    assert client.get(f"{BASE}/candidate-work", headers=headers).json() == []
    assert client.delete(f"{BASE}/candidate-work/TR-01", headers=headers).status_code == 404


def test_candidate_work_is_tenant_isolated():
    a = create_tenant("Work Isolation A")
    b = create_tenant("Work Isolation B")
    with patch("app.tech_regulation_service.TechRegulationAgent") as agent_cls:
        agent_cls.return_value.run.return_value = _fake_result()
        client.post(f"{BASE}/runs", json={}, headers=auth_headers(a["api_key"]))

    assert client.get(f"{BASE}/candidate-work", headers=auth_headers(b["api_key"])).json() == []
    assert client.patch(
        f"{BASE}/candidate-work/TR-01",
        json={"status": "accepted", "dismissal_reason": ""},
        headers=auth_headers(b["api_key"]),
    ).status_code == 404
    assert client.delete(
        f"{BASE}/candidate-work/TR-01", headers=auth_headers(b["api_key"])
    ).status_code == 404
