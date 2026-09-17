"""
Endpoint tests for the Strategy Synthesis (Agent 5) CSV ingest routes,
against a real (in-memory SQLite) database via TestClient. Isolated per
conftest.py's convention: this module defines its own `override_get_db`.
"""
import io
import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-real")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LOOM_ADMIN_KEYS", "test-admin-key")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db

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

ADMIN_HEADERS = {"X-Admin-Key": "test-admin-key"}


def create_tenant(name: str) -> dict:
    resp = client.post("/admin/tenants", json={"name": name}, headers=ADMIN_HEADERS)
    assert resp.status_code == 200, resp.text
    return resp.json()


def auth_headers(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


def put_buckets(api_key: str, buckets: list[dict]) -> dict:
    resp = client.put(
        "/agents/strategy/buckets",
        json={"buckets": buckets},
        headers=auth_headers(api_key),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def upload(api_key: str, file_type: str, filename: str, content: str, **form):
    return client.post(
        f"/agents/strategy/files/{file_type}",
        files={"file": (filename, io.BytesIO(content.encode("utf-8")), "text/csv")},
        data=form,
        headers=auth_headers(api_key),
    )


DEFAULT_BUCKETS = [
    {"bucket_key": "HW", "bucket_name": "Hardware", "contractable": "yes"},
    {"bucket_key": "SW", "bucket_name": "Software", "contractable": "yes"},
    {"bucket_key": "SYS", "bucket_name": "Systems", "contractable": "partial"},
    {"bucket_key": "CERT", "bucket_name": "Certification", "contractable": "no"},
]

VALID_ROADMAP = (
    "project_id,project,type,status,pct_complete,"
    "effort_remaining_HW,effort_remaining_CERT,target_gate,target_fy,owner,mandatory,mandatory_driver,mandatory_deadline\n"
    "P-01,CVR-25 TSO,Compliance,In flight,72,6,40,Q2 FY27,FY27,Jane,true,TSO,Q2 FY27\n"
)

MISMATCHED_ROADMAP = (
    "project_id,project,type,status,pct_complete,"
    "effort_remaining_cert,target_gate,target_fy,owner,mandatory,mandatory_driver,mandatory_deadline\n"
    "P-01,CVR-25 TSO,Compliance,In flight,72,40,Q2 FY27,FY27,Jane,true,TSO,Q2 FY27\n"
)


# ---------------------------------------------------------------------------
# Buckets
# ---------------------------------------------------------------------------


def test_put_buckets_rejects_fewer_than_two():
    tenant = create_tenant("OneBucket Co")
    resp = client.put(
        "/agents/strategy/buckets",
        json={"buckets": [{"bucket_key": "HW", "bucket_name": "Hardware"}]},
        headers=auth_headers(tenant["api_key"]),
    )
    assert resp.status_code == 400


def test_put_buckets_rejects_unsafe_column_header():
    tenant = create_tenant("UnsafeBucket Co")
    resp = client.put(
        "/agents/strategy/buckets",
        json={"buckets": [
            {"bucket_key": "HW space", "bucket_name": "Hardware"},
            {"bucket_key": "SW", "bucket_name": "Software"},
        ]},
        headers=auth_headers(tenant["api_key"]),
    )
    assert resp.status_code == 400


def test_put_and_get_buckets_round_trip():
    tenant = create_tenant("Buckets Co")
    put_buckets(tenant["api_key"], DEFAULT_BUCKETS)
    resp = client.get("/agents/strategy/buckets", headers=auth_headers(tenant["api_key"]))
    assert resp.status_code == 200
    keys = {b["bucket_key"] for b in resp.json()}
    assert keys == {"HW", "SW", "SYS", "CERT"}


# ---------------------------------------------------------------------------
# The requirement: bucket mismatch blocks the file, names both sides
# ---------------------------------------------------------------------------


def test_bucket_mismatch_upload_is_rejected_and_names_both_sides():
    tenant = create_tenant("Mismatch Co")
    put_buckets(tenant["api_key"], DEFAULT_BUCKETS)

    resp = upload(tenant["api_key"], "roadmap", "roadmap.csv", MISMATCHED_ROADMAP)
    assert resp.status_code == 200
    body = resp.json()
    assert body["stored"] is False
    assert body["validation_status"] == "invalid"
    assert len(body["errors"]) == 1
    message = body["errors"][0]["message"]
    assert "effort_remaining_cert" in message
    assert "CERT" in message and "HW" in message


def test_rejected_upload_leaves_prior_valid_data_untouched():
    tenant = create_tenant("Untouched Co")
    put_buckets(tenant["api_key"], DEFAULT_BUCKETS)

    ok = upload(tenant["api_key"], "roadmap", "roadmap.csv", VALID_ROADMAP)
    assert ok.json()["stored"] is True

    bad = upload(tenant["api_key"], "roadmap", "roadmap.csv", MISMATCHED_ROADMAP)
    assert bad.json()["stored"] is False

    files = client.get("/agents/strategy/files", headers=auth_headers(tenant["api_key"])).json()
    roadmap_file = next(f for f in files if f["file_type"] == "roadmap")
    # the LATEST attempt is the rejected one...
    assert roadmap_file["validation_status"] == "invalid"
    # ...but the underlying stored data is still the first, valid upload:
    # confirmed indirectly via a dependencies upload that only succeeds if
    # P-01 (from the valid roadmap) is still known.
    dep = upload(
        tenant["api_key"], "dependencies", "deps.csv",
        "project_id,depends_on_project_id,dependency_type,note\nP-01,P-01,prerequisite,self-check\n",
    )
    # P-01 must still resolve, meaning PortfolioProject rows from the first
    # upload were never deleted by the second, rejected attempt.
    assert dep.json()["stored"] is True, dep.json()


def test_successful_reupload_replaces_prior_rows():
    tenant = create_tenant("Replace Co")
    put_buckets(tenant["api_key"], DEFAULT_BUCKETS)

    first = (
        "project_id,project,type,status,pct_complete,effort_remaining_HW,"
        "target_gate,target_fy,owner,mandatory,mandatory_driver,mandatory_deadline\n"
        "P-01,First,Compliance,In flight,10,5,Q1,FY27,Jane,false,,\n"
    )
    second = (
        "project_id,project,type,status,pct_complete,effort_remaining_HW,"
        "target_gate,target_fy,owner,mandatory,mandatory_driver,mandatory_deadline\n"
        "P-02,Second,Compliance,In flight,10,5,Q1,FY27,Jane,false,,\n"
    )
    r1 = upload(tenant["api_key"], "roadmap", "r1.csv", first)
    assert r1.json()["stored"] is True
    r2 = upload(tenant["api_key"], "roadmap", "r2.csv", second)
    assert r2.json()["stored"] is True

    # P-01 from the first upload must be gone now -- a dependency referencing
    # it should fail to resolve.
    dep = upload(
        tenant["api_key"], "dependencies", "deps.csv",
        "project_id,depends_on_project_id,dependency_type,note\nP-02,P-01,prerequisite,\n",
    )
    assert dep.json()["stored"] is False
    assert any("P-01" in e["message"] for e in dep.json()["errors"])


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


def test_template_reflects_current_declared_buckets():
    tenant = create_tenant("Template Co")
    put_buckets(tenant["api_key"], [
        {"bucket_key": "ALPHA", "bucket_name": "Alpha"},
        {"bucket_key": "BETA", "bucket_name": "Beta"},
    ])
    resp = client.get("/agents/strategy/templates/roadmap", headers=auth_headers(tenant["api_key"]))
    assert resp.status_code == 200
    assert "effort_remaining_ALPHA" in resp.text
    assert "effort_remaining_BETA" in resp.text
    assert "effort_remaining_HW" not in resp.text  # not this tenant's bucket


def test_unknown_file_type_404s():
    tenant = create_tenant("Unknown Type Co")
    resp = client.get("/agents/strategy/templates/not_a_type", headers=auth_headers(tenant["api_key"]))
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Cross-tenant isolation
# ---------------------------------------------------------------------------


def test_buckets_are_tenant_scoped():
    tenant_a = create_tenant("Iso A Co")
    tenant_b = create_tenant("Iso B Co")
    put_buckets(tenant_a["api_key"], DEFAULT_BUCKETS)

    resp_b = client.get("/agents/strategy/buckets", headers=auth_headers(tenant_b["api_key"]))
    assert resp_b.json() == []


def test_files_list_is_tenant_scoped():
    tenant_a = create_tenant("Iso Files A Co")
    tenant_b = create_tenant("Iso Files B Co")
    put_buckets(tenant_a["api_key"], DEFAULT_BUCKETS)
    upload(tenant_a["api_key"], "roadmap", "r.csv", VALID_ROADMAP)

    files_b = client.get("/agents/strategy/files", headers=auth_headers(tenant_b["api_key"])).json()
    assert files_b == []
