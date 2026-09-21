"""
Strategy Synthesis agent (Agent 5) -- the glue between the database and
`strategy_synthesis/` (which knows nothing about either). Everything here
is the part market_insights.py keeps inline (`_execute_run`, `_get_scope`)
scaled up: Agent 5 touches 17 decision-inputs tables instead of one
`AgentScope`, so it gets its own module instead of bloating the router.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import (
    AgentReport,
    AgentRun,
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
from app.tenant_scope import scoped_query
from strategy_synthesis import compute
from strategy_synthesis.agent import StrategySynthesisAgent
from strategy_synthesis.brief import (
    DecisionBrief,
    Objective,
    PriorCandidate,
    ProductFleetItem,
    ProposedProject as BriefProposedProject,
)
from strategy_synthesis.config import Settings as AgentSettings
from strategy_synthesis.schemas import Pass1Candidate

logger = logging.getLogger(__name__)

AGENT_TYPE = "strategy-synthesis"

# Market Insights alone runs ~120KB across nine reports (agent5_build_briefing.md).
# Past this, one upstream agent's report pack is summarized before Pass 1 sees it.
UPSTREAM_SUMMARIZE_THRESHOLD_CHARS = 150_000

# The background task can't use the request-scoped session (closed by the
# time the task runs) -- same reason market_insights.py opens its own.
SessionFactory = SessionLocal


# ---------------------------------------------------------------------------
# Fiscal year default
# ---------------------------------------------------------------------------


class AmbiguousFiscalYearError(Exception):
    """Raised when no fiscal_year is given and capacity data spans more than
    one -- guessing which year to analyze would silently run the bottleneck
    analysis against the wrong one, exactly the failure this platform exists
    to prevent."""

    def __init__(self, candidates: list[str]):
        self.candidates = candidates
        super().__init__(f"Multiple fiscal years in capacity data: {', '.join(candidates)}. Specify fiscal_year.")


def _date_derived_fiscal_year(config: StrategyConfig | None, today: date) -> str:
    """Fallback used only when there's no capacity data yet to read a real
    fiscal year label from -- harmless at that point, since no bottleneck
    analysis is possible either way (see agent5_decision_inputs_brief_spec.md,
    "Consequence if absent: no funding line"). Labels by the calendar year
    the fiscal year *starts* in -- the simpler of two common conventions,
    chosen because guessing which convention a customer with a non-January
    start month actually uses would be worse than being explicit about the
    rule applied."""
    start_month = config.fiscal_year_start_month if config else 1
    label_format = config.fiscal_year_label_format if config else "FY{yy}"
    fy_start_year = today.year if today.month >= start_month else today.year - 1
    yy = str(fy_start_year)[-2:]
    try:
        return label_format.format(yy=yy)
    except (KeyError, IndexError):
        return f"FY{yy}"


def default_fiscal_year(db: Session, tenant: Tenant, config: StrategyConfig | None) -> str:
    capacity_years = {r.fiscal_year for r in scoped_query(db, CapacityRow, tenant).all()}
    if len(capacity_years) == 1:
        return next(iter(capacity_years))
    if len(capacity_years) > 1:
        raise AmbiguousFiscalYearError(sorted(capacity_years))
    return _date_derived_fiscal_year(config, datetime.now(timezone.utc).date())


# ---------------------------------------------------------------------------
# Readiness
# ---------------------------------------------------------------------------


def compute_readiness(db: Session, tenant: Tenant, fiscal_year: str | None) -> list[dict]:
    """What's missing and what it costs -- consequence text taken verbatim
    from agent5_decision_inputs_brief_spec.md's completeness table, so the
    UI never has to show a bare 'missing' badge. A run is never blocked by
    any of this."""

    def _item(name: str, is_set: bool, consequence: str) -> dict:
        # consequence describes what's missing -- irrelevant, and
        # contradictory, once the item is actually set.
        return {"item": name, "status": "set" if is_set else "missing", "consequence": "" if is_set else consequence}

    capacity_q = scoped_query(db, CapacityRow, tenant)
    if fiscal_year:
        capacity_q = capacity_q.filter(CapacityRow.fiscal_year == fiscal_year)

    return [
        _item(
            "Objectives", scoped_query(db, StrategicObjective, tenant).first() is not None,
            "Strategic alignment scored from evidence at reduced confidence; no objective coverage analysis.",
        ),
        _item(
            "Products / installed base", scoped_query(db, ProductFleetRow, tenant).first() is not None,
            "RICE unavailable; revenue scored qualitatively.",
        ),
        _item(
            "Capacity", capacity_q.first() is not None,
            "No funding line, no bottleneck analysis -- the single most consequential omission.",
        ),
        _item(
            "Effort bands", scoped_query(db, EffortBand, tenant).first() is not None,
            "Effort reported in raw units only.",
        ),
        _item(
            "Dependencies", scoped_query(db, ProjectDependency, tenant).first() is not None,
            "Inferred and flagged for confirmation.",
        ),
        _item(
            "Financials", scoped_query(db, ProjectFinancialsRow, tenant).first() is not None,
            "No financial column.",
        ),
        _item(
            "Framework",
            scoped_query(db, PrioritizationFramework, tenant)
            .filter(PrioritizationFramework.run_id.is_(None)).first() is not None,
            "Defaults to value vs effort, stated.",
        ),
        _item(
            "Scenarios", scoped_query(db, ScenarioRow, tenant).first() is not None,
            "Base case only.",
        ),
    ]


# ---------------------------------------------------------------------------
# Upstream selection and loading
# ---------------------------------------------------------------------------


def _discover_upstream_agent_types(db: Session, tenant: Tenant) -> set[str]:
    rows = (
        db.query(AgentRun.agent_type)
        .filter(AgentRun.tenant_id == tenant.id, AgentRun.agent_type != AGENT_TYPE)
        .distinct()
        .all()
    )
    return {r[0] for r in rows}


def _most_recent_successful_run_id(db: Session, tenant: Tenant, agent_type: str) -> str | None:
    run = (
        scoped_query(db, AgentRun, tenant)
        .filter(AgentRun.agent_type == agent_type, AgentRun.status == "succeeded")
        .order_by(AgentRun.created_at.desc())
        .first()
    )
    return run.id if run else None


def load_upstream_text(
    db: Session,
    tenant: Tenant,
    agent: StrategySynthesisAgent,
    overrides: dict[str, str] | None,
) -> dict[str, str]:
    """One agent's full report-pack text at a time, cursor-iterated -- never
    all upstream agents' content held in memory simultaneously. Summarizes
    (via `agent.summarize_upstream_agent`, an LLM call) only the agents whose
    pack exceeds the threshold; this function only decides *when* to call it,
    per strategy_synthesis/agent.py's own division of responsibility."""
    overrides = overrides or {}
    result: dict[str, str] = {}
    for agent_type in _discover_upstream_agent_types(db, tenant):
        run_id = overrides.get(agent_type) or _most_recent_successful_run_id(db, tenant, agent_type)
        if run_id is None:
            continue

        chunks: list[str] = []
        total_chars = 0
        reports = (
            scoped_query(db, AgentReport, tenant)
            .filter(AgentReport.run_id == run_id)
            .order_by(AgentReport.report_number.asc())
        )
        for report in reports.yield_per(1):
            chunks.append(report.content)
            total_chars += len(report.content)
        text = "\n\n".join(chunks)

        if total_chars > UPSTREAM_SUMMARIZE_THRESHOLD_CHARS:
            summarized = agent.summarize_upstream_agent(agent_type, text)
            text = (
                f"[Note: this agent's {total_chars:,}-character report pack was "
                f"summarized before analysis.]\n\n{summarized}"
            )
        result[agent_type] = text
    return result


# ---------------------------------------------------------------------------
# Brief assembly
# ---------------------------------------------------------------------------

# "Default when unselected: value vs effort" (agent5_decision_inputs_brief_spec.md
# Section 7). compute.py has no separate RICE/WSJF/Kano algorithm -- every
# framework reduces to criteria+weights, so this default just supplies a
# plausible pair rather than leaving weights empty.
DEFAULT_FRAMEWORK_NAME = "value_vs_effort"
DEFAULT_FRAMEWORK_WEIGHTS = {"value": 0.5, "effort": 0.5}


def load_framework_weights(db: Session, tenant: Tenant) -> tuple[str, dict[str, float]]:
    """The tenant's current default (run_id IS NULL) framework name and its
    declared criterion weights, as fractions summing to 1.0 -- or the
    value-vs-effort default when nothing has been configured yet."""
    framework_row = (
        scoped_query(db, PrioritizationFramework, tenant)
        .filter(PrioritizationFramework.run_id.is_(None))
        .order_by(PrioritizationFramework.updated_at.desc())
        .first()
    )
    if framework_row is None:
        return DEFAULT_FRAMEWORK_NAME, dict(DEFAULT_FRAMEWORK_WEIGHTS)
    criteria = scoped_query(db, PrioritizationCriterion, tenant).filter(
        PrioritizationCriterion.framework_id == framework_row.id
    ).all()
    return framework_row.framework, {c.criterion: c.weight for c in criteria}


def assemble_brief(db: Session, tenant: Tenant, fiscal_year: str) -> DecisionBrief:
    config = scoped_query(db, StrategyConfig, tenant).first()

    buckets = [
        compute.Bucket(bucket_key=b.bucket_key, bucket_name=b.bucket_name, contractable=b.contractable)
        for b in scoped_query(db, CapacityBucket, tenant).all()
    ]
    capacity = [
        compute.Capacity(
            fiscal_year=c.fiscal_year, bucket_key=c.bucket_key, capacity_units=c.capacity_units, budget=c.budget
        )
        for c in scoped_query(db, CapacityRow, tenant).all()
    ]
    projects = [
        compute.Project(
            project_key=p.project_key,
            name=p.name,
            mandatory=p.mandatory,
            mandatory_driver=p.mandatory_driver,
            mandatory_deadline=p.mandatory_deadline,
        )
        for p in scoped_query(db, PortfolioProject, tenant).all()
    ]
    project_effort = [
        compute.ProjectEffort(
            project_key=e.project_key,
            bucket_key=e.bucket_key,
            effort_remaining=e.effort_remaining,
            effort_total=e.effort_total,
        )
        for e in scoped_query(db, ProjectEffortRow, tenant).all()
    ]
    dependencies = [
        compute.Dependency(
            project_key=d.project_key,
            depends_on=d.depends_on_key,
            dependency_type=d.dependency_type,
            source="customer",
            note=d.note,
        )
        for d in scoped_query(db, ProjectDependency, tenant).all()
    ]
    financials = [
        compute.ProjectFinancials(
            project_key=f.project_key,
            revenue_impact=f.revenue_impact,
            capex=f.capex,
            opex_annual=f.opex_annual,
            discount_rate=f.discount_rate,
        )
        for f in scoped_query(db, ProjectFinancialsRow, tenant).all()
    ]
    objectives = [
        Objective(key=o.objective_key, text=o.text, horizon=o.horizon, owner=o.owner, measure=o.measure)
        for o in scoped_query(db, StrategicObjective, tenant).all()
    ]
    products_fleet = [
        ProductFleetItem(
            product_key=p.product_key, product=p.product, platform=p.platform, platform_class=p.platform_class,
            units_in_service=p.units_in_service, avg_age_years=p.avg_age_years, status=p.status, region=p.region,
        )
        for p in scoped_query(db, ProductFleetRow, tenant).all()
    ]
    proposed_projects = [
        BriefProposedProject(
            key=u.project_key, name=u.name, proposed_by=u.proposed_by,
            description=u.description, rationale=u.rationale,
        )
        for u in scoped_query(db, ProposedProject, tenant).all()
    ]
    prior_candidates = [
        PriorCandidate(key=c.candidate_key, name=c.name, status=c.status, dismissal_reason=c.dismissal_reason)
        for c in scoped_query(db, DiscoveredCandidate, tenant).all()
    ]

    framework_name, weights = load_framework_weights(db, tenant)

    # ScenarioWeight rows are per-criterion overrides (see its docstring in
    # app/models.py), not a standalone weight set -- a scenario that leaves a
    # criterion unmentioned inherits the framework's declared weight for it.
    # A scenario named "Base" with no rows at all (weights: []) means
    # "use the framework's weights unchanged", which this merge gives for
    # free: base weights overridden by an empty dict is just the base weights.
    scenario_rows = scoped_query(db, ScenarioRow, tenant).all()
    scenarios = []
    for s in scenario_rows:
        weight_rows = scoped_query(db, ScenarioWeight, tenant).filter(ScenarioWeight.scenario_id == s.id).all()
        overrides = {w.criterion: w.weight for w in weight_rows}
        scenarios.append(compute.Scenario(name=s.name, weights={**weights, **overrides}))

    rules = [r.value or r.rule_type for r in scoped_query(db, StrategyRule, tenant).all()]

    return DecisionBrief(
        fiscal_year=fiscal_year,
        effort_unit=config.effort_unit if config else "weeks",
        objectives=objectives,
        buckets=buckets,
        capacity=capacity,
        projects=projects,
        project_effort=project_effort,
        dependencies=dependencies,
        financials=financials,
        products_fleet=products_fleet,
        proposed_projects=proposed_projects,
        prior_candidates=prior_candidates,
        framework_name=framework_name,
        weights=weights,
        scenarios=scenarios,
        rules=rules,
    )


# ---------------------------------------------------------------------------
# Candidate persistence
# ---------------------------------------------------------------------------


def persist_candidates(
    db: Session, tenant: Tenant, run: AgentRun, candidates: list[Pass1Candidate]
) -> None:
    """A dismissed candidate is never resurrected as new: only a
    `candidate_key` this tenant has never seen before gets `status="new"`.
    An existing key's `status`/`dismissal_reason` are never assigned here --
    only its evidence fields refresh."""
    existing = {c.candidate_key: c for c in scoped_query(db, DiscoveredCandidate, tenant).all()}
    for candidate in candidates:
        row = existing.get(candidate.key)
        citations = [c.model_dump() for c in candidate.source_citations]
        if row is None:
            db.add(
                DiscoveredCandidate(
                    tenant_id=tenant.id,
                    candidate_key=candidate.key,
                    name=candidate.name,
                    origin=candidate.origin,
                    problem_addressed=candidate.problem,
                    evidence_summary=candidate.evidence_summary,
                    support_classification=candidate.support_classification,
                    source_citations=citations,
                    first_seen_run_id=run.id,
                    status="new",
                )
            )
        else:
            row.name = candidate.name
            row.origin = candidate.origin
            row.problem_addressed = candidate.problem
            row.evidence_summary = candidate.evidence_summary
            row.support_classification = candidate.support_classification
            row.source_citations = citations


# ---------------------------------------------------------------------------
# Run execution
# ---------------------------------------------------------------------------


def execute_run(
    *,
    run_id: str,
    fiscal_year: str,
    upstream_run_overrides: dict[str, str] | None,
    model: str | None,
) -> None:
    db = SessionFactory()
    try:
        run = db.get(AgentRun, run_id)
        if run is None:  # deleted between scheduling and execution
            return
        tenant = db.get(Tenant, run.tenant_id)
        run.status = "running"
        db.commit()

        try:
            settings = AgentSettings.load(model_override=model)
            agent = StrategySynthesisAgent(settings)

            brief = assemble_brief(db, tenant, fiscal_year)
            upstream_text_by_agent = load_upstream_text(db, tenant, agent, upstream_run_overrides)

            result = agent.run(brief, upstream_text_by_agent)

            for report in result.reports:
                db.add(
                    AgentReport(
                        tenant_id=run.tenant_id,
                        run_id=run.id,
                        report_number=report.report_number,
                        title=report.title,
                        content=report.content,
                    )
                )
            persist_candidates(db, tenant, run, result.pass1_output.candidates)

            run.status = "succeeded"
            run.error = None
            db.commit()
        except Exception as exc:  # noqa: BLE001 -- any failure must land on the run row
            logger.exception("Strategy Synthesis run %s failed", run_id)
            db.rollback()
            run = db.get(AgentRun, run_id)
            if run is not None:
                run.status = "failed"
                run.error = f"{type(exc).__name__}: {exc}"[:2000]
                db.commit()
    finally:
        db.close()
