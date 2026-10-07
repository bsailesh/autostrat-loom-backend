"""
Product Sustainment Agent (Agent 4) — computed results as text and tables.

Every number a reader acts on comes from compute.py, and reaches the report
through THIS module, never through the model. The model is given the
results to interpret; the tables below are generated in code and inserted
into the reports verbatim after the model's narrative. A model asked to copy
four thousand numbers into a table is a model asked to make transcription
errors, on the output most likely to drive a last-time-buy.

The table header rows are the exhibit contract the frontend renderers match
on (frontend/src/productSustainment/exhibits/). Changing one is a breaking
change there.
"""
from __future__ import annotations

from fractions import Fraction

from product_sustainment.compute import (
    LEVEL2,
    cascade,
    composite_lru_l2,
    WATCH_MARGIN_MONTHS,
    PartPosition,
    SustainmentResult,
)
from product_sustainment.structure import SustainmentData

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

RUNOUT_TABLE_FIXED_HEADERS = (
    "Component", "Level", "Description", "On hand", "From higher-level stock", "Open POs", "Supplier on order",
    "Supplier WIP", "Counted supply", "Supplier qty (not counted)", "Runout", "LTB status", "Qty required", "Risk type", "Lifecycle status",
    "Affected LRUs", "Product lines", "Programs",
)
# Followed by one "End YYYY" column per projection year.

DEPLETION_TABLE_HEADERS = "| Component | Year | Position |"
EXPOSURE_TABLE_HEADERS = "| Component | Assembly | LRU | Qty per LRU unit |"
COMPETING_TABLE_HEADERS = "| Component | Competing LRUs (every one; no allocation assumed) | Quantity required |"
INSUFFICIENT_TABLE_HEADERS = "| Part | Level | Reasons | Affected LRUs |"

LTB_LABELS = {"critical": "Critical", "watch": "Watch", "ok": "OK", None: "No LTB date"}


def month_label(runout: tuple[int, int] | None) -> str:
    return f"{MONTHS[runout[1] - 1]} {runout[0]}" if runout else "Not within horizon"


def _num(f: Fraction | int) -> str:
    return f"{round(float(f)):,}"


def _cell(s: str) -> str:
    return str(s).replace("|", "/").replace("\n", " ")


def _risk_cells(p: PartPosition) -> tuple[str, str]:
    return (
        ", ".join(sorted({f.risk_type for f in p.risk_flags})) or "—",
        ", ".join(sorted({f.lifecycle_status for f in p.risk_flags if f.lifecycle_status})) or "—",
    )


def _lru_attrs(data: SustainmentData, lrus: tuple[str, ...]) -> tuple[str, str]:
    by_id = {l.lru_id: l for l in data.lrus}
    lines = sorted({by_id[i].product_line for i in lrus if i in by_id and by_id[i].product_line})
    programs = sorted({by_id[i].program for i in lrus if i in by_id and by_id[i].program})
    return ", ".join(lines) or "—", ", ".join(programs) or "—"


def _description(data: SustainmentData, p: PartPosition) -> str:
    if p.level == LEVEL2:
        info = next((l for l in data.level2 if l.level2_id == p.part_id), None)
        return (info.level2_name or info.description) if info else ""
    info = next((l for l in data.level1 if l.level1_id == p.part_id), None)
    return (info.level1_name or info.description) if info else ""


def _sort_key(p: PartPosition):
    order = {"critical": 0, "watch": 1, "ok": 2, None: 3}
    runout = p.depletion.runout or (9999, 12)
    return (order[p.ltb_status], runout, p.part_id)


def years_of(result: SustainmentResult) -> list[int]:
    if result.horizon_end is None:
        return []
    return list(range(result.start.year, result.horizon_end + 1))


# Report caps. A report is markdown that is stored, rendered, exported and
# read by Agent 5 as upstream text, so a 4,000-component table (over 1MB)
# cannot go in it whole. Reports carry the most urgent rows -- sorted
# Critical, Watch, OK, then runout soonest -- and say how many more there
# are; the complete set is stored on the run (runout_rows) and served by
# GET /agents/product-sustainment/runs/{id}/runout. The insufficient-data
# list is NEVER capped: a part missing from it reads as safe.
REPORT_MAX_RUNOUT_ROWS = 200
REPORT_MAX_COMPETING_ROWS = 100
REPORT_MAX_LRUS_PER_CELL = 20
REPORT_MAX_CHART_PARTS = 50


def _lru_cell(lrus: tuple[str, ...]) -> str:
    if not lrus:
        return "—"
    shown = ", ".join(lrus[:REPORT_MAX_LRUS_PER_CELL])
    more = len(lrus) - REPORT_MAX_LRUS_PER_CELL
    return shown + (f" (+{more} more in the full table)" if more > 0 else "")


def runout_rows(result: SustainmentResult, data: SustainmentData) -> list[dict]:
    """Every position, as plain rows -- persisted for the full filterable view."""
    years = years_of(result)
    rows = []
    for p in sorted(result.positions, key=_sort_key):
        risk, lifecycle = _risk_cells(p)
        product_lines, programs = _lru_attrs(data, p.affected_lrus)
        s = p.supply
        rows.append({
            "component": p.part_id, "level": p.level, "description": _description(data, p),
            "on_hand": s.on_hand, "from_higher_level_stock": s.from_level1 + s.from_lru, "open_po": s.open_po,
            "supplier_qty": s.supplier_qty_not_counted, "supplier_on_order": s.supplier_on_order,
            "supplier_wip": s.supplier_wip, "counted_supply": s.total, "runout": month_label(p.depletion.runout),
            "runout_year": p.depletion.runout[0] if p.depletion.runout else None,
            "runout_month": p.depletion.runout[1] if p.depletion.runout else None,
            "ltb_status": LTB_LABELS[p.ltb_status], "quantity_required": p.quantity_required,
            "risk_type": risk, "lifecycle_status": lifecycle, "affected_lrus": list(p.affected_lrus),
            "product_lines": product_lines, "programs": programs,
            "end_inventory": {str(y): p.depletion.year_end.get(y, 0) for y in years},
            "lead_time_check": p.lead_time.status,
        })
    return rows


def runout_table(result: SustainmentResult, data: SustainmentData, limit: int | None = REPORT_MAX_RUNOUT_ROWS) -> str:
    years = years_of(result)
    headers = list(RUNOUT_TABLE_FIXED_HEADERS) + [f"End {y}" for y in years]
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    ordered = sorted(result.positions, key=_sort_key)
    for p in ordered[:limit]:
        risk, lifecycle = _risk_cells(p)
        product_lines, programs = _lru_attrs(data, p.affected_lrus)
        s = p.supply
        cells = [
            p.part_id, p.level, _description(data, p), _num(s.on_hand), _num(s.from_level1 + s.from_lru),
            _num(s.open_po), _num(s.supplier_on_order), _num(s.supplier_wip), _num(s.total),
            _num(s.supplier_qty_not_counted),
            month_label(p.depletion.runout), LTB_LABELS[p.ltb_status], _num(p.quantity_required),
            risk, lifecycle, _lru_cell(p.affected_lrus), product_lines, programs,
        ] + [_num(p.depletion.year_end.get(y, 0)) for y in years]
        lines.append("| " + " | ".join(_cell(c) for c in cells) + " |")
    if limit is not None and len(ordered) > limit:
        lines.append("")
        lines.append(
            f"_Showing the {limit:,} most urgent of {len(ordered):,} components (Critical, Watch, OK, then runout "
            f"soonest). The other {len(ordered) - limit:,} are in the full runout table for this run._"
        )
    return "\n".join(lines)


def depletion_table(result: SustainmentResult, parts: list[str] | None = None) -> str:
    """Long format, one row per component per year -- the depletion chart.
    The most urgent REPORT_MAX_CHART_PARTS only: a chart of thousands of
    lines shows nothing."""
    lines = [DEPLETION_TABLE_HEADERS, "|---|---|---|"]
    chosen = [p for p in sorted(result.positions, key=_sort_key) if parts is None or p.part_id in parts]
    for p in chosen[:REPORT_MAX_CHART_PARTS]:
        for y in years_of(result):
            lines.append(f"| {p.part_id} | {y} | {p.depletion.year_end.get(y, 0)} |")
    return "\n".join(lines)


def exposure_table(result: SustainmentResult, data: SustainmentData, parts: list[str]) -> str:
    """Which LRUs each flagged component reaches, through which assemblies."""
    lines = [EXPOSURE_TABLE_HEADERS, "|---|---|---|---|"]
    by_id = {p.part_id: p for p in result.positions}
    level2_ids = {l.level2_id for l in data.level2}
    # Positioned parts first, most urgent first; then flagged parts with no
    # position (no inventory, say) -- their exposure through the BOM is real
    # even without a runout date, so it comes straight from the matrices.
    ordered = sorted((by_id[x] for x in parts if x in by_id and by_id[x].level == LEVEL2), key=_sort_key)
    unpositioned = [x for x in parts if x not in by_id and x in level2_ids]
    composite = composite_lru_l2(data.lru_l1, data.l1_l2) if unpositioned else {}
    entries = [(p.part_id, p.affected_level1,
                {s.source: s.qty_per_unit for s in p.demand_shares if not s.source.startswith("direct:")})
               for p in ordered]
    for part in unpositioned:
        level1, lrus = cascade(part, LEVEL2, data.lru_l1, data.l1_l2)
        entries.append((part, level1, {i: composite.get(i, {}).get(part, 0) for i in lrus}))
    for part, level1, per_lru in entries[:REPORT_MAX_CHART_PARTS]:
        for j in level1:
            for i in sorted(per_lru):
                if data.lru_l1.get(i, {}).get(j):
                    lines.append(f"| {part} | {j} | {i} | {per_lru[i]} |")
    return "\n".join(lines)


def competing_table(result: SustainmentResult, limit: int | None = REPORT_MAX_COMPETING_ROWS) -> str:
    """One row per component in shortfall, naming EVERY competing LRU."""
    lines = [COMPETING_TABLE_HEADERS, "|---|---|---|"]
    short = [p for p in sorted(result.positions, key=_sort_key) if p.competing_lrus]
    for p in short[:limit]:
        lrus = "; ".join(
            f"{s.source} ({s.qty_per_unit}/unit, {_num(s.demand_in_horizon)} through horizon)" for s in p.competing_lrus
        )
        lines.append(f"| {p.part_id} | {_cell(lrus)} | {_num(p.quantity_required)} |")
    if limit is not None and len(short) > limit:
        lines.append(f"\n_{len(short) - limit:,} further components in shortfall are in the full runout table._")
    return "\n".join(lines)


def insufficient_table(result: SustainmentResult) -> str:
    lines = [INSUFFICIENT_TABLE_HEADERS, "|---|---|---|---|"]
    for p in result.insufficient:
        lines.append(
            f"| {p.part_id} | {p.level} | {_cell(' '.join(p.reasons))} | {', '.join(p.affected_lrus) or '—'} |"
        )
    return "\n".join(lines)


# Prompt caps: full detail for the parts in focus; the complete set is always
# in the computed tables the platform inserts into the reports.
PROMPT_MAX_POSITIONS = 120
PROMPT_MAX_INSUFFICIENT = 300


PROMPT_MAX_LIST = 10


def _first(items, sep: str = ", ") -> str:
    items = list(items)
    if not items:
        return "none"
    shown = sep.join(items[:PROMPT_MAX_LIST])
    return shown + (f"{sep}... (+{len(items) - PROMPT_MAX_LIST} more)" if len(items) > PROMPT_MAX_LIST else "")


def focus_parts(result: SustainmentResult, data: SustainmentData) -> set[str]:
    """Parts whose position matters to a reader: flagged, running out within
    the horizon, in shortfall, or with the lead-time check firing."""
    focus = set(flagged_parts(result, data))
    for p in result.positions:
        if p.quantity_required or p.lead_time.status == "flagged":
            focus.add(p.part_id)
    return focus


def flagged_parts(result: SustainmentResult, data: SustainmentData) -> list[str]:
    """Report 2's scope: every part with a risk flag or a non-Active
    lifecycle status, plus any part whose runout falls inside the horizon."""
    flagged = {r.part_id for r in data.risks}
    flagged |= {p.part_id for p in result.positions if p.depletion.runout}
    return sorted(flagged)


def computed_section(kind: str, result: SustainmentResult, data: SustainmentData) -> str:
    """The code-generated block appended to a report. Never model output."""
    note = "_Computed by the platform from the supplied data; not written by the model._"
    if kind == "runout":
        body = [
            "## Component runout table (computed)", note, "",
            runout_table(result, data) if result.positions else "No component has a computable runout position.",
            "", "## Competing demand (computed)",
            "Every LRU drawing on a component in shortfall. No allocation is assumed: which LRU goes "
            "unserved is a priority decision nobody has stated.", "",
            competing_table(result) if any(p.competing_lrus for p in result.positions) else "No component is in shortfall within the horizon.",
            "", "## Insufficient data — no runout date (computed)",
            "Listed, never omitted: a part missing from this report would read as safe.", "",
            insufficient_table(result) if result.insufficient else "None.",
            "", "## How these figures were computed", *[f"- {n}" for n in result.notes],
        ]
        return "\n".join(body)
    if kind == "obsolescence":
        parts = flagged_parts(result, data)
        positioned = [p for p in result.positions if p.part_id in parts]
        sub = SustainmentResult(result.start, result.horizon_end, tuple(positioned),
                                tuple(i for i in result.insufficient if i.part_id in parts),
                                result.lru_summary, (), result.notes)
        return "\n".join([
            "## Flagged components (computed)", note, "",
            runout_table(sub, data) if positioned else "No flagged component has a computable position.",
            "", "## Flagged components without a runout date (computed)", "",
            insufficient_table(sub) if sub.insufficient else "None.",
        ])
    if kind == "single_source":
        parts = sorted({r.part_id for r in data.risks if r.risk_type in ("single_source", "custom", "at_risk_region")})
        return "\n".join([
            "## Dependency and exposure map (computed)", note,
            "Single-source, custom and at-risk-region components, and every LRU each reaches through every "
            "assembly.", "",
            exposure_table(result, data, parts) if parts else "No single-source, custom or at-risk-region flags supplied.",
        ])
    if kind == "dashboard":
        parts = flagged_parts(result, data)
        return "\n".join([
            "## Inventory depletion (computed)", note, "",
            depletion_table(result, parts) if result.positions else "No positions to chart.",
            "", "## Dependency and exposure (computed)", "",
            exposure_table(result, data, parts),
        ])
    raise ValueError(kind)


def render_results_text(result: SustainmentResult, data: SustainmentData) -> str:
    """The computation, for the model to interpret. Exact numbers, stated
    once; the model quotes them and never recomputes them."""
    if not result.positions and not result.insufficient:
        return "No runout computation was possible: no BOM matrices were supplied."
    lines = [
        f"Projection: {result.start:%B %Y} to December {result.horizon_end}." if result.horizon_end
        else "No demand forecast years were supplied.",
        *[f"- {n}" for n in result.notes],
        "",
        "## Positions in focus (flagged, running out, or in shortfall; sorted Critical, Watch, OK, no LTB; "
        "then runout soonest)",
    ]
    focus = focus_parts(result, data)
    in_focus = [p for p in sorted(result.positions, key=_sort_key) if p.part_id in focus]
    rest = len(result.positions) - len(in_focus)
    for p in in_focus[:PROMPT_MAX_POSITIONS]:
        s = p.supply
        lines.append(
            f"- {p.part_id} ({p.level}): runout {month_label(p.depletion.runout)}; "
            f"LTB status {LTB_LABELS[p.ltb_status]}"
            + (f" ({p.months_runout_after_ltb:+d} months vs window close)" if p.months_runout_after_ltb is not None else "")
            + f"; supply {s.total:,} = on hand {s.on_hand:,} + from Level 1 stock {s.from_level1:,} + from LRU stock "
            f"{s.from_lru:,} + open POs {s.open_po:,} + supplier on-order {s.supplier_on_order:,} + supplier WIP "
            f"{s.supplier_wip:,} ({round(float(s.pipeline_share) * 100)}% rests on orders)"
            f"; demand through horizon {_num(p.depletion.demand_in_horizon)}; quantity required "
            f"{p.quantity_required:,}; affected LRUs ({len(p.affected_lrus)}) {_first(p.affected_lrus)}"
            f"; via assemblies ({len(p.affected_level1)}) {_first(p.affected_level1)}"
            f"; lead-time check: {p.lead_time.status} — {p.lead_time.message}"
            + ("; NO FORECAST DEMAND on any path" if p.no_forecast_demand else "")
        )
        if p.competing_lrus:
            lines.append(
                f"    competing LRUs ({len(p.competing_lrus)}, every one in the computed table): " + _first([
                    f"{c.source} ({c.qty_per_unit} per unit, {_num(c.demand_in_horizon)} through horizon)"
                    for c in p.competing_lrus
                ], sep="; ")
            )
    if len(in_focus) > PROMPT_MAX_POSITIONS:
        lines.append(f"- ... and {len(in_focus) - PROMPT_MAX_POSITIONS:,} further positions in focus, in the computed runout table.")
    if rest:
        lines.append(
            f"- {rest:,} further components have no flag, no runout and no shortfall within the horizon; they are "
            "in the computed runout table."
        )
    lines += ["", "## Insufficient data (no runout date; must be listed, never omitted)"]
    lines += [f"- {p.part_id} ({p.level}): {' '.join(p.reasons)}"
              for p in result.insufficient[:PROMPT_MAX_INSUFFICIENT]] or ["- none"]
    if len(result.insufficient) > PROMPT_MAX_INSUFFICIENT:
        by_reason: dict[str, int] = {}
        for p in result.insufficient[PROMPT_MAX_INSUFFICIENT:]:
            for r in p.reasons:
                by_reason[r] = by_reason.get(r, 0) + 1
        lines.append(
            f"- ... and {len(result.insufficient) - PROMPT_MAX_INSUFFICIENT:,} further parts, all listed in the computed "
            "table. Reasons among them: " + "; ".join(f"{r} ({n:,})" for r, n in sorted(by_reason.items()))
        )
    lines += ["", "## LRU demand (every LRU, including those with no forecast)"]
    for s in result.lru_summary:
        total = sum(s.annual_demand.values(), Fraction(0))
        lines.append(f"- {s.lru_id}: " + (f"{_num(total)} across the forecast" if s.has_demand_rows else "NO demand rows supplied"))
    lines.append(
        f"\nWatch margin: {WATCH_MARGIN_MONTHS} months after the last-time-buy window closes. State this "
        "wherever a status appears."
    )
    return "\n".join(lines)


def candidate_work_table(items) -> str:
    """Report 1's consolidated list, from the validated, merged items --
    ordered by date, soonest first, which is factual; never by importance."""
    from product_sustainment.reports import CANDIDATE_WORK_TABLE_HEADERS

    def key(i):
        return (i.work_date is None, i.work_date or "", i.candidate_key)

    lines = [
        "## Candidate work (computed)",
        "_Dates, quantities and affected LRUs computed by the platform; drivers and work implied from the "
        "agent's research. Candidate alternates are candidates for qualification, never qualified._",
        "",
    ]
    if not items:
        return "\n".join(lines + ["No candidate work was surfaced in this run."])
    lines += [CANDIDATE_WORK_TABLE_HEADERS, "|" + "---|" * 11]
    for i in sorted(items, key=key):
        cands = ", ".join(f"{a['part_number']} (candidate)" for a in i.candidate_alternates) or "—"
        lines.append("| " + " | ".join(_cell(c) for c in [
            i.candidate_key, i.part_id, i.driver, i.work_date or "none established", i.date_basis,
            f"{i.quantity_required:,}" if i.quantity_required is not None else "not computable",
            ", ".join(i.applicability.get("lrus", [])) or "—",
            i.qualified_alternate_part_id or "—", cands, i.work_implied, i.confidence,
        ]) + " |")
    return "\n".join(lines)
