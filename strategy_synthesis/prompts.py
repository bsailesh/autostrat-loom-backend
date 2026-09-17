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


def pass1_user_prompt(brief_text: str, upstream_text_by_agent: dict[str, str]) -> str:
    upstream_sections = "\n\n".join(
        f"### Upstream agent: {agent_type}\n\n{text}" for agent_type, text in upstream_text_by_agent.items()
    ) or "(No upstream agent runs available yet -- discover candidates and score from the brief alone, and say so.)"

    return f"""\
## Decision inputs brief

{brief_text}

## Upstream agent reports

{upstream_sections}

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
            "Open with a level-2 heading exactly '## Key Insights', followed by a "
            "bulleted list of the report's most material findings, each with its "
            "implication and confidence."
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
