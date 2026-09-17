"""
Strategy Synthesis Agent (Agent 5) — computation core.

This package holds the deterministic parts of Agent 5. Judgment (reading
upstream reports, scoring dimensions, discovering candidates) is an LLM pass.
Arithmetic on top of that judgment — composite scores, capacity utilisation,
bottleneck detection, scenario re-ranking, prerequisite checks, financial
metrics — is Python, in `compute.py`, so the same inputs always produce the
same numbers.

`compute.py` has no LLM and no database access: it takes plain data in and
returns plain data out.
"""

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
    compute_bucket_utilisation,
    compute_composite_scores,
    compute_financial_metrics,
    compute_scenarios,
    find_bottlenecks,
)

__all__ = [
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
    "compute_bucket_utilisation",
    "compute_composite_scores",
    "compute_financial_metrics",
    "compute_scenarios",
    "find_bottlenecks",
]
