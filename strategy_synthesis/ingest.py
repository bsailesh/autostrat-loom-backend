"""
Strategy Synthesis agent (Agent 5) — CSV ingest: parse and validate.

Pure functions, like compute.py: CSV text and reference data in (declared
bucket keys, known project keys -- both already queried by the caller),
parsed rows and issues out. No database access, no file I/O. This is what
makes the bucket-name mismatch test ("agent5_build_briefing.md" Part 7)
possible without a database.

Severity model: an Error anywhere in a file blocks that file's entire
ingest -- nothing is written, whatever was previously stored stays exactly
as it was. A Warning never blocks; the file is stored and the warning is
carried along for display. Nothing here ever blocks a run -- callers just
see whatever is currently stored, one file_type at a time.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IngestIssue:
    severity: str  # "error" | "warning"
    row: Optional[int]  # 1-indexed CSV data row (header excluded); None for file-level
    field: Optional[str]
    message: str  # names both sides of any mismatch


def _rows(text: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


def _get_float(row: dict, key: str) -> Optional[float]:
    raw = (row.get(key) or "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _get_bool(row: dict, key: str) -> bool:
    return (row.get(key) or "").strip().lower() in ("true", "yes", "1")


# ---------------------------------------------------------------------------
# roadmap.csv -> PortfolioProject + ProjectEffortRow
# ---------------------------------------------------------------------------

_REMAINING_PREFIX = "effort_remaining_"
_TOTAL_PREFIX = "effort_total_"

# Two figures diverging by more than this many percentage points is a
# real, worth-surfacing inconsistency -- not exact-equality, since these
# are independently-supplied, approximate figures.
_PCT_COMPLETE_TOLERANCE = 10.0


@dataclass(frozen=True)
class ParsedRoadmapRow:
    project_key: str
    name: str
    project_type: str
    status: str
    pct_complete: Optional[float]
    effort_remaining: dict[str, float]  # bucket_key -> effort_remaining
    effort_total: dict[str, float]  # bucket_key -> effort_total (only where supplied)
    target_gate: str
    target_fy: str
    owner: str
    mandatory: bool
    mandatory_driver: str
    mandatory_deadline: str


def parse_roadmap_csv(
    text: str, declared_bucket_keys: set[str]
) -> tuple[list[ParsedRoadmapRow], list[IngestIssue]]:
    raw_rows = _rows(text)
    issues: list[IngestIssue] = []

    if not raw_rows:
        return [], issues

    header = list(raw_rows[0].keys())
    remaining_cols = {h: h[len(_REMAINING_PREFIX):] for h in header if h.startswith(_REMAINING_PREFIX)}
    total_cols = {h: h[len(_TOTAL_PREFIX):] for h in header if h.startswith(_TOTAL_PREFIX)}

    declared_sorted = ", ".join(sorted(declared_bucket_keys))
    for col, bucket_key in sorted(remaining_cols.items()):
        if bucket_key not in declared_bucket_keys:
            issues.append(
                IngestIssue(
                    severity="error",
                    row=None,
                    field=col,
                    message=(
                        f"Roadmap column '{col}' does not match any declared bucket. "
                        f"Declared buckets: {declared_sorted}."
                    ),
                )
            )
    for col, bucket_key in sorted(total_cols.items()):
        if bucket_key not in declared_bucket_keys:
            issues.append(
                IngestIssue(
                    severity="error",
                    row=None,
                    field=col,
                    message=(
                        f"Roadmap column '{col}' does not match any declared bucket. "
                        f"Declared buckets: {declared_sorted}."
                    ),
                )
            )

    if any(i.severity == "error" for i in issues):
        return [], issues

    parsed: list[ParsedRoadmapRow] = []
    for i, row in enumerate(raw_rows, start=1):
        project_key = (row.get("project_id") or "").strip()

        effort_remaining: dict[str, float] = {}
        for col, bucket_key in remaining_cols.items():
            value = _get_float(row, col)
            if value is not None:
                effort_remaining[bucket_key] = value

        effort_total: dict[str, float] = {}
        for col, bucket_key in total_cols.items():
            value = _get_float(row, col)
            if value is not None:
                effort_total[bucket_key] = value

        # Per-bucket sanity: remaining cannot exceed total where both given.
        for bucket_key in sorted(set(effort_remaining) & set(effort_total)):
            remaining = effort_remaining[bucket_key]
            total = effort_total[bucket_key]
            if total > 0 and remaining > total:
                issues.append(
                    IngestIssue(
                        severity="warning",
                        row=i,
                        field=bucket_key,
                        message=(
                            f"Project {project_key}, bucket {bucket_key}: "
                            f"effort_remaining ({remaining:g}) exceeds effort_total ({total:g})."
                        ),
                    )
                )

        # Aggregate pct_complete plausibility, over buckets with both figures.
        pct_complete = _get_float(row, "pct_complete")
        both = sorted(set(effort_remaining) & set(effort_total))
        total_sum = sum(effort_total[b] for b in both if effort_total[b] > 0)
        if both and total_sum > 0 and pct_complete is not None:
            remaining_sum = sum(effort_remaining[b] for b in both if effort_total[b] > 0)
            implied_pct = (1 - remaining_sum / total_sum) * 100
            if abs(implied_pct - pct_complete) > _PCT_COMPLETE_TOLERANCE:
                issues.append(
                    IngestIssue(
                        severity="warning",
                        row=i,
                        field="pct_complete",
                        message=(
                            f"Project {project_key}: declared pct_complete={pct_complete:g}% but "
                            f"effort figures imply {implied_pct:.1f}% complete "
                            f"(buckets: {', '.join(both)})."
                        ),
                    )
                )

        parsed.append(
            ParsedRoadmapRow(
                project_key=project_key,
                name=(row.get("project") or "").strip(),
                project_type=(row.get("type") or "").strip(),
                status=(row.get("status") or "").strip(),
                pct_complete=pct_complete,
                effort_remaining=effort_remaining,
                effort_total=effort_total,
                target_gate=(row.get("target_gate") or "").strip(),
                target_fy=(row.get("target_fy") or "").strip(),
                owner=(row.get("owner") or "").strip(),
                mandatory=_get_bool(row, "mandatory"),
                mandatory_driver=(row.get("mandatory_driver") or "").strip(),
                mandatory_deadline=(row.get("mandatory_deadline") or "").strip(),
            )
        )

    return parsed, issues


# ---------------------------------------------------------------------------
# capacity.csv -> CapacityRow
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParsedCapacityRow:
    fiscal_year: str
    bucket_key: str
    fte: Optional[float]
    capacity_units: Optional[float]
    budget: Optional[float]


def parse_capacity_csv(
    text: str, declared_bucket_keys: set[str]
) -> tuple[list[ParsedCapacityRow], list[IngestIssue]]:
    raw_rows = _rows(text)
    issues: list[IngestIssue] = []
    declared_sorted = ", ".join(sorted(declared_bucket_keys))

    for i, row in enumerate(raw_rows, start=1):
        bucket_key = (row.get("bucket_id") or "").strip()
        if bucket_key not in declared_bucket_keys:
            issues.append(
                IngestIssue(
                    severity="error",
                    row=i,
                    field="bucket_id",
                    message=(
                        f"Capacity row {i} references bucket '{bucket_key}', which is not declared. "
                        f"Declared buckets: {declared_sorted}."
                    ),
                )
            )

    if any(i.severity == "error" for i in issues):
        return [], issues

    parsed = [
        ParsedCapacityRow(
            fiscal_year=(row.get("fiscal_year") or "").strip(),
            bucket_key=(row.get("bucket_id") or "").strip(),
            fte=_get_float(row, "fte"),
            capacity_units=_get_float(row, "capacity_units"),
            budget=_get_float(row, "budget"),
        )
        for row in raw_rows
    ]
    return parsed, issues


# ---------------------------------------------------------------------------
# dependencies.csv -> ProjectDependency
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParsedDependencyRow:
    project_key: str
    depends_on_key: str
    dependency_type: str
    note: str


def parse_dependencies_csv(
    text: str, known_project_keys: set[str]
) -> tuple[list[ParsedDependencyRow], list[IngestIssue]]:
    raw_rows = _rows(text)
    issues: list[IngestIssue] = []

    for i, row in enumerate(raw_rows, start=1):
        project_key = (row.get("project_id") or "").strip()
        depends_on_key = (row.get("depends_on_project_id") or "").strip()
        if project_key not in known_project_keys:
            issues.append(
                IngestIssue(
                    severity="error",
                    row=i,
                    field="project_id",
                    message=f"Dependency row {i}: project_id '{project_key}' does not match any known project.",
                )
            )
        if depends_on_key not in known_project_keys:
            issues.append(
                IngestIssue(
                    severity="error",
                    row=i,
                    field="depends_on_project_id",
                    message=(
                        f"Dependency row {i}: depends_on_project_id '{depends_on_key}' "
                        "does not match any known project."
                    ),
                )
            )

    if any(i.severity == "error" for i in issues):
        return [], issues

    parsed = [
        ParsedDependencyRow(
            project_key=(row.get("project_id") or "").strip(),
            depends_on_key=(row.get("depends_on_project_id") or "").strip(),
            dependency_type=(row.get("dependency_type") or "prerequisite").strip(),
            note=(row.get("note") or "").strip(),
        )
        for row in raw_rows
    ]
    return parsed, issues


# ---------------------------------------------------------------------------
# products_fleet.csv -> ProductFleetRow
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParsedProductRow:
    product_key: str
    product: str
    platform: str
    platform_class: str
    units_in_service: float
    avg_age_years: Optional[float]
    status: str
    region: str


def parse_products_fleet_csv(text: str) -> tuple[list[ParsedProductRow], list[IngestIssue]]:
    raw_rows = _rows(text)
    issues: list[IngestIssue] = []
    seen: dict[tuple[str, str], int] = {}

    for i, row in enumerate(raw_rows, start=1):
        product_key = (row.get("product_id") or "").strip()
        platform = (row.get("platform") or "").strip()
        key = (product_key, platform)
        if key in seen:
            issues.append(
                IngestIssue(
                    severity="warning",
                    row=i,
                    field="product_id",
                    message=(
                        f"Row {i} duplicates product '{product_key}' on platform '{platform}' "
                        f"(first seen at row {seen[key]}). Units would double-count if both are kept."
                    ),
                )
            )
        else:
            seen[key] = i

        units = _get_float(row, "units_in_service")
        if units is not None and units <= 0:
            issues.append(
                IngestIssue(
                    severity="warning",
                    row=i,
                    field="units_in_service",
                    message=f"Row {i} ({product_key}, {platform}): units_in_service is {units:g}, not positive.",
                )
            )

    # Duplicates are a Warning, not an Error, but the unique constraint on
    # (tenant_id, product_key, platform) would reject the second insert
    # outright -- so duplicates are collapsed here (last one wins) rather
    # than left to surface as a raw IntegrityError at write time.
    deduped: dict[tuple[str, str], ParsedProductRow] = {}
    for row in raw_rows:
        product_key = (row.get("product_id") or "").strip()
        platform = (row.get("platform") or "").strip()
        deduped[(product_key, platform)] = ParsedProductRow(
            product_key=product_key,
            product=(row.get("product") or "").strip(),
            platform=platform,
            platform_class=(row.get("platform_class") or "").strip(),
            units_in_service=_get_float(row, "units_in_service") or 0.0,
            avg_age_years=_get_float(row, "avg_age_yrs"),
            status=(row.get("status") or "").strip(),
            region=(row.get("region") or "").strip(),
        )

    return list(deduped.values()), issues


# ---------------------------------------------------------------------------
# project_financials.csv -> ProjectFinancialsRow
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParsedFinancialsRow:
    project_key: str
    revenue_impact: list  # [y1..y5], None for unsupplied years
    capex: Optional[float]
    opex_annual: Optional[float]
    discount_rate: Optional[float]
    currency: str
    basis: str


def parse_financials_csv(
    text: str, known_project_keys: set[str]
) -> tuple[list[ParsedFinancialsRow], list[IngestIssue]]:
    raw_rows = _rows(text)
    issues: list[IngestIssue] = []

    for i, row in enumerate(raw_rows, start=1):
        project_key = (row.get("project_id") or "").strip()
        if project_key not in known_project_keys:
            issues.append(
                IngestIssue(
                    severity="error",
                    row=i,
                    field="project_id",
                    message=f"Financials row {i}: project_id '{project_key}' does not match any known project.",
                )
            )

    if any(i.severity == "error" for i in issues):
        return [], issues

    parsed = [
        ParsedFinancialsRow(
            project_key=(row.get("project_id") or "").strip(),
            revenue_impact=[_get_float(row, f"revenue_impact_y{y}") for y in range(1, 6)],
            capex=_get_float(row, "capex"),
            opex_annual=_get_float(row, "opex_annual"),
            discount_rate=_get_float(row, "discount_rate"),
            currency=(row.get("currency") or "USD").strip(),
            basis=(row.get("basis") or "").strip(),
        )
        for row in raw_rows
    ]
    return parsed, issues


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

STATIC_TEMPLATE_HEADERS: dict[str, list[str]] = {
    "products_fleet": [
        "product_id", "product", "platform", "platform_class",
        "units_in_service", "avg_age_yrs", "status", "region",
    ],
    "capacity": ["fiscal_year", "bucket_id", "fte", "capacity_units", "budget"],
    "dependencies": ["project_id", "depends_on_project_id", "dependency_type", "note"],
    "financials": [
        "project_id",
        "revenue_impact_y1", "revenue_impact_y2", "revenue_impact_y3",
        "revenue_impact_y4", "revenue_impact_y5",
        "capex", "opex_annual", "discount_rate", "currency", "basis",
    ],
}

_ROADMAP_TRAILING_HEADERS = [
    "target_gate", "target_fy", "owner", "mandatory", "mandatory_driver", "mandatory_deadline",
]


def generate_template(file_type: str, declared_bucket_keys: list[str]) -> str:
    """CSV header row (no data rows) for the given file_type. `roadmap`'s
    header is built from the tenant's currently-declared buckets -- the
    other four are fixed, since none of them has a per-bucket column."""
    if file_type == "roadmap":
        header = ["project_id", "project", "type", "status", "pct_complete"]
        for bucket_key in declared_bucket_keys:
            header.append(f"{_REMAINING_PREFIX}{bucket_key}")
            header.append(f"{_TOTAL_PREFIX}{bucket_key}")
        header.extend(_ROADMAP_TRAILING_HEADERS)
    elif file_type in STATIC_TEMPLATE_HEADERS:
        header = STATIC_TEMPLATE_HEADERS[file_type]
    else:
        raise ValueError(f"Unknown file_type: {file_type!r}")

    buf = io.StringIO()
    csv.writer(buf).writerow(header)
    return buf.getvalue()
