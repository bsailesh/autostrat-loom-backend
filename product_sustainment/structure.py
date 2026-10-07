"""
Product Sustainment Agent (Agent 4) — the assembled product structure and
data, as plain data: what was supplied, the operating tier it implies, and
what each absence costs.

DB-free, like tech_regulation/scoping.py: the service layer assembles a
`SustainmentData` from the ps_* tables; tier and degradation logic is
testable here without a database.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from product_sustainment.compute import (
    LEVEL1,
    LEVEL2,
    LRU,
    InventoryRow,
    Pipeline,
    RiskFlag,
    SustainmentInputs,
)
from product_sustainment.evidence import EvidenceFile


@dataclass(frozen=True)
class LruInfo:
    lru_id: str
    lru_name: str = ""
    product_line: str = ""
    program: str = ""
    status: str = ""


@dataclass(frozen=True)
class Level1Info:
    level1_id: str
    level1_name: str = ""
    description: str = ""


@dataclass(frozen=True)
class Level2Info:
    level2_id: str
    level2_name: str = ""
    description: str = ""
    manufacturer: str = ""
    manufacturer_part_number: str = ""


@dataclass(frozen=True)
class RiskRecord:
    part_id: str
    risk_type: str
    risk_detail: str = ""
    source: str = ""
    source_date: str = ""
    lifecycle_status: str = ""
    last_time_buy_date: str = ""
    last_delivery_date: str = ""


@dataclass(frozen=True)
class QualifiedAlternate:
    part_id: str
    alternate_part_id: str
    status: str
    qualified_date: str = ""


@dataclass(frozen=True)
class KnowledgeItem:
    capability: str
    components_affected: str = ""
    people_count: int | None = None
    documentation_status: str = ""


@dataclass(frozen=True)
class Supplier:
    """Read through from Tech & Regulation's supplier watch list (input spec
    Part 10) -- context for research, not an input to the computation."""
    supplier: str
    what_they_supply: str = ""
    criticality: str = ""


@dataclass(frozen=True)
class SustainmentData:
    lrus: list[LruInfo] = field(default_factory=list)
    level1: list[Level1Info] = field(default_factory=list)
    level2: list[Level2Info] = field(default_factory=list)
    lru_l1: dict[str, dict[str, int]] = field(default_factory=dict)
    l1_l2: dict[str, dict[str, int]] = field(default_factory=dict)
    lru_demand: dict[str, dict[int, int]] = field(default_factory=dict)
    direct_demand: dict[tuple[str, str], dict[int, int]] = field(default_factory=dict)
    inventory: list[InventoryRow] = field(default_factory=list)
    inventory_as_of: list[str] = field(default_factory=list)
    pipeline: dict[str, Pipeline] = field(default_factory=dict)
    lead_time_days: dict[str, int] = field(default_factory=dict)
    risks: list[RiskRecord] = field(default_factory=list)
    alternates: list[QualifiedAlternate] = field(default_factory=list)
    knowledge: list[KnowledgeItem] = field(default_factory=list)
    suppliers: list[Supplier] = field(default_factory=list)
    evidence: list[EvidenceFile] = field(default_factory=list)
    fleet_count: int = 0
    maintenance_count: int = 0
    configuration_count: int = 0
    # Whether each file type was uploaded at all.
    demand_supplied: bool = False
    inventory_supplied: bool = False
    pipeline_supplied: bool = False


# ---------------------------------------------------------------------------
# Building compute inputs
# ---------------------------------------------------------------------------


def _parse_date(raw: str) -> date | None:
    try:
        return date.fromisoformat(raw) if raw else None
    except ValueError:
        return None


def start_month(data: SustainmentData, today: date) -> date:
    """Depletion starts from the latest inventory as-of date, or today when
    none is given -- stock counted in March has been drawn on since."""
    dates = [d for d in (_parse_date(s) for s in data.inventory_as_of) if d]
    start = max(dates) if dates else today
    return date(start.year, start.month, 1)


def compute_inputs(data: SustainmentData, today: date) -> SustainmentInputs:
    flags: dict[str, list[RiskFlag]] = {}
    for r in data.risks:
        flags.setdefault(r.part_id, []).append(
            RiskFlag(
                risk_type=r.risk_type,
                lifecycle_status=r.lifecycle_status,
                last_time_buy_date=_parse_date(r.last_time_buy_date),
                last_delivery_date=_parse_date(r.last_delivery_date),
            )
        )
    return SustainmentInputs(
        lrus=[l.lru_id for l in data.lrus],
        level1=[l.level1_id for l in data.level1],
        level2=[l.level2_id for l in data.level2],
        lru_l1=data.lru_l1,
        l1_l2=data.l1_l2,
        lru_demand=data.lru_demand,
        start=start_month(data, today),
        direct_demand=data.direct_demand,
        inventory=data.inventory,
        pipeline=data.pipeline,
        lead_time_days=data.lead_time_days,
        risk_flags=flags,
        demand_supplied=data.demand_supplied,
        inventory_supplied=data.inventory_supplied,
        pipeline_supplied=data.pipeline_supplied,
    )


# ---------------------------------------------------------------------------
# Operating tier
# ---------------------------------------------------------------------------

EXPOSURE_SCAN = "exposure_scan"
TIER_1_PARTIAL = "tier_1_partial"
TIER_1_SUBSTANTIAL = "tier_1_substantial"

TIER_LABELS = {
    EXPOSURE_SCAN: "Obsolescence and exposure scan",
    TIER_1_PARTIAL: "Tier 1 partial",
    TIER_1_SUBSTANTIAL: "Tier 1 substantial",
}

EXPOSURE_SCAN_TITLE = "Obsolescence and exposure scan"

# Substantial = runout computable plus at least this many of the four other
# customer-data analyses (reliability, aging fleet, configuration drift,
# knowledge). A judgement; the spec leaves the line undefined.
SUBSTANTIAL_MIN_OTHER = 3


def runout_enabled(data: SustainmentData) -> bool:
    return bool(data.lru_l1 and data.l1_l2 and data.demand_supplied and (data.inventory_supplied or data.pipeline_supplied))


def _other_analyses(data: SustainmentData) -> dict[str, bool]:
    return {
        "Reliability and failure trends": bool(data.evidence) or data.maintenance_count > 0,
        "Aging fleet analysis": data.fleet_count > 0,
        "Configuration drift": data.configuration_count > 0,
        "Knowledge and capability risk": bool(data.knowledge),
    }


def operating_tier(data: SustainmentData) -> str:
    if not data.lru_l1 and not data.l1_l2:
        return EXPOSURE_SCAN
    if runout_enabled(data) and sum(_other_analyses(data).values()) >= SUBSTANTIAL_MIN_OTHER:
        return TIER_1_SUBSTANTIAL
    return TIER_1_PARTIAL


def report_title(tier: str, title: str) -> str:
    return f"{EXPOSURE_SCAN_TITLE} — {title}" if tier == EXPOSURE_SCAN else title


def run_label(tier: str) -> str:
    return "Obsolescence and Exposure Scan" if tier == EXPOSURE_SCAN else "Product Sustainment"


def operating_tier_statement(data: SustainmentData) -> str:
    tier = operating_tier(data)
    if tier == EXPOSURE_SCAN:
        return (
            "**Operating tier: OBSOLESCENCE AND EXPOSURE SCAN.** No BOM matrices were supplied, so "
            "this run cannot compute any runout date and is NOT a sustainment analysis. It reports "
            "lifecycle status and candidate alternates for the listed parts. Unavailable, and stated as "
            "such: runout dates, last-time-buy timing against demand, the upward cascade to LRUs, "
            "and anything resting on them. Supplying both BOM matrices, demand and inventory is what "
            "converts this into a sustainment analysis."
        )
    enabled = ["Component runout"] if runout_enabled(data) else []
    enabled += [k for k, v in _other_analyses(data).items() if v]
    missing = [i for i in readiness_items(data) if i.status == "missing"]
    head = (
        "**Operating tier: TIER 1 SUBSTANTIAL.**"
        if tier == TIER_1_SUBSTANTIAL
        else "**Operating tier: TIER 1 PARTIAL.**"
    )
    parts = [head, f"Enabled: {', '.join(enabled) or 'none of the customer-data analyses'}."]
    if missing:
        parts.append("Missing, and what each costs: " + "; ".join(f"{i.label} — {i.consequence}" for i in missing))
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Readiness -- input spec Part 9, verbatim consequences
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReadinessItem:
    """`consequence` is empty whenever the item is set (b4f3282)."""
    key: str
    label: str
    status: str  # "set" | "missing"
    count: int
    consequence: str


def readiness_items(data: SustainmentData) -> list[ReadinessItem]:
    a, b = len(data.lru_l1), len(data.l1_l2)
    if not a and not b:
        bom_consequence = "No runout calculation at all. The single most consequential omission."
    elif not a:
        bom_consequence = "LRU to Level 1 matrix missing: Level 1 and Level 2 demand cannot be derived."
    elif not b:
        bom_consequence = (
            "Level 1 to Level 2 matrix missing: component-level exposure cannot be traced; analysis stops "
            "at assembly level."
        )
    else:
        bom_consequence = ""

    rows: list[tuple[str, str, int, bool, str]] = [
        ("bom", "BOM matrices", a + b, bool(a and b), bom_consequence),
        ("demand", "Demand", sum(len(g) for g in data.lru_demand.values()), data.demand_supplied,
         "No runout dates. Risk flags reported without timing — standing context, not schedulable."),
        ("inventory", "Inventory", len(data.inventory), data.inventory_supplied,
         "No runout dates. Risk and exposure reported without position."),
        ("pipeline", "Pipeline quantities", len(data.pipeline), data.pipeline_supplied,
         "Runout computed from on-hand only; stated, and will be pessimistic."),
        ("risk", "Risk flags", len(data.risks), bool(data.risks),
         "Only parts with public EOL notices are flagged; single-source, custom and region exposure invisible."),
        ("lead_times", "Lead times", len(data.lead_time_days), bool(data.lead_time_days),
         "Lead-time assumption check unavailable."),
        ("alternates", "Qualified alternates", len(data.alternates), bool(data.alternates),
         "Phase-out options reported as qualification projects only; the agent cannot know what is already qualified."),
        ("reliability", "Reliability documents", len(data.evidence), bool(data.evidence),
         "No failure clustering, MTBUR or MTTR."),
        ("fleet", "Fleet roster", data.fleet_count, data.fleet_count > 0, "No aging fleet analysis."),
        ("configuration", "Configuration baseline", data.configuration_count, data.configuration_count > 0,
         "No drift analysis."),
        ("knowledge", "Knowledge assessment", len(data.knowledge), bool(data.knowledge), "Unavailable. Not inferred."),
    ]
    return [
        ReadinessItem(key, label, "set" if is_set else "missing", count, "" if is_set else consequence)
        for key, label, count, is_set, consequence in rows
    ]


# ---------------------------------------------------------------------------
# Rendering for the prompt
# ---------------------------------------------------------------------------


def _lines(items, fmt) -> str:
    return "\n".join(fmt(i) for i in items) or "(none supplied)"


# Prompt caps. A real BOM can hold thousands of components and tens of
# thousands of edges; the full set is in the computed tables the platform
# inserts, so the prompt carries every LRU, assembly and LRU->Level 1 edge
# (needed to roll evidence up to LRU level), but Level 2 components and
# their edges only for the parts in focus, with counts for the rest.
PROMPT_MAX_LEVEL1 = 1_000
PROMPT_MAX_LRU_L1_EDGES = 5_000
PROMPT_MAX_FOCUS_PARTS = 400


def _capped(items: list, limit: int, fmt, noun: str) -> str:
    shown = _lines(items[:limit], fmt)
    if len(items) > limit:
        shown += f"\n- ... and {len(items) - limit:,} further {noun}, not listed here (all appear in the computed tables)."
    return shown


def render_structure_text(data: SustainmentData, *, focus_parts: set[str] | None = None) -> str:
    """Customer vocabulary verbatim: ids, locations and forms are quoted back,
    never normalised. The matrices are shown as edges so the model can trace
    a finding to every LRU it reaches -- it never computes with them.

    `focus_parts` (flagged parts, runouts, shortfalls) bounds the Level 2
    detail; None means everything, which is fine for a small BOM."""
    level2 = data.level2 if focus_parts is None else [l for l in data.level2 if l.level2_id in focus_parts]
    level2 = level2[:PROMPT_MAX_FOCUS_PARTS]
    shown_l2 = {l.level2_id for l in level2}
    lru_l1_edges = [(i, j, q) for i, r in sorted(data.lru_l1.items()) for j, q in sorted(r.items())]
    l1_l2_edges = [(j, k, q) for j, r in sorted(data.l1_l2.items()) for k, q in sorted(r.items()) if k in shown_l2]
    omitted_l2 = len(data.level2) - len(level2)
    sections = [
        f"Operating tier: {TIER_LABELS[operating_tier(data)]}.",
        "## LRUs\n" + _lines(
            data.lrus,
            lambda l: f"- {l.lru_id}: {l.lru_name}"
            + (f" — product line {l.product_line}" if l.product_line else "")
            + (f", program {l.program}" if l.program else "")
            + (f", status {l.status}" if l.status else ""),
        ),
        "## Level 1 assemblies\n" + _capped(data.level1, PROMPT_MAX_LEVEL1, lambda l: f"- {l.level1_id}: {l.level1_name}"
                                            + (f" — {l.description}" if l.description else ""), "assemblies"),
        "## Level 2 components (in focus: flagged, running out, or in shortfall)\n" + _lines(
            level2,
            lambda l: f"- {l.level2_id}: {l.level2_name}"
            + (f" — {l.manufacturer}" if l.manufacturer else "")
            + (f" {l.manufacturer_part_number}" if l.manufacturer_part_number else "")
            + (f" ({l.description})" if l.description else ""),
        ) + (f"\n- ... and {omitted_l2:,} further components with no flag, no runout and no shortfall in the horizon "
             "(all appear in the computed tables)." if omitted_l2 else ""),
        "## LRU -> Level 1 (quantity per unit; many-to-many)\n" + _capped(
            lru_l1_edges, PROMPT_MAX_LRU_L1_EDGES, lambda e: f"- {e[0]} contains {e[2]} x {e[1]}", "edges"),
        "## Level 1 -> Level 2 for the components in focus (quantity per unit; many-to-many)\n" + _lines(
            l1_l2_edges, lambda e: f"- {e[0]} contains {e[2]} x {e[1]}"),
    ]
    sections += [
        "## Risk flags (customer-supplied)\n" + _lines(
            data.risks,
            lambda r: f"- {r.part_id}: {r.risk_type}"
            + (f", lifecycle {r.lifecycle_status}" if r.lifecycle_status else "")
            + (f", last-time-buy {r.last_time_buy_date}" if r.last_time_buy_date else "")
            + (f", last delivery {r.last_delivery_date}" if r.last_delivery_date else "")
            + (f" — {r.risk_detail}" if r.risk_detail else "")
            + (f" [source: {r.source}{', ' + r.source_date if r.source_date else ''}]" if r.source else ""),
        ),
        "## Qualified alternates (CUSTOMER-SUPPLIED; the only alternates that may be called qualified)\n"
        + _lines(data.alternates, lambda a: f"- {a.part_id} -> {a.alternate_part_id}: {a.status}"
                 + (f" since {a.qualified_date}" if a.qualified_date else "")),
        "## Supplier watch list (read through from Technology & Regulation)\n" + _lines(
            data.suppliers,
            lambda s: f"- {s.supplier}: {s.what_they_supply}" + (f" ({s.criticality})" if s.criticality else ""),
        ),
        "## Knowledge assessment (customer judgement)\n" + _lines(
            data.knowledge,
            lambda k: f"- {k.capability}"
            + (f" — components: {k.components_affected}" if k.components_affected else "")
            + (f"; people: {k.people_count}" if k.people_count is not None else "")
            + (f"; documentation: {k.documentation_status}" if k.documentation_status else ""),
        ),
        "## What is missing, and what it costs\n" + _lines(
            [i for i in readiness_items(data) if i.status == "missing"],
            lambda i: f"- {i.label}: {i.consequence}",
        ),
    ]
    return "\n\n".join(sections)
