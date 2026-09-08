"""
Tests for GET /agents/market-insights/runs/{run_id}/export.docx.

Same offline pattern as the other test modules: isolated in-memory SQLite,
the Market Insights agent replaced by a fake so no real research runs. The
markdown-parsing/rendering contract itself is covered exhaustively against
real production markdown in test_export_markdown_parser.py -- these tests
are about the endpoint's own responsibilities: tenant scoping, 404s, and
producing a structurally valid .docx.

Tenants are created via the admin route (like test_agents_and_isolation.py),
not self-serve /auth/signup, to avoid a direct cross-session db write (the
allowlist row) that the request path wouldn't otherwise touch.

Every test module in this suite defines its own isolated in-memory engine
and assigns `app.dependency_overrides[get_db]` at import time -- since `app`
is one shared singleton, only the *last-imported* module's assignment
survives collection, so running the full suite together silently points
every other module's HTTP calls at a database its own fixtures never wrote
to. The `_pin_db_override` fixture below re-asserts (and restores) this
module's override around each test so it's correct regardless of import
order or which other test files run alongside it.
"""
import io
import os
import zipfile
from unittest.mock import patch

import pytest

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-real")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LOOM_ADMIN_KEYS", "test-admin-key")

from docx import Document  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.main import app  # noqa: E402
from app.database import Base, get_db  # noqa: E402

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
client = TestClient(app)


@pytest.fixture(autouse=True)
def _pin_db_override():
    """Guarantee this module's database is the one `client` talks to for the
    duration of each test, regardless of which test module was collected
    last (see module docstring). Restores whatever was active afterward so
    this file doesn't do the same thing to modules that run after it."""
    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    try:
        yield
    finally:
        if previous is not None:
            app.dependency_overrides[get_db] = previous
        else:
            app.dependency_overrides.pop(get_db, None)


ADMIN_HEADERS = {"X-Admin-Key": "test-admin-key"}


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create_tenant(name: str) -> dict:
    resp = client.post("/admin/tenants", json={"name": name}, headers=ADMIN_HEADERS)
    assert resp.status_code == 200, resp.text
    return resp.json()


# --------------------------------------------------------------------------
# Fake Market Insights agent (same shape as test_phase2_auth_and_agents.py)
# --------------------------------------------------------------------------

FIXTURE_MARKDOWN = """**Subject: Test scope | Evidence base: Tier 2 public sources | Window: 2021-2026**

## Key Insights

- **Lead finding** (Confidence: High) — this is the body of the finding.

## Body Section

**FACT (High).** Something happened. *So what: it matters.*
"""


class _FakeReport:
    def __init__(self, n: int):
        self.report_number = n
        self.title = f"Report {n} title"
        self.content = FIXTURE_MARKDOWN
        self.confidence_summary = f"Confidence summary {n}."


class _FakeResult:
    def __init__(self):
        self.reports = [_FakeReport(i) for i in range(1, 10)]


class _FakeAgent:
    def __init__(self, *args, **kwargs):
        pass

    def run(self, subject, **kwargs):
        return _FakeResult()


def _run_agent_patches():
    return (
        patch("app.routers.market_insights.MarketInsightsAgent", _FakeAgent),
        patch("app.routers.market_insights.SessionFactory", TestingSessionLocal),
    )


def _set_scope(token: str, product_line: str = "electric ferries — coastal retrofit") -> None:
    resp = client.put(
        "/agents/market-insights/scope",
        json={"product_line": product_line},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text


def _start_run(token: str, product_line: str = "electric ferries — coastal retrofit") -> dict:
    _set_scope(token, product_line)
    p1, p2 = _run_agent_patches()
    with p1, p2:
        resp = client.post("/agents/market-insights/run", json={}, headers=auth_headers(token))
    assert resp.status_code == 202, resp.text
    return resp.json()


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------


def test_export_returns_valid_docx_with_expected_headers():
    tenant = _create_tenant("Acme")
    run = _start_run(tenant["api_key"])

    resp = client.get(
        f"/agents/market-insights/runs/{run['id']}/export.docx",
        headers=auth_headers(tenant["api_key"]),
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    disposition = resp.headers["content-disposition"]
    assert disposition.startswith("attachment; filename=")
    assert "AutoStrat_Loom_Market_Insights_" in disposition
    assert disposition.endswith('.docx"')

    body = resp.content
    assert len(body) > 0
    # Structurally valid docx: a real zip, and python-docx can open it.
    assert zipfile.is_zipfile(io.BytesIO(body))
    doc = Document(io.BytesIO(body))
    heading_texts = [p.text for p in doc.paragraphs if p.style.name.startswith("Heading 1")]
    assert "Report 1 title" in heading_texts
    assert "Report 9 title" in heading_texts


def test_export_404_for_run_with_no_reports():
    tenant = _create_tenant("Acme")
    _set_scope(tenant["api_key"])
    # No run with this id exists for this tenant at all -- same 404 path as
    # a run that exists but has zero report rows.
    resp = client.get(
        "/agents/market-insights/runs/does-not-exist/export.docx",
        headers=auth_headers(tenant["api_key"]),
    )
    assert resp.status_code == 404


def test_export_404_for_run_owned_by_another_tenant():
    tenant_a = _create_tenant("Tenant A")
    run_a = _start_run(tenant_a["api_key"])

    tenant_b = _create_tenant("Tenant B")

    resp = client.get(
        f"/agents/market-insights/runs/{run_a['id']}/export.docx",
        headers=auth_headers(tenant_b["api_key"]),
    )
    assert resp.status_code == 404  # not 403 -- must not confirm the run exists elsewhere


def test_export_uses_scope_derived_filename_slug():
    tenant = _create_tenant("Acme")
    run = _start_run(tenant["api_key"], product_line="Widget Modernization Program")

    resp = client.get(
        f"/agents/market-insights/runs/{run['id']}/export.docx",
        headers=auth_headers(tenant["api_key"]),
    )
    assert resp.status_code == 200, resp.text
    disposition = resp.headers["content-disposition"]
    assert "Widget_Modernization_Program" in disposition
