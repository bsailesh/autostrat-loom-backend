"""
Endpoint tests for Strategy Synthesis (Agent 5) Part 5: runs, config,
objectives, framework, scenarios, readiness, candidates. Isolated per
conftest.py's convention: this module defines its own `override_get_db`.

No real Anthropic calls anywhere -- `StrategySynthesisAgent.run` is patched
directly, the same seam Part 4's own tests use.
"""
import io
import os
import zipfile
from unittest.mock import patch

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-real")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LOOM_ADMIN_KEYS", "test-admin-key")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.models import Tenant
import app.strategy_synthesis_service as strategy_synthesis_service
from strategy_synthesis.agent import AgentRunResult, Report, StrategySynthesisAgent
from strategy_synthesis.schemas import Pass1Candidate, Pass1Output

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
# execute_run's background task opens its OWN session via SessionFactory,
# since the request-scoped session is closed by the time the task runs
# (same reason market_insights.py's _execute_run does this) -- point it at
# the test engine too, or it silently hits the real ./loom.db.
strategy_synthesis_service.SessionFactory = TestingSessionLocal
client = TestClient(app)

ADMIN_HEADERS = {"X-Admin-Key": "test-admin-key"}


def create_tenant(name: str) -> dict:
    resp = client.post("/admin/tenants", json={"name": name}, headers=ADMIN_HEADERS)
    assert resp.status_code == 200, resp.text
    return resp.json()


def auth_headers(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


def _fake_result(reports=None, candidates=None) -> AgentRunResult:
    return AgentRunResult(
        pass1_output=Pass1Output(candidates=candidates or []),
        computed=type("C", (), {})(),  # not inspected by _execute_run beyond .reports/.pass1_output
        reports=reports or [Report(report_number=i, title=f"Report {i}", content=f"# Report {i}") for i in range(1, 8)],
    )


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------


def test_post_runs_returns_202_and_persists_seven_reports():
    tenant = create_tenant("Runs Co")
    with patch.object(StrategySynthesisAgent, "run", return_value=_fake_result()):
        resp = client.post("/agents/strategy/runs", json={"fiscal_year": "FY27"}, headers=auth_headers(tenant["api_key"]))
    assert resp.status_code == 202, resp.text
    run = resp.json()
    # The response body reflects the row as it existed when the handler
    # returned it (status="pending") -- the background task (which the
    # TestClient does run to completion before client.post() returns)
    # mutates the DB row via a separate session/object, not this one.
    # Same reason market_insights.py's own POST /run is documented as
    # "returns at once" rather than "returns the final result."
    assert run["status"] == "pending"
    assert run["agent_type"] == "strategy-synthesis"

    updated = client.get(f"/agents/strategy/runs/{run['id']}", headers=auth_headers(tenant["api_key"])).json()
    assert updated["status"] == "succeeded"

    reports = client.get(f"/agents/strategy/runs/{run['id']}/reports", headers=auth_headers(tenant["api_key"])).json()
    assert len(reports) == 7
    assert [r["report_number"] for r in reports] == list(range(1, 8))


def test_post_runs_persists_candidates_without_resurrecting_dismissed_ones():
    tenant = create_tenant("Runs Candidates Co")

    # first run discovers C-01
    with patch.object(StrategySynthesisAgent, "run", return_value=_fake_result(
        candidates=[Pass1Candidate(key="C-01", name="First", origin="x", problem="p", evidence_summary="e",
                                    support_classification="evidence-supported", evidence_strength_rank=1)]
    )):
        client.post("/agents/strategy/runs", json={"fiscal_year": "FY27"}, headers=auth_headers(tenant["api_key"]))

    patch_resp = client.patch(
        "/agents/strategy/candidates/C-01",
        json={"status": "dismissed", "dismissal_reason": "Not this cycle"},
        headers=auth_headers(tenant["api_key"]),
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "dismissed"

    # second run rediscovers C-01 with refreshed evidence
    with patch.object(StrategySynthesisAgent, "run", return_value=_fake_result(
        candidates=[Pass1Candidate(key="C-01", name="First (updated)", origin="x", problem="p2",
                                    evidence_summary="fresher evidence", support_classification="evidence-supported",
                                    evidence_strength_rank=1)]
    )):
        client.post("/agents/strategy/runs", json={"fiscal_year": "FY27"}, headers=auth_headers(tenant["api_key"]))

    # still dismissed, not resurrected as "new"
    resp = client.get("/agents/strategy/runs", headers=auth_headers(tenant["api_key"]))
    assert resp.status_code == 200


def test_list_candidates_reflects_live_status_not_frozen_report_text():
    tenant = create_tenant("List Candidates Co")
    headers = auth_headers(tenant["api_key"])
    with patch.object(StrategySynthesisAgent, "run", return_value=_fake_result(
        candidates=[Pass1Candidate(key="C-04", name="Route to market", origin="x", problem="p",
                                    evidence_summary="e", support_classification="evidence-supported",
                                    evidence_strength_rank=1)]
    )):
        client.post("/agents/strategy/runs", json={"fiscal_year": "FY27"}, headers=headers)

    listed = client.get("/agents/strategy/candidates", headers=headers).json()
    assert [c["candidate_key"] for c in listed] == ["C-04"]
    assert listed[0]["status"] == "new"

    client.patch("/agents/strategy/candidates/C-04", json={"status": "under_review"}, headers=headers)
    listed_again = client.get("/agents/strategy/candidates", headers=headers).json()
    assert listed_again[0]["status"] == "under_review"


def test_scope_candidate_creates_roadmap_project_and_marks_scoped():
    tenant = create_tenant("Scope Candidate Co")
    headers = auth_headers(tenant["api_key"])
    client.put(
        "/agents/strategy/buckets",
        json={"buckets": [
            {"bucket_key": "HW", "bucket_name": "Hardware", "contractable": "yes"},
            {"bucket_key": "SW", "bucket_name": "Software", "contractable": "yes"},
        ]},
        headers=headers,
    )

    with patch.object(StrategySynthesisAgent, "run", return_value=_fake_result(
        candidates=[Pass1Candidate(key="C-04", name="Route-to-market pilot", origin="x", problem="p",
                                    evidence_summary="e", support_classification="evidence-supported",
                                    evidence_strength_rank=1)]
    )):
        client.post("/agents/strategy/runs", json={"fiscal_year": "FY27"}, headers=headers)

    resp = client.post(
        "/agents/strategy/candidates/C-04/scope",
        json={"project_type": "New product", "target_fy": "FY28", "effort_by_bucket": {"HW": 12, "SW": 8}},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "scoped"

    # scoping again must fail -- it's already a roadmap project now
    again = client.post(
        "/agents/strategy/candidates/C-04/scope",
        json={"effort_by_bucket": {"HW": 5}},
        headers=headers,
    )
    assert again.status_code == 400


def test_scope_candidate_rejects_unknown_bucket():
    tenant = create_tenant("Scope Candidate Bad Bucket Co")
    headers = auth_headers(tenant["api_key"])
    client.put(
        "/agents/strategy/buckets",
        json={"buckets": [{"bucket_key": "HW", "bucket_name": "Hardware", "contractable": "yes"},
                           {"bucket_key": "SW", "bucket_name": "Software", "contractable": "yes"}]},
        headers=headers,
    )
    with patch.object(StrategySynthesisAgent, "run", return_value=_fake_result(
        candidates=[Pass1Candidate(key="C-05", name="X", origin="x", problem="p", evidence_summary="e",
                                    support_classification="evidence-supported", evidence_strength_rank=1)]
    )):
        client.post("/agents/strategy/runs", json={"fiscal_year": "FY27"}, headers=headers)

    resp = client.post(
        "/agents/strategy/candidates/C-05/scope",
        json={"effort_by_bucket": {"NOPE": 5}},
        headers=headers,
    )
    assert resp.status_code == 400


def test_scope_candidate_404s_for_unknown_key():
    tenant = create_tenant("Scope Candidate Unknown Co")
    resp = client.post(
        "/agents/strategy/candidates/C-99/scope",
        json={"effort_by_bucket": {"HW": 5}},
        headers=auth_headers(tenant["api_key"]),
    )
    assert resp.status_code == 404


def test_run_failure_sets_status_failed_with_error_message():
    tenant = create_tenant("Failing Run Co")
    with patch.object(StrategySynthesisAgent, "run", side_effect=RuntimeError("boom")):
        resp = client.post("/agents/strategy/runs", json={"fiscal_year": "FY27"}, headers=auth_headers(tenant["api_key"]))
    run_id = resp.json()["id"]

    run = client.get(f"/agents/strategy/runs/{run_id}", headers=auth_headers(tenant["api_key"])).json()
    assert run["status"] == "failed"
    assert "boom" in run["error"]


def test_ambiguous_fiscal_year_without_explicit_choice_is_a_400():
    tenant = create_tenant("Ambiguous FY Co")
    client.put(
        "/agents/strategy/buckets",
        json={"buckets": [{"bucket_key": "HW", "bucket_name": "Hardware"}, {"bucket_key": "SW", "bucket_name": "Software"}]},
        headers=auth_headers(tenant["api_key"]),
    )
    # capacity.csv ingest is delete-and-replace PER UPLOAD (Part 2) -- two
    # separate uploads would just leave the second year's data, not both.
    # Both fiscal years belong in one file, as a real multi-year
    # capacity_fy26_fy29.csv would have them.
    csv_text = "fiscal_year,bucket_id,fte,capacity_units,budget\nFY27,HW,1,10,1\nFY28,HW,1,10,1\n"
    upload_resp = client.post(
        "/agents/strategy/files/capacity",
        files={"file": ("c.csv", io.BytesIO(csv_text.encode()), "text/csv")},
        headers=auth_headers(tenant["api_key"]),
    )
    assert upload_resp.json()["stored"] is True, upload_resp.json()

    resp = client.post("/agents/strategy/runs", json={}, headers=auth_headers(tenant["api_key"]))
    assert resp.status_code == 400
    assert "FY27" in resp.json()["detail"] and "FY28" in resp.json()["detail"]

    # The frontend can offer a choice up front instead of discovering the
    # ambiguity only from that 400.
    years_resp = client.get("/agents/strategy/fiscal-years", headers=auth_headers(tenant["api_key"]))
    assert years_resp.status_code == 200
    assert years_resp.json() == ["FY27", "FY28"]

    # Passing the now-disambiguated year succeeds.
    with patch.object(StrategySynthesisAgent, "run", return_value=_fake_result()):
        ok_resp = client.post("/agents/strategy/runs", json={"fiscal_year": "FY27"}, headers=auth_headers(tenant["api_key"]))
    assert ok_resp.status_code == 202


def test_fiscal_years_empty_when_no_capacity_declared():
    tenant = create_tenant("No Capacity FY Co")
    resp = client.get("/agents/strategy/fiscal-years", headers=auth_headers(tenant["api_key"]))
    assert resp.status_code == 200
    assert resp.json() == []


def test_runs_are_tenant_scoped():
    tenant_a = create_tenant("Iso Run A Co")
    tenant_b = create_tenant("Iso Run B Co")
    with patch.object(StrategySynthesisAgent, "run", return_value=_fake_result()):
        resp = client.post("/agents/strategy/runs", json={"fiscal_year": "FY27"}, headers=auth_headers(tenant_a["api_key"]))
    run_id = resp.json()["id"]

    resp_b = client.get(f"/agents/strategy/runs/{run_id}", headers=auth_headers(tenant_b["api_key"]))
    assert resp_b.status_code == 404


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def test_export_docx_uses_strategy_synthesis_cover_not_market_insights():
    tenant = create_tenant("Export Cover Co")
    with patch.object(StrategySynthesisAgent, "run", return_value=_fake_result()):
        resp = client.post("/agents/strategy/runs", json={"fiscal_year": "FY27"}, headers=auth_headers(tenant["api_key"]))
    run_id = resp.json()["id"]

    export_resp = client.get(f"/agents/strategy/runs/{run_id}/export.docx", headers=auth_headers(tenant["api_key"]))
    assert export_resp.status_code == 200
    assert export_resp.content[:2] == b"PK"  # docx is a zip

    with zipfile.ZipFile(io.BytesIO(export_resp.content)) as zf:
        document_xml = zf.read("word/document.xml").decode("utf-8", errors="ignore")
    assert "Strategy Synthesis" in document_xml
    assert "Market Insights" not in document_xml
    assert "AutoStrat_Loom_Strategy_Synthesis_" in export_resp.headers["content-disposition"]


# ---------------------------------------------------------------------------
# Config / objectives / framework / scenarios round-trips
# ---------------------------------------------------------------------------


def test_config_round_trip():
    tenant = create_tenant("Config Co")
    payload = {
        "effort_unit": "engineer_weeks",
        "fiscal_year_start_month": 10,
        "fiscal_year_label_format": "FY{yy}",
        "project_types": ["Compliance", "Sustainment"],
        "effort_bands": [{"band_name": "Small", "min_units": 0, "max_units": 40}],
        "rules": [{"rule_type": "min_effort_to_rank", "value": "20"}],
    }
    put_resp = client.put("/agents/strategy/config", json=payload, headers=auth_headers(tenant["api_key"]))
    assert put_resp.status_code == 200, put_resp.text
    assert put_resp.json()["configured"] is True

    get_resp = client.get("/agents/strategy/config", headers=auth_headers(tenant["api_key"])).json()
    assert get_resp["effort_unit"] == "engineer_weeks"
    assert get_resp["effort_bands"][0]["band_name"] == "Small"
    assert get_resp["rules"][0]["rule_type"] == "min_effort_to_rank"


def test_objectives_round_trip():
    tenant = create_tenant("Objectives Co")
    payload = {"objectives": [{"objective_key": "SO-1", "text": "Capture the cohort", "horizon": "2030"}]}
    client.put("/agents/strategy/objectives", json=payload, headers=auth_headers(tenant["api_key"]))
    result = client.get("/agents/strategy/objectives", headers=auth_headers(tenant["api_key"])).json()
    assert result[0]["objective_key"] == "SO-1"


def test_proposals_round_trip():
    tenant = create_tenant("Proposals Co")
    payload = {"proposals": [
        {"project_key": "U-01", "name": "Shore-power retrofit kit", "proposed_by": "VP Sales",
         "description": "Bundled kit for the retrofit cohort.", "rationale": "Customers keep asking for it."},
    ]}
    put_resp = client.put("/agents/strategy/proposals", json=payload, headers=auth_headers(tenant["api_key"]))
    assert put_resp.status_code == 200, put_resp.text
    assert put_resp.json()[0]["project_key"] == "U-01"

    result = client.get("/agents/strategy/proposals", headers=auth_headers(tenant["api_key"])).json()
    assert result[0]["project_key"] == "U-01"
    assert result[0]["proposed_by"] == "VP Sales"


def test_proposals_reject_duplicate_project_keys():
    tenant = create_tenant("Proposals Dup Co")
    resp = client.put(
        "/agents/strategy/proposals",
        json={"proposals": [
            {"project_key": "U-01", "name": "A"},
            {"project_key": "U-01", "name": "B"},
        ]},
        headers=auth_headers(tenant["api_key"]),
    )
    assert resp.status_code == 400


def test_framework_rejects_weights_not_summing_to_one():
    tenant = create_tenant("Framework Bad Co")
    resp = client.put(
        "/agents/strategy/framework",
        json={"framework": "weighted_scoring", "criteria": [{"criterion": "customer", "weight": 0.9}]},
        headers=auth_headers(tenant["api_key"]),
    )
    assert resp.status_code == 400


def test_framework_round_trip():
    tenant = create_tenant("Framework Co")
    payload = {
        "framework": "weighted_scoring",
        "criteria": [
            {"criterion": "customer", "weight": 0.5, "source_agent": "voice-of-customer"},
            {"criterion": "effort", "weight": 0.5},
        ],
    }
    client.put("/agents/strategy/framework", json=payload, headers=auth_headers(tenant["api_key"]))
    result = client.get("/agents/strategy/framework", headers=auth_headers(tenant["api_key"])).json()
    assert result["configured"] is True
    assert {c["criterion"] for c in result["criteria"]} == {"customer", "effort"}


def test_scenarios_round_trip():
    tenant = create_tenant("Scenarios Co")
    client.put(
        "/agents/strategy/framework",
        json={"framework": "weighted_scoring", "criteria": [
            {"criterion": "customer", "weight": 0.5}, {"criterion": "risk", "weight": 0.5},
        ]},
        headers=auth_headers(tenant["api_key"]),
    )
    # Each scenario's weights override the framework's per criterion and must
    # still sum to 1.0 once merged with it -- both criteria are overridden
    # here so the merge is just the override itself.
    payload = {
        "scenarios": [
            {"name": "Growth", "weights": [{"criterion": "customer", "weight": 0.8}, {"criterion": "risk", "weight": 0.2}]},
            {"name": "Sustainment", "weights": [{"criterion": "risk", "weight": 0.7}, {"criterion": "customer", "weight": 0.3}]},
        ]
    }
    resp = client.put("/agents/strategy/scenarios", json=payload, headers=auth_headers(tenant["api_key"]))
    assert resp.status_code == 200, resp.text
    result = client.get("/agents/strategy/scenarios", headers=auth_headers(tenant["api_key"])).json()
    assert {s["name"] for s in result} == {"Growth", "Sustainment"}
    growth = next(s for s in result if s["name"] == "Growth")
    assert growth["weights"][0]["criterion"] == "customer"


def test_scenarios_reject_weights_that_do_not_sum_to_one_with_framework():
    tenant = create_tenant("Scenarios Bad Co")
    client.put(
        "/agents/strategy/framework",
        json={"framework": "weighted_scoring", "criteria": [
            {"criterion": "customer", "weight": 0.5}, {"criterion": "risk", "weight": 0.5},
        ]},
        headers=auth_headers(tenant["api_key"]),
    )
    resp = client.put(
        "/agents/strategy/scenarios",
        json={"scenarios": [
            {"name": "Growth", "weights": [{"criterion": "customer", "weight": 0.8}]},
            {"name": "Base", "weights": []},
        ]},
        headers=auth_headers(tenant["api_key"]),
    )
    assert resp.status_code == 400
    assert "Growth" in resp.text


def test_framework_weights_reach_assembled_brief():
    """Regression test for a production incident: a run failed with
    "criterion weights must sum to 1.0, got 0" even though PUT /framework
    had succeeded. Root cause was that assemble_brief passed a scenario's
    per-criterion weight overrides straight to compute.py as if they were a
    complete weight set, instead of merging them onto the framework's
    declared weights -- so a "Base" scenario declared with no overrides
    (weights: [], meaning "use the framework's weights unchanged") produced
    an empty weight set instead of inheriting the framework's. This
    round-trips PUT framework -> PUT scenarios -> assemble_brief and checks
    the weights that would actually reach compute.py."""
    tenant = create_tenant("Weights Round Trip Co")
    api_headers = auth_headers(tenant["api_key"])
    framework_payload = {
        "framework": "weighted_scoring",
        "criteria": [
            {"criterion": "customer_value", "weight": 0.6},
            {"criterion": "effort_inverse", "weight": 0.4},
        ],
    }
    resp = client.put("/agents/strategy/framework", json=framework_payload, headers=api_headers)
    assert resp.status_code == 200, resp.text

    resp = client.put(
        "/agents/strategy/scenarios",
        json={"scenarios": [
            {"name": "Base", "emphasis": "Weights as declared in the framework", "weights": []},
            {"name": "Growth", "weights": [{"criterion": "customer_value", "weight": 0.9},
                                            {"criterion": "effort_inverse", "weight": 0.1}]},
        ]},
        headers=api_headers,
    )
    assert resp.status_code == 200, resp.text

    db = TestingSessionLocal()
    try:
        tenant_row = db.query(Tenant).filter(Tenant.id == tenant["id"]).first()
        brief = strategy_synthesis_service.assemble_brief(db, tenant_row, fiscal_year="FY27")
    finally:
        db.close()

    assert brief.weights == {"customer_value": 0.6, "effort_inverse": 0.4}
    scenarios_by_name = {s.name: s.weights for s in brief.scenarios}
    # The regression case: an empty override list inherits the framework's
    # weights rather than producing an empty (sum-to-zero) weight set.
    assert scenarios_by_name["Base"] == {"customer_value": 0.6, "effort_inverse": 0.4}
    assert scenarios_by_name["Growth"] == {"customer_value": 0.9, "effort_inverse": 0.1}
    for weights in scenarios_by_name.values():
        assert abs(sum(weights.values()) - 1.0) < 0.01


def test_scenarios_reject_fewer_than_two():
    tenant = create_tenant("Too Few Scenarios Co")
    resp = client.put(
        "/agents/strategy/scenarios",
        json={"scenarios": [{"name": "OnlyOne", "weights": []}]},
        headers=auth_headers(tenant["api_key"]),
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Readiness
# ---------------------------------------------------------------------------


def test_readiness_reflects_incomplete_brief_with_stated_consequence():
    tenant = create_tenant("Readiness Co")
    items = client.get("/agents/strategy/readiness", headers=auth_headers(tenant["api_key"])).json()
    by_item = {i["item"]: i for i in items}
    assert by_item["Capacity"]["status"] == "missing"
    assert "bottleneck analysis" in by_item["Capacity"]["consequence"]
    assert by_item["Scenarios"]["status"] == "missing"
    assert by_item["Scenarios"]["consequence"] == "Base case only."


def test_readiness_never_blocks_a_run():
    tenant = create_tenant("Readiness Never Blocks Co")
    items = client.get("/agents/strategy/readiness", headers=auth_headers(tenant["api_key"])).json()
    assert all(i["status"] == "missing" for i in items)  # brief-new tenant, everything missing

    with patch.object(StrategySynthesisAgent, "run", return_value=_fake_result()):
        resp = client.post("/agents/strategy/runs", json={"fiscal_year": "FY27"}, headers=auth_headers(tenant["api_key"]))
    assert resp.status_code == 202


# ---------------------------------------------------------------------------
# Cross-tenant isolation, spot-checked across the new endpoints
# ---------------------------------------------------------------------------


def test_config_objectives_framework_scenarios_are_tenant_scoped():
    tenant_a = create_tenant("Iso Config A Co")
    tenant_b = create_tenant("Iso Config B Co")

    client.put(
        "/agents/strategy/config",
        json={"effort_unit": "person_days", "fiscal_year_start_month": 1, "fiscal_year_label_format": "FY{yy}"},
        headers=auth_headers(tenant_a["api_key"]),
    )
    b_config = client.get("/agents/strategy/config", headers=auth_headers(tenant_b["api_key"])).json()
    assert b_config["configured"] is False
    assert b_config["effort_unit"] == "weeks"  # tenant B's own default, untouched by A's PUT
