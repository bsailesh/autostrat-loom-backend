"""
Product Sustainment (Agent 4) endpoints.

Follows app/routers/tech_regulation.py: the agent is `product_sustainment/`,
wired up here; a run returns at once and a background task does the work.
Tenant-scoped through app/tenant_scope.py; another tenant's row is 404, not
403.

**A run is never blocked.** With no BOM it is an obsolescence and exposure
scan, titled as such; with partial data it degrades and says what each
absence costs.
"""
import csv
import io
import logging
import re
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.auth import get_current_tenant
from app.database import get_db
from app.export.docx_builder import ExportBuilder, agent_label_for
from app.models import (
    AgentReport,
    AgentRun,
    PsCandidateWork,
    PsEvidenceFile,
    PsFile,
    PsKnowledge,
    PsRunMeta,
    Tenant,
)
from app.product_sustainment_service import (
    AGENT_TYPE,
    MASTER_MODELS,
    ReferentialError,
    assemble_data,
    delete_evidence,
    execute_run,
    ingest_data_file,
    ingest_evidence,
    ingest_mapping,
    replace_master,
    structure_summary,
    template,
)
from app.schemas import (
    AgentReportOut,
    AgentReportSummary,
    PsCandidateWorkOut,
    PsCandidateWorkPatchRequest,
    PsEvidenceFileOut,
    PsFileOut,
    PsKnowledgeIn,
    PsLevel1In,
    PsLevel2In,
    PsLruIn,
    PsMatrixUploadOut,
    PsReadinessItemOut,
    PsReadinessOut,
    PsRunOut,
    PsStructureSummaryOut,
    ProductSustainmentRunRequest,
)
from app.tenant_scope import get_or_404, scoped_query

from product_sustainment import evidence_ingest, ingest
from product_sustainment.evidence import FILE_TYPES as EVIDENCE_FILE_TYPES
from product_sustainment.structure import (
    EXPOSURE_SCAN,
    TIER_LABELS,
    operating_tier,
    operating_tier_statement,
    readiness_items,
    run_label,
)

router = APIRouter(prefix="/agents/product-sustainment", tags=["product-sustainment"])
logger = logging.getLogger(__name__)

DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_SLUG_STRIP_RE = re.compile(r"[^A-Za-z0-9]+")


async def _read_text(file: UploadFile) -> str:
    raw = await file.read()
    if len(raw) > evidence_ingest.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=evidence_ingest.upload_too_large_message(len(raw)))
    return raw.decode("utf-8-sig", errors="replace")


# ---------------------------------------------------------------------------
# Structure -- masters, matrices, templates
# ---------------------------------------------------------------------------


def _put_master(which: str, payload: list, tenant: Tenant, db: Session):
    _, key = MASTER_MODELS[which]
    ids = [getattr(p, key) for p in payload]
    if len(ids) != len(set(ids)):
        raise HTTPException(status_code=422, detail=f"{key} values must be unique")
    try:
        return replace_master(db, tenant, which, [p.model_dump() for p in payload])
    except ReferentialError as e:
        raise HTTPException(status_code=409, detail=str(e))


def _get_master(which: str, tenant: Tenant, db: Session):
    model, key = MASTER_MODELS[which]
    return scoped_query(db, model, tenant).order_by(getattr(model, key).asc()).all()


@router.get("/structure/lrus", response_model=list[PsLruIn])
def get_lrus(tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    return _get_master("lrus", tenant, db)


@router.put("/structure/lrus", response_model=list[PsLruIn])
def put_lrus(payload: list[PsLruIn], tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    return _put_master("lrus", payload, tenant, db)


@router.get("/structure/level1", response_model=list[PsLevel1In])
def get_level1(tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    return _get_master("level1", tenant, db)


@router.put("/structure/level1", response_model=list[PsLevel1In])
def put_level1(payload: list[PsLevel1In], tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    return _put_master("level1", payload, tenant, db)


@router.get("/structure/level2", response_model=list[PsLevel2In])
def get_level2(tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    return _get_master("level2", tenant, db)


@router.put("/structure/level2", response_model=list[PsLevel2In])
def put_level2(payload: list[PsLevel2In], tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    return _put_master("level2", payload, tenant, db)


@router.get("/structure/summary", response_model=PsStructureSummaryOut)
def get_structure_summary(tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    return structure_summary(db, tenant)


@router.post("/structure/matrix/{which}", response_model=PsMatrixUploadOut)
async def upload_matrix(
    which: str,
    file: UploadFile = File(...),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    """Matrix or edge list. Any unresolved reference is an ERROR that blocks
    the whole file -- it would silently remove demand. The response carries
    the validation result and the derived picture."""
    if which not in ingest.MATRIX_KINDS:
        raise HTTPException(status_code=404, detail=f"Unknown matrix {which!r}; one of {', '.join(ingest.MATRIX_KINDS)}")
    text = await _read_text(file)
    try:
        rec, _ = ingest_mapping(db, tenant, which, text, file.filename or "")
    except csv.Error as e:
        raise HTTPException(status_code=422, detail=f"This CSV could not be parsed: {e}")
    return PsMatrixUploadOut(file=rec, summary=structure_summary(db, tenant))


TEMPLATE_KINDS = (*ingest.MATRIX_KINDS, *ingest.DATA_FILE_TYPES)


@router.get("/structure/templates/{which}")
def get_template(which: str, tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    """Generated from the declared ids, so headers are correct by construction."""
    if which not in TEMPLATE_KINDS:
        raise HTTPException(status_code=404, detail=f"Unknown template {which!r}")
    return PlainTextResponse(
        template(db, tenant, which, datetime.now(timezone.utc).date()),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{which}_template.csv"'},
    )


# ---------------------------------------------------------------------------
# Data files
# ---------------------------------------------------------------------------


@router.post("/files/{file_type}", response_model=PsFileOut)
async def upload_file(
    file_type: str,
    file: UploadFile = File(...),
    as_of: str = Form(default=""),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    """Any error blocks this file's ingest; the previous data stays. Warnings
    never block."""
    if file_type not in ingest.DATA_FILE_TYPES:
        raise HTTPException(status_code=404, detail=f"Unknown file_type {file_type!r}")
    text = await _read_text(file)
    try:
        return ingest_data_file(db, tenant, file_type, text, file.filename or "", as_of.strip())
    except csv.Error as e:
        raise HTTPException(status_code=422, detail=f"This CSV could not be parsed: {e}")


@router.get("/files", response_model=list[PsFileOut])
def list_files(tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    return scoped_query(db, PsFile, tenant).order_by(PsFile.file_type.asc()).all()


@router.get("/knowledge", response_model=list[PsKnowledgeIn])
def get_knowledge(tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    return scoped_query(db, PsKnowledge, tenant).all()


@router.put("/knowledge", response_model=list[PsKnowledgeIn])
def put_knowledge(payload: list[PsKnowledgeIn], tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    """A form, not an upload: there is no source file for a judgement."""
    scoped_query(db, PsKnowledge, tenant).delete(synchronize_session=False)
    for p in payload:
        db.add(PsKnowledge(tenant_id=tenant.id, **p.model_dump()))
    db.commit()
    return scoped_query(db, PsKnowledge, tenant).all()


# ---------------------------------------------------------------------------
# Evidence -- the Voice of Customer pattern
# ---------------------------------------------------------------------------


def _upload_size(upload: UploadFile) -> int:
    if upload.size is not None:
        return upload.size
    f = upload.file
    f.seek(0, io.SEEK_END)
    size = f.tell()
    f.seek(0)
    return size


@router.post("/evidence", response_model=PsEvidenceFileOut, status_code=201)
def upload_evidence(
    file: UploadFile = File(...),
    file_type: str = Form(...),
    as_of: str = Form(default=""),
    period_start: str = Form(default=""),
    period_end: str = Form(default=""),
    is_sample: bool = Form(default=False),
    sample_description: str = Form(default=""),
    row_unit: str = Form(default=""),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    if file_type not in EVIDENCE_FILE_TYPES:
        raise HTTPException(status_code=422, detail=f"Unknown file_type {file_type!r}. One of: {', '.join(EVIDENCE_FILE_TYPES)}.")
    metadata = {
        "file_type": file_type, "as_of": as_of.strip(), "period_start": period_start.strip(),
        "period_end": period_end.strip(), "is_sample": is_sample,
        "sample_description": sample_description.strip(), "row_unit": row_unit.strip(),
    }
    try:
        return ingest_evidence(db, tenant, fileobj=file.file, filename=file.filename or "upload",
                               content_type=file.content_type or "", size_bytes=_upload_size(file), metadata=metadata)
    except evidence_ingest.IngestRejected as e:
        raise HTTPException(status_code=413 if str(e).startswith("File is ") else 422, detail=str(e))
    except csv.Error as e:
        raise HTTPException(status_code=422, detail=f"This CSV could not be parsed: {e}")


@router.get("/evidence", response_model=list[PsEvidenceFileOut])
def list_evidence(tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    return scoped_query(db, PsEvidenceFile, tenant).order_by(PsEvidenceFile.created_at.asc()).all()


@router.delete("/evidence/{file_id}", status_code=204)
def remove_evidence(file_id: str, tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    delete_evidence(db, tenant, get_or_404(db, PsEvidenceFile, tenant, file_id))
    return None


# ---------------------------------------------------------------------------
# Readiness
# ---------------------------------------------------------------------------


@router.get("/readiness", response_model=PsReadinessOut)
def get_readiness(tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    """What is missing and what it costs. Consequence text arrives empty for
    every item that is set and is passed through untouched (b4f3282). Never
    gates a run."""
    data = assemble_data(db, tenant)
    tier = operating_tier(data)
    return PsReadinessOut(
        operating_tier=tier,
        tier_label=TIER_LABELS[tier],
        run_label=run_label(tier),
        statement=operating_tier_statement(data),
        items=[PsReadinessItemOut(key=i.key, label=i.label, status=i.status, count=i.count, consequence=i.consequence)
               for i in readiness_items(data)],
    )


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------


def _meta_for(db, tenant, run_id) -> PsRunMeta | None:
    return scoped_query(db, PsRunMeta, tenant).filter(PsRunMeta.run_id == run_id).first()


def _run_out(run: AgentRun, meta: PsRunMeta | None) -> PsRunOut:
    return PsRunOut(
        id=run.id, agent_type=run.agent_type, subject=run.subject, status=run.status, error=run.error,
        created_at=run.created_at,
        operating_tier=meta.tier if meta else None,
        run_label=run_label(meta.tier) if meta else None,
        notes=list(meta.notes or []) if meta else [],
        candidate_work_dropped=list(meta.candidate_work_dropped or []) if meta else [],
    )


def _ps_run_or_404(db, tenant, run_id) -> AgentRun:
    run = get_or_404(db, AgentRun, tenant, run_id)
    if run.agent_type != AGENT_TYPE:
        raise HTTPException(status_code=404, detail="AgentRun not found")
    return run


def _compose_subject(db, tenant) -> str:
    data = assemble_data(db, tenant)
    tier = operating_tier(data)
    return (
        f"{run_label(tier)} — {len(data.lrus)} LRU(s), {len(data.level1)} assemblies, "
        f"{len(data.level2)} components — {TIER_LABELS[tier]}"
    )


@router.post("/run", response_model=PsRunOut, status_code=202)
def start_run(
    background_tasks: BackgroundTasks,
    payload: ProductSustainmentRunRequest = ProductSustainmentRunRequest(),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    run = AgentRun(tenant_id=tenant.id, agent_type=AGENT_TYPE, subject=_compose_subject(db, tenant), status="pending")
    db.add(run)
    db.commit()
    db.refresh(run)
    background_tasks.add_task(execute_run, run_id=run.id, model=payload.model,
                              max_searches=payload.max_searches, research_rounds=payload.research_rounds)
    return _run_out(run, None)


# POST /runs matches GET /runs and the other agents' routers; both accepted.
router.add_api_route("/runs", start_run, methods=["POST"], response_model=PsRunOut, status_code=202,
                     include_in_schema=False)


@router.get("/runs", response_model=list[PsRunOut])
def list_runs(tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    runs = scoped_query(db, AgentRun, tenant).filter(AgentRun.agent_type == AGENT_TYPE).order_by(AgentRun.created_at.desc()).all()
    metas = {m.run_id: m for m in scoped_query(db, PsRunMeta, tenant).filter(PsRunMeta.run_id.in_([r.id for r in runs]))} if runs else {}
    return [_run_out(r, metas.get(r.id)) for r in runs]


@router.get("/runs/{run_id}", response_model=PsRunOut)
def get_run(run_id: str, tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    run = _ps_run_or_404(db, tenant, run_id)
    return _run_out(run, _meta_for(db, tenant, run.id))


@router.get("/runs/{run_id}/reports", response_model=list[AgentReportSummary])
def list_run_reports(run_id: str, tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    run = _ps_run_or_404(db, tenant, run_id)
    return scoped_query(db, AgentReport, tenant).filter(AgentReport.run_id == run.id).order_by(AgentReport.report_number.asc()).all()


@router.get("/runs/{run_id}/runout")
def get_runout(run_id: str, tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    """The complete computed runout table for a run -- every component, not
    the most-urgent subset the report markdown carries -- plus every part
    with insufficient data. The filterable view reads from here."""
    run = _ps_run_or_404(db, tenant, run_id)
    meta = _meta_for(db, tenant, run.id)
    if meta is None:
        raise HTTPException(status_code=404, detail="This run has no computed results yet")
    return {
        "horizon_years": meta.horizon_years or [],
        "rows": meta.runout_rows or [],
        "insufficient": meta.insufficient_rows or [],
        "notes": meta.notes or [],
    }


@router.get("/reports/{report_id}", response_model=AgentReportOut)
def get_report(report_id: str, tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    return get_or_404(db, AgentReport, tenant, report_id)


@router.get("/runs/{run_id}/export.docx")
def export_run_docx(run_id: str, tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    """Cover label is the agent's registered one, except for an exposure
    scan, which the cover says it is."""
    run = _ps_run_or_404(db, tenant, run_id)
    rows = scoped_query(db, AgentReport, tenant).filter(AgentReport.run_id == run.id).order_by(AgentReport.report_number.asc())
    if rows.first() is None:
        raise HTTPException(status_code=404, detail="This run has no reports yet")
    meta = _meta_for(db, tenant, run.id)
    scan = meta is not None and meta.tier == EXPOSURE_SCAN
    builder = ExportBuilder()
    builder.add_cover_page(
        agent_label=run_label(EXPOSURE_SCAN) if scan else agent_label_for(run.agent_type),
        scope_summary=run.subject or "",
        run_date=run.created_at.date().isoformat(),
    )
    builder.add_toc()
    for row in rows.yield_per(1):
        builder.add_report(row.content, report_number=row.report_number, title=row.title)
    prefix = "Exposure_Scan" if scan else "Product_Sustainment"
    filename = f"AutoStrat_Loom_{prefix}_{run.created_at.date().isoformat()}.docx"
    return StreamingResponse(io.BytesIO(builder.to_bytes()), media_type=DOCX_MEDIA_TYPE,
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})


# ---------------------------------------------------------------------------
# Candidate work
# ---------------------------------------------------------------------------


@router.get("/candidate-work", response_model=list[PsCandidateWorkOut])
def list_candidate_work(run_id: str | None = None, tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    q = scoped_query(db, PsCandidateWork, tenant)
    if run_id is not None:
        run = _ps_run_or_404(db, tenant, run_id)
        q = q.filter(PsCandidateWork.last_seen_run_id == run.id)
    return q.order_by(PsCandidateWork.candidate_key.asc()).all()


def _cw_or_404(db, tenant, key) -> PsCandidateWork:
    row = scoped_query(db, PsCandidateWork, tenant).filter(PsCandidateWork.candidate_key == key).first()
    if row is None:
        raise HTTPException(status_code=404, detail=f"No candidate work with key {key!r}")
    return row


@router.patch("/candidate-work/{key}", response_model=PsCandidateWorkOut)
def patch_candidate_work(key: str, payload: PsCandidateWorkPatchRequest,
                         tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    row = _cw_or_404(db, tenant, key)
    if payload.status == "dismissed" and not payload.dismissal_reason.strip():
        raise HTTPException(status_code=422, detail="dismissal_reason is required when dismissing an item")
    row.status = payload.status
    row.dismissal_reason = payload.dismissal_reason
    db.commit()
    db.refresh(row)
    return row


@router.delete("/candidate-work/{key}", status_code=204)
def delete_candidate_work(key: str, tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    """Present from the start. Persistence is additive, so an item whose
    evidence still exists is re-surfaced by the next run; to suppress it,
    dismiss it with a reason."""
    db.delete(_cw_or_404(db, tenant, key))
    db.commit()
    return None
