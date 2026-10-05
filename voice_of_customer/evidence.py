"""
Voice of Customer Agent (Agent 1) — rendering evidence for the prompt.

The rule this module exists to hold: **customer verbatims are never
summarised.** The upstream-report summarisation Agent 5 applies above 150K
characters does not apply here -- summarising customer language destroys
exactly what makes it valuable. Instead, a large file is rendered as:

  * COUNTS OVER EVERY ROW. One cursor pass over the whole file: total rows,
    per-value counts for each mapped column, counts by month. These are
    census figures for the file as uploaded (or, where the file is itself
    declared a sample, figures "in the sample supplied").
  * VERBATIMS SAMPLED, WORD FOR WORD. Which rows appear as quotations is
    sampled -- stratified, seeded, stated -- but no row is ever paraphrased.
    A verbatim over VERBATIM_MAX_CHARS is cut with a visible marker, never
    reworded.

Frequency therefore never comes from the sample where a mapped column
exists. Where it does not -- themes that live only in free text -- theme
frequency can only be read off the sampled verbatims, and the prompt
requires it to be reported as an estimate from N sampled rows, never as a
count.

Memory: every function here consumes an iterator (a DB cursor in
production) and holds at most the bounded sample pools and bounded counters
below -- never the whole file. The production instance has 414MB of RAM.

DB-free, like the rest of the package: the service layer supplies the
iterators.
"""
from __future__ import annotations

import math
import random
import re
import zlib
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable

from voice_of_customer.context import EvidenceFile

# ---------------------------------------------------------------------------
# Thresholds -- agreed in the implementation plan
# ---------------------------------------------------------------------------

# A CSV at or under both limits is passed whole: every row verbatim.
VERBATIM_ALL_ROWS_MAX = 300
VERBATIM_ALL_CHARS_MAX = 60_000

# Evidence characters per report prompt (~37K tokens), across all files.
# The nine report calls share one cached prefix, so this is not paid nine
# times in full.
EVIDENCE_BUDGET_CHARS = 150_000
# No file is squeezed below this share, however small next to the others.
PER_FILE_FLOOR_CHARS = 15_000

# One verbatim longer than this is cut with a visible marker, never reworded.
VERBATIM_MAX_CHARS = 2_000

# Bounded memory for the sample: at most MAX_STRATA pools of
# SAMPLE_POOL_PER_STRATUM rows each (~5,000 rows), however large the file.
SAMPLE_POOL_PER_STRATUM = 200
MAX_STRATA = 25

# Bounded counters: the top TOP_VALUES values per mapped column are listed,
# and tracking of new distinct values stops at MAX_DISTINCT_TRACKED so a
# free-text column mapped by mistake cannot exhaust memory.
TOP_VALUES = 25
MAX_DISTINCT_TRACKED = 5_000

_OTHER_STRATUM = "(other values)"
_ISO_MONTH = re.compile(r"^\s*(\d{4})[-/.](\d{1,2})(?:[-/.]\d{1,2})?(?:[T\s].*)?$")


def _seed_for(file_id: str) -> int:
    # zlib.crc32, not hash(): hash() is salted per process, so the "same"
    # sample would differ between runs of the same file.
    return zlib.crc32(file_id.encode("utf-8"))


def _clip(text: str, limit: int = VERBATIM_MAX_CHARS) -> str:
    if len(text) <= limit:
        return text
    return f"{text[:limit]} [truncated at {limit:,} of {len(text):,} chars]"


def _month_of(value: str) -> str | None:
    m = _ISO_MONTH.match(value or "")
    if not m:
        return None
    month = int(m.group(2))
    if not 1 <= month <= 12:
        return None
    return f"{m.group(1)}-{month:02d}"


# ---------------------------------------------------------------------------
# Budget allocation across files
# ---------------------------------------------------------------------------


def estimated_need(f: EvidenceFile) -> int:
    """Characters a file needs to be rendered whole. A CSV renders each cell
    as "column: value", so it costs more than its raw size."""
    base = f.char_count or 0
    if f.file_format == "csv":
        return int(base * 1.6) + 2_000
    return base + 1_000


def allocate_budget(
    files: list[EvidenceFile],
    total: int = EVIDENCE_BUDGET_CHARS,
    floor: int = PER_FILE_FLOOR_CHARS,
) -> dict[str, int]:
    """Split the evidence budget across files in proportion to size, with a
    per-file floor; a file that needs less than its share gets what it needs
    and the slack is redistributed to the rest, until stable."""
    if not files:
        return {}
    if len(files) * floor >= total:
        equal = total // len(files)
        return {f.file_id: min(equal, estimated_need(f)) for f in files}

    alloc: dict[str, int] = {}
    pending = list(files)
    remaining = total
    while pending:
        weight = sum(max(1, estimated_need(f)) for f in pending)
        spare = remaining - floor * len(pending)
        shares = {
            f.file_id: floor + int(spare * max(1, estimated_need(f)) / weight) for f in pending
        }
        satisfied = [f for f in pending if estimated_need(f) <= shares[f.file_id]]
        if not satisfied:
            alloc.update(shares)
            break
        for f in satisfied:
            alloc[f.file_id] = estimated_need(f)
            remaining -= alloc[f.file_id]
        pending = [f for f in pending if f not in satisfied]
    return alloc


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------


@dataclass
class ColumnCounts:
    column: str
    counter: Counter = field(default_factory=Counter)
    untracked_rows: int = 0  # rows whose value arrived after MAX_DISTINCT_TRACKED was hit
    blank: int = 0

    def add(self, value: str) -> None:
        value = (value or "").strip()
        if not value:
            self.blank += 1
        elif value in self.counter or len(self.counter) < MAX_DISTINCT_TRACKED:
            self.counter[value] += 1
        else:
            self.untracked_rows += 1


@dataclass
class CsvDigest:
    total_rows: int
    counts: dict[str, ColumnCounts]  # role -> counts
    months: Counter
    undated_rows: int
    stratify_by: str | None  # role used for stratification, or None for uniform
    strata_sizes: Counter
    rows: list[tuple[int, dict]]  # the candidate verbatims, in render order
    keep_all: bool
    customer_values: set[str]


def _stratify_role(roles: dict[str, str]) -> str | None:
    for role in ("category", "segment"):
        if roles.get(role):
            return role
    return None


def digest_csv(
    meta: EvidenceFile,
    rows: Iterable[tuple[int, dict]],
    all_rows_char_limit: int = VERBATIM_ALL_CHARS_MAX,
) -> CsvDigest:
    """One pass over every row. Counts are exact; the sample is bounded.

    A file at or under VERBATIM_ALL_ROWS_MAX rows is kept whole, and passed
    whole if its rendering also fits `all_rows_char_limit`. If it does not,
    it is sampled exactly like a large file -- never cut off in file order,
    which would quietly drop the end of the period."""
    roles = {r: c for r, c in (meta.column_roles or {}).items() if c}
    counted_roles = [r for r in ("segment", "product", "category", "severity", "status", "customer") if r in roles]
    counts = {r: ColumnCounts(column=roles[r]) for r in counted_roles}
    months: Counter = Counter()
    undated = 0
    stratify = _stratify_role(roles)
    strata_sizes: Counter = Counter()
    pools: dict[str, list[tuple[int, dict]]] = {}
    seen_in_stratum: Counter = Counter()
    rng = random.Random(_seed_for(meta.file_id))
    keep_all = (meta.row_count or 0) <= VERBATIM_ALL_ROWS_MAX
    kept_all: list[tuple[int, dict]] = []
    total = 0

    for seq, cells in rows:
        total += 1
        cells = cells or {}
        for role, cc in counts.items():
            cc.add(str(cells.get(cc.column, "")))
        if "date" in roles:
            month = _month_of(str(cells.get(roles["date"], "")))
            if month:
                months[month] += 1
            else:
                undated += 1

        if keep_all:
            kept_all.append((seq, cells))
            continue

        key = "_all"
        if stratify:
            key = str(cells.get(roles[stratify], "")).strip() or "(blank)"
            if key not in pools and len(pools) >= MAX_STRATA:
                key = _OTHER_STRATUM
        strata_sizes[key] += 1
        pool = pools.setdefault(key, [])
        seen_in_stratum[key] += 1
        # Algorithm R reservoir per stratum: a uniform sample of that
        # stratum's rows, whatever its length, in bounded memory.
        if len(pool) < SAMPLE_POOL_PER_STRATUM:
            pool.append((seq, cells))
        else:
            j = rng.randrange(seen_in_stratum[key])
            if j < SAMPLE_POOL_PER_STRATUM:
                pool[j] = (seq, cells)

    if keep_all:
        size = sum(len(_render_row(seq, cells, meta.columns)) + 1 for seq, cells in kept_all)
        if size > all_rows_char_limit:
            keep_all = False
            for seq, cells in kept_all:
                key = "_all"
                if stratify:
                    key = str(cells.get(roles[stratify], "")).strip() or "(blank)"
                    if key not in pools and len(pools) >= MAX_STRATA:
                        key = _OTHER_STRATUM
                strata_sizes[key] += 1
                pools.setdefault(key, []).append((seq, cells))

    if keep_all:
        ordered = kept_all
    else:
        ordered = _interleave(pools, strata_sizes, total, rng)

    customer_values = set(counts["customer"].counter) if "customer" in counts else set()
    return CsvDigest(
        total_rows=total,
        counts=counts,
        months=months,
        undated_rows=undated,
        stratify_by=stratify if not keep_all else None,
        strata_sizes=strata_sizes,
        rows=ordered,
        keep_all=keep_all,
        customer_values=customer_values,
    )


def _interleave(
    pools: dict[str, list[tuple[int, dict]]], sizes: Counter, total: int, rng: random.Random
) -> list[tuple[int, dict]]:
    """Order the pooled rows so that ANY prefix is close to proportional to
    each stratum's share of the file, with at least one row per stratum.
    Rendering then stops wherever the budget runs out and the included set
    is still stratified."""
    capacity = sum(len(p) for p in pools.values())
    keyed: list[tuple[float, int, tuple[int, dict]]] = []
    for key, pool in pools.items():
        rng.shuffle(pool)
        quota = max(1, min(len(pool), round(capacity * sizes[key] / max(1, total))))
        for i, row in enumerate(pool[:quota]):
            # position i of quota evenly spread across [0, 1)
            keyed.append(((i + 0.5) / quota, row[0], row))
    keyed.sort(key=lambda t: (t[0], t[1]))
    return [row for _, _, row in keyed]


def _render_row(seq: int, cells: dict, columns: tuple[str, ...]) -> str:
    order = list(columns) or list(cells)
    parts = [f"{c}: {cells[c]}" for c in order if str(cells.get(c, "")).strip()]
    return _clip(f"[row {seq}] " + " | ".join(parts))


@dataclass(frozen=True)
class RenderedEvidence:
    file_id: str
    text: str
    sampling_note: str  # one line, carried into Report 1 and the run meta
    customer_values: frozenset[str] = frozenset()


def _completeness_line(meta: EvidenceFile) -> str:
    if meta.is_sample:
        desc = f" — {meta.sample_description}" if meta.sample_description else " — no description of the sample given"
        return (
            f"- COMPLETENESS: SAMPLE{desc}. This file is NOT a census: every count from it is "
            "\"in the sample supplied\", and must never be reported as the frequency in the whole "
            "population."
        )
    return "- COMPLETENESS: declared complete (not a sample) for the period stated."


def _header(meta: EvidenceFile, fmt_label: str) -> list[str]:
    period = (
        f"{meta.period_start or '?'} to {meta.period_end or '?'}"
        if (meta.period_start or meta.period_end)
        else "not stated"
    )
    lines = [
        f"### Evidence file: {meta.filename}",
        f"- Type: {meta.type_label} | Format: {fmt_label}",
        f"- As of: {meta.as_of or 'not stated'} | Period covered: {period}",
        f"- Segment coverage: {', '.join(meta.segment_coverage) if meta.segment_coverage else 'not stated'}",
        _completeness_line(meta),
    ]
    return lines


def _top(cc: ColumnCounts) -> str:
    items = cc.counter.most_common(TOP_VALUES)
    shown = ", ".join(f"{v}: {n:,}" for v, n in items)
    rest_values = len(cc.counter) - len(items)
    rest_rows = sum(cc.counter.values()) - sum(n for _, n in items)
    extras = []
    if rest_values > 0:
        extras.append(f"{rest_values:,} further values covering {rest_rows:,} rows")
    if cc.untracked_rows:
        extras.append(
            f"{cc.untracked_rows:,} rows with values beyond the first {MAX_DISTINCT_TRACKED:,} distinct, not itemised"
        )
    if cc.blank:
        extras.append(f"{cc.blank:,} blank")
    return shown + (f" ({'; '.join(extras)})" if extras else "")


def render_csv(meta: EvidenceFile, rows: Iterable[tuple[int, dict]], budget: int) -> RenderedEvidence:
    digest = digest_csv(meta, rows, all_rows_char_limit=min(budget, VERBATIM_ALL_CHARS_MAX))
    unit = meta.row_unit or "row (what one row represents was not stated)"
    roles = {r: c for r, c in (meta.column_roles or {}).items() if c}
    mapped = set(roles.values())
    unmapped = [c for c in meta.columns if c not in mapped]

    lines = _header(meta, "CSV")
    lines.append(f"- One row = one {unit}. Total rows: {digest.total_rows:,}.")
    lines.append(
        "- Column roles mapped: "
        + (", ".join(f"{r} = \"{c}\"" for r, c in roles.items()) if roles else "none")
        + ("; unmapped columns, passed through as-is: " + ", ".join(f'"{c}"' for c in unmapped) if unmapped else "")
    )

    body: list[str] = []
    if digest.counts or digest.months:
        scope = "in the sample supplied" if meta.is_sample else "across every row of the file"
        body.append(f"#### Counts {scope} ({digest.total_rows:,} rows) — exact, not sampled")
        for role, cc in digest.counts.items():
            body.append(f"- by {role} (\"{cc.column}\"): {_top(cc)}")
        if digest.months:
            body.append(
                "- by month: "
                + ", ".join(f"{m}: {n:,}" for m, n in sorted(digest.months.items()))
                + (f" ({digest.undated_rows:,} rows with a date not in ISO form, not bucketed)" if digest.undated_rows else "")
            )
    else:
        body.append(
            "#### Counts\n- No column is mapped to segment, product, category, severity or status, so "
            "the only exact count is the total row count. Any theme frequency read from the verbatims "
            "below is an ESTIMATE from the rows shown, and must be reported as \"N of the M sampled "
            "rows\", never as a count."
        )

    head_text = "\n".join(lines + body)
    remaining = max(0, budget - len(head_text) - 400)

    rendered: list[str] = []
    used = 0
    for seq, cells in digest.rows:
        line = _render_row(seq, cells, meta.columns)
        if used + len(line) + 1 > remaining:
            break
        rendered.append(line)
        used += len(line) + 1

    shown = len(rendered)
    if digest.keep_all and shown == digest.total_rows:
        method = f"all {digest.total_rows:,} rows passed verbatim; nothing sampled"
    elif digest.keep_all:
        # Fitted the all-rows limit but not this file's share once the header
        # was added -- rare, and stated rather than hidden.
        method = (
            f"{shown:,} of {digest.total_rows:,} rows passed verbatim, in file order; the "
            f"remainder did not fit this file's prompt budget ({budget:,} chars)"
        )
    else:
        strat = (
            f"stratified by {digest.stratify_by} (\"{roles[digest.stratify_by]}\"), in proportion to "
            f"each value's share of the file with at least one row per value"
            if digest.stratify_by
            else "uniform random (no category or segment column mapped to stratify by)"
        )
        method = (
            f"{shown:,} of {digest.total_rows:,} rows sampled verbatim — {strat}; seeded, so the same "
            f"file yields the same sample"
        )
    count_basis = (
        "counts cover every row" if (digest.counts or digest.months) else "only the total row count is exact"
    )
    note = f"{meta.filename}: {method}; {count_basis}."

    text = "\n".join(
        [
            head_text,
            f"- RENDERING: {method}. The counts above are {'exact over all rows' if (digest.counts or digest.months) else 'limited to the row total'}; only the choice of which rows to quote is sampled.",
            "#### Verbatim rows (word for word — the platform never paraphrases them)",
            *(rendered or ["(no rows fit the budget)"]),
        ]
    )
    return RenderedEvidence(
        file_id=meta.file_id,
        text=text,
        sampling_note=note,
        customer_values=frozenset(digest.customer_values),
    )


# ---------------------------------------------------------------------------
# Text and PDF
# ---------------------------------------------------------------------------


def select_passages(item_count: int, total_chars: int, budget: int, runs: int = 4) -> set[int] | None:
    """Which items (pages / sections, 1-based) to include when a document
    exceeds its budget: `runs` contiguous passages, evenly spaced through the
    document, so the reader sees its beginning, end and middle rather than
    only its first pages. Returns None when the whole document fits."""
    if item_count <= 0 or total_chars <= budget:
        return None
    per_item = total_chars / item_count
    target = max(1, min(item_count, math.floor(budget / max(1.0, per_item))))
    runs = max(1, min(runs, target))
    run_len = max(1, target // runs)
    if runs == 1:
        starts = [1]
    else:
        span = item_count - run_len
        starts = [1 + round(j * span / (runs - 1)) for j in range(runs)]
    chosen: set[int] = set()
    for s in starts:
        chosen.update(range(s, min(item_count, s + run_len - 1) + 1))
    return chosen


def _ranges(nums: list[int]) -> str:
    if not nums:
        return "none"
    out, start, prev = [], nums[0], nums[0]
    for n in nums[1:]:
        if n == prev + 1:
            prev = n
            continue
        out.append(f"{start}–{prev}" if start != prev else f"{start}")
        start = prev = n
    out.append(f"{start}–{prev}" if start != prev else f"{start}")
    return ", ".join(out)


def render_document(
    meta: EvidenceFile, items: Iterable[tuple[int, str]], item_count: int, budget: int
) -> RenderedEvidence:
    unit = "page" if meta.file_format == "pdf" else "section"
    fmt_label = "PDF (text extracted)" if meta.file_format == "pdf" else "text"
    lines = _header(meta, fmt_label)
    head = "\n".join(lines)
    room = max(0, budget - len(head) - 400)
    chosen = select_passages(item_count, meta.char_count, room)

    included: list[int] = []
    parts: list[str] = []
    used = 0
    for seq, text in items:
        if chosen is not None and seq not in chosen:
            continue
        block = f"[{unit} {seq}]\n{text}"
        if used + len(block) > room:
            left = room - used
            if left > 200:
                parts.append(_clip(block, left))
                included.append(seq)
            break
        parts.append(block)
        included.append(seq)
        used += len(block) + 2

    if chosen is None and len(included) == item_count:
        method = f"complete — all {item_count:,} {unit}s passed verbatim"
    else:
        method = (
            f"{unit}s {_ranges(included)} of {item_count:,} passed verbatim as evenly spaced unedited "
            f"passages (about {used:,} of {meta.char_count:,} chars); the rest was not shown, and nothing "
            "was summarised"
        )
    text = "\n".join([head, f"- RENDERING: {method}.", "#### Content (verbatim)", *(parts or ["(empty)"])])
    return RenderedEvidence(
        file_id=meta.file_id,
        text=text,
        sampling_note=f"{meta.filename}: {method}.",
    )


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def render_evidence_text(rendered: list[RenderedEvidence]) -> str:
    if not rendered:
        return (
            "NO CUSTOMER EVIDENCE WAS SUPPLIED. This is a Tier 2 run. Do not produce sentiment "
            "scores, frequency rankings, validated personas, feature request frequency, win/loss "
            "rationale or segment clustering -- state each as unavailable."
        )
    notes = "\n".join(f"- {r.sampling_note}" for r in rendered)
    return (
        "Customer evidence follows. It is confidential. Quote it only as the attribution policy "
        "permits.\n\n"
        "## How each file was rendered into this prompt (state this in the output wherever a "
        "count or quotation is used)\n"
        f"{notes}\n\n" + "\n\n".join(r.text for r in rendered)
    )
