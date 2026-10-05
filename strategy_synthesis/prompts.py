"""
Strategy Synthesis Agent (Agent 5) — prompt assembly.

Mirrors market_insights/prompts.py's interpolation pattern
(standards.X dropped in under its own heading, f-string, no templating
library) but two passes instead of research/synthesis.
"""

from __future__ import annotations

import json

from strategy_synthesis import standards
from strategy_synthesis.reports import ReportSpec
from strategy_synthesis.schemas import Pass1Output

_SHARED_IDENTITY = f"""\
{standards.ROLE}

{standards.FIVE_QUESTIONS}

{standards.TWO_POPULATIONS}

{standards.CUSTOMER_VOCABULARY}
"""


def pass1_system_prompt() -> str:
    return f"""\
{_SHARED_IDENTITY}
{standards.PASS1_ANALYSIS_REQUIREMENTS}

{standards.BASIS_LABELS}

{standards.CRITERION_SUBSTITUTION}

{standards.NEVER_ELIMINATE_CUSTOMER_INPUT}

{standards.DUPLICATE_DETECTION}

{standards.EVIDENCE_AND_CONFIDENCE_STANDARD}

Return your output as a single call to the `emit_pass1_output` tool, matching
its schema exactly. No composites, no rankings, no capacity utilisation --
those are computed after this pass, from what you emit here."""


def _structured_candidate_section(structured_candidates: list[dict] | None) -> str:
    """Agent 3's candidate work, handed to Pass 1 pre-structured.

    These arrive as rows from `tr_candidate_work`, not parsed out of Tech &
    Regulation's report prose -- that agent generates them structurally
    before it narrates them, so there is no second parser of an undocumented
    contract here. Pass 1's own discovery from upstream markdown is
    unchanged and runs alongside this; the two populations stay
    distinguishable because only these carry a driver and a date.
    """
    if not structured_candidates:
        return ""

    rows = json.dumps(structured_candidates, indent=2, default=str)
    return f"""
## Pre-structured candidate work (from Tech & Regulation)

These are already-structured candidate work items from the selected upstream
Tech & Regulation run. They are NOT prose to interpret: each one already has a
named driver, a date (or a stated reason there is none), its applicability, and
the work it implies.

{rows}

Carry each of these into `candidates` using its own key verbatim (TR-xx), and
populate `driver`, `work_date`, `date_basis` and `source_candidate_key` from the
row. Do not renumber them, do not merge them with each other, and do not
re-derive their fields from the report text -- the row is authoritative and the
prose is a narration of it.

Set `origin` to "Tech & Regulation — candidate work <key>" so the two
populations remain distinguishable: a candidate derived from structured
candidate work carries its driver and date, one you inferred from prose does
not. Say which is which where it matters.

Score and rank these exactly as you would any other candidate -- their
`evidence_strength_rank` is yours to assign. Tech & Regulation deliberately
supplies no effort, duration, cost or priority, because it cannot see capacity;
that assessment is this pass's job and the compute that follows it.

A candidate work item you judge not worth carrying forward should still appear,
with your reasoning in `evidence_summary`. Dropping it silently would make it
look as though Tech & Regulation never surfaced it.
"""


def pass1_user_prompt(
    brief_text: str,
    upstream_text_by_agent: dict[str, str],
    structured_candidates: list[dict] | None = None,
) -> str:
    upstream_sections = "\n\n".join(
        f"### Upstream agent: {agent_type}\n\n{text}" for agent_type, text in upstream_text_by_agent.items()
    ) or "(No upstream agent runs available yet -- discover candidates and score from the brief alone, and say so.)"

    return f"""\
## Decision inputs brief

{brief_text}

## Upstream agent reports

{upstream_sections}
{_structured_candidate_section(structured_candidates)}
Produce the Pass 1 structured output: candidates, per-project dimension
scores (with objectives_served), criterion substitutions, and inferred
dependencies."""


def pass2_system_prompt() -> str:
    return f"""\
{_SHARED_IDENTITY}
{standards.PASS2_ANALYSIS_REQUIREMENTS}

{standards.BASIS_LABELS}

{standards.PARTIAL_AGENT_COVERAGE}

{standards.MANDATORY_VS_DISCRETIONARY}

{standards.PRIORITY_NOT_PREREQUISITE}

{standards.HUMAN_DECISION_GATES}

{standards.EVIDENCE_AND_CONFIDENCE_STANDARD}

{standards.CONSULTING_GRADE_OUTPUT_STANDARD}

Write the one report requested below as Markdown. Nothing else."""


def _opening_instruction(spec: ReportSpec) -> str:
    if spec.opening == "scqa":
        return (
            "Open with a level-2 heading exactly '## Governing Insight', followed by "
            "Situation / Complication / Question / Answer -- a claim, not a topic label."
        )
    if spec.opening == "key_insights":
        return (
            "Open with a level-2 heading exactly '## Key Insights', followed by at "
            "most three bulleted insights -- a ceiling, not a target. Each is one "
            "sentence, states its consequence, and ends with a short tag carrying "
            "confidence and basis label, such as (Confidence: High -- calculated) -- "
            "one tag, never two. Everything else goes in the body, except a "
            "validity caveat, which goes on its own line below the bullets "
            "beginning 'Validity:' and does not count against the three."
        )
    return "No special opening heading is required for this report -- go straight into the content."


def pass2_user_prompt(
    spec: ReportSpec,
    brief_text: str,
    pass1_output: Pass1Output,
    computed_text: str,
) -> str:
    return f"""\
## Report to write

Report {spec.number} -- {spec.title}

{_opening_instruction(spec)}

Must include: {spec.must_include}

Exhibit: {spec.exhibit}

## Decision inputs brief

{brief_text}

## Pass 1 output (candidates, dimension scores, substitutions, inferred dependencies)

{json.dumps(pass1_output.model_dump(), indent=2)}

## Computed results (already correct -- narrate, do not recalculate)

{computed_text}

Write Report {spec.number} now."""
