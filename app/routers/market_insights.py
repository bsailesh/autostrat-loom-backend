"""
Market Insights agent endpoints.

The agent itself is the Phase 1 module (`market_insights/`), wired up here — its
research/synthesis logic is not touched or reimplemented. A run takes tens of
minutes, so POST /run returns immediately with a `pending` AgentRun and the work
happens in a FastAPI background task that writes the nine reports and flips the
run to `succeeded` / `failed`.

(A background task is fine for this phase; a real job queue — arq/RQ/Celery — is
the Phase 3+ move so runs survive a process restart and can be scaled out.)

Every read is tenant-scoped through app/tenant_scope.py: a run or report is only
ever visible to the tenant whose id is on the row.
"""
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_tenant
from app.database import SessionLocal, get_db
from app.models import AgentReport, AgentRun, AgentScope, Tenant
from app.schemas import (
    AgentReportOut,
    AgentReportSummary,
    AgentRunOut,
    AgentScopeResponse,
    AgentScopeUpsertRequest,
    MarketInsightsRunRequest,
)
from app.tenant_scope import get_or_404, scoped_query

from market_insights import MarketInsightsAgent
from market_insights.config import Settings as AgentSettings

router = APIRouter(prefix="/agents/market-insights", tags=["market-insights"])

logger = logging.getLogger(__name__)

AGENT_TYPE = "market-insights"

# The background task can't use the request-scoped session (it's closed by the
# time the task runs), so it opens its own. Held at module level so tests can
# point it at their in-memory database.
SessionFactory = SessionLocal


def _get_scope(db: Session, tenant: Tenant) -> AgentScope | None:
    return (
        scoped_query(db, AgentScope, tenant)
        .filter(AgentScope.agent_type == AGENT_TYPE)
        .first()
    )


def _compose_subject(scope: AgentScope) -> str:
    """Turn the configured scope into the single subject string the Phase 1
    agent module takes (its input handling is unchanged — only the source is)."""
    parts = [scope.product_line.strip()]
    if (scope.competitors or "").strip():
        parts.append(f"Competitor focus: {scope.competitors.strip()}")
    if (scope.geography or "").strip():
        parts.append(f"Geographic focus: {scope.geography.strip()}")
    return " — ".join(parts)


def _scope_response(scope: AgentScope | None) -> AgentScopeResponse:
    if scope is None:
        return AgentScopeResponse(configured=False, agent_type=AGENT_TYPE)
    return AgentScopeResponse(
        configured=True,
        agent_type=AGENT_TYPE,
        product_line=scope.product_line,
        competitors=scope.competitors or None,
        geography=scope.geography or None,
        updated_at=scope.updated_at,
    )


@router.get("/scope", response_model=AgentScopeResponse)
def get_scope(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    """Current standing research scope for this tenant, or configured=false."""
    return _scope_response(_get_scope(db, tenant))


@router.put("/scope", response_model=AgentScopeResponse)
def put_scope(
    payload: AgentScopeUpsertRequest,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    """Create or update the scope. product_line is required and non-empty."""
    product_line = (payload.product_line or "").strip()
    if not product_line:
        raise HTTPException(status_code=400, detail="product_line is required and cannot be empty")

    competitors = (payload.competitors or "").strip()
    geography = (payload.geography or "").strip()

    scope = _get_scope(db, tenant)
    if scope is None:
        scope = AgentScope(tenant_id=tenant.id, agent_type=AGENT_TYPE)
        db.add(scope)
    scope.product_line = product_line
    scope.competitors = competitors
    scope.geography = geography
    db.commit()
    db.refresh(scope)
    return _scope_response(scope)


@router.post("/run", response_model=AgentRunOut, status_code=202)
def start_run(
    background_tasks: BackgroundTasks,
    payload: MarketInsightsRunRequest = MarketInsightsRunRequest(),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    """Kick off a Market Insights run for the caller's tenant, against their
    configured scope. Returns at once. 409 if no scope is configured yet."""
    scope = _get_scope(db, tenant)
    if scope is None or not scope.product_line.strip():
        raise HTTPException(
            status_code=409,
            detail="Product line must be configured before this agent can run. "
                   "Set it via PUT /agents/market-insights/scope.",
        )

    run = AgentRun(
        tenant_id=tenant.id,
        agent_type=AGENT_TYPE,
        subject=_compose_subject(scope),
        status="pending",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    background_tasks.add_task(
        _execute_run,
        run_id=run.id,
        subject=run.subject,
        model=payload.model,
        max_searches=payload.max_searches,
        research_rounds=payload.research_rounds,
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


# --------------------------------------------------------------------------
# Background execution
# --------------------------------------------------------------------------

def _execute_run(
    *,
    run_id: str,
    subject: str,
    model: str | None,
    max_searches: int | None,
    research_rounds: int | None,
) -> None:
    db = SessionFactory()
    try:
        run = db.get(AgentRun, run_id)
        if run is None:  # deleted between scheduling and execution
            return
        run.status = "running"
        db.commit()

        try:
            settings = AgentSettings.load(model_override=model)
            agent = MarketInsightsAgent(settings)
            run_kwargs: dict = {}
            if max_searches is not None:
                run_kwargs["max_searches"] = max_searches
            if research_rounds is not None:
                run_kwargs["research_rounds"] = research_rounds
            result = agent.run(subject, **run_kwargs)

            for report in result.reports:
                db.add(
                    AgentReport(
                        tenant_id=run.tenant_id,
                        run_id=run.id,
                        report_number=report.report_number,
                        title=report.title,
                        content=report.content,
                        confidence_summary=report.confidence_summary,
                    )
                )
            run.status = "succeeded"
            run.error = None
            db.commit()
        except Exception as exc:  # noqa: BLE001 - any failure must land on the run row
            logger.exception("Market Insights run %s failed", run_id)
            db.rollback()
            run = db.get(AgentRun, run_id)
            if run is not None:
                run.status = "failed"
                run.error = f"{type(exc).__name__}: {exc}"[:2000]
                db.commit()
    finally:
        db.close()
