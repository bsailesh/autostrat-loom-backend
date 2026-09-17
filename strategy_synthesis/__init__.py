"""
Strategy Synthesis Agent (Agent 5).

Two passes: judgment (Pass 1, an LLM call producing candidates and
per-project dimension scores as strict JSON -- no composites, no rankings,
no utilisation) and narrative (Pass 2, one LLM call per report, given
already-computed results to interpret). Every calculation in between --
composite scores, capacity utilisation, bottleneck detection, scenario
re-ranking, prerequisite checks, financial metrics, project classification,
objective-coverage gaps -- is deterministic Python in `compute.py`, so the
same inputs always produce the same numbers regardless of what either LLM
call does.

Deliberately independent of `app/`, like `market_insights/`: no database,
no FastAPI. `agent.py`'s `StrategySynthesisAgent.run()` takes a
`DecisionBrief` (brief.py) and already-loaded upstream report text; a
future router assembles both from the database and persists the result.
"""

from strategy_synthesis.agent import AgentRunResult, Pass1ValidationError, Report, StrategySynthesisAgent
from strategy_synthesis.brief import DecisionBrief
from strategy_synthesis.compute import (
    Bucket,
    Capacity,
    CompositeScore,
    Dependency,
    DimensionScore,
    Project,
    ProjectEffort,
    ProjectFinancials,
    ProjectScore,
    BucketUtilisation,
    AggregateUtilisation,
    BottleneckFinding,
    FinancialMetrics,
    PrerequisiteViolation,
    Scenario,
    ScenarioResult,
    check_cross_scenario_prerequisites,
    classify_projects,
    compute_bucket_utilisation,
    compute_composite_scores,
    compute_financial_metrics,
    compute_scenarios,
    coverage_gaps,
    find_bottlenecks,
)

__all__ = [
    "AgentRunResult",
    "Pass1ValidationError",
    "Report",
    "StrategySynthesisAgent",
    "DecisionBrief",
    "Bucket",
    "Capacity",
    "CompositeScore",
    "Dependency",
    "DimensionScore",
    "Project",
    "ProjectEffort",
    "ProjectFinancials",
    "ProjectScore",
    "BucketUtilisation",
    "AggregateUtilisation",
    "BottleneckFinding",
    "FinancialMetrics",
    "PrerequisiteViolation",
    "Scenario",
    "ScenarioResult",
    "check_cross_scenario_prerequisites",
    "classify_projects",
    "compute_bucket_utilisation",
    "compute_composite_scores",
    "compute_financial_metrics",
    "compute_scenarios",
    "coverage_gaps",
    "find_bottlenecks",
]
