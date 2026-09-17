"""
Strategy Synthesis Agent (Agent 5) — the decision-inputs brief, as plain
data. Separate from compute.py's dataclasses: these aren't arithmetic
inputs (compute.py doesn't touch objectives, products/fleet, proposed
projects, or prior candidates at all), they're context the prompts need.

Assembling a `DecisionBrief` from the database is a future router's job
(Part 5) -- this package takes the assembled, plain-data result, never a
DB session.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from strategy_synthesis.compute import Bucket, Capacity, Dependency, Project, ProjectEffort, ProjectFinancials, Scenario


@dataclass(frozen=True)
class Objective:
    key: str
    text: str
    horizon: str = ""
    owner: str = ""
    measure: str = ""


@dataclass(frozen=True)
class ProductFleetItem:
    product_key: str
    product: str
    platform: str
    platform_class: str = ""
    units_in_service: float = 0.0
    avg_age_years: float | None = None
    status: str = ""
    region: str = ""


@dataclass(frozen=True)
class ProposedProject:
    key: str
    name: str
    proposed_by: str = ""
    description: str = ""
    rationale: str = ""


@dataclass(frozen=True)
class PriorCandidate:
    """A discovered_candidates row from a previous run -- given to Pass 1
    for continuity, so a dismissed candidate isn't silently re-discovered
    as new."""
    key: str
    name: str
    status: str  # new | under_review | scoped | dismissed
    dismissal_reason: str = ""


@dataclass(frozen=True)
class DecisionBrief:
    fiscal_year: str  # which capacity year to analyze, e.g. "FY27"
    effort_unit: str
    objectives: list[Objective] = field(default_factory=list)
    buckets: list[Bucket] = field(default_factory=list)
    capacity: list[Capacity] = field(default_factory=list)
    projects: list[Project] = field(default_factory=list)
    project_effort: list[ProjectEffort] = field(default_factory=list)
    dependencies: list[Dependency] = field(default_factory=list)  # customer-supplied only; source="customer"
    financials: list[ProjectFinancials] = field(default_factory=list)
    products_fleet: list[ProductFleetItem] = field(default_factory=list)
    proposed_projects: list[ProposedProject] = field(default_factory=list)
    prior_candidates: list[PriorCandidate] = field(default_factory=list)
    framework_name: str = "weighted_scoring"
    weights: dict[str, float] = field(default_factory=dict)
    scenarios: list[Scenario] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)


def render_brief_text(brief: DecisionBrief) -> str:
    """Plain-text rendering of the brief for the prompt. One block per
    section, customer vocabulary preserved verbatim (bucket/objective/
    project keys and names are never translated)."""

    def _lines(items, fmt):
        return "\n".join(fmt(i) for i in items) or "(none supplied)"

    sections = [
        f"Fiscal year under analysis: {brief.fiscal_year}. Effort unit: {brief.effort_unit}.",
        f"Framework: {brief.framework_name}. Weights: "
        + ", ".join(f"{k}={v}" for k, v in brief.weights.items()),
        "## Strategic objectives\n"
        + _lines(brief.objectives, lambda o: f"- {o.key}: {o.text} (horizon: {o.horizon}, owner: {o.owner})"),
        "## Capacity buckets\n"
        + _lines(brief.buckets, lambda b: f"- {b.bucket_key} ({b.bucket_name}), contractable: {b.contractable}"),
        "## Capacity (this fiscal year)\n"
        + _lines(
            [c for c in brief.capacity if c.fiscal_year == brief.fiscal_year],
            lambda c: f"- {c.bucket_key}: {c.capacity_units if c.capacity_units is not None else 'unplanned'} units",
        ),
        "## Committed projects\n"
        + _lines(
            brief.projects,
            lambda p: (
                f"- {p.project_key}: {p.name} (mandatory: {p.mandatory}"
                + (f", driver: {p.mandatory_driver}, deadline: {p.mandatory_deadline}" if p.mandatory else "")
                + ")"
            ),
        ),
        "## Effort remaining by project x bucket\n"
        + _lines(
            brief.project_effort,
            lambda e: f"- {e.project_key} / {e.bucket_key}: {e.effort_remaining} remaining"
            + (f" of {e.effort_total} total" if e.effort_total is not None else ""),
        ),
        "## Customer-supplied dependencies\n"
        + _lines(brief.dependencies, lambda d: f"- {d.project_key} depends on {d.depends_on}"),
        "## Financials\n"
        + _lines(
            brief.financials,
            lambda f: f"- {f.project_key}: revenue_impact={f.revenue_impact}, capex={f.capex}, "
            f"opex_annual={f.opex_annual}, discount_rate={f.discount_rate}",
        ),
        "## Products / installed base\n"
        + _lines(
            brief.products_fleet,
            lambda p: f"- {p.product_key} ({p.product}) on {p.platform}: {p.units_in_service} units, "
            f"status {p.status}",
        ),
        "## User-proposed projects (candidates only -- no effort, never ranked)\n"
        + _lines(
            brief.proposed_projects,
            lambda u: f"- {u.key}: {u.name}, proposed by {u.proposed_by}. {u.description}",
        ),
        "## Candidates from prior runs (for continuity -- do not re-discover a dismissed candidate as new)\n"
        + _lines(
            brief.prior_candidates,
            lambda c: f"- {c.key}: {c.name} -- status: {c.status}"
            + (f" ({c.dismissal_reason})" if c.status == "dismissed" else ""),
        ),
        "## Scenarios\n"
        + _lines(brief.scenarios, lambda s: f"- {s.name}: " + ", ".join(f"{k}={v}" for k, v in s.weights.items())),
        "## Rules and thresholds\n" + _lines(brief.rules, lambda r: f"- {r}"),
    ]
    return "\n\n".join(sections)
