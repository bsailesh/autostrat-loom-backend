"""
Strategy Synthesis agent (Agent 5) endpoints -- Parts 2 and 5 of
agent5_build_briefing.md: CSV ingest/validation/templates (Part 2) plus
runs, the remaining brief config endpoints, readiness, and candidates
(Part 5).

Mirrors app/routers/market_insights.py's conventions: tenant scoping via
get_current_tenant + get_db, 404-not-403 via get_or_404/scoped_query
(app/tenant_scope.py). Run assembly/execution lives in
app/strategy_synthesis_service.py, not here -- Agent 5 touches 17
decision-inputs tables versus Market Insights' one AgentScope, so keeping
that logic out of the router keeps this file readable.
"""
import csv
import dataclasses
import io
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.auth import get_current_tenant
from app.database import get_db
from app.export.docx_builder import ExportBuilder, agent_label_for
from app.models import (
    AgentReport,
    AgentRun,
    BriefFile,
    CapacityBucket,
    CapacityRow,
    DiscoveredCandidate,
    EffortBand,
    PortfolioProject,
    PrioritizationCriterion,
    PrioritizationFramework,
    ProductFleetRow,
    ProjectDependency,
    ProjectEffortRow,
    ProjectFinancialsRow,
    ProposedProject,
    ScenarioRow,
    ScenarioWeight,
    StrategicObjective,
    StrategyConfig,
    StrategyRule,
    Tenant,
)
from app.schemas import (
    AgentReportOut,
    AgentReportSummary,
    AgentRunOut,
    BriefFileOut,
    CandidatePatchRequest,
    CandidateScopeRequest,
    CapacityBucketOut,
    CapacityBucketsUpsertRequest,
    DiscoveredCandidateOut,
    EffortBandOut,
    FrameworkResponse,
    FrameworkUpsertRequest,
    IngestIssueOut,
    IngestResultOut,
    ProposedProjectOut,
    ProposedProjectsUpsertRequest,
    ReadinessItemOut,
    ScenarioOut,
    ScenariosUpsertRequest,
    StrategicObjectiveOut,
    StrategicObjectivesUpsertRequest,
    StrategyConfigResponse,
    StrategyConfigUpsertRequest,
    StrategyRuleOut,
    StrategyRunRequest,
)
from app.strategy_synthesis_service import (
    AGENT_TYPE,
    AmbiguousFiscalYearError,
    compute_readiness,
    default_fiscal_year,
    execute_run,
    load_framework_weights,
)
from app.tenant_scope import get_or_404, scoped_query

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
    # Header row only, independent of ingest.py's row parsing below -- so the
    # decision inputs screen can show "detected columns" even when the file
    # is otherwise empty or rejected outright.
    columns = list(csv.DictReader(io.StringIO(text)).fieldnames or [])

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
            columns=columns,
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
        columns=columns,
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
                columns=row.columns,
                is_stale=is_stale,
                created_at=row.created_at,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------


@router.post("/runs", response_model=AgentRunOut, status_code=202)
def start_run(
    background_tasks: BackgroundTasks,
    payload: StrategyRunRequest = StrategyRunRequest(),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    """Kick off a Strategy Synthesis run. Returns at once; the work happens
    in a background task. Never blocked by an incomplete brief -- see
    GET /readiness for what's missing and its cost."""
    if payload.fiscal_year:
        fiscal_year = payload.fiscal_year
    else:
        config = scoped_query(db, StrategyConfig, tenant).first()
        try:
            fiscal_year = default_fiscal_year(db, tenant, config)
        except AmbiguousFiscalYearError as e:
            raise HTTPException(status_code=400, detail=str(e))

    run = AgentRun(
        tenant_id=tenant.id,
        agent_type=AGENT_TYPE,
        subject=f"Strategy Synthesis — {fiscal_year}",
        status="pending",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    background_tasks.add_task(
        execute_run,
        run_id=run.id,
        fiscal_year=fiscal_year,
        upstream_run_overrides=payload.upstream_run_overrides,
        model=payload.model,
    )
    return run


@router.get("/runs", response_model=list[AgentRunOut])
def list_runs(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    return (
        scoped_query(db, AgentRun, tenant)
        .filter(AgentRun.agent_type == AGENT_TYPE)
        .order_by(AgentRun.created_at.desc())
        .all()
    )


@router.get("/runs/{run_id}", response_model=AgentRunOut)
def get_run(
    run_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    return get_or_404(db, AgentRun, tenant, run_id)


@router.get("/runs/{run_id}/reports", response_model=list[AgentReportSummary])
def list_run_reports(
    run_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    get_or_404(db, AgentRun, tenant, run_id)  # 404s if the run isn't this tenant's
    return (
        scoped_query(db, AgentReport, tenant)
        .filter(AgentReport.run_id == run_id)
        .order_by(AgentReport.report_number.asc())
        .all()
    )


@router.get("/reports/{report_id}", response_model=AgentReportOut)
def get_report(
    report_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    return get_or_404(db, AgentReport, tenant, report_id)


DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

_SLUG_STRIP_RE = re.compile(r"[^A-Za-z0-9]+")


def _filename_slug(run: AgentRun) -> str:
    basis = (run.subject or "").split("—")[0].strip()
    slug = _SLUG_STRIP_RE.sub("_", basis).strip("_")
    slug = slug[:60].strip("_")
    return slug or run.id


@router.get("/runs/{run_id}/export.docx")
def export_run_docx(
    run_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    """The full report pack for a run, rendered to a single .docx on demand
    from the stored markdown -- identical mechanics to Market Insights'
    own export endpoint, since it's the same agent_reports table."""
    run = get_or_404(db, AgentRun, tenant, run_id)  # 404s (not 403) outside this tenant

    report_rows = (
        scoped_query(db, AgentReport, tenant)
        .filter(AgentReport.run_id == run.id)
        .order_by(AgentReport.report_number.asc())
    )
    if report_rows.first() is None:
        raise HTTPException(status_code=404, detail="This run has no reports yet")

    builder = ExportBuilder()
    builder.add_cover_page(
        agent_label=agent_label_for(run.agent_type),
        scope_summary=run.subject or "",
        run_date=run.created_at.date().isoformat(),
    )
    builder.add_toc()

    for row in report_rows.yield_per(1):  # iterate the cursor, never materialize the list
        builder.add_report(row.content, report_number=row.report_number, title=row.title)

    docx_bytes = builder.to_bytes()
    filename = f"AutoStrat_Loom_Strategy_Synthesis_{_filename_slug(run)}_{run.created_at.date().isoformat()}.docx"

    return StreamingResponse(
        io.BytesIO(docx_bytes),
        media_type=DOCX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Config (effort unit, fiscal year convention, project types, effort bands, rules)
# ---------------------------------------------------------------------------


def _config_response(db: Session, tenant: Tenant) -> StrategyConfigResponse:
    config = scoped_query(db, StrategyConfig, tenant).first()
    return StrategyConfigResponse(
        configured=config is not None,
        effort_unit=config.effort_unit if config else "weeks",
        fiscal_year_start_month=config.fiscal_year_start_month if config else 1,
        fiscal_year_label_format=config.fiscal_year_label_format if config else "FY{yy}",
        project_types=config.project_types if config else [],
        effort_bands=scoped_query(db, EffortBand, tenant).all(),
        rules=scoped_query(db, StrategyRule, tenant).all(),
    )


@router.get("/config", response_model=StrategyConfigResponse)
def get_config(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    return _config_response(db, tenant)


@router.put("/config", response_model=StrategyConfigResponse)
def put_config(
    payload: StrategyConfigUpsertRequest,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    config = scoped_query(db, StrategyConfig, tenant).first()
    if config is None:
        config = StrategyConfig(tenant_id=tenant.id)
        db.add(config)
    config.effort_unit = payload.effort_unit
    config.fiscal_year_start_month = payload.fiscal_year_start_month
    config.fiscal_year_label_format = payload.fiscal_year_label_format
    config.project_types = payload.project_types

    scoped_query(db, EffortBand, tenant).delete()
    for b in payload.effort_bands:
        db.add(
            EffortBand(tenant_id=tenant.id, band_name=b.band_name, min_units=b.min_units, max_units=b.max_units)
        )

    scoped_query(db, StrategyRule, tenant).delete()
    for r in payload.rules:
        db.add(StrategyRule(tenant_id=tenant.id, rule_type=r.rule_type, value=r.value, note=r.note))

    db.commit()
    return _config_response(db, tenant)


# ---------------------------------------------------------------------------
# Objectives
# ---------------------------------------------------------------------------


@router.get("/objectives", response_model=list[StrategicObjectiveOut])
def get_objectives(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    return scoped_query(db, StrategicObjective, tenant).order_by(StrategicObjective.created_at.asc()).all()


@router.put("/objectives", response_model=list[StrategicObjectiveOut])
def put_objectives(
    payload: StrategicObjectivesUpsertRequest,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    keys = [o.objective_key.strip() for o in payload.objectives]
    if len(keys) != len(set(keys)):
        raise HTTPException(status_code=400, detail="objective_key values must be unique.")

    scoped_query(db, StrategicObjective, tenant).delete()
    rows = []
    for o in payload.objectives:
        row = StrategicObjective(
            tenant_id=tenant.id, objective_key=o.objective_key.strip(), text=o.text,
            horizon=o.horizon, owner=o.owner, measure=o.measure,
        )
        db.add(row)
        rows.append(row)
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows


# ---------------------------------------------------------------------------
# Proposals
# ---------------------------------------------------------------------------


@router.get("/proposals", response_model=list[ProposedProjectOut])
def get_proposals(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    return scoped_query(db, ProposedProject, tenant).order_by(ProposedProject.created_at.asc()).all()


@router.put("/proposals", response_model=list[ProposedProjectOut])
def put_proposals(
    payload: ProposedProjectsUpsertRequest,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    """Replaces the tenant's proposed projects wholesale -- how a design
    partner's own ideas (no effort estimate, never ranked) enter the
    candidate set, distinct from DiscoveredCandidate's agent-discovered
    ones."""
    keys = [p.project_key.strip() for p in payload.proposals]
    if len(keys) != len(set(keys)):
        raise HTTPException(status_code=400, detail="project_key values must be unique.")

    scoped_query(db, ProposedProject, tenant).delete()
    rows = []
    for p in payload.proposals:
        row = ProposedProject(
            tenant_id=tenant.id, project_key=p.project_key.strip(), name=p.name,
            proposed_by=p.proposed_by, description=p.description, rationale=p.rationale,
        )
        db.add(row)
        rows.append(row)
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows


# ---------------------------------------------------------------------------
# Framework
# ---------------------------------------------------------------------------


def _framework_response(db: Session, tenant: Tenant) -> FrameworkResponse:
    framework_row = (
        scoped_query(db, PrioritizationFramework, tenant)
        .filter(PrioritizationFramework.run_id.is_(None))
        .order_by(PrioritizationFramework.updated_at.desc())
        .first()
    )
    if framework_row is None:
        return FrameworkResponse(configured=False, framework="value_vs_effort", criteria=[])
    criteria = (
        scoped_query(db, PrioritizationCriterion, tenant)
        .filter(PrioritizationCriterion.framework_id == framework_row.id)
        .all()
    )
    return FrameworkResponse(configured=True, framework=framework_row.framework, criteria=criteria)


@router.get("/framework", response_model=FrameworkResponse)
def get_framework(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    return _framework_response(db, tenant)


@router.put("/framework", response_model=FrameworkResponse)
def put_framework(
    payload: FrameworkUpsertRequest,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    """Replaces the tenant's default (run_id IS NULL) framework selection
    and criteria wholesale. Weights must sum to ~1.0 -- the same check
    compute.py itself enforces, surfaced here early rather than only at
    run time."""
    total_weight = sum(c.weight for c in payload.criteria)
    if payload.criteria and abs(total_weight - 1.0) > 0.01:
        raise HTTPException(status_code=400, detail=f"Criterion weights must sum to 1.0, got {total_weight}")

    framework_row = (
        scoped_query(db, PrioritizationFramework, tenant)
        .filter(PrioritizationFramework.run_id.is_(None))
        .first()
    )
    if framework_row is None:
        framework_row = PrioritizationFramework(tenant_id=tenant.id)
        db.add(framework_row)
        db.flush()  # need framework_row.id before inserting criteria below
    framework_row.framework = payload.framework

    scoped_query(db, PrioritizationCriterion, tenant).filter(
        PrioritizationCriterion.framework_id == framework_row.id
    ).delete()
    for c in payload.criteria:
        db.add(
            PrioritizationCriterion(
                tenant_id=tenant.id, framework_id=framework_row.id,
                criterion=c.criterion, weight=c.weight, source_agent=c.source_agent,
            )
        )
    db.commit()
    return _framework_response(db, tenant)


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


def _scenarios_response(db: Session, tenant: Tenant) -> list[ScenarioOut]:
    rows = scoped_query(db, ScenarioRow, tenant).order_by(ScenarioRow.created_at.asc()).all()
    out = []
    for row in rows:
        weights = scoped_query(db, ScenarioWeight, tenant).filter(ScenarioWeight.scenario_id == row.id).all()
        out.append(ScenarioOut(id=row.id, name=row.name, emphasis=row.emphasis, weights=weights))
    return out


@router.get("/scenarios", response_model=list[ScenarioOut])
def get_scenarios(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    return _scenarios_response(db, tenant)


@router.put("/scenarios", response_model=list[ScenarioOut])
def put_scenarios(
    payload: ScenariosUpsertRequest,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    """Replaces the tenant's scenarios wholesale, 2-6 entries (per
    agent5_decision_inputs_brief_spec.md Section 8: "Two to six").

    Each scenario's `weights` are per-criterion overrides on top of the
    framework's declared weights, not a standalone set -- an unmentioned
    criterion keeps its framework weight (an empty list, e.g. a "Base"
    scenario, means "use the framework's weights unchanged"). compute.py
    requires every weight set to sum to 1.0, so that's checked here, against
    the framework as currently declared, rather than failing deep in a run
    later (same reasoning as the sum check in put_framework above)."""
    if not (2 <= len(payload.scenarios) <= 6):
        raise HTTPException(status_code=400, detail="Between 2 and 6 scenarios must be declared.")
    names = [s.name.strip() for s in payload.scenarios]
    if len(names) != len(set(names)):
        raise HTTPException(status_code=400, detail="Scenario names must be unique.")

    _, framework_weights = load_framework_weights(db, tenant)
    for s in payload.scenarios:
        overrides = {w.criterion: w.weight for w in s.weights}
        merged_total = sum({**framework_weights, **overrides}.values())
        if abs(merged_total - 1.0) > 0.01:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Scenario {s.name!r}: weights (framework weights with this scenario's "
                    f"overrides applied) must sum to 1.0, got {merged_total}"
                ),
            )

    existing_ids = [row.id for row in scoped_query(db, ScenarioRow, tenant).all()]
    if existing_ids:
        db.query(ScenarioWeight).filter(
            ScenarioWeight.tenant_id == tenant.id, ScenarioWeight.scenario_id.in_(existing_ids)
        ).delete(synchronize_session=False)
    scoped_query(db, ScenarioRow, tenant).delete()

    for s in payload.scenarios:
        row = ScenarioRow(tenant_id=tenant.id, name=s.name.strip(), emphasis=s.emphasis)
        db.add(row)
        db.flush()  # need row.id before inserting its weights below
        for w in s.weights:
            db.add(ScenarioWeight(tenant_id=tenant.id, scenario_id=row.id, criterion=w.criterion, weight=w.weight))
    db.commit()
    return _scenarios_response(db, tenant)


# ---------------------------------------------------------------------------
# Fiscal years
# ---------------------------------------------------------------------------


@router.get("/fiscal-years", response_model=list[str])
def list_fiscal_years(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    """Distinct fiscal years declared in capacity data, sorted -- the same
    set default_fiscal_year() reads. Lets the frontend offer a fiscal-year
    choice before POST /runs, rather than the caller discovering the
    ambiguity only from that endpoint's 400 (AmbiguousFiscalYearError)."""
    years = {r.fiscal_year for r in scoped_query(db, CapacityRow, tenant).all()}
    return sorted(years)


# ---------------------------------------------------------------------------
# Readiness
# ---------------------------------------------------------------------------


@router.get("/readiness", response_model=list[ReadinessItemOut])
def get_readiness(
    fiscal_year: str | None = None,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    """What's missing and what it costs -- never a bare 'missing' badge.
    Never gates POST /runs; that endpoint runs regardless."""
    return [ReadinessItemOut(**item) for item in compute_readiness(db, tenant, fiscal_year)]


# ---------------------------------------------------------------------------
# Candidates
# ---------------------------------------------------------------------------


_CANDIDATE_STATUSES = {"new", "under_review", "scoped", "dismissed"}


@router.get("/candidates", response_model=list[DiscoveredCandidateOut])
def list_candidates(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    """Live candidate state -- Report 7's own text is frozen at run time, so
    the "what to scope next" UI reads from here, not from parsed report
    prose, to reflect actions taken since that run."""
    return scoped_query(db, DiscoveredCandidate, tenant).order_by(DiscoveredCandidate.created_at.asc()).all()


@router.patch("/candidates/{key}", response_model=DiscoveredCandidateOut)
def patch_candidate(
    key: str,
    payload: CandidatePatchRequest,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    if payload.status not in _CANDIDATE_STATUSES:
        raise HTTPException(status_code=400, detail=f"Unknown status: {payload.status!r}")

    row = (
        scoped_query(db, DiscoveredCandidate, tenant)
        .filter(DiscoveredCandidate.candidate_key == key)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="DiscoveredCandidate not found")

    row.status = payload.status
    row.dismissal_reason = payload.dismissal_reason
    db.commit()
    db.refresh(row)
    return row


@router.post("/candidates/{key}/scope", response_model=DiscoveredCandidateOut)
def scope_candidate(
    key: str,
    payload: CandidateScopeRequest,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    """The bridge from the unscoped candidate population into the ranked
    portfolio: adds one PortfolioProject (+ its per-bucket effort) to the
    roadmap outside the CSV wholesale-replace path, and marks the source
    candidate scoped so it stops appearing as still-unscoped. `mandatory` is
    never set here -- always False, per PortfolioProject's own invariant
    (never inferred, only a customer declaration via roadmap.csv)."""
    candidate = (
        scoped_query(db, DiscoveredCandidate, tenant)
        .filter(DiscoveredCandidate.candidate_key == key)
        .first()
    )
    if candidate is None:
        raise HTTPException(status_code=404, detail="DiscoveredCandidate not found")

    declared_buckets = _declared_bucket_keys(db, tenant)
    unknown_buckets = set(payload.effort_by_bucket) - declared_buckets
    if unknown_buckets:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown bucket_key(s): {sorted(unknown_buckets)}. Declared buckets: {sorted(declared_buckets)}",
        )

    existing = (
        scoped_query(db, PortfolioProject, tenant)
        .filter(PortfolioProject.project_key == candidate.candidate_key)
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=400, detail=f"{candidate.candidate_key!r} is already a roadmap project."
        )

    db.add(
        PortfolioProject(
            tenant_id=tenant.id,
            project_key=candidate.candidate_key,
            name=candidate.name,
            project_type=payload.project_type,
            status="Not started",
            target_fy=payload.target_fy,
            target_gate=payload.target_gate,
            owner=payload.owner,
            mandatory=False,
        )
    )
    for bucket_key, effort_remaining in payload.effort_by_bucket.items():
        db.add(
            ProjectEffortRow(
                tenant_id=tenant.id, project_key=candidate.candidate_key,
                bucket_key=bucket_key, effort_remaining=effort_remaining,
            )
        )
    candidate.status = "scoped"
    db.commit()
    db.refresh(candidate)
    return candidate
