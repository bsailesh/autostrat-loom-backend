"""
Strategy Synthesis Agent (Agent 5) — deterministic computation.

Pure functions: plain data in, plain data out. No LLM calls, no database
access, no I/O. Everything here is arithmetic that must be reliable and
identical across runs, which is the entire reason it lives in Python instead
of being left to the model:

    - weighted composite scores and rankings (ties reported, not broken)
    - per-bucket and aggregate capacity utilisation
    - bottleneck detection, including the minimum resolving deferral
    - scenario re-ranking against alternate weight sets
    - cross-scenario prerequisite violations
    - financial metrics (NPV, payback), kept separate from composite scores

The one finding this module exists to make reliable: aggregate utilisation
can look comfortable (e.g. 51%) while a single bucket is oversubscribed
(e.g. certification at 115%). See `find_bottlenecks`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from typing import Optional


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DimensionScore:
    """One scored criterion for one project, from Pass 1 (the model's judgment)."""

    criterion: str
    score: float  # 1-10. For an inverse criterion (e.g. effort), the score
    # already encodes the inversion — a small-effort project scores high.
    basis: str = "estimated"  # measured | calculated | source-derived | estimated
    reason: str = ""


@dataclass(frozen=True)
class ProjectScore:
    project_key: str
    dimensions: list[DimensionScore]
    confidence: str = "Medium"

    def score_for(self, criterion: str) -> Optional[float]:
        for d in self.dimensions:
            if d.criterion == criterion:
                return d.score
        return None


@dataclass(frozen=True)
class Project:
    project_key: str
    name: str
    mandatory: bool = False
    mandatory_driver: Optional[str] = None
    mandatory_deadline: Optional[str] = None


@dataclass(frozen=True)
class ProjectEffort:
    """One row per project x bucket. Effort remaining is what feeds scoring."""

    project_key: str
    bucket_key: str
    effort_remaining: float
    effort_total: Optional[float] = None


@dataclass(frozen=True)
class Bucket:
    bucket_key: str
    bucket_name: str
    contractable: str = "no"  # yes | partial | no


@dataclass(frozen=True)
class Capacity:
    fiscal_year: str
    bucket_key: str
    capacity_units: Optional[float]  # None = unplanned, never 0 for "unplanned"
    budget: Optional[float] = None


@dataclass(frozen=True)
class Dependency:
    project_key: str
    depends_on: str
    dependency_type: str = "prerequisite"
    source: str = "inferred"  # customer | inferred
    note: str = ""


@dataclass(frozen=True)
class Scenario:
    name: str
    weights: dict[str, float]


@dataclass(frozen=True)
class ProjectFinancials:
    project_key: str
    revenue_impact: list[Optional[float]] = field(default_factory=list)  # y1..y5
    capex: Optional[float] = None
    opex_annual: Optional[float] = None
    discount_rate: Optional[float] = None


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CompositeScore:
    project_key: str
    composite_score: float
    rank: int
    tied_with: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class BucketUtilisation:
    bucket_key: str
    fiscal_year: str
    demand: float
    capacity: Optional[float]  # None if this bucket is unplanned for this FY
    utilisation_pct: Optional[float]
    contractable: str
    over_capacity: bool


@dataclass(frozen=True)
class AggregateUtilisation:
    fiscal_year: str
    demand: float
    capacity: float
    utilisation_pct: float
    excluded_buckets: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class BottleneckFinding:
    bucket_key: str
    fiscal_year: str
    overage: float
    demand: float
    capacity: float
    mandatory_demand: float
    mandatory_share_pct: float
    contractable: str
    resolvable_by_deferral: bool
    deferral_set: list[str]
    deferral_weeks_removed: float
    resulting_utilisation_pct: Optional[float]
    # True when a single project's deferral resolves the bucket — the
    # "clean" case. False when multiple projects must be deferred together.
    agrees_with_ranking: Optional[bool]


@dataclass(frozen=True)
class ScenarioResult:
    scenario_name: str
    ranking: list[CompositeScore]
    bottlenecks: list[BottleneckFinding]


@dataclass(frozen=True)
class PrerequisiteViolation:
    scenario_name: str
    project_key: str
    project_rank: int
    depends_on: str
    depends_on_rank: int


@dataclass(frozen=True)
class FinancialMetrics:
    project_key: str
    npv: Optional[float]
    payback_years: Optional[float]
    total_cost: Optional[float]
    cost_only: bool
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# 3.1 Composite scoring
# ---------------------------------------------------------------------------


def compute_composite_scores(
    project_scores: list[ProjectScore], weights: dict[str, float]
) -> list[CompositeScore]:
    """Weighted composite score and rank per project. Ties share a rank —
    the next rank skips ahead by the size of the tie (1, 2, 2, 4), never
    broken arbitrarily."""

    weight_total = sum(weights.values())
    if not weights or abs(weight_total - 1.0) > 0.01:
        raise ValueError(f"criterion weights must sum to 1.0, got {weight_total}")

    raw: list[tuple[str, float]] = []
    for ps in project_scores:
        total = 0.0
        for criterion, weight in weights.items():
            score = ps.score_for(criterion)
            if score is None:
                raise ValueError(
                    f"project {ps.project_key!r} has no score for criterion {criterion!r}"
                )
            total += score * weight
        raw.append((ps.project_key, round(total, 2)))

    raw.sort(key=lambda kv: kv[1], reverse=True)

    scores_by_value: dict[float, list[str]] = {}
    for key, value in raw:
        scores_by_value.setdefault(value, []).append(key)

    results = []
    rank = 1
    for key, value in raw:
        tied_with = [k for k in scores_by_value[value] if k != key]
        results.append(CompositeScore(project_key=key, composite_score=value, rank=rank, tied_with=tied_with))
        # advance rank only once we've emitted every member of this tie group
        if key == scores_by_value[value][-1]:
            rank += len(scores_by_value[value])
    return results


# ---------------------------------------------------------------------------
# 3.2 Capacity utilisation
# ---------------------------------------------------------------------------


def compute_bucket_utilisation(
    project_effort: list[ProjectEffort],
    capacity: list[Capacity],
    buckets: list[Bucket],
    committed_project_keys: set[str],
    fiscal_year: str,
) -> tuple[list[BucketUtilisation], Optional[AggregateUtilisation]]:
    """Demand vs. capacity, per bucket, for one fiscal year. Also computes
    the aggregate — the caller must never present the aggregate alone; it is
    provided so a bottleneck can be shown *against* it, not instead of it."""

    demand_by_bucket: dict[str, float] = {b.bucket_key: 0.0 for b in buckets}
    for pe in project_effort:
        if pe.project_key not in committed_project_keys:
            continue
        if pe.bucket_key in demand_by_bucket:
            demand_by_bucket[pe.bucket_key] += pe.effort_remaining

    capacity_by_bucket: dict[str, Optional[float]] = {}
    for c in capacity:
        if c.fiscal_year == fiscal_year:
            capacity_by_bucket[c.bucket_key] = c.capacity_units

    results: list[BucketUtilisation] = []
    excluded: list[str] = []
    total_demand = 0.0
    total_capacity = 0.0

    for b in buckets:
        demand = demand_by_bucket.get(b.bucket_key, 0.0)
        cap = capacity_by_bucket.get(b.bucket_key)
        if cap is None:
            results.append(
                BucketUtilisation(
                    bucket_key=b.bucket_key,
                    fiscal_year=fiscal_year,
                    demand=demand,
                    capacity=None,
                    utilisation_pct=None,
                    contractable=b.contractable,
                    over_capacity=False,
                )
            )
            excluded.append(b.bucket_key)
            continue

        pct = round((demand / cap) * 100, 1) if cap else None
        results.append(
            BucketUtilisation(
                bucket_key=b.bucket_key,
                fiscal_year=fiscal_year,
                demand=demand,
                capacity=cap,
                utilisation_pct=pct,
                contractable=b.contractable,
                over_capacity=bool(pct is not None and pct > 100),
            )
        )
        total_demand += demand
        total_capacity += cap

    if total_capacity <= 0:
        aggregate = None
    else:
        aggregate = AggregateUtilisation(
            fiscal_year=fiscal_year,
            demand=total_demand,
            capacity=total_capacity,
            utilisation_pct=round((total_demand / total_capacity) * 100, 1),
            excluded_buckets=excluded,
        )

    return results, aggregate


# ---------------------------------------------------------------------------
# 3.3 Bottleneck analysis
# ---------------------------------------------------------------------------


def _search_minimum_deferral(
    demand: float, capacity: float, discretionary_worst_first: list[tuple[str, float]]
) -> Optional[list[str]]:
    """Smallest set of discretionary projects whose deferral brings demand
    at or under capacity. Tries every single project first (worst-ranked
    first), then every pair, and so on — so a single high-effort project
    ranked mid-table is preferred over accumulating several worse-ranked
    but smaller ones, matching "report the smallest set found"."""

    keys = [k for k, _ in discretionary_worst_first]
    effort = dict(discretionary_worst_first)
    n = len(keys)
    for size in range(1, n + 1):
        for combo in combinations(range(n), size):
            removed = sum(effort[keys[i]] for i in combo)
            if demand - removed <= capacity:
                return [keys[i] for i in combo]
    return None


def find_bottlenecks(
    bucket_utilisation: list[BucketUtilisation],
    project_effort: list[ProjectEffort],
    projects: list[Project],
    ranking: list[CompositeScore],
) -> list[BottleneckFinding]:
    """For every bucket over 100%: the overage, how much of that demand is
    mandatory, the smallest deferral that resolves it, and whether that
    deferral is a single project (the clean case) or several."""

    mandatory_keys = {p.project_key for p in projects if p.mandatory}
    rank_by_key = {c.project_key: c.rank for c in ranking}

    effort_by_bucket: dict[str, dict[str, float]] = {}
    for pe in project_effort:
        effort_by_bucket.setdefault(pe.bucket_key, {})[pe.project_key] = pe.effort_remaining

    findings: list[BottleneckFinding] = []
    for bu in bucket_utilisation:
        if bu.capacity is None or not bu.over_capacity:
            continue

        bucket_effort = effort_by_bucket.get(bu.bucket_key, {})
        mandatory_demand = sum(v for k, v in bucket_effort.items() if k in mandatory_keys)
        mandatory_share_pct = round((mandatory_demand / bu.capacity) * 100, 1)

        discretionary = [
            (key, effort) for key, effort in bucket_effort.items() if key not in mandatory_keys and effort > 0
        ]
        # worst-ranked (highest rank number) first; unranked projects sort as worst
        discretionary.sort(key=lambda kv: rank_by_key.get(kv[0], len(ranking) + 1), reverse=True)

        deferral_set = _search_minimum_deferral(bu.demand, bu.capacity, discretionary)

        if deferral_set is None:
            findings.append(
                BottleneckFinding(
                    bucket_key=bu.bucket_key,
                    fiscal_year=bu.fiscal_year,
                    overage=round(bu.demand - bu.capacity, 2),
                    demand=bu.demand,
                    capacity=bu.capacity,
                    mandatory_demand=mandatory_demand,
                    mandatory_share_pct=mandatory_share_pct,
                    contractable=bu.contractable,
                    resolvable_by_deferral=False,
                    deferral_set=[],
                    deferral_weeks_removed=0.0,
                    resulting_utilisation_pct=bu.utilisation_pct,
                    agrees_with_ranking=None,
                )
            )
            continue

        removed = sum(effort for key, effort in bucket_effort.items() if key in deferral_set)
        resulting_pct = round(((bu.demand - removed) / bu.capacity) * 100, 1)
        findings.append(
            BottleneckFinding(
                bucket_key=bu.bucket_key,
                fiscal_year=bu.fiscal_year,
                overage=round(bu.demand - bu.capacity, 2),
                demand=bu.demand,
                capacity=bu.capacity,
                mandatory_demand=mandatory_demand,
                mandatory_share_pct=mandatory_share_pct,
                contractable=bu.contractable,
                resolvable_by_deferral=True,
                deferral_set=deferral_set,
                deferral_weeks_removed=removed,
                resulting_utilisation_pct=resulting_pct,
                agrees_with_ranking=(len(deferral_set) == 1),
            )
        )

    return findings


# ---------------------------------------------------------------------------
# 3.4 Scenario re-ranking
# ---------------------------------------------------------------------------


def compute_scenarios(
    project_scores: list[ProjectScore],
    scenarios: list[Scenario],
    bucket_utilisation: list[BucketUtilisation],
    project_effort: list[ProjectEffort],
    projects: list[Project],
) -> list[ScenarioResult]:
    """Same dimension scores, each scenario's weights, recomputed. Capacity
    demand does not change per scenario — only which projects a scenario's
    ranking would defer to resolve a bottleneck does."""

    results = []
    for scenario in scenarios:
        ranking = compute_composite_scores(project_scores, scenario.weights)
        bottlenecks = find_bottlenecks(bucket_utilisation, project_effort, projects, ranking)
        results.append(ScenarioResult(scenario_name=scenario.name, ranking=ranking, bottlenecks=bottlenecks))
    return results


# ---------------------------------------------------------------------------
# 3.5 Cross-scenario prerequisite check
# ---------------------------------------------------------------------------


def check_cross_scenario_prerequisites(
    scenario_results: list[ScenarioResult], dependencies: list[Dependency]
) -> list[PrerequisiteViolation]:
    """A violation is a project ranked above (better than) a project it
    depends on — i.e. prioritised ahead of its own prerequisite."""

    violations = []
    for sr in scenario_results:
        rank_by_key = {c.project_key: c.rank for c in sr.ranking}
        for dep in dependencies:
            project_rank = rank_by_key.get(dep.project_key)
            prereq_rank = rank_by_key.get(dep.depends_on)
            if project_rank is None or prereq_rank is None:
                continue
            if project_rank < prereq_rank:
                violations.append(
                    PrerequisiteViolation(
                        scenario_name=sr.scenario_name,
                        project_key=dep.project_key,
                        project_rank=project_rank,
                        depends_on=dep.depends_on,
                        depends_on_rank=prereq_rank,
                    )
                )
    return violations


# ---------------------------------------------------------------------------
# 3.6 Financial metrics
# ---------------------------------------------------------------------------


def _total_cost(f: ProjectFinancials) -> Optional[float]:
    if f.capex is None and f.opex_annual is None:
        return None
    return (f.capex or 0.0) + (f.opex_annual or 0.0)


def _net_cash_flows(f: ProjectFinancials) -> list[Optional[float]]:
    opex = f.opex_annual or 0.0
    return [None if r is None else r - opex for r in f.revenue_impact]


def _npv(f: ProjectFinancials) -> float:
    total = -(f.capex or 0.0)
    for year, net in enumerate(_net_cash_flows(f), start=1):
        if net is None:
            continue
        total += net / ((1 + f.discount_rate) ** year)
    return total


def _payback_years(f: ProjectFinancials) -> Optional[float]:
    cumulative = -(f.capex or 0.0)
    for year, net in enumerate(_net_cash_flows(f), start=1):
        if net is None:
            continue
        prev = cumulative
        cumulative += net
        if cumulative >= 0:
            fraction = (-prev / net) if net else 0.0
            return round((year - 1) + fraction, 2)
    return None


def compute_financial_metrics(
    financials: list[ProjectFinancials], mandatory_project_keys: set[str]
) -> list[FinancialMetrics]:
    """NPV and payback where computable. Never merged into the composite
    score. Mandatory projects and projects with no revenue projection get
    cost only, with a reason — never a fabricated return."""

    results = []
    for f in financials:
        total_cost = _total_cost(f)

        if f.project_key in mandatory_project_keys:
            results.append(
                FinancialMetrics(
                    project_key=f.project_key,
                    npv=None,
                    payback_years=None,
                    total_cost=total_cost,
                    cost_only=True,
                    reason="mandatory — return not computed",
                )
            )
            continue

        if not f.revenue_impact or all(r is None for r in f.revenue_impact):
            results.append(
                FinancialMetrics(
                    project_key=f.project_key,
                    npv=None,
                    payback_years=None,
                    total_cost=total_cost,
                    cost_only=True,
                    reason="revenue projections absent",
                )
            )
            continue

        if f.discount_rate is None:
            results.append(
                FinancialMetrics(
                    project_key=f.project_key,
                    npv=None,
                    payback_years=None,
                    total_cost=total_cost,
                    cost_only=True,
                    reason="discount rate not supplied",
                )
            )
            continue

        results.append(
            FinancialMetrics(
                project_key=f.project_key,
                npv=round(_npv(f), 2),
                payback_years=_payback_years(f),
                total_cost=total_cost,
                cost_only=False,
                reason=None,
            )
        )
    return results
