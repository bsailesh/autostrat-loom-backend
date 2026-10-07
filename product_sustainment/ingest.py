"""
Product Sustainment Agent (Agent 4) — structured file ingest.

DB-free: every parser takes CSV text plus the declared part ids and returns
(parsed rows, issues). Any Error blocks that file's ingest entirely; warnings
never block.

**Dangling references are errors, not warnings.** A matrix header or row
label that resolves to no declared part, or demand for an LRU that does not
exist, silently removes demand from the calculation -- the same class of
failure as the bucket-name mismatch in Agent 5's ingest: invisible, and it
corrupts the analysis this agent exists to perform.

Two BOM formats are accepted for each mapping:

  * MATRIX -- what arrives from a spreadsheet. Rows are parts, columns are
    parents, cells are quantity per unit, an empty cell is no relationship:

        LRU,     CCA-MC, CCA-PWR, CCA-SENS        Level2,   CCA-MC, CCA-PWR
        AR-FIN,  1,      1,       1               GaN-650,  ,       6
        AR-TVC,  1,      2,

  * EDGE LIST -- what arrives from a PLM export: one row per relationship
    (lru_id,level1_id,quantity_per_unit or level1_id,level2_id,quantity_per_unit).

Both become the same edges. The matrix is a transport format.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date

LEVELS = ("lru", "level1", "level2")
RISK_TYPES = ("end_of_life", "single_source", "custom", "at_risk_region")
ALTERNATE_STATUSES = ("qualified", "in_qualification", "approved_for_new_design_only")

MATRIX_KINDS = ("lru-level1", "level1-level2")


@dataclass(frozen=True)
class IngestIssue:
    severity: str  # "error" | "warning"
    row: int | None
    field: str
    message: str

    def as_dict(self) -> dict:
        return {"severity": self.severity, "row": self.row, "field": self.field, "message": self.message}


@dataclass(frozen=True)
class DeclaredParts:
    lrus: frozenset[str] = frozenset()
    level1: frozenset[str] = frozenset()
    level2: frozenset[str] = frozenset()

    def of_level(self, level: str) -> frozenset[str]:
        return {"lru": self.lrus, "level1": self.level1, "level2": self.level2}[level]

    @property
    def all(self) -> frozenset[str]:
        return self.lrus | self.level1 | self.level2


def _rows(text: str) -> list[list[str]]:
    return [[c.strip() for c in r] for r in csv.reader(io.StringIO(text)) if any(c.strip() for c in r)]


def _err(row, fld, msg) -> IngestIssue:
    return IngestIssue("error", row, fld, msg)


def _warn(row, fld, msg) -> IngestIssue:
    return IngestIssue("warning", row, fld, msg)


def _non_negative_int(raw: str) -> int | None:
    raw = raw.strip()
    if not re.fullmatch(r"\d+(\.0+)?", raw):
        return None
    return int(float(raw))


# ---------------------------------------------------------------------------
# BOM mappings
# ---------------------------------------------------------------------------


def _matrix_axes(which: str, parts: DeclaredParts) -> tuple[str, frozenset[str], str, frozenset[str]]:
    """(row label noun, row ids, column noun, column ids)."""
    if which == "lru-level1":
        return "LRU", parts.lrus, "Level 1", parts.level1
    return "Level 2", parts.level2, "Level 1", parts.level1


def _edge_columns(which: str) -> tuple[str, str]:
    return ("lru_id", "level1_id") if which == "lru-level1" else ("level1_id", "level2_id")


def parse_mapping(text: str, which: str, parts: DeclaredParts) -> tuple[list[tuple[str, str, int]], list[IngestIssue]]:
    """Edges as (parent, child, qty): for lru-level1 (lru, level1, qty); for
    level1-level2 (level1, level2, qty). Accepts the matrix or an edge list."""
    if which not in MATRIX_KINDS:
        raise ValueError(which)
    rows = _rows(text)
    if not rows:
        return [], [_err(None, "", "The file is empty.")]
    header = [h.lower() for h in rows[0]]
    parent_col, child_col = _edge_columns(which)
    if parent_col in header and child_col in header and "quantity_per_unit" in header:
        return _parse_edge_list(rows, which, parts)
    return _parse_matrix(rows, which, parts)


def _parse_matrix(rows: list[list[str]], which: str, parts: DeclaredParts):
    row_noun, row_ids, col_noun, col_ids = _matrix_axes(which, parts)
    issues: list[IngestIssue] = []
    header = rows[0][1:]
    seen_cols: set[str] = set()
    for c, h in enumerate(header, start=2):
        if not h:
            issues.append(_err(1, f"column {c}", "Blank column header."))
        elif h in seen_cols:
            issues.append(_err(1, h, f"Duplicate column header {h!r}."))
        elif h not in col_ids:
            issues.append(_err(1, h, f"Column header {h!r} is not a declared {col_noun} id. "
                                     "An unresolved reference would silently remove demand."))
        seen_cols.add(h)

    edges: list[tuple[str, str, int]] = []
    seen_rows: set[str] = set()
    for r, row in enumerate(rows[1:], start=2):
        label = row[0] if row else ""
        if not label:
            issues.append(_err(r, "row label", "Blank row label."))
            continue
        if label in seen_rows:
            issues.append(_err(r, label, f"Duplicate row {label!r}."))
        seen_rows.add(label)
        if label not in row_ids:
            issues.append(_err(r, label, f"Row label {label!r} is not a declared {row_noun} id. "
                                         "An unresolved reference would silently remove demand."))
        if len(row) - 1 > len(header):
            issues.append(_err(r, label, "Row has more cells than the header has columns."))
        for c, cell in enumerate(row[1:len(header) + 1]):
            if not cell:
                continue
            qty = _non_negative_int(cell)
            if qty is None:
                issues.append(_err(r, header[c], f"Quantity {cell!r} is not a non-negative integer."))
            elif qty > 0:
                child_or_parent = header[c]
                if which == "lru-level1":
                    edges.append((label, child_or_parent, qty))
                else:
                    edges.append((child_or_parent, label, qty))
    return edges, issues


def _parse_edge_list(rows: list[list[str]], which: str, parts: DeclaredParts):
    parent_col, child_col = _edge_columns(which)
    header = [h.lower() for h in rows[0]]
    pi, ci, qi = header.index(parent_col), header.index(child_col), header.index("quantity_per_unit")
    parent_ids = parts.lrus if which == "lru-level1" else parts.level1
    child_ids = parts.level1 if which == "lru-level1" else parts.level2
    issues: list[IngestIssue] = []
    edges: dict[tuple[str, str], int] = {}
    for r, row in enumerate(rows[1:], start=2):
        get = lambda i: row[i] if i < len(row) else ""
        parent, child, raw = get(pi), get(ci), get(qi)
        if parent not in parent_ids:
            issues.append(_err(r, parent_col, f"{parent!r} is not a declared id. An unresolved reference would silently remove demand."))
        if child not in child_ids:
            issues.append(_err(r, child_col, f"{child!r} is not a declared id. An unresolved reference would silently remove demand."))
        qty = _non_negative_int(raw)
        if qty is None:
            issues.append(_err(r, "quantity_per_unit", f"Quantity {raw!r} is not a non-negative integer."))
            continue
        if (parent, child) in edges:
            issues.append(_err(r, child_col, f"Duplicate relationship {parent} -> {child}."))
        if qty > 0:
            edges[(parent, child)] = qty
    return [(p, c, q) for (p, c), q in edges.items()], issues


def unlinked_part_warnings(
    parts: DeclaredParts,
    lru_l1: list[tuple[str, str, int]],
    l1_l2: list[tuple[str, str, int]],
) -> list[IngestIssue]:
    """Parts appearing in no matrix: a warning, because each will have no
    demand path. Reported in full -- this count is what catches a bad matrix."""
    out = []
    in_a_lru = {p for p, _, _ in lru_l1}
    in_a_l1 = {c for _, c, _ in lru_l1} | {p for p, _, _ in l1_l2}
    in_a_l2 = {c for _, c, _ in l1_l2}
    for lru in sorted(parts.lrus - in_a_lru):
        out.append(_warn(None, lru, f"LRU {lru} contains no Level 1 assembly in the matrix."))
    for j in sorted(parts.level1 - in_a_l1):
        out.append(_warn(None, j, f"Level 1 {j} appears in no matrix; it will have no demand path."))
    for k in sorted(parts.level2 - in_a_l2):
        out.append(_warn(None, k, f"Level 2 {k} appears in no Level 1 assembly; it will have no demand path."))
    return out


def mapping_template(which: str, parts: DeclaredParts) -> str:
    """Generated from the declared ids, so headers are correct by construction."""
    row_noun, row_ids, _, col_ids = _matrix_axes(which, parts)
    first = "LRU" if which == "lru-level1" else "Level2"
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow([first, *sorted(col_ids)])
    for r in sorted(row_ids):
        w.writerow([r, *([""] * len(col_ids))])
    return out.getvalue()


# ---------------------------------------------------------------------------
# Demand grids (wide: one row per part, one column per year)
# ---------------------------------------------------------------------------


def parse_demand(text: str, parts: DeclaredParts) -> tuple[list[tuple[str, int, int]], list[IngestIssue]]:
    """(lru_id, year, qty). A blank cell is ZERO demand that year, not missing
    data -- so blanks produce no row and no issue."""
    rows = _rows(text)
    if not rows:
        return [], [_err(None, "", "The file is empty.")]
    issues: list[IngestIssue] = []
    years: list[int | None] = []
    for h in rows[0][1:]:
        years.append(int(h) if re.fullmatch(r"\d{4}", h) else None)
        if years[-1] is None:
            issues.append(_err(1, h, f"Column header {h!r} is not a four-digit year."))
    out: list[tuple[str, int, int]] = []
    seen: set[str] = set()
    for r, row in enumerate(rows[1:], start=2):
        lru = row[0]
        if lru in seen:
            issues.append(_err(r, lru, f"Duplicate row for LRU {lru!r}."))
        seen.add(lru)
        if lru not in parts.lrus:
            issues.append(_err(r, lru, f"Demand references LRU {lru!r}, which is not in the LRU master. "
                                       "Its demand would be silently dropped."))
        for c, cell in enumerate(row[1:len(years) + 1]):
            if not cell or years[c] is None:
                continue
            qty = _non_negative_int(cell)
            if qty is None:
                issues.append(_err(r, str(years[c]), f"Quantity {cell!r} is not a non-negative integer."))
            elif qty:
                out.append((lru, years[c], qty))
    return out, issues


def parse_direct_demand(text: str, parts: DeclaredParts) -> tuple[list[tuple[str, str, int, int]], list[IngestIssue]]:
    """(part_id, part_level, year, qty). Wide: part_id, part_level, then years."""
    rows = _rows(text)
    if not rows:
        return [], [_err(None, "", "The file is empty.")]
    issues: list[IngestIssue] = []
    head = rows[0]
    if len(head) < 2 or head[0].lower() != "part_id" or head[1].lower() != "part_level":
        return [], [_err(1, "", "Header must start with part_id,part_level followed by year columns.")]
    years = []
    for h in head[2:]:
        years.append(int(h) if re.fullmatch(r"\d{4}", h) else None)
        if years[-1] is None:
            issues.append(_err(1, h, f"Column header {h!r} is not a four-digit year."))
    out = []
    for r, row in enumerate(rows[1:], start=2):
        part, level = row[0], (row[1] if len(row) > 1 else "").lower()
        if level not in LEVELS:
            issues.append(_err(r, "part_level", f"part_level {level!r} must be one of {', '.join(LEVELS)}."))
        elif part not in parts.of_level(level):
            issues.append(_err(r, "part_id", f"{part!r} is not a declared {level} id."))
        for c, cell in enumerate(row[2:len(years) + 2]):
            if not cell or years[c] is None:
                continue
            qty = _non_negative_int(cell)
            if qty is None:
                issues.append(_err(r, str(years[c]), f"Quantity {cell!r} is not a non-negative integer."))
            elif qty:
                out.append((part, level, years[c], qty))
    return out, issues


def demand_template(parts: DeclaredParts, first_year: int, years: int = 6) -> str:
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(["LRU", *[str(first_year + n) for n in range(years)]])
    for lru in sorted(parts.lrus):
        w.writerow([lru, *([""] * years)])
    return out.getvalue()


# ---------------------------------------------------------------------------
# Record files (one row per record)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RecordSpec:
    columns: tuple[str, ...]
    required: tuple[str, ...]
    ints: tuple[str, ...] = ()
    optional_ints: tuple[str, ...] = ()
    enums: dict[str, tuple[str, ...]] = field(default_factory=dict)
    dates: tuple[str, ...] = ()
    # field -> (level or "any", severity). Severity "error" where an
    # unresolved id would corrupt the runout; "warning" where it would not.
    refs: dict[str, tuple[str, str]] = field(default_factory=dict)
    level_field: str | None = None  # for inventory: the part_level column that scopes part_id


RECORD_SPECS: dict[str, RecordSpec] = {
    "inventory": RecordSpec(
        columns=("part_id", "part_level", "location", "form", "quantity", "as_of"),
        required=("part_id", "part_level", "quantity"),
        ints=("quantity",),
        enums={"part_level": LEVELS},
        level_field="part_level",
        refs={"part_id": ("by_level", "error")},
    ),
    "pipeline": RecordSpec(
        columns=("part_id", "open_po_qty", "supplier_qty", "supplier_on_order_qty", "supplier_wip_qty", "as_of"),
        required=("part_id",),
        optional_ints=("open_po_qty", "supplier_qty", "supplier_on_order_qty", "supplier_wip_qty"),
        refs={"part_id": ("any", "error")},
    ),
    "lead-times": RecordSpec(
        columns=("part_id", "lead_time_days"),
        required=("part_id", "lead_time_days"),
        ints=("lead_time_days",),
        refs={"part_id": ("any", "error")},
    ),
    "risk": RecordSpec(
        columns=("part_id", "risk_type", "risk_detail", "source", "source_date", "lifecycle_status",
                 "last_time_buy_date", "last_delivery_date"),
        required=("part_id", "risk_type"),
        enums={"risk_type": RISK_TYPES},
        dates=("last_time_buy_date", "last_delivery_date"),
        # A flag on an undeclared part is still reported (as insufficient
        # data), so it does not corrupt anything -- warn, don't block.
        refs={"part_id": ("any", "warning")},
    ),
    "alternates": RecordSpec(
        columns=("part_id", "alternate_part_id", "status", "qualified_date"),
        required=("part_id", "alternate_part_id", "status"),
        enums={"status": ALTERNATE_STATUSES},
        dates=("qualified_date",),
        refs={"part_id": ("any", "error")},
    ),
    "fleet": RecordSpec(
        columns=("unit_id", "lru_id", "in_service_date", "utilisation", "environment", "operator_segment"),
        required=("unit_id",),
        refs={"lru_id": ("lru", "warning")},
    ),
    "maintenance": RecordSpec(
        columns=("unit_id", "lru_id", "event_date", "event_type", "time_in_service", "downtime"),
        required=("unit_id",),
        refs={"lru_id": ("lru", "warning")},
    ),
    "configuration": RecordSpec(
        columns=("unit_id", "lru_id", "as_maintained_config", "as_designed_baseline"),
        required=("unit_id",),
        refs={"lru_id": ("lru", "warning")},
    ),
}

DATA_FILE_TYPES = ("inventory", "pipeline", "demand", "direct-demand", "risk", "alternates",
                   "lead-times", "fleet", "maintenance", "configuration")


def _valid_iso_date(raw: str) -> bool:
    try:
        date.fromisoformat(raw)
        return True
    except ValueError:
        return False


def parse_records(text: str, file_type: str, parts: DeclaredParts) -> tuple[list[dict], list[IngestIssue]]:
    spec = RECORD_SPECS[file_type]
    rows = _rows(text)
    if not rows:
        return [], [_err(None, "", "The file is empty.")]
    header = [h.lower() for h in rows[0]]
    missing = [c for c in spec.required if c not in header]
    if missing:
        return [], [_err(1, ", ".join(missing), f"Missing required column(s): {', '.join(missing)}. "
                                                f"Expected: {', '.join(spec.columns)}.")]
    issues: list[IngestIssue] = []
    out: list[dict] = []
    for r, raw in enumerate(rows[1:], start=2):
        rec = {c: (raw[header.index(c)] if c in header and header.index(c) < len(raw) else "") for c in spec.columns}
        bad = False
        for c in spec.required:
            if not rec[c]:
                issues.append(_err(r, c, f"{c} is required."))
                bad = True
        for c in spec.ints:
            if rec[c]:
                v = _non_negative_int(rec[c])
                if v is None:
                    issues.append(_err(r, c, f"{c} {rec[c]!r} is not a non-negative integer."))
                    bad = True
                else:
                    rec[c] = v
        for c in spec.optional_ints:
            v = _non_negative_int(rec[c]) if rec[c] else 0
            if v is None:
                issues.append(_err(r, c, f"{c} {rec[c]!r} is not a non-negative integer."))
                bad = True
            else:
                rec[c] = v
        for c, allowed in spec.enums.items():
            if rec[c]:
                rec[c] = rec[c].lower()
                if rec[c] not in allowed:
                    issues.append(_err(r, c, f"{c} {rec[c]!r} must be one of {', '.join(allowed)}."))
                    bad = True
        for c in spec.dates:
            if rec[c] and not _valid_iso_date(rec[c]):
                issues.append(_err(r, c, f"{c} {rec[c]!r} is not an ISO date (YYYY-MM-DD)."))
                bad = True
        for c, (scope, severity) in spec.refs.items():
            value = rec[c]
            if not value:
                continue
            if scope == "by_level":
                level = rec.get(spec.level_field or "", "")
                known = parts.of_level(level) if level in LEVELS else frozenset()
                noun = f"{level} id"
            elif scope == "any":
                known, noun = parts.all, "part id in any master"
            else:
                known, noun = parts.of_level(scope), f"{scope} id"
            if value not in known:
                msg = f"{value!r} is not a declared {noun}."
                issues.append(_err(r, c, msg) if severity == "error" else _warn(r, c, msg))
        if not bad:
            out.append(rec)
    return out, issues


def record_template(file_type: str) -> str:
    return ",".join(RECORD_SPECS[file_type].columns) + "\n"
