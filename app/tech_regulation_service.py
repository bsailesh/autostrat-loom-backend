"""
Technology & Regulatory Intelligence (Agent 3) service layer.

The boundary this file exists to hold: `tech_regulation/` never sees a
database session, exactly as `market_insights/` and `strategy_synthesis/`
never do. So envelope assembly from the tr_* tables, candidate-work
persistence, and background run execution live here, while the operating
state, degradation consequences and prompt rendering live in
`tech_regulation/scoping.py` where they can be tested without a DB.

Mirrors app/strategy_synthesis_service.py's division of labour
(assemble_brief / persist_candidates / execute_run) rather than inventing a
new one.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.database import SessionLocal
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
from app.tenant_scope import scoped_query

from tech_regulation import TechRegulationAgent
from tech_regulation.config import Settings as AgentSettings
from tech_regulation.schemas import CandidateWorkItem
from tech_regulation.scoping import (
    CertificationBasis,
    Exclusion,
    Jurisdiction,
    Platform,
    ProductCategory,
    ScopeItem,
    ScopingEnvelope,
    StandardHeld,
    Supplier,
    operating_state,
    scope_items,
)

logger = logging.getLogger(__name__)

AGENT_TYPE = "tech-regulation"

# The background task can't use the request-scoped session (it's closed by
# the time the task runs), so it opens its own. Held at module level so tests
# can point it at their in-memory database -- same as the other two agents.
SessionFactory = SessionLocal


# ---------------------------------------------------------------------------
# Envelope assembly
# ---------------------------------------------------------------------------


def assemble_envelope(db: Session, tenant: Tenant) -> ScopingEnvelope:
    """Read the eight tr_* scoping tables into the plain-data envelope the
    agent package takes. Customer vocabulary is carried across verbatim --
    no normalising of category keys, basis identifiers or platform names,
    because the agent quotes them back and the customer has to recognise
    them."""

    def rows(model, order_by):
        return scoped_query(db, model, tenant).order_by(order_by).all()

    return ScopingEnvelope(
        categories=[
            ProductCategory(
                category_key=r.category_key,
                category_name=r.category_name,
                description=r.description,
            )
            for r in rows(TrProductCategory, TrProductCategory.category_key.asc())
        ],
        jurisdictions=[
            Jurisdiction(jurisdiction=r.jurisdiction, role=r.role)
            for r in rows(TrJurisdiction, TrJurisdiction.jurisdiction.asc())
        ],
        certification_basis=[
            CertificationBasis(
                category_key=r.category_key,
                basis_type=r.basis_type,
                basis_identifier=r.basis_identifier,
                status=r.status,
                held_since=r.held_since,
            )
            for r in rows(TrCertificationBasis, TrCertificationBasis.category_key.asc())
        ],
        platforms=[
            Platform(
                platform=r.platform,
                platform_class=r.platform_class,
                relationship=r.relationship,
                programme_status=r.programme_status,
            )
            for r in rows(TrPlatform, TrPlatform.platform.asc())
        ],
        standards_held=[
            StandardHeld(
                standard_id=r.standard_id, revision=r.revision, scope=r.scope, status=r.status
            )
            for r in rows(TrStandardHeld, TrStandardHeld.standard_id.asc())
        ],
        suppliers=[
            Supplier(
                supplier=r.supplier,
                what_they_supply=r.what_they_supply,
                criticality=r.criticality,
            )
            for r in rows(TrSupplier, TrSupplier.supplier.asc())
        ],
        domains=[r.domain for r in rows(TrDomain, TrDomain.domain.asc())],
        exclusions=[
            Exclusion(exclusion_type=r.exclusion_type, value=r.value, reason=r.reason)
            for r in rows(TrExclusion, TrExclusion.exclusion_type.asc())
        ],
        # Tier 1 evidence ingestion is not built for this agent yet; the
        # envelope carries the field so the agent can state which documents
        # were supplied, and today the honest answer is none.
        tier1_evidence_supplied=[],
    )


def compute_scope_state(db: Session, tenant: Tenant) -> tuple[str, list[ScopeItem]]:
    """The operating state and the per-dimension status/consequence list.

    Returns `scope_items()`' output unchanged. The consequence text is
    already empty for every item that is set, and this layer must not
    recompute or re-attach it: showing a dimension's missing-case warning
    next to a dimension that is actually populated is the exact bug that
    shipped on Agent 5's /readiness and had to be fixed in b4f3282."""
    envelope = assemble_envelope(db, tenant)
    return operating_state(envelope), scope_items(envelope)


def compose_subject(envelope: ScopingEnvelope) -> str:
    """The run's scope snapshot, frozen at run time -- used on the export
    cover page and in the export filename, so it must not be re-derived from
    the possibly-since-edited envelope."""
    categories = ", ".join(c.category_name for c in envelope.categories[:3]) or "no product categories"
    if len(envelope.categories) > 3:
        categories += f" (+{len(envelope.categories) - 3} more)"
    jurisdictions = ", ".join(j.jurisdiction for j in envelope.jurisdictions[:3]) or "no jurisdictions"
    return f"{categories} — {jurisdictions} — {operating_state(envelope)}"


# ---------------------------------------------------------------------------
# Candidate work persistence
# ---------------------------------------------------------------------------


def persist_candidate_work(
    db: Session, tenant: Tenant, run: AgentRun, items: list[CandidateWorkItem]
) -> None:
    """Additive, keyed by candidate_key, mirroring persist_candidates for
    DiscoveredCandidate.

    A re-run refreshes the evidence fields on an existing key -- which is how
    a corrected effective date propagates, and why Agent 5's linked candidate
    stores no copy of it -- but never touches `status` or
    `dismissal_reason`. A dismissed item re-surfaced by a later run stays
    dismissed; it is not resurrected as new.

    `last_seen_run_id` is set on every appearance. Agent 5 reads the
    candidate work *for an upstream run*, so an item this run re-surfaced has
    to be attributable to it, not only to the run that first found it."""
    existing = {
        row.candidate_key: row
        for row in scoped_query(db, TrCandidateWork, tenant).all()
    }

    for item in items:
        row = existing.get(item.candidate_key)
        applicability = item.applicability.model_dump()

        if row is None:
            db.add(
                TrCandidateWork(
                    tenant_id=tenant.id,
                    candidate_key=item.candidate_key,
                    driver=item.driver,
                    work_date=item.work_date,
                    date_basis=item.date_basis,
                    date_absent_reason=item.date_absent_reason,
                    applicability=applicability,
                    work_implied=item.work_implied,
                    work_implied_description=item.work_implied_description,
                    platform_relationship=item.platform_relationship,
                    classification=item.classification,
                    confidence=item.confidence,
                    source=item.source,
                    source_date=item.source_date,
                    status="new",
                    first_seen_run_id=run.id,
                    last_seen_run_id=run.id,
                )
            )
            continue

        # Evidence fields refresh; triage fields do not.
        row.driver = item.driver
        row.work_date = item.work_date
        row.date_basis = item.date_basis
        row.date_absent_reason = item.date_absent_reason
        row.applicability = applicability
        row.work_implied = item.work_implied
        row.work_implied_description = item.work_implied_description
        row.platform_relationship = item.platform_relationship
        row.classification = item.classification
        row.confidence = item.confidence
        row.source = item.source
        row.source_date = item.source_date
        row.last_seen_run_id = run.id


def load_candidate_work_for_run(
    db: Session, tenant: Tenant, run_id: str
) -> list[TrCandidateWork]:
    """The candidate work attributable to one run -- items it discovered and
    items it re-surfaced. This is what Agent 5 reads (stage 4)."""
    return (
        scoped_query(db, TrCandidateWork, tenant)
        .filter(TrCandidateWork.last_seen_run_id == run_id)
        .order_by(TrCandidateWork.candidate_key.asc())
        .all()
    )


# ---------------------------------------------------------------------------
# Run execution
# ---------------------------------------------------------------------------


def execute_run(
    *,
    run_id: str,
    model: str | None,
    max_searches: int | None,
    research_rounds: int | None,
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
            agent = TechRegulationAgent(settings)

            envelope = assemble_envelope(db, tenant)
            run_kwargs: dict = {}
            if max_searches is not None:
                run_kwargs["max_searches"] = max_searches
            if research_rounds is not None:
                run_kwargs["research_rounds"] = research_rounds

            result = agent.run(envelope, **run_kwargs)

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

            # Persisted from the validated objects, never parsed back out of
            # the report prose written above. That ordering is the whole
            # reason Agent 5's read of this table is parse-free.
            persist_candidate_work(db, tenant, run, result.candidate_work)

            if result.candidate_work_dropped:
                logger.warning(
                    "Tech & Regulation run %s dropped %d incomplete candidate work item(s): %s",
                    run_id,
                    len(result.candidate_work_dropped),
                    "; ".join(
                        f"{d.candidate_key}: {', '.join(d.gaps)}"
                        for d in result.candidate_work_dropped
                    ),
                )

            run.status = "succeeded"
            run.error = None
            db.commit()
        except Exception as exc:  # noqa: BLE001 -- any failure must land on the run row
            logger.exception("Tech & Regulation run %s failed", run_id)
            db.rollback()
            run = db.get(AgentRun, run_id)
            if run is not None:
                run.status = "failed"
                run.error = f"{type(exc).__name__}: {exc}"[:2000]
                db.commit()
    finally:
        db.close()
