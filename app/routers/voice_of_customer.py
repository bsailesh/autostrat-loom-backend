"""
Voice of Customer (Agent 1) endpoints.

Follows app/routers/tech_regulation.py: the agent itself is
`voice_of_customer/`, wired up here; POST /runs returns at once with a
`pending` AgentRun and a background task writes the nine reports.

Every read is tenant-scoped through app/tenant_scope.py, and a row outside
the caller's tenant 404s rather than 403s.

**A run is never blocked.** Without evidence it degrades to Tier 2 and is
titled an external customer-context analysis.
"""
import csv
import io
import json
import logging
import re

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth import get_current_tenant
from app.database import get_db
from app.export.docx_builder import ExportBuilder, agent_label_for
from app.models import (
    AgentReport,
    AgentRun,
    Tenant,
    VocChannel,
    VocConfig,
    VocCustomer,
    VocEvidenceFile,
    VocKnownPainPoint,
    VocProductCategory,
    VocRunMeta,
    VocSegment,
)
from app.schemas import (
    AgentReportOut,
    AgentReportSummary,
    VocAnalysisOut,
    VocCategoryOut,
    VocChannelIn,
    VocConfigIn,
    VocContextStateItemOut,
    VocContextStateOut,
    VocCustomerIn,
    VocEvidenceFileOut,
    VocEvidencePatchRequest,
    VocKnownPainPointIn,
    VocProductCategoryIn,
    VocRunOut,
    VocSegmentIn,
    VoiceOfCustomerRunRequest,
)
from app.tenant_scope import get_or_404, scoped_query
from app.voice_of_customer_service import (
    AGENT_TYPE,
    assemble_context,
    compose_subject,
    compute_context_state,
    delete_evidence_file,
    execute_run,
    ingest_file,
    merged_categories,
)

from voice_of_customer import ingest
from voice_of_customer.context import (
    COLUMN_ROLES,
    FILE_TYPES,
    TIER_2,
    TIER_LABELS,
    analysis_availability,
    operating_tier_statement,
    run_label,
)

router = APIRouter(prefix="/agents/voice-of-customer", tags=["voice-of-customer"])

logger = logging.getLogger(__name__)

DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_SLUG_STRIP_RE = re.compile(r"[^A-Za-z0-9]+")


# ---------------------------------------------------------------------------
# Context -- each section a GET/PUT list, PUT replacing it wholesale (the
# input spec puts the whole context at fifteen minutes of form work)
# ---------------------------------------------------------------------------


def _replace(db: Session, tenant: Tenant, model, rows: list[dict], order_by) -> list:
    scoped_query(db, model, tenant).delete(synchronize_session=False)
    for row in rows:
        db.add(model(tenant_id=tenant.id, **row))
    db.commit()
    return scoped_query(db, model, tenant).order_by(order_by).all()


def _unique(values: list, what: str) -> None:
    if len(values) != len(set(values)):
        raise HTTPException(status_code=422, detail=f"{what} values must be unique")


@router.get("/context/segments", response_model=list[VocSegmentIn])
def get_segments(tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    return scoped_query(db, VocSegment, tenant).order_by(VocSegment.segment_key.asc()).all()


@router.put("/context/segments", response_model=list[VocSegmentIn])
def put_segments(
    payload: list[VocSegmentIn],
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    _unique([p.segment_key for p in payload], "segment_key")
    return _replace(db, tenant, VocSegment, [p.model_dump() for p in payload], VocSegment.segment_key.asc())


@router.get("/context/channels", response_model=list[VocChannelIn])
def get_channels(tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    return scoped_query(db, VocChannel, tenant).order_by(VocChannel.channel.asc()).all()


@router.put("/context/channels", response_model=list[VocChannelIn])
def put_channels(
    payload: list[VocChannelIn],
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    _unique([p.channel for p in payload], "channel")
    return _replace(db, tenant, VocChannel, [p.model_dump() for p in payload], VocChannel.channel.asc())


@router.get("/context/customers", response_model=list[VocCustomerIn])
def get_customers(tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    return scoped_query(db, VocCustomer, tenant).order_by(VocCustomer.customer_name.asc()).all()


@router.put("/context/customers", response_model=list[VocCustomerIn])
def put_customers(
    payload: list[VocCustomerIn],
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    """Optional and sensitive. These names are also the list the output
    attribution check scans every report for."""
    _unique([p.customer_name for p in payload], "customer_name")
    return _replace(db, tenant, VocCustomer, [p.model_dump() for p in payload], VocCustomer.customer_name.asc())


@router.get("/context/known-pain-points", response_model=list[VocKnownPainPointIn])
def get_known_pain_points(tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    return scoped_query(db, VocKnownPainPoint, tenant).order_by(VocKnownPainPoint.created_at.asc()).all()


@router.put("/context/known-pain-points", response_model=list[VocKnownPainPointIn])
def put_known_pain_points(
    payload: list[VocKnownPainPointIn],
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    """The input to belief testing -- the highest-value analysis this agent
    performs, and unavailable unless the beliefs are recorded before a run."""
    _unique([p.pain_point for p in payload], "pain_point")
    return _replace(
        db, tenant, VocKnownPainPoint, [p.model_dump() for p in payload], VocKnownPainPoint.created_at.asc()
    )


@router.get("/context/config", response_model=VocConfigIn)
def get_config(tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    row = scoped_query(db, VocConfig, tenant).first()
    return row or VocConfigIn()


@router.put("/context/config", response_model=VocConfigIn)
def put_config(
    payload: VocConfigIn,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    row = scoped_query(db, VocConfig, tenant).first()
    if row is None:
        row = VocConfig(tenant_id=tenant.id)
        db.add(row)
    row.attribution_policy = payload.attribution_policy
    db.commit()
    db.refresh(row)
    return row


@router.get("/context/categories", response_model=list[VocCategoryOut])
def get_categories(tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    """Tech & Regulation's product categories read through, plus this
    agent's own additions, each tagged with its source."""
    return [
        VocCategoryOut(
            category_key=c.category_key,
            category_name=c.category_name,
            description=c.description,
            source=c.source,
        )
        for c in merged_categories(db, tenant)
    ]


@router.put("/context/categories", response_model=list[VocCategoryOut])
def put_category_additions(
    payload: list[VocProductCategoryIn],
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    """Replaces this agent's ADDITIONS only. The read-through categories are
    edited where they are owned, on the Tech & Regulation scope screen."""
    _unique([p.category_key for p in payload], "category_key")
    _replace(db, tenant, VocProductCategory, [p.model_dump() for p in payload], VocProductCategory.category_key.asc())
    return get_categories(tenant=tenant, db=db)


@router.get("/context/state", response_model=VocContextStateOut)
def get_context_state(tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    """The operating tier, what is missing, and what each absence costs.
    Consequence text arrives empty for every item that is set and is passed
    through untouched (b4f3282). Never gates POST /runs."""
    context, tier, items = compute_context_state(db, tenant)
    return VocContextStateOut(
        operating_tier=tier,
        tier_label=TIER_LABELS[tier],
        run_label=run_label(tier),
        statement=operating_tier_statement(context),
        items=[
            VocContextStateItemOut(
                key=i.key, label=i.label, status=i.status, count=i.count, consequence=i.consequence
            )
            for i in items
        ],
        analyses=[
            VocAnalysisOut(
                key=a.key,
                label=a.label,
                available=a.available,
                enabled_by=a.enabled_by,
                minimum_source=a.minimum_source,
                note=a.note,
            )
            for a in analysis_availability(context)
        ],
    )


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------


def _parse_roles(raw: dict | None, columns: list[str] | None = None) -> dict[str, str]:
    roles = {k: v for k, v in (raw or {}).items() if v}
    unknown = sorted(set(roles) - set(COLUMN_ROLES))
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown column role(s): {', '.join(unknown)}. Roles: {', '.join(COLUMN_ROLES)}.",
        )
    if columns is not None:
        missing = sorted(c for c in roles.values() if c not in columns)
        if missing:
            raise HTTPException(
                status_code=422,
                detail=f"Column(s) not in this file: {', '.join(missing)}. Detected: {', '.join(columns)}.",
            )
    return roles


def _check_file_type(file_type: str) -> None:
    if file_type not in FILE_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown file_type {file_type!r}. One of: {', '.join(FILE_TYPES)}.",
        )


def _upload_size(upload: UploadFile) -> int:
    if upload.size is not None:
        return upload.size
    f = upload.file
    f.seek(0, io.SEEK_END)
    size = f.tell()
    f.seek(0)
    return size


@router.post("/evidence", response_model=VocEvidenceFileOut, status_code=201)
def upload_evidence(
    file: UploadFile = File(...),
    file_type: str = Form(...),
    as_of: str = Form(default=""),
    period_start: str = Form(default=""),
    period_end: str = Form(default=""),
    is_sample: bool = Form(default=False),
    sample_description: str = Form(default=""),
    segment_coverage: str = Form(default="", description="Comma-separated segment keys"),
    row_unit: str = Form(default="", description="CSV: what one row represents, e.g. ticket"),
    column_roles: str = Form(default="", description='CSV: JSON object, role -> column, e.g. {"category": "Type"}'),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    """Text, PDF or CSV. A CSV's detected columns are returned so the mapping
    can be confirmed (PATCH) -- the mapping helps the agent but its absence
    never blocks ingest. Sync (not async) on purpose: parsing is blocking
    work, and FastAPI runs a sync endpoint in its threadpool."""
    _check_file_type(file_type)
    try:
        roles_raw = json.loads(column_roles) if column_roles.strip() else {}
        if not isinstance(roles_raw, dict):
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=422, detail="column_roles must be a JSON object of role -> column")
    roles = _parse_roles(roles_raw)
    metadata = {
        "file_type": file_type,
        "as_of": as_of.strip(),
        "period_start": period_start.strip(),
        "period_end": period_end.strip(),
        "is_sample": is_sample,
        "sample_description": sample_description.strip(),
        "segment_coverage": [s.strip() for s in segment_coverage.split(",") if s.strip()],
        "row_unit": row_unit.strip(),
        "column_roles": roles,
    }
    try:
        return ingest_file(
            db,
            tenant,
            fileobj=file.file,
            filename=file.filename or "upload",
            content_type=file.content_type or "",
            size_bytes=_upload_size(file),
            metadata=metadata,
        )
    except ingest.IngestRejected as exc:
        status = 413 if str(exc).startswith("File is ") else 422
        raise HTTPException(status_code=status, detail=str(exc))
    except csv.Error as exc:
        raise HTTPException(status_code=422, detail=f"This CSV could not be parsed: {exc}")


@router.get("/evidence", response_model=list[VocEvidenceFileOut])
def list_evidence(tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    return scoped_query(db, VocEvidenceFile, tenant).order_by(VocEvidenceFile.created_at.asc()).all()


@router.patch("/evidence/{file_id}", response_model=VocEvidenceFileOut)
def patch_evidence(
    file_id: str,
    payload: VocEvidencePatchRequest,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    row = get_or_404(db, VocEvidenceFile, tenant, file_id)
    data = payload.model_dump(exclude_unset=True)
    if "file_type" in data and data["file_type"] is not None:
        _check_file_type(data["file_type"])
    if "column_roles" in data and data["column_roles"] is not None:
        if row.file_format != "csv":
            raise HTTPException(status_code=422, detail="column_roles apply to CSV files only")
        data["column_roles"] = _parse_roles(data["column_roles"], list(row.columns or []))
    for key, value in data.items():
        if value is not None:
            setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/evidence/{file_id}", status_code=204)
def delete_evidence(file_id: str, tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    row = get_or_404(db, VocEvidenceFile, tenant, file_id)
    delete_evidence_file(db, tenant, row)
    return None


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------


def _run_out(run: AgentRun, meta: VocRunMeta | None) -> VocRunOut:
    return VocRunOut(
        id=run.id,
        agent_type=run.agent_type,
        subject=run.subject,
        status=run.status,
        error=run.error,
        created_at=run.created_at,
        operating_tier=meta.tier if meta else None,
        run_label=run_label(meta.tier) if meta else None,
        sampling_notes=list(meta.sampling_notes or []) if meta else [],
    )


def _meta_for(db: Session, tenant: Tenant, run_id: str) -> VocRunMeta | None:
    return scoped_query(db, VocRunMeta, tenant).filter(VocRunMeta.run_id == run_id).first()


def _voc_run_or_404(db: Session, tenant: Tenant, run_id: str) -> AgentRun:
    run = get_or_404(db, AgentRun, tenant, run_id)
    if run.agent_type != AGENT_TYPE:
        raise HTTPException(status_code=404, detail="AgentRun not found")
    return run


@router.post("/runs", response_model=VocRunOut, status_code=202)
def start_run(
    background_tasks: BackgroundTasks,
    payload: VoiceOfCustomerRunRequest = VoiceOfCustomerRunRequest(),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    context = assemble_context(db, tenant)
    run = AgentRun(
        tenant_id=tenant.id,
        agent_type=AGENT_TYPE,
        subject=compose_subject(context),
        status="pending",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    background_tasks.add_task(
        execute_run,
        run_id=run.id,
        model=payload.model,
        max_searches=payload.max_searches,
        research_rounds=payload.research_rounds,
    )
    return _run_out(run, None)


# The briefing's endpoint list names POST /run; /runs matches GET /runs and
# every other agent's router. Both are accepted.
router.add_api_route(
    "/run", start_run, methods=["POST"], response_model=VocRunOut, status_code=202, include_in_schema=False
)


@router.get("/runs", response_model=list[VocRunOut])
def list_runs(tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    runs = (
        scoped_query(db, AgentRun, tenant)
        .filter(AgentRun.agent_type == AGENT_TYPE)
        .order_by(AgentRun.created_at.desc())
        .all()
    )
    metas = {
        m.run_id: m
        for m in scoped_query(db, VocRunMeta, tenant).filter(VocRunMeta.run_id.in_([r.id for r in runs]))
    } if runs else {}
    return [_run_out(r, metas.get(r.id)) for r in runs]


@router.get("/runs/{run_id}", response_model=VocRunOut)
def get_run(run_id: str, tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    run = _voc_run_or_404(db, tenant, run_id)
    return _run_out(run, _meta_for(db, tenant, run.id))


@router.get("/runs/{run_id}/reports", response_model=list[AgentReportSummary])
def list_run_reports(run_id: str, tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    run = _voc_run_or_404(db, tenant, run_id)
    return (
        scoped_query(db, AgentReport, tenant)
        .filter(AgentReport.run_id == run.id)
        .order_by(AgentReport.report_number.asc())
        .all()
    )


@router.get("/reports/{report_id}", response_model=AgentReportOut)
def get_report(report_id: str, tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    return get_or_404(db, AgentReport, tenant, report_id)


def _filename_slug(run: AgentRun) -> str:
    parts = (run.subject or "").split("—")
    basis = parts[1].strip() if len(parts) > 1 else ""
    slug = _SLUG_STRIP_RE.sub("_", basis).strip("_")[:60].strip("_")
    return slug or run.id


@router.get("/runs/{run_id}/export.docx")
def export_run_docx(run_id: str, tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    """The full pack as one .docx, reports streamed off the cursor. The
    cover label is the agent's registered label, except at Tier 2, where it
    is "External Customer-Context Analysis" -- the title is the unmissable
    signal, and the cover is the first thing a reader of the file sees."""
    run = _voc_run_or_404(db, tenant, run_id)
    report_rows = (
        scoped_query(db, AgentReport, tenant)
        .filter(AgentReport.run_id == run.id)
        .order_by(AgentReport.report_number.asc())
    )
    if report_rows.first() is None:
        raise HTTPException(status_code=404, detail="This run has no reports yet")

    meta = _meta_for(db, tenant, run.id)
    label = run_label(TIER_2) if meta and meta.tier == TIER_2 else agent_label_for(run.agent_type)

    builder = ExportBuilder()
    builder.add_cover_page(
        agent_label=label,
        scope_summary=run.subject or "",
        run_date=run.created_at.date().isoformat(),
    )
    builder.add_toc()
    for row in report_rows.yield_per(1):
        builder.add_report(row.content, report_number=row.report_number, title=row.title)

    prefix = "External_Customer_Context" if meta and meta.tier == TIER_2 else "Voice_of_Customer"
    filename = f"AutoStrat_Loom_{prefix}_{_filename_slug(run)}_{run.created_at.date().isoformat()}.docx"
    return StreamingResponse(
        io.BytesIO(builder.to_bytes()),
        media_type=DOCX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
