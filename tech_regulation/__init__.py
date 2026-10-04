"""
Technology & Regulatory Intelligence Agent (Agent 3).

Independent of app/, like market_insights/ and strategy_synthesis/: no
database, no FastAPI. `agent.py`'s `TechRegulationAgent.run()` takes an
assembled `ScopingEnvelope` (scoping.py) and returns an `AgentRunResult`
whose `candidate_work` is already structured and validated. The service
layer assembles the envelope from the tr_* tables and persists the result,
exactly as `app/strategy_synthesis_service.py` does for Agent 5's
DecisionBrief.

The agent's main contribution downstream is `candidate_work`: structured
rows with driver, date, applicability, work implied and evidence basis,
which Agent 5 reads directly rather than parsing out of report prose.
"""

from tech_regulation.agent import (
    AgentRunResult,
    CandidateWorkError,
    DroppedCandidateWork,
    Report,
    Source,
    TechRegulationAgent,
)
from tech_regulation.reports import REPORTS, ReportSpec
from tech_regulation.schemas import (
    CandidateWorkApplicability,
    CandidateWorkItem,
    CandidateWorkOutput,
)
from tech_regulation.scoping import (
    PARTIALLY_SCOPED,
    SCOPED,
    UNSCOPED,
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
    operating_state_statement,
    render_envelope_text,
    report_title,
    scope_items,
)
from tech_regulation.validation import candidate_work_gaps, partition_candidate_work

__all__ = [
    "AgentRunResult",
    "CandidateWorkError",
    "DroppedCandidateWork",
    "Report",
    "Source",
    "TechRegulationAgent",
    "REPORTS",
    "ReportSpec",
    "CandidateWorkApplicability",
    "CandidateWorkItem",
    "CandidateWorkOutput",
    "SCOPED",
    "PARTIALLY_SCOPED",
    "UNSCOPED",
    "CertificationBasis",
    "Exclusion",
    "Jurisdiction",
    "Platform",
    "ProductCategory",
    "ScopeItem",
    "ScopingEnvelope",
    "StandardHeld",
    "Supplier",
    "operating_state",
    "operating_state_statement",
    "render_envelope_text",
    "report_title",
    "scope_items",
    "candidate_work_gaps",
    "partition_candidate_work",
]
