"""
Agent 4 endpoints and persistence: masters with referential integrity,
matrix ingest failing loudly on a dangling reference, data files, readiness,
runs that succeed with incomplete data, export cover label, candidate work
triage (dismissal survives re-discovery), cross-tenant 404 -- and Agent 5
reading ps_candidate_work.

Isolated per conftest.py: `override_get_db` at module level, the service
SessionFactory pinned per test, never at import.
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

import app.product_sustainment_service as ps_service
from app.database import Base
from app.main import app
from app.models import AgentRun, PsCandidateWork, Tenant
from app.strategy_synthesis_service import load_sustainment_candidate_work
from product_sustainment.agent import AgentRunResult, Report
from product_sustainment.compute import compute_sustainment
from product_sustainment.schemas import CandidateWorkItem
from product_sustainment.structure import compute_inputs
from strategy_synthesis.prompts import pass1_user_prompt

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _pin_ps_session_factory():
    previous = ps_service.SessionFactory
    ps_service.SessionFactory = TestingSessionLocal
    try:
        yield
    finally:
        ps_service.SessionFactory = previous


client = TestClient(app)
BASE = "/agents/product-sustainment"


def create_tenant(name: str) -> dict:
    resp = client.post("/admin/tenants", json={"name": name}, headers={"X-Admin-Key": "test-admin-key"})
    assert resp.status_code == 200, resp.text
    return resp.json()


class Headers(dict):
    """Auth headers that also carry the tenant id, for direct DB reads."""
    tenant_id: str


@pytest.fixture
def h():
    t = create_tenant("Arden")
    headers = Headers({"Authorization": f"Bearer {t['api_key']}"})
    headers.tenant_id = t["id"]
    return headers


def _upload(h, path, text, **form):
    return client.post(f"{BASE}{path}", files={"file": ("f.csv", text.encode(), "text/csv")}, data=form, headers=h)


LRU_L1 = "LRU,CCA-MC,CCA-PWR,CCA-SENS\nAR-FIN,1,1,1\nAR-TVC,1,2,\nAR-UTIL,1,,1\n"
L1_L2 = "Level2,CCA-MC,CCA-PWR,CCA-SENS\nGaN-650,,6,\nFPGA-A,1,,1\nRES-PREC,12,8,4\n"


def _load_masters(h):
    for path, rows in [
        ("lrus", [{"lru_id": i, "product_line": pl} for i, pl in (("AR-FIN", "Missile"), ("AR-TVC", "Launch"), ("AR-UTIL", "Aero"))]),
        ("level1", [{"level1_id": i} for i in ("CCA-MC", "CCA-PWR", "CCA-SENS")]),
        ("level2", [{"level2_id": i} for i in ("GaN-650", "FPGA-A", "RES-PREC")]),
    ]:
        assert client.put(f"{BASE}/structure/{path}", json=rows, headers=h).status_code == 200


def _load_arden(h):
    _load_masters(h)
    # Warns on the first matrix: Level 2 has no assembly link until the second.
    assert _upload(h, "/structure/matrix/lru-level1", LRU_L1).json()["file"]["validation_status"] != "invalid"
    assert _upload(h, "/structure/matrix/level1-level2", L1_L2).json()["file"]["validation_status"] == "valid"
    _upload(h, "/files/demand", "LRU,2027,2028\nAR-FIN,120,120\nAR-TVC,120,120\nAR-UTIL,,\n")
    _upload(h, "/files/inventory", "part_id,part_level,location,form,quantity,as_of\nGaN-650,level2,Plant A,raw,1000,2027-01-01\n")
    _upload(h, "/files/risk", "part_id,risk_type,source,lifecycle_status,last_time_buy_date\n"
                             "GaN-650,end_of_life,Infineon PCN 2026-117,NFND,2027-09-30\n")


class TestStructure:
    def test_matrix_upload_returns_validation_and_derived_picture(self, h):
        _load_masters(h)
        out = _upload(h, "/structure/matrix/lru-level1", LRU_L1).json()
        assert out["file"]["validation_status"] in ("valid", "valid_with_warnings")
        # Level 2 has no assembly link yet: every component lacks a demand path.
        assert set(out["summary"]["parts_without_demand_path"]) == {"GaN-650", "FPGA-A", "RES-PREC"}
        out = _upload(h, "/structure/matrix/level1-level2", L1_L2).json()
        assert out["summary"]["parts_without_demand_path"] == []
        assert out["summary"]["lru_level1_edges"] == 7

    def test_dangling_reference_fails_loudly_and_writes_nothing(self, h):
        _load_masters(h)
        _upload(h, "/structure/matrix/lru-level1", LRU_L1)
        out = _upload(h, "/structure/matrix/lru-level1", LRU_L1.replace("CCA-SENS", "CCA-GHOST")).json()
        assert out["file"]["validation_status"] == "invalid"
        assert any("CCA-GHOST" in i["message"] for i in out["file"]["issues"])
        assert out["summary"]["lru_level1_edges"] == 7  # previous edges untouched

    def test_removing_a_referenced_master_id_is_refused(self, h):
        _load_masters(h)
        _upload(h, "/structure/matrix/lru-level1", LRU_L1)
        resp = client.put(f"{BASE}/structure/level1", json=[{"level1_id": "CCA-MC"}, {"level1_id": "CCA-PWR"}], headers=h)
        assert resp.status_code == 409 and "CCA-SENS" in resp.json()["detail"]

    def test_template_from_declared_ids(self, h):
        _load_masters(h)
        text = client.get(f"{BASE}/structure/templates/level1-level2", headers=h).text
        assert text.splitlines()[0] == "Level2,CCA-MC,CCA-PWR,CCA-SENS"

    def test_demand_for_undeclared_lru_is_an_error(self, h):
        _load_masters(h)
        f = _upload(h, "/files/demand", "LRU,2027\nAR-GHOST,5\n").json()
        assert f["validation_status"] == "invalid"


class TestReadinessAndRuns:
    def test_readiness_consequence_empty_for_set_items(self, h):
        _load_arden(h)
        state = client.get(f"{BASE}/readiness", headers=h).json()
        for i in state["items"]:
            assert (i["consequence"] == "") == (i["status"] == "set")

    def test_empty_tenant_is_an_exposure_scan(self, h):
        state = client.get(f"{BASE}/readiness", headers=h).json()
        assert state["operating_tier"] == "exposure_scan"
        bom = next(i for i in state["items"] if i["key"] == "bom")
        assert "single most consequential omission" in bom["consequence"]


def _fake_result(tenant_id, tier="tier_1_partial", items=None):
    db = TestingSessionLocal()
    try:
        data = ps_service.assemble_data(db, db.get(Tenant, tenant_id))
    finally:
        db.close()
    from datetime import date
    computation = compute_sustainment(compute_inputs(data, date(2027, 1, 15)))
    return AgentRunResult(
        operating_tier=tier, operating_tier_line="**Operating tier**", generated_at="2027-01-15T00:00:00Z",
        model="claude-opus-5", computation=computation, web_search_queries=[], research_sources=[],
        research_brief="", candidate_work=items or [],
        reports=[Report(1, "Sustainment intelligence report", "## Governing Insight\nx", "")],
    )


def _cw(**over) -> CandidateWorkItem:
    base = dict(
        candidate_key="PS-GaN-650", part_id="GaN-650", driver="GaN-650 EOL, Infineon PCN 2026-117",
        work_date="2027-06", date_basis="runout", applicability={"part": "GaN-650", "lrus": ["AR-FIN", "AR-TVC"], "level1": ["CCA-PWR"]},
        quantity_required=3320, quantity_basis="through the end of the supplied forecast horizon (2028)",
        qualified_alternate_part_id=None, candidate_alternates=[{"part_number": "X", "basis": "manufacturer_replacement"}],
        work_implied="last_time_buy", work_implied_description="", classification="FACT", confidence="High",
        source="Infineon PCN 2026-117", source_date="2026-10-01",
    )
    base.update(over)
    return CandidateWorkItem(**base)


def _tenant_id(h):
    return h.tenant_id


def _run(h, result_factory):
    with patch.object(ps_service.ProductSustainmentAgent, "run", side_effect=lambda *a, **k: result_factory()):
        resp = client.post(f"{BASE}/run", headers=h)
    assert resp.status_code == 202, resp.text
    return resp.json()


class TestRunsAndCandidateWork:
    def test_incomplete_data_still_runs(self, h):
        _load_masters(h)  # no matrices, no demand, no inventory
        tid = _tenant_id(h)
        run = _run(h, lambda: _fake_result(tid, tier="exposure_scan"))
        got = client.get(f"{BASE}/runs/{run['id']}", headers=h).json()
        assert got["status"] == "succeeded" and got["operating_tier"] == "exposure_scan"

    def test_candidate_work_persisted_and_dismissal_survives_rediscovery(self, h):
        _load_arden(h)
        tid = _tenant_id(h)
        _run(h, lambda: _fake_result(tid, items=[_cw()]))
        rows = client.get(f"{BASE}/candidate-work", headers=h).json()
        assert rows[0]["quantity_required"] == 3320 and rows[0]["applicability"]["lrus"] == ["AR-FIN", "AR-TVC"]
        assert client.patch(f"{BASE}/candidate-work/PS-GaN-650", json={"status": "dismissed"}, headers=h).status_code == 422
        client.patch(f"{BASE}/candidate-work/PS-GaN-650", json={"status": "dismissed", "dismissal_reason": "redesign funded"}, headers=h)
        _run(h, lambda: _fake_result(tid, items=[_cw(quantity_required=3000)]))
        row = client.get(f"{BASE}/candidate-work", headers=h).json()[0]
        assert row["status"] == "dismissed" and row["quantity_required"] == 3000

    def test_delete_candidate_work(self, h):
        _load_arden(h)
        tid = _tenant_id(h)
        _run(h, lambda: _fake_result(tid, items=[_cw()]))
        assert client.delete(f"{BASE}/candidate-work/PS-GaN-650", headers=h).status_code == 204
        assert client.get(f"{BASE}/candidate-work", headers=h).json() == []

    def test_cross_tenant_404(self, h):
        _load_arden(h)
        tid = _tenant_id(h)
        run = _run(h, lambda: _fake_result(tid, items=[_cw()]))
        other = {"Authorization": f"Bearer {create_tenant('Other')['api_key']}"}
        for path in (f"/runs/{run['id']}", f"/runs/{run['id']}/reports", f"/runs/{run['id']}/export.docx"):
            assert client.get(f"{BASE}{path}", headers=other).status_code == 404
        assert client.patch(f"{BASE}/candidate-work/PS-GaN-650", json={"status": "accepted"}, headers=other).status_code == 404
        assert client.delete(f"{BASE}/candidate-work/PS-GaN-650", headers=other).status_code == 404

    @pytest.mark.parametrize("tier,label", [("tier_1_partial", "Product Sustainment"),
                                            ("exposure_scan", "Obsolescence and Exposure Scan")])
    def test_export_cover_label(self, h, tier, label):
        _load_arden(h)
        tid = _tenant_id(h)
        run = _run(h, lambda: _fake_result(tid, tier=tier))
        resp = client.get(f"{BASE}/runs/{run['id']}/export.docx", headers=h)
        assert resp.status_code == 200
        with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
            assert label in z.read("word/document.xml").decode("utf-8")


class TestAgent5ReadsSustainmentCandidateWork:
    def test_rows_reach_pass1_with_quantity_and_every_lru(self, h):
        _load_arden(h)
        tid = _tenant_id(h)
        _run(h, lambda: _fake_result(tid, items=[_cw()]))
        db = TestingSessionLocal()
        try:
            rows = load_sustainment_candidate_work(db, db.get(Tenant, tid), None)
        finally:
            db.close()
        assert rows[0]["candidate_key"] == "PS-GaN-650"
        assert rows[0]["quantity_required"] == 3320
        prompt = pass1_user_prompt("brief", {}, None, rows)
        assert "Pre-structured candidate work (from Product Sustainment)" in prompt
        assert '"AR-TVC"' in prompt and "NOT qualified" in prompt

    def test_dismissed_items_do_not_reach_agent5(self, h):
        _load_arden(h)
        tid = _tenant_id(h)
        _run(h, lambda: _fake_result(tid, items=[_cw()]))
        client.patch(f"{BASE}/candidate-work/PS-GaN-650", json={"status": "dismissed", "dismissal_reason": "x"}, headers=h)
        db = TestingSessionLocal()
        try:
            assert load_sustainment_candidate_work(db, db.get(Tenant, tid), None) == []
        finally:
            db.close()

    def test_tech_regulation_section_is_unchanged_when_no_sustainment_rows(self):
        assert "Product Sustainment" not in pass1_user_prompt("brief", {}, [{"candidate_key": "TR-01"}])


class TestFullRunoutTable:
    def test_full_positions_served_beyond_the_report_cap(self, h):
        _load_arden(h)
        tid = _tenant_id(h)
        run = _run(h, lambda: _fake_result(tid))
        body = client.get(f"{BASE}/runs/{run['id']}/runout", headers=h).json()
        gan = next(r for r in body["rows"] if r["component"] == "GaN-650")
        assert gan["runout"] == "Jun 2027" and gan["ltb_status"] == "Critical"
        assert gan["affected_lrus"] == ["AR-FIN", "AR-TVC"]
        assert gan["end_inventory"] == {"2027": -1160, "2028": -3320}
        assert {p["part_id"] for p in body["insufficient"]} >= {"FPGA-A", "RES-PREC"}
        other = {"Authorization": f"Bearer {create_tenant('Other')['api_key']}"}
        assert client.get(f"{BASE}/runs/{run['id']}/runout", headers=other).status_code == 404
