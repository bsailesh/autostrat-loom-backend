"""
Technology & Regulatory Intelligence Agent (Agent 3) — prompt assembly.

Mirrors market_insights/prompts.py's interpolation pattern (standards.X
dropped in under its own heading, f-string, no templating library), with one
extra prompt the other agents do not have: the candidate-work extraction
prompt, which is the structured call that makes the Agent 5 integration
parse-free.

Three phases, three prompt families:

  research_*          — live web search, scoped by the envelope
  candidate_work_*    — ONE structured call, forced tool choice
  synthesis_*         — one streamed call per report, narrating the
                        already-validated candidate work

The ordering is the point. Candidate work is generated once, structurally,
and then narrated; the reports never produce it, and nothing ever parses it
back out of their prose.
"""
from __future__ import annotations

import json

from tech_regulation import standards
from tech_regulation.reports import DEFERRED_REPORTS_NOTE, ReportSpec
from tech_regulation.schemas import CandidateWorkItem

_SHARED_IDENTITY = f"""\
{standards.ROLE}

{standards.SCOPE_BOUNDARY}

{standards.IMPLICATION_CANDIDATE_WORK_RECOMMENDATION}

{standards.OPERATING_STATE_RULES}
"""


# ---------------------------------------------------------------------------
# Phase 1 — research
# ---------------------------------------------------------------------------

RESEARCH_SYSTEM_PROMPT = f"""\
{_SHARED_IDENTITY}
{standards.SOURCE_PRECEDENCE}

{standards.DO_NOT_INVENT}

{standards.PATENT_SEARCH_SCOPE}

{standards.REQUIRED_ANALYSES}

{standards.EVIDENCE_AND_CONFIDENCE_STANDARD}

{standards.MONITORING_ABSENCE}

You are in the RESEARCH phase. Use web search to gather evidence. Do not write
reports yet, and do not emit candidate work yet -- that is a separate structured
step after this one. Output evidence rows: each with its observation, source,
source type, publication date, observation date, confidence, and its
FACT/OBSERVATION/INTERPRETATION/FORECAST/UNKNOWN classification, plus the
technology-evidence label where it applies.

Group your rows under these headings, which match the required analyses:
technology maturity; technology trends; ecosystem; patents and IP; R&D;
suppliers (discontinuations FIRST under this heading); regulatory intelligence;
regulatory changes; standards; competitor technical capability.

Search against the applicability envelope, not the industry generally. Where the
envelope excludes something, do not research it -- note that it was excluded."""


def research_user_prompt(envelope_text: str) -> str:
    return f"""\
## Applicability envelope

{envelope_text}

## Your task

Research the current technology and regulatory environment for this customer.

Priorities, in order:
1. Revisions, changes or new requirements touching the certification bases and
   standards held listed above. These are the findings that can bind this
   customer, so establish them from primary sources and get their dates.
2. Supplier discontinuations and product change notices for the watch list,
   with runout or last-time-buy dates.
3. Regulatory changes in the listed jurisdictions applying to the listed product
   categories and platforms -- distinguishing proposed, final, effective and
   enforced.
4. Technology maturity, trends, ecosystem, patents and R&D in the monitored
   domains and the customer's own product categories.
5. Competitor technical capability and its evidence.

Pursue DATES throughout. A finding with a date can be scheduled downstream; the
same finding without one is only standing context."""


RESEARCH_FOLLOWUP_PROMPT = (
    "Now review what you have gathered. Identify the 3-4 weakest or thinnest "
    "areas (least evidence, stalest sources, unresolved contradictions, or "
    "findings where you have a regulation but not its effective date) and run "
    "additional web searches to strengthen them. Prioritise locating primary "
    "sources for anything currently resting on secondary reporting, and "
    "resolving missing dates. Then output ONLY the new or revised evidence rows, "
    "grouped under the same headings. If an area genuinely has no more public "
    "evidence, say so explicitly."
)


# ---------------------------------------------------------------------------
# Phase 2 — candidate work extraction (the structured call)
# ---------------------------------------------------------------------------

CANDIDATE_WORK_TOOL_NAME = "emit_candidate_work"

CANDIDATE_WORK_SYSTEM_PROMPT = f"""\
{_SHARED_IDENTITY}
{standards.CANDIDATE_WORK_CONTRACT}

{standards.EVIDENCE_AND_CONFIDENCE_STANDARD}

You are in the CANDIDATE WORK phase. You are not writing prose. Return a single
call to the `{CANDIDATE_WORK_TOOL_NAME}` tool matching its schema exactly.

This payload is the authoritative record of candidate work for this run. The
reports written afterwards narrate it; they do not add to it, and nothing
downstream re-derives it from their prose. An item you omit here does not exist
downstream, and an item you invent here will be presented to the customer as
work their evidence implies.

Emit an item ONLY where all five required fields are genuinely present. Where a
finding is real but a required field is not available, omit the item -- the
finding will still be stated in the reports. Omitting is correct; guessing is
not.

There is no field for effort, duration, cost, reach, priority or rank, because
you cannot see the customer's capacity or what competes for it. Do not put such
language in the descriptions either."""


def candidate_work_user_prompt(envelope_text: str, research_brief: str) -> str:
    return f"""\
## Applicability envelope

{envelope_text}

## Research brief (the only evidence you may use)

{research_brief}

## Your task

Emit the candidate work this evidence implies for THIS customer, as a single
`{CANDIDATE_WORK_TOOL_NAME}` call.

Number the items TR-01, TR-02, ... in the order you emit them.

Work through these sources of candidate work in order, since they are the ones
most likely to yield dated items:
1. Revisions to standards the customer HOLDS (cross-reference the standards-held
   list; a revision to one they do not hold is background, not work).
2. Regulatory changes applying to their certification bases.
3. Supplier discontinuations with runout dates.
4. Certification pathways opening on platforms they are PURSUING -- mark
   platform_relationship so the entry-condition reading survives.
5. Standards gaps where a requirement has been called for but nothing published.
6. Technologies reaching Demonstrated maturity in an application they serve.

For each item, set `applicability` from the envelope's own keys and identifiers,
never invented ones. Set `work_date` wherever a date exists, with the matching
`date_basis`. Where no date genuinely exists, set `date_basis` to
"none_established" and give `date_absent_reason`.

If the evidence implies no candidate work at all, return an empty `items` list.
That is a legitimate outcome and is better than padding."""


def candidate_work_retry_prompt(user_prompt: str, failure: str) -> str:
    return f"""\
{user_prompt}

## Your previous response was rejected

{failure}

Return a corrected `{CANDIDATE_WORK_TOOL_NAME}` call matching the schema exactly.
Where an item cannot be completed from the evidence, omit that item rather than
filling a field with a guess."""


# ---------------------------------------------------------------------------
# Phase 3 — synthesis, one call per report
# ---------------------------------------------------------------------------


def synthesis_system_prompt() -> str:
    return f"""\
{_SHARED_IDENTITY}
{standards.DO_NOT_INVENT}

{standards.SOURCE_PRECEDENCE}

{standards.EVIDENCE_AND_CONFIDENCE_STANDARD}

{standards.CONSULTING_GRADE_OUTPUT_STANDARD}

{standards.MONITORING_ABSENCE}

{standards.COLOR_SEMANTICS}

You are in the SYNTHESIS phase. Write the one report requested below as
Markdown, drawing only on the research brief and the candidate work payload
supplied -- no new research, no new candidate work.

The candidate work payload is already validated and authoritative. Narrate it;
do not re-derive it, do not renumber it, do not add to it, and do not drop an
item from it. Refer to items by their key (TR-01, ...). If a finding in the
research brief has no candidate work item, state the finding without inventing
one.

Write the report body only. Do not restate the "# Report N — Title" heading."""


def _opening_instruction(spec: ReportSpec) -> str:
    if spec.opening == "scqa":
        return (
            "Open with the operating-state line given above, verbatim and on its own. "
            "Then a level-2 heading exactly '## Governing Insight', followed by "
            "Situation / Complication / Question / Answer -- the Answer being a claim "
            "about what the evidence shows, never a course of action."
        )
    return (
        "Open with a level-2 heading exactly '## Key Insights', followed by at most "
        "three bulleted insights -- a ceiling, not a target. Each is one sentence, "
        "states its consequence, and ends with a short tag such as "
        "(Confidence: High -- FACT) -- one tag, never two. Everything else goes in "
        "the body, except a validity caveat, which goes on its own line below the "
        "bullets beginning 'Validity:' and does not count against the three."
    )


def synthesis_user_prompt(
    spec: ReportSpec,
    envelope_text: str,
    research_brief: str,
    candidate_work: list[CandidateWorkItem],
    operating_state_line: str,
    title: str,
) -> str:
    payload = json.dumps([item.model_dump() for item in candidate_work], indent=2)
    deferred = (
        f"\n## Deferred-reports note (include verbatim at the end of this report)\n\n"
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

## Operating state line (first line of this run)

{operating_state_line}

## Applicability envelope

{envelope_text}

## Research brief (the only evidence you may use)

{research_brief}

## Candidate work for this run (validated, authoritative -- narrate, do not re-derive)

{payload}
{deferred}
Write Report {spec.number} now."""
