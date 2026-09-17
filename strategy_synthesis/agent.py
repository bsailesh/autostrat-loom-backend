"""
Strategy Synthesis Agent (Agent 5) — orchestration.

Two passes:
  Pass 1 (judgment) -- one forced-tool-choice call, retried once on schema
  failure, then a clear error. No composites, no rankings, no utilisation.
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
    """Raised when Pass 1's output fails schema validation twice."""


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
        `run()` itself, which takes upstream text as already-prepared."""
        response = self._client.messages.create(
            model=self._model,
            max_tokens=4000,
            system=(
                "Summarize the following analyst report for use as input to another agent. "
                "Preserve every cited fact, finding, and its confidence/classification tag "
                "(FACT/OBSERVATION/INTERPRETATION/FORECAST/UNKNOWN, High/Medium/Low). "
                "Do not add claims that are not in the source text."
            ),
            messages=[{"role": "user", "content": f"Agent: {agent_type}\n\n{text}"}],
        )
        return "".join(block.text for block in response.content if block.type == "text")

    # -----------------------------------------------------------------
    # Pass 1 -- structured, schema-validated, retry-once-then-fail
    # -----------------------------------------------------------------

    def _call_pass1(self, brief_text: str, upstream_text_by_agent: dict[str, str]) -> Pass1Output:
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
            response = self._client.messages.create(
                model=self._model,
                max_tokens=16000,
                system=system,
                messages=[{"role": "user", "content": user_prompt}],
                tools=[tool_def],
                tool_choice={"type": "tool", "name": tool_name},
            )
            block = next(
                (b for b in response.content if b.type == "tool_use" and b.name == tool_name), None
            )
            if block is None:
                last_error = f"no matching tool_use block in response (stop_reason={response.stop_reason})"
            else:
                try:
                    return Pass1Output.model_validate(block.input)
                except ValidationError as e:
                    last_error = str(e)

            if attempt == 1:
                logger.warning("Pass 1 output failed validation on attempt 1: %s", last_error)
                user_prompt = (
                    f"{user_prompt}\n\n"
                    f"Your previous response failed schema validation:\n{last_error}\n"
                    "Return corrected JSON matching the schema exactly."
                )

        raise Pass1ValidationError(f"Pass 1 output failed schema validation twice: {last_error}")

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

        pass1_output = self._call_pass1(brief_text, upstream_text_by_agent)

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
