"""
Endpoint, ingest and persistence tests for Agent 1 (Voice of Customer):
context sections, /context/state, evidence upload (text, PDF, CSV), runs,
reports and export.

Isolated per conftest.py's convention: `override_get_db` at module level,
and the service SessionFactory pinned per test in a fixture -- never at
import, which is the collection-order trap logged in conftest.py.

No real Anthropic calls -- `VoiceOfCustomerAgent.run` is patched.
"""
import io
import json
import os
import zipfile
from unittest.mock import patch

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-real")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LOOM_ADMIN_KEYS", "test-admin-key")

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.voice_of_customer_service as voc_service
from app.database import Base
from app.main import app
from app.models import AgentRun, Tenant, VocEvidenceItem
from voice_of_customer.agent import AgentRunResult, Report
from voice_of_customer import ingest

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
def _pin_voc_session_factory():
    previous = voc_service.SessionFactory
    voc_service.SessionFactory = TestingSessionLocal
    try:
        yield
    finally:
        voc_service.SessionFactory = previous


client = TestClient(app)

ADMIN_HEADERS = {"X-Admin-Key": "test-admin-key"}
BASE = "/agents/voice-of-customer"


def create_tenant(name: str) -> dict:
    resp = client.post("/admin/tenants", json={"name": name}, headers=ADMIN_HEADERS)
    assert resp.status_code == 200, resp.text
    return resp.json()


def auth_headers(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


@pytest.fixture
def tenant():
    t = create_tenant("VoC tenant")
    return {"id": t["id"], "headers": auth_headers(t["api_key"])}


def _text_pdf(text: str) -> bytes:
    """A minimal one-page PDF with a real text layer, built by hand so the
    test needs nothing beyond pypdf to read it back."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % i + body + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1))
    for off in offsets:
        out.write(b"%010d 00000 n \n" % off)
    out.write(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref))
    return out.getvalue()


def _blank_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def _upload(tenant, filename, content: bytes, file_type="support_tickets", **form):
    data = {"file_type": file_type, **{k: (json.dumps(v) if isinstance(v, dict) else str(v)) for k, v in form.items()}}
    return client.post(
        f"{BASE}/evidence",
        files={"file": (filename, content, "application/octet-stream")},
        data=data,
        headers=tenant["headers"],
    )


TICKETS_CSV = (
    "Ticket,Opened,Segment,Category,Description\n"
    "T-1,2026-01-03,OEM-PRIME,Integration,Control interface handshake failed\n"
    "T-2,2026-02-11,OEM-TIER1,Lead time,Waiting on shipset\n"
    "T-3,2026-02-19,OEM-PRIME,Integration,CAN timing mismatch\n"
).encode()


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------


class TestIngestFormats:
    def test_text_is_stored(self, tenant):
        resp = _upload(tenant, "notes.md", b"# Visit\n\nThe integrator asked for a service tool.\n",
                       file_type="visit_interview_notes")
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["file_format"] == "text" and body["ingest_status"] == "ingested"
        assert body["char_count"] > 0

    def test_pdf_text_is_extracted(self, tenant):
        resp = _upload(tenant, "visit.pdf", _text_pdf("Field diagnosis takes too long"),
                       file_type="visit_interview_notes")
        assert resp.status_code == 201, resp.text
        assert resp.json()["page_count"] == 1
        db = TestingSessionLocal()
        try:
            item = db.query(VocEvidenceItem).filter(VocEvidenceItem.file_id == resp.json()["id"]).one()
            assert "Field diagnosis takes too long" in item.text
        finally:
            db.close()

    def test_pdf_with_no_extractable_text_is_rejected_as_scanned(self, tenant):
        resp = _upload(tenant, "scan.pdf", _blank_pdf(), file_type="warranty_claims")
        assert resp.status_code == 422
        assert resp.json()["detail"] == ingest.SCANNED_PDF_MESSAGE
        assert "almost certainly a scanned image" in resp.json()["detail"]
        assert client.get(f"{BASE}/evidence", headers=tenant["headers"]).json() == []

    @pytest.mark.parametrize("name", ["claims.docx", "export.xlsx", "email.msg"])
    def test_office_formats_rejected_naming_supported_ones(self, tenant, name):
        resp = _upload(tenant, name, b"PK\x03\x04")
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert ".txt" in detail and ".pdf" in detail and ".csv" in detail

    def test_unknown_format_rejected_naming_supported_ones(self, tenant):
        resp = _upload(tenant, "data.json", b"{}")
        assert resp.status_code == 422
        assert "Supported formats" in resp.json()["detail"]

    def test_upload_cap_is_stated(self, tenant, monkeypatch):
        monkeypatch.setattr(ingest, "MAX_UPLOAD_BYTES", 10)
        resp = _upload(tenant, "big.csv", TICKETS_CSV)
        assert resp.status_code == 413
        assert "upload limit" in resp.json()["detail"]

    def test_unknown_file_type_rejected(self, tenant):
        resp = _upload(tenant, "t.csv", TICKETS_CSV, file_type="tea_leaves")
        assert resp.status_code == 422


class TestCsv:
    def test_header_detected_and_returned_without_requiring_a_mapping(self, tenant):
        resp = _upload(tenant, "tickets.csv", TICKETS_CSV, row_unit="ticket")
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["columns"] == ["Ticket", "Opened", "Segment", "Category", "Description"]
        assert body["row_count"] == 3
        assert body["column_roles"] == {}
        assert any("No columns are mapped" in i["message"] for i in body["issues"])

    def test_mapping_at_upload_and_by_patch(self, tenant):
        resp = _upload(tenant, "tickets.csv", TICKETS_CSV, column_roles={"category": "Category"})
        assert resp.json()["column_roles"] == {"category": "Category"}
        fid = resp.json()["id"]
        patched = client.patch(
            f"{BASE}/evidence/{fid}",
            json={"column_roles": {"date": "Opened", "segment": "Segment"}, "row_unit": "ticket"},
            headers=tenant["headers"],
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["column_roles"] == {"date": "Opened", "segment": "Segment"}

    def test_mapping_to_a_column_not_in_the_file_is_rejected(self, tenant):
        fid = _upload(tenant, "tickets.csv", TICKETS_CSV).json()["id"]
        resp = client.patch(f"{BASE}/evidence/{fid}", json={"column_roles": {"category": "Nope"}},
                            headers=tenant["headers"])
        assert resp.status_code == 422
        assert "Detected" in resp.json()["detail"]

    def test_unknown_role_rejected(self, tenant):
        resp = _upload(tenant, "tickets.csv", TICKETS_CSV, column_roles={"mood": "Category"})
        assert resp.status_code == 422

    def test_header_only_csv_rejected(self, tenant):
        resp = _upload(tenant, "empty.csv", b"A,B\n")
        assert resp.status_code == 422

    def test_delete_removes_items(self, tenant):
        fid = _upload(tenant, "tickets.csv", TICKETS_CSV).json()["id"]
        assert client.delete(f"{BASE}/evidence/{fid}", headers=tenant["headers"]).status_code == 204
        db = TestingSessionLocal()
        try:
            assert db.query(VocEvidenceItem).filter(VocEvidenceItem.file_id == fid).count() == 0
        finally:
            db.close()

    def test_other_tenants_file_is_404(self, tenant):
        fid = _upload(tenant, "tickets.csv", TICKETS_CSV).json()["id"]
        other = create_tenant("Other")
        h = auth_headers(other["api_key"])
        assert client.delete(f"{BASE}/evidence/{fid}", headers=h).status_code == 404
        assert client.patch(f"{BASE}/evidence/{fid}", json={"row_unit": "x"}, headers=h).status_code == 404


class TestIsSampleReachesThePrompt:
    def test_is_sample_carried_through_to_rendered_evidence(self, tenant):
        _upload(tenant, "tickets.csv", TICKETS_CSV, is_sample="true",
                sample_description="Q1 only, EMEA region", row_unit="ticket",
                column_roles={"category": "Category"})
        db = TestingSessionLocal()
        try:
            t = db.get(Tenant, tenant["id"])
            context = voc_service.assemble_context(db, t)
            assert context.evidence[0].is_sample is True
            text, notes, _ = voc_service.render_evidence(db, t, context)
        finally:
            db.close()
        assert "COMPLETENESS: SAMPLE — Q1 only, EMEA region" in text
        assert "in the sample supplied" in text
        assert "Integration: 2" in text
        assert notes and "tickets.csv" in notes[0]


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------


class TestContext:
    def test_sections_round_trip(self, tenant):
        h = tenant["headers"]
        segs = [{"segment_key": "OPERATOR", "segment_name": "End operators", "approximate_count": None}]
        assert client.put(f"{BASE}/context/segments", json=segs, headers=h).status_code == 200
        got = client.get(f"{BASE}/context/segments", headers=h).json()
        assert got[0]["approximate_count"] is None  # unknown, never zero

        for path, payload in [
            ("channels", [{"channel": "Field service", "direction": "inbound"}]),
            ("customers", [{"customer_name": "Northwind", "segment_key": "OPERATOR"}]),
            ("known-pain-points", [{"pain_point": "Lead times are the longest"}]),
        ]:
            assert client.put(f"{BASE}/context/{path}", json=payload, headers=h).status_code == 200
            assert len(client.get(f"{BASE}/context/{path}", headers=h).json()) == 1

    def test_config_defaults_to_segment_only(self, tenant):
        h = tenant["headers"]
        assert client.get(f"{BASE}/context/config", headers=h).json() == {"attribution_policy": "segment_only"}
        client.put(f"{BASE}/context/config", json={"attribution_policy": "named"}, headers=h)
        assert client.get(f"{BASE}/context/config", headers=h).json()["attribution_policy"] == "named"
        assert client.put(f"{BASE}/context/config", json={"attribution_policy": "everyone"},
                          headers=h).status_code == 422

    def test_categories_read_through_tech_regulation_plus_additions(self, tenant):
        h = tenant["headers"]
        client.put("/agents/tech-regulation/scope/categories",
                   json=[{"category_key": "EMA-FIN", "category_name": "Missile fin actuation"}], headers=h)
        resp = client.put(
            f"{BASE}/context/categories",
            json=[{"category_key": "SVC-TOOL", "category_name": "Service tooling"},
                  {"category_key": "EMA-FIN", "category_name": "Duplicate, ignored"}],
            headers=h,
        )
        assert resp.status_code == 200
        cats = {c["category_key"]: c for c in client.get(f"{BASE}/context/categories", headers=h).json()}
        assert cats["EMA-FIN"]["source"] == "tech-regulation"
        assert cats["EMA-FIN"]["category_name"] == "Missile fin actuation"
        assert cats["SVC-TOOL"]["source"] == "voice-of-customer"

    def test_state_consequence_empty_for_set_items(self, tenant):
        h = tenant["headers"]
        client.put(f"{BASE}/context/segments", json=[{"segment_key": "MRO", "segment_name": "MRO"}], headers=h)
        state = client.get(f"{BASE}/context/state", headers=h).json()
        assert state["operating_tier"] == "tier_2"
        assert state["run_label"] == "External Customer-Context Analysis"
        items = {i["key"]: i for i in state["items"]}
        assert items["segments"]["status"] == "set" and items["segments"]["consequence"] == ""
        assert items["evidence"]["status"] == "missing"
        assert "most consequential" in items["evidence"]["consequence"]
        for i in state["items"]:
            assert (i["consequence"] == "") == (i["status"] == "set")

    def test_state_moves_to_tier_1_with_evidence(self, tenant):
        _upload(tenant, "tickets.csv", TICKETS_CSV)
        state = client.get(f"{BASE}/context/state", headers=tenant["headers"]).json()
        assert state["operating_tier"] == "tier_1_partial"
        freq = next(a for a in state["analyses"] if a["key"] == "pain_point_frequency")
        assert freq["available"] and freq["enabled_by"] == ["tickets.csv"]


# ---------------------------------------------------------------------------
# Runs, reports, export
# ---------------------------------------------------------------------------


def _fake_result(tier="tier_2") -> AgentRunResult:
    title = "External customer-context analysis — Executive summary" if tier == "tier_2" else "Executive summary"
    return AgentRunResult(
        operating_tier=tier,
        operating_tier_line="**Operating tier: ...**",
        generated_at="2026-10-05T00:00:00Z",
        model="claude-opus-5",
        web_search_queries=[],
        research_sources=[],
        research_brief="brief",
        attribution_policy="segment_only",
        names_checked=1,
        attribution_replacements={1: 0},
        reports=[
            Report(1, title, "## Governing Insight\nx\n\n## Findings for synthesis\nA finding.", ""),
            Report(2, "Ranked customer pain points", "## Key Insights\n- y", ""),
        ],
    )


def _run(tenant, tier="tier_2"):
    with patch.object(voc_service.VoiceOfCustomerAgent, "run", return_value=_fake_result(tier)):
        resp = client.post(f"{BASE}/runs", headers=tenant["headers"])
    assert resp.status_code == 202, resp.text
    return resp.json()


class TestRuns:
    def test_run_is_never_blocked_and_degrades_to_tier_2(self, tenant):
        run = _run(tenant)
        assert run["subject"].startswith("External Customer-Context Analysis")
        got = client.get(f"{BASE}/runs/{run['id']}", headers=tenant["headers"]).json()
        assert got["status"] == "succeeded"
        assert got["operating_tier"] == "tier_2"
        reports = client.get(f"{BASE}/runs/{run['id']}/reports", headers=tenant["headers"]).json()
        assert reports[0]["title"].startswith("External customer-context analysis")

    def test_post_run_alias(self, tenant):
        with patch.object(voc_service.VoiceOfCustomerAgent, "run", return_value=_fake_result()):
            assert client.post(f"{BASE}/run", headers=tenant["headers"]).status_code == 202

    def test_failure_lands_on_the_run(self, tenant):
        with patch.object(voc_service.VoiceOfCustomerAgent, "run", side_effect=RuntimeError("boom")):
            run = client.post(f"{BASE}/runs", headers=tenant["headers"]).json()
        got = client.get(f"{BASE}/runs/{run['id']}", headers=tenant["headers"]).json()
        assert got["status"] == "failed" and "boom" in got["error"]

    def test_runs_are_tenant_scoped(self, tenant):
        run = _run(tenant)
        other = auth_headers(create_tenant("Other")["api_key"])
        assert client.get(f"{BASE}/runs/{run['id']}", headers=other).status_code == 404
        assert client.get(f"{BASE}/runs/{run['id']}/reports", headers=other).status_code == 404
        assert client.get(f"{BASE}/runs/{run['id']}/export.docx", headers=other).status_code == 404
        assert client.get(f"{BASE}/runs", headers=other).json() == []

    def test_another_agents_run_is_404_here(self, tenant):
        # Inserted directly rather than via POST /agents/tech-regulation/runs:
        # that would run Agent 3's background task through ITS SessionFactory,
        # which this module does not pin (the trap logged in conftest.py).
        db = TestingSessionLocal()
        try:
            other = AgentRun(tenant_id=tenant["id"], agent_type="tech-regulation", subject="x", status="succeeded")
            db.add(other)
            db.commit()
            other_id = other.id
        finally:
            db.close()
        assert client.get(f"{BASE}/runs/{other_id}", headers=tenant["headers"]).status_code == 404


def _cover_text(docx_bytes: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(docx_bytes)) as z:
        return z.read("word/document.xml").decode("utf-8")


class TestExport:
    def test_tier_2_cover_label(self, tenant):
        run = _run(tenant, "tier_2")
        resp = client.get(f"{BASE}/runs/{run['id']}/export.docx", headers=tenant["headers"])
        assert resp.status_code == 200
        assert "External_Customer_Context" in resp.headers["content-disposition"]
        xml = _cover_text(resp.content)
        assert "External Customer-Context Analysis" in xml

    def test_tier_1_cover_label(self, tenant):
        _upload(tenant, "tickets.csv", TICKETS_CSV)
        run = _run(tenant, "tier_1_partial")
        resp = client.get(f"{BASE}/runs/{run['id']}/export.docx", headers=tenant["headers"])
        assert resp.status_code == 200
        assert "Voice_of_Customer" in resp.headers["content-disposition"]
        xml = _cover_text(resp.content)
        assert "Voice of Customer" in xml
        assert "External Customer-Context Analysis" not in xml
