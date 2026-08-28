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

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app.auth import get_current_tenant
from app.database import SessionLocal, get_db
from app.models import AgentReport, AgentRun, Tenant
from app.schemas import (
    AgentReportOut,
    AgentReportSummary,
    AgentRunOut,
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


@router.post("/run", response_model=AgentRunOut, status_code=202)
def start_run(
    payload: MarketInsightsRunRequest,
    background_tasks: BackgroundTasks,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    """Kick off a Market Insights run for the caller's tenant. Returns at once."""
    run = AgentRun(
        tenant_id=tenant.id,
        agent_type=AGENT_TYPE,
        subject=payload.subject.strip(),
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
