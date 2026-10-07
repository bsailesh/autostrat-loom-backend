"""
Product Sustainment Agent (Agent 4) — prompt assembly.

Three prompt families, Tech & Regulation's shape:

  research_*        — live web search: lifecycle status, PCNs and EOL notices
                      for the listed parts, supplier risk, and candidate
                      alternates. Runs AFTER the computation, so it can be
                      aimed at the parts whose runout or flag matters.
  candidate_work_*  — ONE structured call. The model supplies judgement only;
                      validation.py merges in the computed numbers.
  synthesis_*       — one streamed call per report. Everything shared across
                      the nine is one cached prefix.
"""
from __future__ import annotations

from product_sustainment import standards
from product_sustainment.reports import DEFERRED_REPORTS_NOTE, ReportSpec

_SHARED_IDENTITY = f"""\
{standards.ROLE}

{standards.SCOPE_BOUNDARY}

{standards.OPTIONS_NOT_DECISIONS}

{standards.DO_NOT_INVENT}

{standards.STRUCTURE_RULES}
"""

# ---------------------------------------------------------------------------
# Research
# ---------------------------------------------------------------------------

RESEARCH_SYSTEM_PROMPT = f"""\
{_SHARED_IDENTITY}
{standards.RISK_CATEGORIES}

{standards.ALTERNATES_RULES}

{standards.EVIDENCE_AND_CONFIDENCE_STANDARD}

{standards.TIME_HORIZON}

You are in the RESEARCH phase. Use web search to gather public evidence. Do not
write reports and do not emit candidate work yet.

Output evidence rows, each with its observation, source, source type,
publication date, observation date, confidence and FACT/OBSERVATION/
INTERPRETATION/FORECAST/UNKNOWN label, grouped under: lifecycle status and
notices (per part number); supplier risk; candidate alternates (per part
number, each with its basis -- manufacturer replacement, pin-compatible family,
distributor cross-reference -- and the limits of that evidence); service
bulletins and directives; material and regulatory exposure."""


def research_user_prompt(structure_text: str, results_text: str, priority_parts: list[str]) -> str:
    focus = ", ".join(priority_parts) or "(none flagged -- survey the listed Level 2 components)"
    return f"""\
## Product structure and customer-supplied risk

{structure_text}

## Computed runout results (exact -- do not recompute)

{results_text}

## Your task

Research, in this order:
1. The CURRENT lifecycle status of each part listed here first: {focus}.
   Manufacturer PCNs and EOL notices, last-time-buy and last-delivery dates,
   NFND or similar designations. The most current notice wins; a superseded PCN
   is worse than none.
2. Candidate alternates for those parts: manufacturer-recommended replacements,
   pin-compatible families, distributor cross-references. Each is a CANDIDATE
   FOR QUALIFICATION -- record what the evidence does not establish.
3. Supplier risk for the supplier watch list and the listed manufacturers.
4. Service bulletins, directives and material regulation (RoHS, REACH) bearing
   on the listed parts.

Search by manufacturer part number where one is given."""


RESEARCH_FOLLOWUP_PROMPT = (
    "Now review what you have gathered. Identify the 3-4 weakest areas -- a flagged part with "
    "no current lifecycle source, a candidate alternate resting on one secondary source, a "
    "last-time-buy date you could not confirm -- and search again. Output ONLY new or revised "
    "evidence rows under the same headings. Where nothing more exists, say so."
)


# ---------------------------------------------------------------------------
# Candidate work (structured)
# ---------------------------------------------------------------------------

CANDIDATE_WORK_TOOL_NAME = "emit_candidate_work"

CANDIDATE_WORK_SYSTEM_PROMPT = f"""\
{_SHARED_IDENTITY}
{standards.RISK_CATEGORIES}

{standards.ALTERNATES_RULES}

{standards.EVIDENCE_AND_CONFIDENCE_STANDARD}

You are in the CANDIDATE WORK phase. Return a single call to the
`{CANDIDATE_WORK_TOOL_NAME}` tool matching its schema exactly -- no other keys,
and nothing wrapped around `items`.

You supply JUDGEMENT ONLY. The schema has no field for a date, a quantity or the
affected LRUs, because the platform fills those from its own computation after
you answer. Do not try to state them anywhere.

One item per at-risk part, keyed by its exact part_id. Emit an item where a part
carries a risk flag, a non-Active lifecycle status found in research, or a
computed runout within the forecast horizon. Omit a part where the driver cannot
be named with a source -- the finding still appears in the reports.

work_implied names the KIND of work the situation opens, never a choice between
them: last_time_buy, alternate_qualification, redesign, inventory_rebalance,
monitor. Where several are open, pick the one the evidence most directly
implies and describe the others in work_implied_description -- factually, never
as a recommendation.

Where the computed results give a part no runout within the horizon and no
last-time-buy date, date_absent_reason is REQUIRED: say why no date exists (for
example, standing single-source exposure with no notice).

An empty `items` list is a legitimate answer when nothing qualifies."""


def candidate_work_user_prompt(structure_text: str, results_text: str, research_brief: str) -> str:
    return f"""\
## Product structure and customer-supplied risk

{structure_text}

## Computed runout results (exact)

{results_text}

## Research brief (public evidence)

{research_brief}

Emit the candidate work now, as a single `{CANDIDATE_WORK_TOOL_NAME}` call."""


def candidate_work_retry_prompt(user_prompt: str, failure: str) -> str:
    return f"""\
{user_prompt}

## Your previous response was rejected

{failure}

Return a corrected `{CANDIDATE_WORK_TOOL_NAME}` call matching the schema exactly. Where an
item cannot be completed from the evidence, omit that item rather than guessing."""


# ---------------------------------------------------------------------------
# Synthesis
# ---------------------------------------------------------------------------


def synthesis_system_prompt() -> str:
    return f"""\
{_SHARED_IDENTITY}
{standards.RISK_CATEGORIES}

{standards.ALTERNATES_RULES}

{standards.EVIDENCE_LEVEL_TRANSLATION}

{standards.EVIDENCE_AND_CONFIDENCE_STANDARD}

{standards.CONSULTING_GRADE_OUTPUT_STANDARD}

{standards.TIME_HORIZON}

{standards.COLOR_SEMANTICS}

You are in the SYNTHESIS phase. Write the one report requested at the end of the
user message as Markdown, drawing only on what is supplied -- no new research.

The candidate work is validated and authoritative: refer to items by key
(PS-<part>), never renumber, add or drop one.

Write the report body only. Do not restate the "# Report N — Title" heading."""


def synthesis_shared_block(
    tier_line: str,
    structure_text: str,
    results_text: str,
    evidence_text: str,
    operational_text: str,
    research_brief: str,
    candidate_work_json: str,
) -> str:
    """Identical across all nine report calls -- one cached prefix."""
    return f"""\
## Operating tier line (the first line of every report, verbatim)

{tier_line}

## Product structure and customer-supplied data

{structure_text}

## Computed runout results (exact -- quote, never recompute)

{results_text}

## Reliability and quality evidence

{evidence_text}

## Fleet, maintenance and configuration data

{operational_text}

## Research brief (public evidence)

{research_brief}

## Candidate work (validated; numbers computed by the platform)

{candidate_work_json}"""


def _opening_instruction(spec: ReportSpec) -> str:
    if spec.opening == "scqa":
        return (
            "Open with the operating-tier line verbatim, on its own. Then a level-2 heading exactly "
            "'## Governing Insight' with Situation / Complication / Question / Answer -- the Answer a "
            "claim about what the evidence shows, never a course of action."
        )
    return (
        "Open with the operating-tier line verbatim, on its own. Then a level-2 heading exactly "
        "'## Key Insights' with at most three bulleted one-sentence insights, each stating its "
        "consequence and ending with one tag such as (Confidence: High -- FACT). A validity caveat, if "
        "any, goes on its own line below beginning 'Validity:'."
    )


def synthesis_report_instruction(spec: ReportSpec, title: str) -> str:
    deferred = (
        f"\n## Deferred-reports note (include verbatim at the end of this report)\n\n{DEFERRED_REPORTS_NOTE}"
        if spec.number == 1
        else ""
    )
    computed = (
        "\nThe platform appends computed tables after your text. Refer to them; do not reproduce them.\n"
        if spec.computed
        else ""
    )
    return f"""\
## Report to write

Report {spec.number} — {title}

{_opening_instruction(spec)}

Must include: {spec.must_include}

Exhibit: {spec.exhibit}
{computed}{deferred}
Write Report {spec.number} now."""
