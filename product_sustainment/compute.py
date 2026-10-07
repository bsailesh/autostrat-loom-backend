"""
Product Sustainment Agent (Agent 4) — deterministic runout computation.

Pure functions: plain data in, plain data out. No LLM, no database, no I/O,
like strategy_synthesis/compute.py and for the same reason -- a
plausible-looking arithmetic error here drives a six-figure last-time-buy.

**The BOM is a matrix, not a tree.** LRU -> Level 1 and Level 1 -> Level 2
are both many-to-many. Nothing in this module walks the structure from a
root. The two mappings are held as sparse matrices (edges with a quantity)
and every derived figure is a matrix product:

    M[i][k]  = sum_j A[i][j] * B[j][k]        Level 2 per LRU unit, ALL paths summed
    D1[j][y] = sum_i Dlru[i][y] * A[i][j]  + direct1[j][y]
    D2[k][y] = sum_j D1[j][y]   * B[j][k]  + direct2[k][y]

`M` accumulates with `+=` over every (i, j, k) edge pair, so a component
reached through three assemblies in one LRU gets all three contributions,
and an assembly appearing twice in an LRU contributes twice. A traversal
that picks a path, or marks a node visited, undercounts -- the worked
example in the input spec Part 11 is the canonical case: GaN-650 sits only
in CCA-PWR, CCA-PWR is in AR-FIN once and AR-TVC twice, so its draw is
6 x (AR-FIN + 2 x AR-TVC), and AR-FIN alone shows a third of it.

Direct demand at any level flows downward exactly as derived demand does:
LRU direct demand joins the LRU grid, Level 1 direct demand (spare cards)
consumes Level 2 through B.

Arithmetic is exact (`Fraction`): annual demand / 12 is rarely an integer,
and float drift must not be able to move a runout month. Rounding happens
only on the way out -- year-end positions are floored (conservative) and a
quantity required is ceiled (you buy whole units).

Monthly internally, year-end reported. The horizon is the supplied demand
forecast: "through the end of the supplied forecast horizon" is what every
quantity required means, never "through end of life" -- a customer whose
grid stops at 2030 may simply not forecast further.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from fractions import Fraction

LRU = "lru"
LEVEL1 = "level1"
LEVEL2 = "level2"
LEVELS = (LRU, LEVEL1, LEVEL2)

# A runout this many months after the last-time-buy window closes is
# "Watch"; later is "OK". A judgement, not from the spec, and stated in the
# output wherever a status appears.
WATCH_MARGIN_MONTHS = 12

AVERAGE_DAYS_PER_MONTH = Fraction(36525, 1200)  # 30.4375


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InventoryRow:
    part_id: str
    part_level: str  # lru | level1 | level2
    location: str
    form: str
    quantity: int


@dataclass(frozen=True)
class Pipeline:
    open_po_qty: int = 0
    supplier_qty: int = 0  # reported, NOT counted -- see SupplyComposition
    supplier_on_order_qty: int = 0
    supplier_wip_qty: int = 0


@dataclass(frozen=True)
class RiskFlag:
    risk_type: str  # end_of_life | single_source | custom | at_risk_region
    lifecycle_status: str = ""
    last_time_buy_date: date | None = None
    last_delivery_date: date | None = None


@dataclass(frozen=True)
class SustainmentInputs:
    """Everything the computation needs, already resolved.

    `lru_l1[lru][l1]` and `l1_l2[l1][l2]` are the two matrices as sparse
    edge maps. `lru_demand[lru][year]`: a missing year is zero demand, not
    missing data. `direct_demand[(level, part)][year]` is added at that level
    and flows downward."""
    lrus: list[str]
    level1: list[str]
    level2: list[str]
    lru_l1: dict[str, dict[str, int]]
    l1_l2: dict[str, dict[str, int]]
    lru_demand: dict[str, dict[int, int]]
    start: date
    direct_demand: dict[tuple[str, str], dict[int, int]] = field(default_factory=dict)
    inventory: list[InventoryRow] = field(default_factory=list)
    pipeline: dict[str, Pipeline] = field(default_factory=dict)
    lead_time_days: dict[str, int] = field(default_factory=dict)
    risk_flags: dict[str, list[RiskFlag]] = field(default_factory=dict)
    # Whether each input was supplied at all -- absence of a whole file is a
    # different statement from a part missing from a file that exists.
    demand_supplied: bool = True
    inventory_supplied: bool = True
    pipeline_supplied: bool = True


# ---------------------------------------------------------------------------
# Matrix arithmetic
# ---------------------------------------------------------------------------


def composite_lru_l2(
    lru_l1: dict[str, dict[str, int]], l1_l2: dict[str, dict[str, int]]
) -> dict[str, dict[str, int]]:
    """M = A x B: Level 2 quantity per LRU unit, summed over every path.

    Iterates edges, not a tree: for every LRU->L1 edge and every L1->L2
    edge out of that L1, add the product. No path is chosen and nothing is
    skipped as already visited."""
    m: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for i, row in lru_l1.items():
        for j, a in row.items():
            if not a:
                continue
            for k, b in l1_l2.get(j, {}).items():
                if b:
                    m[i][k] += a * b
    return {i: dict(r) for i, r in m.items()}


def _transpose(mat: dict[str, dict[str, int]]) -> dict[str, dict[str, int]]:
    t: dict[str, dict[str, int]] = defaultdict(dict)
    for r, row in mat.items():
        for c, q in row.items():
            if q:
                t[c][r] = q
    return dict(t)


def _add_grid(target: dict[int, Fraction], grid: dict[int, int | Fraction], factor: int | Fraction = 1) -> None:
    for year, qty in grid.items():
        if qty:
            target[year] = target.get(year, Fraction(0)) + Fraction(qty) * factor


@dataclass(frozen=True)
class DemandShare:
    """One source of a part's draw across the horizon: an LRU (through every
    path, `qty_per_unit` summed) or a direct-demand grid."""
    source: str  # an LRU id, or "direct:<level>:<part>"
    qty_per_unit: int  # per LRU unit, all paths summed; 1 for direct demand at this level
    demand_in_horizon: Fraction


def derive_demand(inputs: SustainmentInputs) -> tuple[
    dict[str, dict[int, Fraction]], dict[str, dict[int, Fraction]], dict[str, dict[int, Fraction]]
]:
    """(lru_total, level1, level2) annual demand grids. Direct demand is added
    at its own level and flows downward through the matrices."""
    lru_total: dict[str, dict[int, Fraction]] = {i: {} for i in inputs.lrus}
    for i, grid in inputs.lru_demand.items():
        _add_grid(lru_total.setdefault(i, {}), grid)
    for (level, part), grid in inputs.direct_demand.items():
        if level == LRU:
            _add_grid(lru_total.setdefault(part, {}), grid)

    d1: dict[str, dict[int, Fraction]] = {j: {} for j in inputs.level1}
    for i, row in inputs.lru_l1.items():
        for j, a in row.items():
            _add_grid(d1.setdefault(j, {}), lru_total.get(i, {}), a)
    for (level, part), grid in inputs.direct_demand.items():
        if level == LEVEL1:
            _add_grid(d1.setdefault(part, {}), grid)

    d2: dict[str, dict[int, Fraction]] = {k: {} for k in inputs.level2}
    for j, row in inputs.l1_l2.items():
        for k, b in row.items():
            _add_grid(d2.setdefault(k, {}), d1.get(j, {}), b)
    for (level, part), grid in inputs.direct_demand.items():
        if level == LEVEL2:
            _add_grid(d2.setdefault(part, {}), grid)

    return lru_total, d1, d2


# ---------------------------------------------------------------------------
# Supply
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StockLine:
    location: str
    form: str
    quantity: int


@dataclass(frozen=True)
class SupplyComposition:
    """Available inventory for one part, by where it comes from.

    `total` = on_hand + from_level1 + from_lru + open_po + supplier_on_order
    + supplier_wip, per the input spec §2.2. `supplier_qty` is reported but
    NOT counted: both the spec's formula and the briefing's §4.2 list the four
    pipeline terms without it. Pipeline quantities are treated as arriving
    immediately."""
    on_hand: int
    on_hand_lines: tuple[StockLine, ...]
    from_level1: int  # Level 1 stock x qty per unit (Level 2 parts only)
    from_lru: int  # LRU stock x qty per unit, all paths summed
    open_po: int
    supplier_on_order: int
    supplier_wip: int
    supplier_qty_not_counted: int

    @property
    def total(self) -> int:
        return (
            self.on_hand + self.from_level1 + self.from_lru
            + self.open_po + self.supplier_on_order + self.supplier_wip
        )

    @property
    def pipeline(self) -> int:
        return self.open_po + self.supplier_on_order + self.supplier_wip

    @property
    def pipeline_share(self) -> Fraction:
        return Fraction(self.pipeline, self.total) if self.total else Fraction(0)


def _stock_by_part(inventory: list[InventoryRow]) -> tuple[dict[tuple[str, str], int], dict[tuple[str, str], list[StockLine]]]:
    totals: dict[tuple[str, str], int] = defaultdict(int)
    lines: dict[tuple[str, str], list[StockLine]] = defaultdict(list)
    for row in inventory:
        key = (row.part_level, row.part_id)
        totals[key] += row.quantity
        lines[key].append(StockLine(row.location, row.form, row.quantity))
    return totals, lines


def supply_for(
    level: str,
    part: str,
    inputs: SustainmentInputs,
    stock: dict[tuple[str, str], int],
    stock_lines: dict[tuple[str, str], list[StockLine]],
    l1_parents_of: dict[str, dict[str, int]],
    lru_parents_of_l1: dict[str, dict[str, int]],
    lru_parents_of_l2: dict[str, dict[str, int]],
) -> SupplyComposition:
    """Rolls higher-level stock DOWN through the matrices: twenty spare cards
    with four of a resistor each are eighty resistors."""
    from_l1 = 0
    from_lru = 0
    if level == LEVEL2:
        from_l1 = sum(stock.get((LEVEL1, j), 0) * b for j, b in l1_parents_of.get(part, {}).items())
        from_lru = sum(stock.get((LRU, i), 0) * m for i, m in lru_parents_of_l2.get(part, {}).items())
    elif level == LEVEL1:
        from_lru = sum(stock.get((LRU, i), 0) * a for i, a in lru_parents_of_l1.get(part, {}).items())
    p = inputs.pipeline.get(part, Pipeline())
    return SupplyComposition(
        on_hand=stock.get((level, part), 0),
        on_hand_lines=tuple(stock_lines.get((level, part), [])),
        from_level1=from_l1,
        from_lru=from_lru,
        open_po=p.open_po_qty,
        supplier_on_order=p.supplier_on_order_qty,
        supplier_wip=p.supplier_wip_qty,
        supplier_qty_not_counted=p.supplier_qty,
    )


# ---------------------------------------------------------------------------
# Depletion
# ---------------------------------------------------------------------------


def _months(start: date, end_year: int):
    y, m = start.year, start.month
    while y <= end_year:
        yield y, m
        m += 1
        if m == 13:
            y, m = y + 1, 1


@dataclass(frozen=True)
class Depletion:
    runout: tuple[int, int] | None  # (year, month): first month projected position <= 0
    year_end: dict[int, int]  # projected position at December, floored; negative = shortfall
    demand_in_horizon: Fraction
    shortfall: Fraction  # demand in horizon beyond supply, >= 0


def deplete(supply: int, annual: dict[int, Fraction], start: date, horizon_end: int) -> Depletion:
    """Annual demand spread evenly over twelve months, depleted month by month
    from `start` (months of the start year before it are already past).
    Runout is the first month the position reaches zero or below while there
    is demand -- a part with nothing to draw it down never runs out."""
    position = Fraction(supply)
    runout = None
    year_end: dict[int, int] = {}
    total = Fraction(0)
    for y, m in _months(start, horizon_end):
        monthly = annual.get(y, Fraction(0)) / 12
        if monthly:
            position -= monthly
            total += monthly
            if runout is None and position <= 0:
                runout = (y, m)
        if m == 12:
            year_end[y] = math.floor(position)
    return Depletion(
        runout=runout,
        year_end=year_end,
        demand_in_horizon=total,
        shortfall=max(Fraction(0), total - supply),
    )


def _month_index(y: int, m: int) -> int:
    return y * 12 + (m - 1)


# ---------------------------------------------------------------------------
# Per-part result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LeadTimeCheck:
    status: str  # flagged | clear | not_applicable | unavailable
    message: str


@dataclass(frozen=True)
class PartPosition:
    part_id: str
    level: str
    supply: SupplyComposition
    annual_demand: dict[int, Fraction]
    demand_shares: tuple[DemandShare, ...]  # every LRU and direct source, none omitted
    depletion: Depletion
    quantity_required: int  # ceil(shortfall): units to cover demand through the supplied horizon
    ltb_status: str | None  # critical | watch | ok | None (no LTB date)
    months_runout_after_ltb: int | None  # negative = runout before the window closes
    lead_time: LeadTimeCheck
    affected_level1: tuple[str, ...]
    affected_lrus: tuple[str, ...]
    risk_flags: tuple[RiskFlag, ...]
    no_forecast_demand: bool  # has a demand path, but every year is zero

    @property
    def competing_lrus(self) -> tuple[DemandShare, ...]:
        """In a shortfall, every LRU drawing on this part -- not the first or
        the largest. Which goes unserved is a priority decision nobody has
        stated, so none is chosen."""
        if not self.depletion.shortfall:
            return ()
        return tuple(s for s in self.demand_shares if not s.source.startswith("direct:"))


@dataclass(frozen=True)
class InsufficientPart:
    """No runout date, and the reasons. Listed separately and never dropped:
    a part missing from the report reads as safe."""
    part_id: str
    level: str
    reasons: tuple[str, ...]
    affected_lrus: tuple[str, ...] = ()


@dataclass(frozen=True)
class LruDemandSummary:
    """Every declared LRU, including one with no demand rows at all -- its
    absence from the calculation is a finding, not an omission."""
    lru_id: str
    annual_demand: dict[int, Fraction]
    has_demand_rows: bool


@dataclass(frozen=True)
class SustainmentResult:
    start: date
    horizon_end: int | None
    positions: tuple[PartPosition, ...]
    insufficient: tuple[InsufficientPart, ...]
    lru_summary: tuple[LruDemandSummary, ...]
    parts_without_demand_path: tuple[str, ...]
    notes: tuple[str, ...]


def _ltb(flags: tuple[RiskFlag, ...], runout: tuple[int, int] | None) -> tuple[str | None, int | None]:
    ltb_dates = [f.last_time_buy_date for f in flags if f.last_time_buy_date]
    if not ltb_dates:
        return None, None
    close = min(ltb_dates)
    if runout is None:
        return "ok", None
    after = _month_index(*runout) - _month_index(close.year, close.month)
    if after <= 0:
        return "critical", after
    if after <= WATCH_MARGIN_MONTHS:
        return "watch", after
    return "ok", after


def _lead_time_check(part: str, inputs: SustainmentInputs, supply: SupplyComposition,
                     runout: tuple[int, int] | None) -> LeadTimeCheck:
    days = inputs.lead_time_days.get(part)
    if days is None:
        return LeadTimeCheck("unavailable", "No lead time supplied; the open-PO timing check could not be performed.")
    if runout is None:
        return LeadTimeCheck("clear", "No runout within the forecast horizon.")
    if not supply.pipeline:
        return LeadTimeCheck("not_applicable", "No pipeline quantity is counted, so no arrival timing is assumed.")
    months_out = _month_index(*runout) - _month_index(inputs.start.year, inputs.start.month)
    days_out = months_out * AVERAGE_DAYS_PER_MONTH
    if days_out <= days:
        return LeadTimeCheck(
            "flagged",
            f"Runout falls within the {days}-day lead time. Open-PO and supplier quantities "
            f"({supply.pipeline} units, {round(float(supply.pipeline_share) * 100)}% of supply) were "
            "treated as arriving immediately; that assumption may not hold.",
        )
    return LeadTimeCheck("clear", f"Runout falls beyond the {days}-day lead time.")


def compute_sustainment(inputs: SustainmentInputs) -> SustainmentResult:
    m = composite_lru_l2(inputs.lru_l1, inputs.l1_l2)
    l1_parents_of = _transpose(inputs.l1_l2)  # l2 -> {l1: qty}
    lru_parents_of_l1 = _transpose(inputs.lru_l1)  # l1 -> {lru: qty}
    lru_parents_of_l2 = _transpose(m)  # l2 -> {lru: qty, all paths}
    lru_total, d1, d2 = derive_demand(inputs)
    stock, stock_lines = _stock_by_part(inputs.inventory)

    years = [y for grid in inputs.lru_demand.values() for y in grid]
    years += [y for grid in inputs.direct_demand.values() for y in grid]
    horizon_end = max(years) if years else None

    notes = [
        f"Depletion runs month by month from {inputs.start:%B %Y}; annual demand is spread evenly over "
        "twelve months, and months of the start year before that are treated as past.",
        "Pipeline quantities (open POs, supplier on-order, supplier WIP) are counted as available on "
        "arrival immediately. Supplier quantity is reported but not counted.",
        "Quantities required cover demand through the end of the supplied forecast horizon"
        + (f" ({horizon_end})" if horizon_end else "")
        + " -- not necessarily through end of life. If the product is supported beyond the horizon, "
        "a last-time-buy sized on these figures is too small.",
        f"Last-time-buy status: Critical = runout on or before the window closes; Watch = runout within "
        f"{WATCH_MARGIN_MONTHS} months after it closes; OK = later, or no runout in the horizon. The "
        f"{WATCH_MARGIN_MONTHS}-month margin is a platform convention, not a customer setting.",
    ]
    if not inputs.pipeline_supplied:
        notes.append("No pipeline data was supplied: runout is computed from on-hand stock only, and is pessimistic.")

    def has_record(level: str, part: str) -> bool:
        if stock.get((level, part)) is not None or part in inputs.pipeline:
            return True
        if level == LEVEL2:
            if any((LEVEL1, j) in stock for j in l1_parents_of.get(part, {})):
                return True
            return any((LRU, i) in stock for i in lru_parents_of_l2.get(part, {}))
        if level == LEVEL1:
            return any((LRU, i) in stock for i in lru_parents_of_l1.get(part, {}))
        return False

    # Each LRU's demand within the horizon, once. A part's share from that LRU
    # is this times its all-paths quantity per unit -- linear, so there is no
    # need to re-run a depletion per part per LRU (which took a minute on a
    # 4,000-component BOM).
    lru_horizon: dict[str, Fraction] = {
        i: (deplete(0, grid, inputs.start, horizon_end).demand_in_horizon if horizon_end else Fraction(0))
        for i, grid in lru_total.items()
    }

    positions: list[PartPosition] = []
    insufficient: list[InsufficientPart] = []
    no_path: list[str] = []

    candidates = [(LEVEL1, j) for j in inputs.level1] + [(LEVEL2, k) for k in inputs.level2]
    for level, part in candidates:
        if level == LEVEL2:
            l1s = l1_parents_of.get(part, {})
            lrus = lru_parents_of_l2.get(part, {})
            annual = d2.get(part, {})
            direct_here = (LEVEL2, part) in inputs.direct_demand
            direct_above = any((LEVEL1, j) in inputs.direct_demand for j in l1s)
        else:
            l1s = {}
            lrus = lru_parents_of_l1.get(part, {})
            annual = d1.get(part, {})
            direct_here = (LEVEL1, part) in inputs.direct_demand
            direct_above = False
        affected_lrus = tuple(sorted(lrus))

        reasons: list[str] = []
        if level == LEVEL2 and not l1s:
            reasons.append("No BOM link: this component appears in no Level 1 assembly.")
        if not lrus and not direct_here and not direct_above:
            if level == LEVEL1 or l1s:
                reasons.append("No demand path: no LRU consumes it through the matrices, and no direct demand is supplied.")
            no_path.append(part)
        if not inputs.demand_supplied:
            reasons.append("No demand forecast was supplied.")
        if not inputs.inventory_supplied and not inputs.pipeline_supplied:
            reasons.append("No inventory or pipeline data was supplied.")
        elif not has_record(level, part):
            reasons.append("No inventory or pipeline record for this part or any assembly or LRU containing it.")
        if horizon_end is None and inputs.demand_supplied:
            reasons.append("The demand forecast contains no years.")
        if reasons:
            insufficient.append(InsufficientPart(part, level, tuple(dict.fromkeys(reasons)), affected_lrus))
            continue

        supply = supply_for(level, part, inputs, stock, stock_lines, l1_parents_of, lru_parents_of_l1, lru_parents_of_l2)
        dep = deplete(supply.total, annual, inputs.start, horizon_end)

        shares: list[DemandShare] = []
        for i, qty in sorted(lrus.items()):
            shares.append(DemandShare(i, qty, lru_horizon[i] * qty))
        if direct_here:
            grid: dict[int, Fraction] = {}
            _add_grid(grid, inputs.direct_demand[(level, part)])
            shares.append(DemandShare(f"direct:{level}:{part}", 1, deplete(0, grid, inputs.start, horizon_end).demand_in_horizon))
        for j, b in sorted(l1s.items()):
            if (LEVEL1, j) in inputs.direct_demand:
                grid = {}
                _add_grid(grid, inputs.direct_demand[(LEVEL1, j)], b)
                shares.append(DemandShare(f"direct:{LEVEL1}:{j}", b, deplete(0, grid, inputs.start, horizon_end).demand_in_horizon))

        flags = tuple(inputs.risk_flags.get(part, ()))
        ltb_status, after = _ltb(flags, dep.runout)
        positions.append(
            PartPosition(
                part_id=part,
                level=level,
                supply=supply,
                annual_demand=dict(annual),
                demand_shares=tuple(shares),
                depletion=dep,
                quantity_required=math.ceil(dep.shortfall),
                ltb_status=ltb_status,
                months_runout_after_ltb=after,
                lead_time=_lead_time_check(part, inputs, supply, dep.runout),
                affected_level1=tuple(sorted(l1s)),
                affected_lrus=affected_lrus,
                risk_flags=flags,
                no_forecast_demand=dep.demand_in_horizon == 0,
            )
        )

    # Risk flags on parts that are in no master are still reported, never
    # silently dropped.
    known = set(inputs.lrus) | set(inputs.level1) | set(inputs.level2)
    for part in sorted(set(inputs.risk_flags) - known):
        insufficient.append(InsufficientPart(part, "unknown", ("Risk-flagged, but not in any part master.",)))

    lru_summary = tuple(
        LruDemandSummary(i, dict(lru_total.get(i, {})), bool(inputs.lru_demand.get(i)))
        for i in inputs.lrus
    )
    return SustainmentResult(
        start=inputs.start,
        horizon_end=horizon_end,
        positions=tuple(positions),
        insufficient=tuple(insufficient),
        lru_summary=lru_summary,
        parts_without_demand_path=tuple(no_path),
        notes=tuple(notes),
    )


def cascade(part: str, level: str, lru_l1: dict[str, dict[str, int]], l1_l2: dict[str, dict[str, int]]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(affected Level 1, affected LRUs) for an at-risk part, through the
    matrices. Used for evidence roll-up and risk flags on parts with no
    position."""
    if level == LEVEL2:
        l1s = sorted(j for j, row in l1_l2.items() if row.get(part))
        lrus = sorted(i for i, row in lru_l1.items() if any(row.get(j) for j in l1s))
        return tuple(l1s), tuple(lrus)
    if level == LEVEL1:
        return (), tuple(sorted(i for i, row in lru_l1.items() if row.get(part)))
    return (), (part,)
