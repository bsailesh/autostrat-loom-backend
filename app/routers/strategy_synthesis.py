"""
Strategy Synthesis agent (Agent 5) endpoints -- Part 2 of
agent5_build_briefing.md: CSV ingest and validation, plus the minimum
`buckets` config endpoint that ingest and templates both depend on.

Mirrors app/routers/market_insights.py's conventions: tenant scoping via
get_current_tenant + get_db, 404-not-403 via get_or_404/scoped_query
(app/tenant_scope.py).

Everything else in agent5_build_briefing.md Part 5 -- /config, /objectives,
/framework, /scenarios, /readiness, /runs, /reports, /export.docx,
/candidates -- is out of scope for this round.
"""
import dataclasses
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.auth import get_current_tenant
from app.database import get_db
from app.models import (
    BriefFile,
    CapacityBucket,
    CapacityRow,
    PortfolioProject,
    ProductFleetRow,
    ProjectDependency,
    ProjectEffortRow,
    ProjectFinancialsRow,
    Tenant,
)
from app.schemas import (
    BriefFileOut,
    CapacityBucketOut,
    CapacityBucketsUpsertRequest,
    IngestIssueOut,
    IngestResultOut,
)
from app.tenant_scope import get_or_404, scoped_query  # noqa: F401 -- get_or_404 not used yet, kept for parity

from strategy_synthesis import ingest

router = APIRouter(prefix="/agents/strategy", tags=["strategy-synthesis"])

STALENESS_DAYS = 180

FILE_TYPES = {"products_fleet", "capacity", "roadmap", "dependencies", "financials"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _declared_bucket_keys(db: Session, tenant: Tenant) -> set[str]:
    return {b.bucket_key for b in scoped_query(db, CapacityBucket, tenant).all()}


def _known_project_keys(db: Session, tenant: Tenant) -> set[str]:
    return {p.project_key for p in scoped_query(db, PortfolioProject, tenant).all()}


def _issue_dict(issue: ingest.IngestIssue) -> dict:
    return dataclasses.asdict(issue)


def _issues_out(dicts: list[dict]) -> list[IngestIssueOut]:
    return [IngestIssueOut(**d) for d in dicts]


def _as_of_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _fiscal_year_coverage_warnings(db: Session, tenant: Tenant) -> list[ingest.IngestIssue]:
    """Cross-file check: every roadmap target_fy should be covered by a
    declared capacity fiscal year. Only fires once capacity exists at all --
    capacity's own absence already has a stated consequence elsewhere (no
    funding line), so this isn't double-counted here."""
    capacity_years = {r.fiscal_year for r in scoped_query(db, CapacityRow, tenant).all()}
    if not capacity_years:
        return []
    target_fys = {p.target_fy for p in scoped_query(db, PortfolioProject, tenant).all() if p.target_fy}
    missing = sorted(target_fys - capacity_years)
    if not missing:
        return []
    return [
        ingest.IngestIssue(
            severity="warning",
            row=None,
            field="target_fy",
            message=(
                f"Roadmap target_fy {', '.join(missing)} not covered by declared capacity "
                f"fiscal years ({', '.join(sorted(capacity_years))})."
            ),
        )
    ]


# ---------------------------------------------------------------------------
# Buckets (prerequisite for ingest validation and templates)
# ---------------------------------------------------------------------------


@router.get("/buckets", response_model=list[CapacityBucketOut])
def get_buckets(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    return scoped_query(db, CapacityBucket, tenant).order_by(CapacityBucket.created_at.asc()).all()


@router.put("/buckets", response_model=list[CapacityBucketOut])
def put_buckets(
    payload: CapacityBucketsUpsertRequest,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    """Replace the tenant's declared buckets wholesale, 2-8 entries.
    Changing buckets after files are uploaded invalidates those files'
    bucket-dependent columns -- the frontend's job to warn about, per the
    briefing; this endpoint just performs the replace."""
    if not (2 <= len(payload.buckets) <= 8):
        raise HTTPException(status_code=400, detail="Between 2 and 8 buckets must be declared.")

    keys = [b.bucket_key.strip() for b in payload.buckets]
    if len(keys) != len(set(keys)):
        raise HTTPException(status_code=400, detail="bucket_key values must be unique.")

    for key in keys:
        safe = key and key[0].isalpha() and key.replace("_", "").isalnum() and len(key) <= 40
        if not safe:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"bucket_key '{key}' is not safe as a CSV column header -- use letters, "
                    "digits, and underscore only, starting with a letter, 40 characters or fewer."
                ),
            )

    scoped_query(db, CapacityBucket, tenant).delete()
    rows = []
    for b in payload.buckets:
        row = CapacityBucket(
            tenant_id=tenant.id,
            bucket_key=b.bucket_key.strip(),
            bucket_name=b.bucket_name.strip(),
            contractable=b.contractable,
            note=b.note,
        )
        db.add(row)
        rows.append(row)
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


@router.get("/templates/{file_type}")
def get_template(
    file_type: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    if file_type not in FILE_TYPES:
        raise HTTPException(status_code=404, detail=f"Unknown file_type: {file_type!r}")

    bucket_keys = [
        b.bucket_key
        for b in scoped_query(db, CapacityBucket, tenant).order_by(CapacityBucket.created_at.asc()).all()
    ]
    csv_text = ingest.generate_template(file_type, bucket_keys)
    return PlainTextResponse(
        csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{file_type}_template.csv"'},
    )


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


@router.post("/files/{file_type}", response_model=IngestResultOut)
async def upload_file(
    file_type: str,
    file: UploadFile = File(...),
    as_of: str | None = Form(default=None, description="ISO date/datetime this data is current as of"),
    uploaded_by: str = Form(default=""),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    """Parse, validate, and store one CSV. Any Error blocks this file's
    ingest entirely -- nothing is written, whatever was previously stored
    stays exactly as it was. Warnings never block. Never blocks a run."""
    if file_type not in FILE_TYPES:
        raise HTTPException(status_code=404, detail=f"Unknown file_type: {file_type!r}")

    raw_bytes = await file.read()
    text = raw_bytes.decode("utf-8-sig")  # -sig tolerates a BOM from Excel exports

    as_of_dt: datetime | None = None
    if as_of:
        try:
            as_of_dt = datetime.fromisoformat(as_of)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"as_of must be an ISO date/datetime, got {as_of!r}")

    if file_type == "products_fleet":
        parsed, issues = ingest.parse_products_fleet_csv(text)
    elif file_type == "capacity":
        parsed, issues = ingest.parse_capacity_csv(text, _declared_bucket_keys(db, tenant))
    elif file_type == "roadmap":
        parsed, issues = ingest.parse_roadmap_csv(text, _declared_bucket_keys(db, tenant))
    elif file_type == "dependencies":
        parsed, issues = ingest.parse_dependencies_csv(text, _known_project_keys(db, tenant))
    else:  # financials
        parsed, issues = ingest.parse_financials_csv(text, _known_project_keys(db, tenant))

    has_errors = any(i.severity == "error" for i in issues)
    row_count = len(parsed)

    if not has_errors:
        if file_type == "products_fleet":
            scoped_query(db, ProductFleetRow, tenant).delete()
            for r in parsed:
                db.add(
                    ProductFleetRow(
                        tenant_id=tenant.id, product_key=r.product_key, product=r.product,
                        platform=r.platform, platform_class=r.platform_class,
                        units_in_service=r.units_in_service, avg_age_years=r.avg_age_years,
                        status=r.status, region=r.region,
                    )
                )
        elif file_type == "capacity":
            scoped_query(db, CapacityRow, tenant).delete()
            for r in parsed:
                db.add(
                    CapacityRow(
                        tenant_id=tenant.id, fiscal_year=r.fiscal_year, bucket_key=r.bucket_key,
                        fte=r.fte, capacity_units=r.capacity_units, budget=r.budget,
                    )
                )
            issues = issues + _fiscal_year_coverage_warnings(db, tenant)
        elif file_type == "roadmap":
            scoped_query(db, PortfolioProject, tenant).delete()
            scoped_query(db, ProjectEffortRow, tenant).delete()
            for r in parsed:
                db.add(
                    PortfolioProject(
                        tenant_id=tenant.id, project_key=r.project_key, name=r.name,
                        project_type=r.project_type, status=r.status, pct_complete=r.pct_complete,
                        target_gate=r.target_gate, target_fy=r.target_fy, owner=r.owner,
                        mandatory=r.mandatory, mandatory_driver=r.mandatory_driver,
                        mandatory_deadline=r.mandatory_deadline,
                    )
                )
                for bucket_key, effort_remaining in r.effort_remaining.items():
                    db.add(
                        ProjectEffortRow(
                            tenant_id=tenant.id, project_key=r.project_key, bucket_key=bucket_key,
                            effort_remaining=effort_remaining, effort_total=r.effort_total.get(bucket_key),
                        )
                    )
            issues = issues + _fiscal_year_coverage_warnings(db, tenant)
        elif file_type == "dependencies":
            scoped_query(db, ProjectDependency, tenant).delete()
            for r in parsed:
                db.add(
                    ProjectDependency(
                        tenant_id=tenant.id, project_key=r.project_key, depends_on_key=r.depends_on_key,
                        dependency_type=r.dependency_type, note=r.note, source="customer",
                    )
                )
        else:  # financials
            scoped_query(db, ProjectFinancialsRow, tenant).delete()
            for r in parsed:
                db.add(
                    ProjectFinancialsRow(
                        tenant_id=tenant.id, project_key=r.project_key, revenue_impact=r.revenue_impact,
                        capex=r.capex, opex_annual=r.opex_annual, discount_rate=r.discount_rate,
                        currency=r.currency, basis=r.basis,
                    )
                )

    if has_errors:
        validation_status = "invalid"
    elif issues:
        validation_status = "valid_with_warnings"
    else:
        validation_status = "valid"

    # BriefFile is an append-only upload history, never delete-and-replaced --
    # GET /files surfaces only the latest per file_type, but every attempt
    # (including rejected ones) stays visible for audit.
    db.add(
        BriefFile(
            tenant_id=tenant.id,
            file_type=file_type,
            filename=file.filename or file_type,
            as_of=as_of_dt,
            uploaded_by=uploaded_by,
            row_count=row_count,
            validation_status=validation_status,
            issues=[_issue_dict(i) for i in issues],
        )
    )
    db.commit()

    return IngestResultOut(
        file_type=file_type,
        row_count=row_count,
        stored=not has_errors,
        validation_status=validation_status,
        errors=_issues_out([_issue_dict(i) for i in issues if i.severity == "error"]),
        warnings=_issues_out([_issue_dict(i) for i in issues if i.severity == "warning"]),
    )


@router.get("/files", response_model=list[BriefFileOut])
def list_files(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    """Latest upload attempt per file_type. Older attempts stay in the table
    (append-only) but aren't surfaced here."""
    rows = scoped_query(db, BriefFile, tenant).order_by(BriefFile.created_at.desc()).all()
    latest_by_type: dict[str, BriefFile] = {}
    for row in rows:
        latest_by_type.setdefault(row.file_type, row)

    now = datetime.now(timezone.utc)
    out = []
    for row in latest_by_type.values():
        is_stale = row.as_of is not None and (now - _as_of_utc(row.as_of)) > timedelta(days=STALENESS_DAYS)
        out.append(
            BriefFileOut(
                id=row.id,
                file_type=row.file_type,
                filename=row.filename,
                as_of=row.as_of,
                uploaded_by=row.uploaded_by,
                row_count=row.row_count,
                validation_status=row.validation_status,
                issues=_issues_out(row.issues),
                is_stale=is_stale,
                created_at=row.created_at,
            )
        )
    return out
