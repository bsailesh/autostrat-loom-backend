"""
Voice of Customer Agent (Agent 1).

Independent of app/, like the other agent packages: no database, no
FastAPI. The service layer (app/voice_of_customer_service.py) assembles a
`CustomerContext` from the voc_* tables, renders the evidence through
`evidence.py` from database cursors, and calls `VoiceOfCustomerAgent.run()`.

This agent emits no candidate work. Its contribution downstream is textual:
the evidence that lets Agent 5 score `customer_value` from customer data
rather than market-level substitution, and a "Findings for synthesis"
section in Report 1 that Agent 5 carries verbatim into its decision brief.
"""

from voice_of_customer.agent import AgentRunResult, Report, ReportStructureError, Source, VoiceOfCustomerAgent
from voice_of_customer.context import (
    TIER_1_PARTIAL,
    TIER_1_SUBSTANTIAL,
    TIER_2,
    CustomerContext,
    operating_tier,
    operating_tier_statement,
    report_title,
)
from voice_of_customer.reports import FINDINGS_FOR_SYNTHESIS_HEADING, REPORTS, ReportSpec

__all__ = [
    "AgentRunResult",
    "Report",
    "ReportStructureError",
    "Source",
    "VoiceOfCustomerAgent",
    "TIER_1_PARTIAL",
    "TIER_1_SUBSTANTIAL",
    "TIER_2",
    "CustomerContext",
    "operating_tier",
    "operating_tier_statement",
    "report_title",
    "FINDINGS_FOR_SYNTHESIS_HEADING",
    "REPORTS",
    "ReportSpec",
]
