"""
Voice of Customer Agent (Agent 1) — the nine reports.

Same 5-field ReportSpec shape as the other agents, declared locally rather
than imported.

**Nine, not ten.** Report 6 (the compiled Voice of Customer narrative)
restates Reports 1-5 and would double generation cost for a worse reader
experience. It is noted as deferred in Report 1 rather than silently
dropped -- see DEFERRED_REPORTS_NOTE. The remaining reports keep their spec
numbers, so this pack's numbering agrees with the spec that describes it.

**Exhibit contract.** As in Tech & Regulation: the model emits an ordinary
Markdown table with the exact header row below, and the frontend's
voiceOfCustomer exhibit registry claims it by matching that header, falling
back to a themed table when it cannot. No ASCII art, ever.

**Findings for synthesis** is a section of Report 1 with an exact heading,
because Agent 5 extracts it by that heading and carries it verbatim into
its decision brief. Changing FINDINGS_FOR_SYNTHESIS_HEADING is a breaking
change for app/strategy_synthesis_service.py.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReportSpec:
    number: int
    title: str
    opening: str  # "scqa" | "key_insights"
    must_include: str
    exhibit: str


FINDINGS_FOR_SYNTHESIS_HEADING = "## Findings for synthesis"
BELIEF_TESTING_HEADING = "## Testing your stated beliefs"

# ---------------------------------------------------------------------------
# Exhibit table contracts -- the header rows the renderers match on.
# Changing one is a breaking change for frontend/src/voiceOfCustomer/exhibits/.
# ---------------------------------------------------------------------------

BELIEF_TESTING_TABLE_HEADERS = "| Belief | Segment | Outcome | Evidence | Confidence |"

PAIN_POINT_TABLE_HEADERS = "| Pain point | Segment | Severity | Frequency | Composite | Frequency basis |"

OPPORTUNITY_MAP_TABLE_HEADERS = "| Opportunity | Impact | Effort | Effort basis | Confidence |"

SWOT_TABLE_HEADERS = "| Quadrant | Statement | Evidence | Business impact | Confidence |"

HARVEY_BALL_FIRST_HEADER = "Feature"
CELL_EVIDENCE_TABLE_HEADERS = "| Vendor | Feature | Rating | Evidence | Source |"

INSIGHTS_MATRIX_TABLE_HEADERS = "| Audience | Quadrant | Entry | Evidence | Confidence |"

STEEP_TABLE_HEADERS = (
    "| Factor | Change | Evidence | Transmission path | Effect on customer expectations | Confidence |"
)


DEFERRED_REPORTS_NOTE = """\
One report from the source specification is deferred in this version, and is
named here rather than omitted silently:

- **Report 6 — Voice of Customer report.** The compiled narrative deliverable
  restates Reports 1–5. Producing the same content twice doubles generation cost
  for a worse reader experience, so it is deferred pending a decision on whether
  it is a distinct deliverable or a compiled export of Reports 1–5.
"""


REPORTS: list[ReportSpec] = [
    ReportSpec(
        number=1,
        title="Executive summary",
        opening="scqa",
        must_include=(
            "The operating-tier line first, then the Governing Insight. Then, in this order: "
            "a short '## Evidence used' section stating, once, how each evidence file was "
            "rendered (complete, or sampled and how) and what that means for any count or "
            "quotation in this pack -- or that no customer evidence was supplied; top customer "
            "concerns; key trends; strategic risks; strategic opportunities. Then a section "
            f"headed exactly '{BELIEF_TESTING_HEADING}' covering EVERY known pain point the "
            "customer stated, each with exactly one outcome: Corroborated, Contradicted, "
            "'Not found — no evidence supplied that could test it', or 'Not found — absent "
            "from the evidence supplied'. State a contradiction plainly and say what the "
            "evidence shows instead. If no beliefs were recorded, say that this analysis was "
            "unavailable and why it matters. Then a section headed exactly "
            f"'{FINDINGS_FOR_SYNTHESIS_HEADING}' -- short stand-alone paragraphs per the "
            "Findings for synthesis rules; present in every run, including Tier 2. Then "
            "'## Recommended actions': capped at what the evidence supports, with the count "
            "stated, never padded, each with a confidence -- and never a project proposal, "
            "candidate work or an effort estimate. Close with the deferred-reports note "
            "supplied in the prompt, verbatim."
        ),
        exhibit=(
            "Under the belief-testing heading, a table with exactly these headers: "
            f"{BELIEF_TESTING_TABLE_HEADERS} -- one row per stated belief."
        ),
    ),
    ReportSpec(
        number=2,
        title="Ranked customer pain points",
        opening="key_insights",
        must_include=(
            "A table: problem, affected customers by segment, frequency, severity, business "
            "impact, trend, confidence, recommended priority. Frequency only from counts -- "
            "say for each whether it is a count over all rows, a count in a declared sample, "
            "or an estimate from sampled verbatims. Where frequency is unavailable, rank by "
            "severity alone and say so. In a Tier 2 run, report pain points visible in public "
            "evidence UNRANKED by frequency and state that no counts exist."
        ),
        exhibit=(
            "A pain point chart table with exactly these headers: "
            f"{PAIN_POINT_TABLE_HEADERS} -- Severity is 1-5; Frequency is a number or 'n/a'; "
            "Composite is Severity × Frequency where Frequency is a number, otherwise Severity "
            "alone; Frequency basis is one of 'count, all rows', 'count, in the sample "
            "supplied', 'estimate, N of M sampled rows', 'unavailable'. Renders as a "
            "horizontal bar chart ranked by Composite."
        ),
    ),
    ReportSpec(
        number=3,
        title="Feature requests",
        opening="key_insights",
        must_include=(
            "A table: requested feature, segment, business value, competitive need, estimated "
            "impact, frequency, priority, confidence. Distinguish a broad need from a loud "
            "single customer. REQUIRES A REQUEST SOURCE (feature request logs, CRM notes, "
            "dealer feedback). Without one, report this section unavailable and name what "
            "would enable it -- never derive requests from competitor features, which would be "
            "inventing customer priorities."
        ),
        exhibit="A colour-coded table of requests against segment, frequency and confidence, where a source exists.",
    ),
    ReportSpec(
        number=4,
        title="Customer personas",
        opening="key_insights",
        must_include=(
            "Each persona: role, industry, goals, pain points, decision drivers, success "
            "metrics, buying criteria, product usage, support channels, technology adoption. "
            "Every persona states its evidence basis and how many distinct sources support it. "
            "Without visit or interview evidence, produce PERSONA HYPOTHESES TO VALIDATE, "
            "labelled as such in each heading, each with the specific question that would "
            "confirm or refute it. An invented persona is worse than nothing, because it will "
            "be quoted back as fact."
        ),
        exhibit="A persona comparison table: persona, role, segment, evidence basis, distinct sources, status (validated / hypothesis).",
    ),
    ReportSpec(
        number=5,
        title="Opportunity map",
        opening="key_insights",
        must_include=(
            "Per opportunity: customer value, business value, market growth, competitive "
            "differentiation, technical complexity, implementation difficulty, revenue "
            "potential, strategic alignment. STATE IN THE BODY: this agent has no engineering "
            "data; effort here is a relative public-evidence judgement, labelled `estimated`, "
            "and is NOT comparable to the effort figures in the customer's roadmap. No "
            "opportunity is a project proposal."
        ),
        exhibit=(
            "An impact vs effort table with exactly these headers: "
            f"{OPPORTUNITY_MAP_TABLE_HEADERS} -- Impact and Effort are numbers 1-10; Effort "
            "basis is 'estimated'. Renders as a 2×2 scatter."
        ),
    ),
    ReportSpec(
        number=7,
        title="SWOT",
        opening="key_insights",
        must_include=(
            "Four quadrants, tailored to technical capability. Strengths and weaknesses are "
            "internal and product-specific, not corporate strategy; opportunities and threats "
            "are external. Each entry: statement, evidence, business impact, confidence."
        ),
        exhibit=(
            "A SWOT table with exactly these headers: "
            f"{SWOT_TABLE_HEADERS} -- Quadrant is one of Strengths, Weaknesses, "
            "Opportunities, Threats. Renders as four quadrants."
        ),
    ),
    ReportSpec(
        number=8,
        title="Competitive feature comparison matrix",
        opening="key_insights",
        must_include=(
            "Per the competitor feature comparison rules: competitors identified from "
            "evidence, no cap on discovery; compare on performance, reliability, availability, "
            "ease of use, digital features, connected services, maintainability, warranty, "
            "safety, automation, efficiency, customer support, service network, "
            "differentiators. Below the grid, every excluded competitor with a one-line "
            "reason. Then the cell evidence, grouped by vendor, as a table -- only filled "
            "cells need rows. Mark which gaps customers actually mention in the evidence, as "
            "distinct from datasheet gaps."
        ),
        exhibit=(
            "A Harvey Ball grid as a Markdown table whose first header is exactly "
            f"'{HARVEY_BALL_FIRST_HEADER}', followed by the reference product and up to 5 "
            "competitors (6 columns maximum), each cell one of ● ◕ ◑ ◔ ○ —. Legend: ● full / "
            "◕ strong / ◑ partial / ◔ limited / ○ none / — undisclosed. Then the cell "
            f"evidence table with exactly these headers: {CELL_EVIDENCE_TABLE_HEADERS}."
        ),
    ),
    ReportSpec(
        number=9,
        title="STEEP analysis",
        opening="key_insights",
        must_include=(
            "Social, technological, economic, environmental, political. Each factor: the "
            "change, its evidence, its transmission path into the industry, its effect on "
            "customer expectations. Keep STEEP structural; the external forces analysis "
            "elsewhere is customer-expectation focused -- do not restate the same findings in "
            "both. Never generic commentary."
        ),
        exhibit=f"A STEEP table with exactly these headers: {STEEP_TABLE_HEADERS}.",
    ),
    ReportSpec(
        number=10,
        title="Customer insights matrix",
        opening="key_insights",
        must_include=(
            "Existing customers: firmographics, buyer persona, pain points and triggers, "
            "jobs-to-be-done, and unsolved market gaps. Adjacent customers: the same "
            "structure, looking beyond the current customer category -- globally, and at "
            "anyone sharing the same jobs-to-be-done. Where a quadrant cannot be evidenced, "
            "say so in it rather than filling it."
        ),
        exhibit=(
            "An insights matrix table with exactly these headers: "
            f"{INSIGHTS_MATRIX_TABLE_HEADERS} -- Audience is 'Existing customers' or "
            "'Adjacent customers'; Quadrant is one of Firmographics, Buyer persona, Pain points "
            "and triggers, Jobs-to-be-done, Unsolved market gaps. Renders as quadrants with a "
            "full-width gaps callout."
        ),
    ),
]
