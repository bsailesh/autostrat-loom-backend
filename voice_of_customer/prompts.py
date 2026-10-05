"""
Voice of Customer Agent (Agent 1) — prompt assembly.

Same interpolation pattern as the other agents (standards.X under its own
heading, f-strings, no templating library). Two prompt families:

  research_*   — live web search for the public side: external forces,
                 STEEP, competitors, market-level demand. Never sees the
                 customer evidence or the named customers -- nothing
                 confidential goes into a search query.
  synthesis_*  — one streamed call per report. The context, the evidence
                 and the research brief are identical across all nine calls,
                 so they form one cached prefix (`synthesis_shared_block`)
                 and only the short per-report instruction differs.

There is no structured extraction phase, unlike Tech & Regulation: this
agent emits no candidate work.
"""
from __future__ import annotations

from voice_of_customer import standards
from voice_of_customer.reports import DEFERRED_REPORTS_NOTE, ReportSpec

_SHARED_IDENTITY = f"""\
{standards.ROLE}

{standards.DO_NOT_INVENT}

{standards.OPERATING_TIER_RULES}
"""


# ---------------------------------------------------------------------------
# Research
# ---------------------------------------------------------------------------

RESEARCH_SYSTEM_PROMPT = f"""\
{_SHARED_IDENTITY}
{standards.EVIDENCE_AND_CONFIDENCE_STANDARD}

{standards.TIME_HORIZON}

{standards.REQUIRED_ANALYSES}

You are in the RESEARCH phase. Use web search to gather PUBLIC evidence only.
Customer evidence, where any exists, is supplied separately at the next phase and
is not your concern here. Do not write reports yet.

Output evidence rows: each with its observation, source, source type,
publication date, observation date, confidence, and its
FACT/OBSERVATION/INTERPRETATION/FORECAST/UNKNOWN classification.

Group rows under these headings: external forces (political, economic, social,
technological, environmental, regulatory, supply chain, industry consolidation)
with transmission paths; emerging trends; market-level customer demand; public
segment structure; competitors and their disclosed features; public customer
commentary (reviews, trade press, forums, procurement statements) bearing on
the stated product categories and on the customer's stated beliefs."""


def research_user_prompt(context_text: str) -> str:
    return f"""\
## Customer context (named customers withheld from this phase)

{context_text}

## Your task

Research the public evidence around this customer's markets and products.

Priorities, in order:
1. Public evidence bearing on each known pain point listed above -- for or
   against. Public evidence cannot corroborate a belief about THIS customer's
   customers, but it can show whether the problem is industry-wide.
2. External forces changing what these segments expect, with the transmission
   path into the industry and its dates.
3. The significant competitors in these product categories, identified from
   evidence, and their publicly disclosed features.
4. Market-level demand and segment structure from public sources.
5. Emerging trends, distinguishing current from emerging.

Never generic commentary. Every row carries data, source and date."""


RESEARCH_FOLLOWUP_PROMPT = (
    "Now review what you have gathered. Identify the 3-4 weakest or thinnest areas "
    "(least evidence, stalest sources, unresolved contradictions, competitor cells "
    "with no disclosure found) and run additional web searches to strengthen them. "
    "Then output ONLY the new or revised evidence rows, grouped under the same "
    "headings. If an area genuinely has no more public evidence, say so explicitly."
)


# ---------------------------------------------------------------------------
# Synthesis, one call per report
# ---------------------------------------------------------------------------


def synthesis_system_prompt() -> str:
    return f"""\
{_SHARED_IDENTITY}
{standards.ATTRIBUTION_AND_CONFIDENTIALITY}

{standards.SAMPLE_AND_VERBATIM_RULES}

{standards.BELIEF_TESTING}

{standards.REQUIRED_ANALYSES}

{standards.FINDINGS_FOR_SYNTHESIS}

{standards.WHAT_AGENT_5_MUST_NOT_RECEIVE}

{standards.EVIDENCE_AND_CONFIDENCE_STANDARD}

{standards.CONSULTING_GRADE_OUTPUT_STANDARD}

{standards.TIME_HORIZON}

{standards.MONITORING_ABSENCE}

{standards.COLOR_SEMANTICS}

You are in the SYNTHESIS phase. Write the one report requested at the end of the
user message as Markdown, drawing only on the customer context, the customer
evidence and the research brief supplied -- no new research.

Customer evidence outranks public evidence on anything about this customer's
customers. Public evidence is used for external forces and competitive context,
and for the market-level picture where customer evidence is absent -- labelled
as market-level whenever it is.

Write the report body only. Do not restate the "# Report N — Title" heading."""


def synthesis_shared_block(
    operating_tier_line: str, context_text: str, evidence_text: str, research_brief: str
) -> str:
    """Identical across all nine report calls -- sent as one cached prefix."""
    return f"""\
## Operating tier line (the first line of every report, verbatim)

{operating_tier_line}

## Customer context

{context_text}

## Customer evidence

{evidence_text}

## Research brief (public evidence)

{research_brief}"""


def _opening_instruction(spec: ReportSpec) -> str:
    if spec.opening == "scqa":
        return (
            "Open with the operating-tier line given above, verbatim and on its own. Then a "
            "level-2 heading exactly '## Governing Insight', followed by Situation / "
            "Complication / Question / Answer -- the Answer being a claim about what the "
            "evidence shows."
        )
    return (
        "Open with the operating-tier line given above, verbatim and on its own. Then a "
        "level-2 heading exactly '## Key Insights', followed by at most three bulleted "
        "insights -- a ceiling, not a target. Each is one sentence, states its consequence, "
        "and ends with a short tag such as (Confidence: High -- FACT) -- one tag, never two. "
        "Everything else goes in the body, except a validity caveat, which goes on its own "
        "line below the bullets beginning 'Validity:' and does not count against the three."
    )


def synthesis_report_instruction(spec: ReportSpec, title: str) -> str:
    deferred = (
        "\n## Deferred-reports note (include verbatim at the end of this report)\n\n"
        f"{DEFERRED_REPORTS_NOTE}"
        if spec.number == 1
        else ""
    )
    return f"""\
## Report to write

Report {spec.number} — {title}

{_opening_instruction(spec)}

Must include: {spec.must_include}

Exhibit: {spec.exhibit}
{deferred}
Write Report {spec.number} now."""
