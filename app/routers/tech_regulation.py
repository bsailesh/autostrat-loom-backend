"""
Technology & Regulatory Intelligence (Agent 3) endpoints.

The agent itself is `tech_regulation/`, wired up here -- its research,
candidate-work and synthesis logic is not touched or reimplemented. A run
takes tens of minutes, so POST /runs returns immediately with a `pending`
AgentRun and the work happens in a FastAPI background task that writes the
nine reports plus the structured candidate work, then flips the run to
`succeeded` / `failed`.

Every read is tenant-scoped through app/tenant_scope.py, and a row outside
the caller's tenant 404s rather than 403s -- the existence of another
tenant's run is not information this API leaks.

Two deliberate differences from app/routers/market_insights.py:

* **A run is never blocked by incomplete scoping.** Market Insights 409s
  without a product line; this agent degrades and says so in its own output,
  because an unscoped regulatory survey is still useful as long as it cannot
  be mistaken for the customer's obligations.
* **DELETE exists for candidate work from the start.** The missing delete
  path for DiscoveredCandidate is logged as a known gap in
  app/routers/strategy_synthesis.py; repeating it here would repeat a
  problem already understood.
"""
import io
import logging
import re

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth import get_current_tenant
from app.database import get_db
from app.export.docx_builder import ExportBuilder, agent_label_for
from app.models import (
    AgentReport,
    AgentRun,
    Tenant,
    TrCandidateWork,
    TrCertificationBasis,
    TrDomain,
    TrExclusion,
    TrJurisdiction,
    TrPlatform,
    TrProductCategory,
    TrStandardHeld,
    TrSupplier,
)
from app.schemas import (
    AgentReportOut,
    AgentReportSummary,
    AgentRunOut,
    TechRegulationRunRequest,
    TrCandidateWorkOut,
    TrCandidateWorkPatchRequest,
    TrCertificationBasisIn,
    TrDomainIn,
    TrExclusionIn,
    TrJurisdictionIn,
    TrPlatformIn,
    TrProductCategoryIn,
    TrScopeStateItemOut,
    TrScopeStateOut,
    TrStandardHeldIn,
    TrSupplierIn,
)
from app.tech_regulation_service import (
    AGENT_TYPE,
    assemble_envelope,
    compose_subject,
    compute_scope_state,
    execute_run,
)
from app.tenant_scope import get_or_404, scoped_query

from tech_regulation.scoping import operating_state_statement

router = APIRouter(prefix="/agents/tech-regulation", tags=["tech-regulation"])

logger = logging.getLogger(__name__)

DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_SLUG_STRIP_RE = re.compile(r"[^A-Za-z0-9]+")


# ---------------------------------------------------------------------------
# Scope -- eight dimensions, each a GET/PUT list
#
# PUT replaces that dimension wholesale. The envelope is small (the scoping
# spec puts it at fifteen minutes of work), the UI is form-based with
# repeatable rows, and whole-section replacement avoids per-row id juggling
# for no loss of capability.
# ---------------------------------------------------------------------------


def _replace_dimension(db: Session, tenant: Tenant, model, rows: list) -> list:
    scoped_query(db, model, tenant).delete(synchronize_session=False)
    for row in rows:
        db.add(model(tenant_id=tenant.id, **row))
    db.commit()
    return scoped_query(db, model, tenant).all()


@router.get("/scope/categories", response_model=list[TrProductCategoryIn])
def get_categories(tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    return scoped_query(db, TrProductCategory, tenant).order_by(TrProductCategory.category_key.asc()).all()


@router.put("/scope/categories", response_model=list[TrProductCategoryIn])
def put_categories(
    payload: list[TrProductCategoryIn],
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    keys = [p.category_key for p in payload]
    if len(keys) != len(set(keys)):
        raise HTTPException(status_code=422, detail="category_key values must be unique")
    return _replace_dimension(db, tenant, TrProductCategory, [p.model_dump() for p in payload])


@router.get("/scope/jurisdictions", response_model=list[TrJurisdictionIn])
def get_jurisdictions(tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    return scoped_query(db, TrJurisdiction, tenant).order_by(TrJurisdiction.jurisdiction.asc()).all()


@router.put("/scope/jurisdictions", response_model=list[TrJurisdictionIn])
def put_jurisdictions(
    payload: list[TrJurisdictionIn],
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    names = [p.jurisdiction for p in payload]
    if len(names) != len(set(names)):
        raise HTTPException(status_code=422, detail="jurisdiction values must be unique")
    return _replace_dimension(db, tenant, TrJurisdiction, [p.model_dump() for p in payload])


@router.get("/scope/certification-basis", response_model=list[TrCertificationBasisIn])
def get_certification_basis(tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    return (
        scoped_query(db, TrCertificationBasis, tenant)
        .order_by(TrCertificationBasis.category_key.asc())
        .all()
    )


@router.put("/scope/certification-basis", response_model=list[TrCertificationBasisIn])
def put_certification_basis(
    payload: list[TrCertificationBasisIn],
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    """The highest-leverage dimension in the envelope: without it, a
    regulatory change can be reported but not assessed for applicability."""
    triples = [(p.category_key, p.basis_type, p.basis_identifier) for p in payload]
    if len(triples) != len(set(triples)):
        raise HTTPException(
            status_code=422,
            detail="category_key + basis_type + basis_identifier must be unique "
                   "(one category may hold several bases, but not the same one twice)",
        )
    return _replace_dimension(db, tenant, TrCertificationBasis, [p.model_dump() for p in payload])


@router.get("/scope/platforms", response_model=list[TrPlatformIn])
def get_platforms(tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    return scoped_query(db, TrPlatform, tenant).order_by(TrPlatform.platform.asc()).all()


@router.put("/scope/platforms", response_model=list[TrPlatformIn])
def put_platforms(
    payload: list[TrPlatformIn],
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    names = [p.platform for p in payload]
    if len(names) != len(set(names)):
        raise HTTPException(status_code=422, detail="platform values must be unique")
    return _replace_dimension(db, tenant, TrPlatform, [p.model_dump() for p in payload])


@router.get("/scope/standards", response_model=list[TrStandardHeldIn])
def get_standards(tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    return scoped_query(db, TrStandardHeld, tenant).order_by(TrStandardHeld.standard_id.asc()).all()


@router.put("/scope/standards", response_model=list[TrStandardHeldIn])
def put_standards(
    payload: list[TrStandardHeldIn],
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    pairs = [(p.standard_id, p.revision) for p in payload]
    if len(pairs) != len(set(pairs)):
        raise HTTPException(status_code=422, detail="standard_id + revision must be unique")
    return _replace_dimension(db, tenant, TrStandardHeld, [p.model_dump() for p in payload])


@router.get("/scope/suppliers", response_model=list[TrSupplierIn])
def get_suppliers(tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    return scoped_query(db, TrSupplier, tenant).order_by(TrSupplier.supplier.asc()).all()


@router.put("/scope/suppliers", response_model=list[TrSupplierIn])
def put_suppliers(
    payload: list[TrSupplierIn],
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    names = [p.supplier for p in payload]
    if len(names) != len(set(names)):
        raise HTTPException(status_code=422, detail="supplier values must be unique")
    return _replace_dimension(db, tenant, TrSupplier, [p.model_dump() for p in payload])


@router.get("/scope/domains", response_model=list[TrDomainIn])
def get_domains(tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    return scoped_query(db, TrDomain, tenant).order_by(TrDomain.domain.asc()).all()


@router.put("/scope/domains", response_model=list[TrDomainIn])
def put_domains(
    payload: list[TrDomainIn],
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    names = [p.domain for p in payload]
    if len(names) != len(set(names)):
        raise HTTPException(status_code=422, detail="domain values must be unique")
    return _replace_dimension(db, tenant, TrDomain, [p.model_dump() for p in payload])


@router.get("/scope/exclusions", response_model=list[TrExclusionIn])
def get_exclusions(tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    return scoped_query(db, TrExclusion, tenant).order_by(TrExclusion.exclusion_type.asc()).all()


@router.put("/scope/exclusions", response_model=list[TrExclusionIn])
def put_exclusions(
    payload: list[TrExclusionIn],
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    pairs = [(p.exclusion_type, p.value) for p in payload]
    if len(pairs) != len(set(pairs)):
        raise HTTPException(status_code=422, detail="exclusion_type + value must be unique")
    return _replace_dimension(db, tenant, TrExclusion, [p.model_dump() for p in payload])


# ---------------------------------------------------------------------------
# Scope state
# ---------------------------------------------------------------------------


@router.get("/scope/state", response_model=TrScopeStateOut)
def get_scope_state(tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    """The operating state, what is missing, and what each absence costs --
    never a bare 'missing' badge. Never gates POST /runs.

    The consequence text arrives already empty for every dimension that is
    set, and this endpoint passes it through untouched. Attaching it
    unconditionally is the bug that shipped on Agent 5's /readiness and was
    fixed in b4f3282: every section displayed its missing-case warning
    regardless of status, which reads as an alarm about something that is
    fine and teaches the user to ignore the column."""
    state, items = compute_scope_state(db, tenant)
    envelope = assemble_envelope(db, tenant)
    return TrScopeStateOut(
        operating_state=state,
        statement=operating_state_statement(envelope),
        items=[
            TrScopeStateItemOut(
                key=i.key, label=i.label, status=i.status, count=i.count, consequence=i.consequence
            )
            for i in items
        ],
    )


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------


@router.post("/runs", response_model=AgentRunOut, status_code=202)
def start_run(
    background_tasks: BackgroundTasks,
    payload: TechRegulationRunRequest = TechRegulationRunRequest(),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    """Kick off a run against the caller's stored envelope. Returns at once.

    Deliberately no 409 for incomplete scoping: the run degrades and states
    its operating state in the first line of every report, and an unscoped
    run is titled so it cannot be mistaken for an applicability
    assessment."""
    envelope = assemble_envelope(db, tenant)
    run = AgentRun(
        tenant_id=tenant.id,
        agent_type=AGENT_TYPE,
        subject=compose_subject(envelope),
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
    return run


@router.get("/runs", response_model=list[AgentRunOut])
def list_runs(tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    return (
        scoped_query(db, AgentRun, tenant)
        .filter(AgentRun.agent_type == AGENT_TYPE)
        .order_by(AgentRun.created_at.desc())
        .all()
    )


@router.get("/runs/{run_id}", response_model=AgentRunOut)
def get_run(run_id: str, tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    return get_or_404(db, AgentRun, tenant, run_id)


@router.get("/runs/{run_id}/reports", response_model=list[AgentReportSummary])
def list_run_reports(
    run_id: str, tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)
):
    run = get_or_404(db, AgentRun, tenant, run_id)
    return (
        scoped_query(db, AgentReport, tenant)
        .filter(AgentReport.run_id == run.id)
        .order_by(AgentReport.report_number.asc())
        .all()
    )


@router.get("/reports/{report_id}", response_model=AgentReportOut)
def get_report(
    report_id: str, tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)
):
    return get_or_404(db, AgentReport, tenant, report_id)


def _filename_slug(run: AgentRun) -> str:
    basis = (run.subject or "").split("—")[0].strip()
    slug = _SLUG_STRIP_RE.sub("_", basis).strip("_")
    slug = slug[:60].strip("_")
    return slug or run.id


@router.get("/runs/{run_id}/export.docx")
def export_run_docx(
    run_id: str, tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)
):
    """The full report pack for a run as a single .docx, built in memory from
    the stored markdown. Reports are streamed off the query cursor rather
    than materialized as a list -- the production instance has 414MB RAM."""
    run = get_or_404(db, AgentRun, tenant, run_id)

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

    for row in report_rows.yield_per(1):
        builder.add_report(row.content, report_number=row.report_number, title=row.title)

    docx_bytes = builder.to_bytes()
    filename = (
        f"AutoStrat_Loom_Technology_Regulation_{_filename_slug(run)}_"
        f"{run.created_at.date().isoformat()}.docx"
    )
    return StreamingResponse(
        io.BytesIO(docx_bytes),
        media_type=DOCX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Candidate work
#
# The live triage surface. Report 1's consolidated list is frozen at run
# time, so the UI reads status from here rather than from the report prose,
# to reflect actions taken since that run.
# ---------------------------------------------------------------------------


@router.get("/candidate-work", response_model=list[TrCandidateWorkOut])
def list_candidate_work(
    run_id: str | None = None,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    """All candidate work for the tenant, or just one run's with `run_id`.

    Scoping by run means the items that run surfaced -- including ones an
    earlier run first found and this one re-confirmed -- which is the same
    set Agent 5 reads for a pinned upstream run."""
    query = scoped_query(db, TrCandidateWork, tenant)
    if run_id is not None:
        run = get_or_404(db, AgentRun, tenant, run_id)
        query = query.filter(TrCandidateWork.last_seen_run_id == run.id)
    return query.order_by(TrCandidateWork.candidate_key.asc()).all()


def _candidate_work_or_404(db: Session, tenant: Tenant, key: str) -> TrCandidateWork:
    row = (
        scoped_query(db, TrCandidateWork, tenant)
        .filter(TrCandidateWork.candidate_key == key)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"No candidate work with key {key!r}")
    return row


@router.patch("/candidate-work/{key}", response_model=TrCandidateWorkOut)
def patch_candidate_work(
    key: str,
    payload: TrCandidateWorkPatchRequest,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    """Triage an item. A later run refreshes this item's evidence fields but
    never its status, so a dismissal survives re-discovery."""
    row = _candidate_work_or_404(db, tenant, key)
    if payload.status == "dismissed" and not payload.dismissal_reason.strip():
        raise HTTPException(
            status_code=422,
            detail="dismissal_reason is required when dismissing an item -- a dismissal with no "
                   "reason cannot be reviewed later, and this item will be re-surfaced by "
                   "every future run that still finds the evidence",
        )
    row.status = payload.status
    row.dismissal_reason = payload.dismissal_reason
    db.commit()
    db.refresh(row)
    return row


@router.delete("/candidate-work/{key}", status_code=204)
def delete_candidate_work(
    key: str, tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)
):
    """Remove an item outright.

    Present from the start, unlike DiscoveredCandidate's missing delete path
    (logged as a known gap in app/routers/strategy_synthesis.py). Note what
    delete does NOT do: persistence is additive and keyed by candidate_key,
    so a deleted item whose evidence still exists will be re-surfaced as
    `new` by the next run. To suppress something permanently, dismiss it with
    a reason -- that status survives re-discovery. Delete is for an item that
    should never have existed, not for one the customer has decided
    against."""
    row = _candidate_work_or_404(db, tenant, key)
    db.delete(row)
    db.commit()
    return None
