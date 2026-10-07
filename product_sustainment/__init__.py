"""
Product Sustainment Agent (Agent 4).

Independent of app/, like the other agent packages: no database, no
FastAPI. The service layer (app/product_sustainment_service.py) assembles a
`SustainmentData` from the ps_* tables and calls
`ProductSustainmentAgent.run()`.

The one structural agent besides Agent 5 to have a deterministic compute
module: `compute.py` treats the BOM as two matrices and sums demand across
every path. Its contribution downstream is structured candidate work --
dated runouts with quantities and every affected LRU -- which Agent 5 reads
from ps_candidate_work directly.
"""

from product_sustainment.agent import (
    AgentRunResult,
    CandidateWorkError,
    DroppedCandidateWork,
    ProductSustainmentAgent,
    Report,
)
from product_sustainment.reports import REPORTS, ReportSpec

__all__ = [
    "AgentRunResult",
    "CandidateWorkError",
    "DroppedCandidateWork",
    "ProductSustainmentAgent",
    "Report",
    "REPORTS",
    "ReportSpec",
]
