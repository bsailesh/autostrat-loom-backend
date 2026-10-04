"""
Strategy Synthesis Agent (Agent 5) — orchestration.

Two passes:
  Pass 1 (judgment) -- one forced-tool-choice call, retried once if the
  output is unusable (schema failure, truncation at the output ceiling, or
  a score missing for a committed project), then a clear error. No
  composites, no rankings, no utilisation.
  Compute -- every calculation in strategy_synthesis/compute.py.
  Pass 2 (narrative) -- one streamed call per report, given Pass 1's output
  and the computed results as already-correct numbers to narrate.

Independent of app/, like market_insights/: no database, no FastAPI. A
future router (Part 5) assembles a DecisionBrief and an
upstream_text_by_agent dict from the database -- including the
cursor-iteration and size-threshold decision the 414MB RAM constraint
requires -- and calls `StrategySynthesisAgent.run(...)` with the results.
This package never sees a database session; `summarize_upstream_agent` is
the one piece of that pipeline that belongs here (it's an LLM call), but
deciding *when* to call it is the router's job.
"""

from __future__ import annotations

import dataclasses
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from anthropic import Anthropic
from pydantic import ValidationError

from strategy_synthesis import compute
from strategy_synthesis.brief import DecisionBrief, render_brief_text
from strategy_synthesis.config import Settings
from strategy_synthesis.prompts import pass1_system_prompt, pass1_user_prompt, pass2_system_prompt, pass2_user_prompt
from strategy_synthesis.reports import REPORTS, ReportSpec
from strategy_synthesis.schemas import Pass1Candidate, Pass1Output

logger = logging.getLogger(__name__)


class Pass1ValidationError(Exception):
    """Raised when Pass 1's output is rejected twice -- schema failure,
    truncation at the output ceiling, or structural incompleteness."""


class UpstreamSummaryError(Exception):
    """Raised when an upstream agent's summary comes back truncated or
    empty. Never swallowed: Pass 1 scoring a portfolio against upstream
    evidence it was silently never given is the same class of failure as
    Pass 1 returning no scores at all, only harder to see afterwards --
    the reports still render, just with nothing behind their citations."""


# Streamed, with a ceiling well clear of what a faithful summary costs, and
# for the same reason as PASS1_MAX_TOKENS below. Measured on Arden's upstream
# pack (154,379 chars / 63,668 input tokens, over
# UPSTREAM_SUMMARIZE_THRESHOLD_CHARS, so the summarizer did run): the old
# non-streamed 4000-token call returned stop_reason=max_tokens and *zero*
# characters of text -- on Opus 5 thinking is on by default, and the whole
# 4000 went to it before any text block was opened. load_upstream_text then
# handed Pass 1 its "[Note: ... was summarized before analysis.]" header
# followed by nothing. A complete summary of that pack measures ~21.8k output
# tokens, so the ceiling is set above it rather than at it.
UPSTREAM_SUMMARY_MAX_TOKENS = 32000


# Streamed, with a ceiling well clear of what a complete answer costs.
# Measured on the nine-project Arden brief (six criteria, twelve candidates):
# a complete Pass 1 payload is ~10k output tokens, and Opus 5 reached 12.0k
# having emitted only five of those twelve candidates -- 75% of the old
# non-streamed 16k ceiling, with Sonnet 5 on the same prompt at 6.3k. Hitting
# the ceiling does not fail loudly: the truncated tool_use input comes back
# coerced to a fragment of the JSON the model was still writing (in the Arden
# run, literally `{"context": {}}`), and that fragment is schema-valid against
# a model whose every field defaults to [] -- so an empty Pass1Output used to
# pass validation and flow into compute. Streaming is what allows a ceiling
# this high: a non-streamed request this size risks an HTTP timeout, the same
# reason Pass 2's per-report call streams.
PASS1_MAX_TOKENS = 64000


@dataclass(frozen=True)
class ComputedResults:
    composite: list[compute.CompositeScore]
    bucket_utilisation: list[compute.BucketUtilisation]
    aggregate_utilisation: compute.AggregateUtilisation | None
    bottlenecks: list[compute.BottleneckFinding]
    scenario_results: list[compute.ScenarioResult]
    prerequisite_violations: list[compute.PrerequisiteViolation]
    financials: list[compute.FinancialMetrics]
    classifications: dict[str, str]
    coverage_gaps: list[str]
    candidates_sorted: list[Pass1Candidate]


@dataclass(frozen=True)
class Report:
    report_number: int
    title: str
    content: str


@dataclass(frozen=True)
class AgentRunResult:
    pass1_output: Pass1Output
    computed: ComputedResults
    reports: list[Report] = field(default_factory=list)


def _to_jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {k: _to_jsonable(v) for k, v in dataclasses.asdict(value).items()}
    if isinstance(value, list):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: _to_jsonable(v) for k, v in value.items()}
    return value


def render_computed_text(computed: ComputedResults) -> str:
    return json.dumps(_to_jsonable(computed), indent=2, default=str)


def _pass1_completeness_gaps(output: Pass1Output, brief: DecisionBrief) -> list[str]:
    """Structural completeness of Pass 1's scores, checked against the brief
    it was given. A schema-valid payload can still be wrong in a way the
    schema cannot express -- zero project_scores against nine committed
    projects is not an empty answer, it is a missing one -- and because every
    field on Pass1Output defaults to [], emptiness is exactly what a
    truncated or coerced tool input degrades into.

    compute.compute_composite_scores already raises when a project it is
    handed lacks a criterion score, so the per-project criterion check here
    is not new strictness: it moves that failure forward to where a retry
    with a corrective prompt is still possible, and turns compute's guard
    into an invariant rather than the first line of defence. The set-level
    check is the part that was genuinely missing -- an empty list never
    enters compute's loop body at all, so nothing fired.
    """
    gaps: list[str] = []

    committed = [p.project_key for p in brief.projects]
    scored = {ps.project_key for ps in output.project_scores}
    missing = [key for key in committed if key not in scored]
    if missing:
        gaps.append(
            f"{len(scored)} of {len(committed)} committed projects scored; no project_scores "
            f"entry for {', '.join(missing)}"
        )

    for ps in output.project_scores:
        scored_criteria = {d.criterion for d in ps.dimensions}
        absent = [c for c in brief.weights if c not in scored_criteria]
        if absent:
            gaps.append(f"project {ps.project_key} has no score for criterion {', '.join(absent)}")

    return gaps


class StrategySynthesisAgent:
    def __init__(self, settings: Settings):
        self._client = Anthropic(api_key=settings.anthropic_api_key, timeout=900.0)
        self._model = settings.model

    # -----------------------------------------------------------------
    # Upstream content -- the one LLM-calling piece of the memory-
    # constraint pipeline that belongs in this package (see module
    # docstring: deciding *when* to call this is the router's job).
    # -----------------------------------------------------------------

    def summarize_upstream_agent(self, agent_type: str, text: str) -> str:
        """Compress one oversized upstream agent's report text before it's
        folded into Pass 1's prompt, preserving cited facts and their
        confidence/classification tags. Called by the router when that
        agent's content exceeds its size threshold -- never called from
        `run()` itself, which takes upstream text as already-prepared.

        Raises UpstreamSummaryError rather than returning a partial summary:
        see UPSTREAM_SUMMARY_MAX_TOKENS."""
        with self._client.messages.stream(
            model=self._model,
            max_tokens=UPSTREAM_SUMMARY_MAX_TOKENS,
            system=(
                "Summarize the following analyst report for use as input to another agent. "
                "Preserve every cited fact, finding, and its confidence/classification tag "
                "(FACT/OBSERVATION/INTERPRETATION/FORECAST/UNKNOWN, High/Medium/Low). "
                "Do not add claims that are not in the source text."
            ),
            messages=[{"role": "user", "content": f"Agent: {agent_type}\n\n{text}"}],
        ) as stream:
            response = stream.get_final_message()

        logger.info(
            "Upstream summary for %s: stop_reason=%s, %s source chars -> %s output tokens of %s",
            agent_type,
            response.stop_reason,
            len(text),
            response.usage.output_tokens,
            UPSTREAM_SUMMARY_MAX_TOKENS,
        )

        summary = "".join(block.text for block in response.content if block.type == "text")
        if response.stop_reason == "max_tokens":
            raise UpstreamSummaryError(
                f"{agent_type} summary hit the {UPSTREAM_SUMMARY_MAX_TOKENS}-token ceiling "
                f"(stop_reason=max_tokens, {response.usage.output_tokens} output tokens, "
                f"{len(summary)} chars of text); a truncated summary silently drops the "
                "evidence Pass 1 would have cited"
            )
        if not summary.strip():
            raise UpstreamSummaryError(
                f"{agent_type} summary came back empty (stop_reason={response.stop_reason}, "
                f"{response.usage.output_tokens} output tokens) -- Pass 1 would have scored "
                "against no upstream evidence at all"
            )
        return summary

    # -----------------------------------------------------------------
    # Pass 1 -- structured, schema-validated, retry-once-then-fail
    # -----------------------------------------------------------------

    def _call_pass1(
        self, brief: DecisionBrief, brief_text: str, upstream_text_by_agent: dict[str, str]
    ) -> Pass1Output:
        system = pass1_system_prompt()
        user_prompt = pass1_user_prompt(brief_text, upstream_text_by_agent)

        tool_name = "emit_pass1_output"
        tool_def = {
            "name": tool_name,
            "description": "Return Pass 1's structured output: candidates, project dimension scores, "
            "criterion substitutions, and inferred dependencies.",
            "input_schema": Pass1Output.model_json_schema(),
        }

        last_error: str = "unknown error"
        for attempt in (1, 2):
            with self._client.messages.stream(
                model=self._model,
                max_tokens=PASS1_MAX_TOKENS,
                system=system,
                messages=[{"role": "user", "content": user_prompt}],
                tools=[tool_def],
                tool_choice={"type": "tool", "name": tool_name},
            ) as stream:
                response = stream.get_final_message()

            # Logged on every attempt, not only failures: the Arden run's empty
            # payload was undiagnosable afterwards because nothing recorded
            # stop_reason or how much of the ceiling the answer used.
            logger.info(
                "Pass 1 attempt %d: stop_reason=%s, output_tokens=%s of %s",
                attempt,
                response.stop_reason,
                response.usage.output_tokens,
                PASS1_MAX_TOKENS,
            )

            block = next(
                (b for b in response.content if b.type == "tool_use" and b.name == tool_name), None
            )
            if response.stop_reason == "max_tokens":
                # Checked before the block is parsed at all -- see
                # PASS1_MAX_TOKENS on why parsing it is worse than failing.
                last_error = (
                    f"output hit the {PASS1_MAX_TOKENS}-token ceiling "
                    f"(stop_reason=max_tokens, {response.usage.output_tokens} output tokens); "
                    "the tool input is a truncated fragment, not an answer"
                )
            elif block is None:
                last_error = f"no matching tool_use block in response (stop_reason={response.stop_reason})"
            else:
                try:
                    output = Pass1Output.model_validate(block.input)
                except ValidationError as e:
                    last_error = f"failed schema validation: {e}"
                else:
                    gaps = _pass1_completeness_gaps(output, brief)
                    if not gaps:
                        return output
                    last_error = "schema-valid but structurally incomplete -- " + "; ".join(gaps)

            if attempt == 1:
                logger.warning("Pass 1 output rejected on attempt 1: %s", last_error)
                user_prompt = (
                    f"{user_prompt}\n\n"
                    f"Your previous response was rejected:\n{last_error}\n"
                    "Return corrected JSON matching the schema exactly, with one project_scores "
                    "entry for every committed project and every framework criterion scored on "
                    "each of them."
                )

        raise Pass1ValidationError(f"Pass 1 output rejected twice: {last_error}")

    # -----------------------------------------------------------------
    # Pass 2 -- one streamed call per report, narrating already-computed
    # results. Mirrors market_insights/agent.py's per-report streaming
    # call exactly (max_tokens, adaptive thinking, empty-text-raises,
    # max_tokens-truncation-annotates) -- reused as-is, no new behavior.
    # -----------------------------------------------------------------

    def _call_pass2_report(
        self, spec: ReportSpec, brief_text: str, pass1_output: Pass1Output, computed_text: str
    ) -> str:
        with self._client.messages.stream(
            model=self._model,
            max_tokens=20000,
            system=pass2_system_prompt(),
            messages=[
                {
                    "role": "user",
                    "content": pass2_user_prompt(spec, brief_text, pass1_output, computed_text),
                }
            ],
            thinking={"type": "adaptive"},
        ) as stream:
            final = stream.get_final_message()

        text = "".join(block.text for block in final.content if block.type == "text")
        if not text:
            raise RuntimeError(
                f"Report {spec.number}: model returned no text (stop_reason={final.stop_reason})."
            )
        if final.stop_reason == "max_tokens":
            text += "\n\n_[Note: generation hit the length ceiling; this report may be truncated.]_"
        return text

    # -----------------------------------------------------------------
    # Orchestration
    # -----------------------------------------------------------------

    def run(self, brief: DecisionBrief, upstream_text_by_agent: dict[str, str]) -> AgentRunResult:
        brief_text = render_brief_text(brief)

        pass1_output = self._call_pass1(brief, brief_text, upstream_text_by_agent)

        computed = self._compute(brief, pass1_output)
        computed_text = render_computed_text(computed)

        reports = [
            Report(
                report_number=spec.number,
                title=spec.title,
                content=self._call_pass2_report(spec, brief_text, pass1_output, computed_text),
            )
            for spec in REPORTS
        ]
        return AgentRunResult(pass1_output=pass1_output, computed=computed, reports=reports)

    def _compute(self, brief: DecisionBrief, pass1_output: Pass1Output) -> ComputedResults:
        """Every number in the whole run, computed exactly once, here --
        nothing downstream (Pass 2) is asked to derive any of it."""

        project_scores = [
            compute.ProjectScore(
                project_key=ps.project_key,
                dimensions=[
                    compute.DimensionScore(criterion=d.criterion, score=d.score, basis=d.basis, reason=d.reason)
                    for d in ps.dimensions
                ],
                confidence=ps.confidence,
            )
            for ps in pass1_output.project_scores
        ]

        # Customer-supplied dependencies (source="customer") + Pass 1's
        # inferred ones (source="inferred") -- merged once, used everywhere
        # a dependency list is needed below.
        dependencies = list(brief.dependencies) + [
            compute.Dependency(
                project_key=d.project_key, depends_on=d.depends_on, source="inferred", note=d.reason
            )
            for d in pass1_output.inferred_dependencies
        ]

        committed_keys = {p.project_key for p in brief.projects}

        composite = compute.compute_composite_scores(project_scores, brief.weights)

        bucket_utilisation, aggregate = compute.compute_bucket_utilisation(
            brief.project_effort, brief.capacity, brief.buckets, committed_keys, brief.fiscal_year
        )
        bottlenecks = compute.find_bottlenecks(bucket_utilisation, brief.project_effort, brief.projects, composite)

        # Report 6 always needs a same-weights-as-the-primary-ranking
        # reference column, even if the customer's declared scenarios don't
        # happen to include one named "Base".
        has_base = any(s.name.strip().lower() == "base" for s in brief.scenarios)
        scenarios = brief.scenarios if has_base else [
            compute.Scenario(name="Base", weights=brief.weights)
        ] + list(brief.scenarios)

        scenario_results = compute.compute_scenarios(
            project_scores, scenarios, bucket_utilisation, brief.project_effort, brief.projects
        )
        prerequisite_violations = compute.check_cross_scenario_prerequisites(scenario_results, dependencies)

        mandatory_keys = {p.project_key for p in brief.projects if p.mandatory}
        financials = compute.compute_financial_metrics(brief.financials, mandatory_keys)

        classifications = compute.classify_projects(brief.projects, dependencies)

        objectives_served_by_project = {ps.project_key: ps.objectives_served for ps in pass1_output.project_scores}
        gaps = compute.coverage_gaps([o.key for o in brief.objectives], objectives_served_by_project)

        # Candidate ORDER is decided here, in Python, from Pass 1's assigned
        # evidence_strength_rank -- Pass 2 preserves it, never re-sorts.
        candidates_sorted = sorted(pass1_output.candidates, key=lambda c: c.evidence_strength_rank)

        return ComputedResults(
            composite=composite,
            bucket_utilisation=bucket_utilisation,
            aggregate_utilisation=aggregate,
            bottlenecks=bottlenecks,
            scenario_results=scenario_results,
            prerequisite_violations=prerequisite_violations,
            financials=financials,
            classifications=classifications,
            coverage_gaps=gaps,
            candidates_sorted=candidates_sorted,
        )
