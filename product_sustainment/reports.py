"""
Product Sustainment Agent (Agent 4) — the nine reports.

**Nine, not ten.** Report 9 (sustainment trend digest) needs run-to-run
change detection the platform does not have; it is noted as deferred in
Report 1 rather than dropped silently. Report 10 keeps its number.

Each spec may name a `computed` block: a table generated in code from
compute.py's results (product_sustainment/results.py) and inserted verbatim
after the model's narrative. The model writes around the numbers; it never
transcribes them.

Exhibit contracts the MODEL emits (header rows the frontend matches on):
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReportSpec:
    number: int
    title: str
    opening: str  # "scqa" | "key_insights"
    must_include: str
    exhibit: str
    computed: str | None = None  # results.computed_section kind, or "candidate_work"


FAILURE_TREND_TABLE_HEADERS = "| Series | Period | Value | Measure |"
CANDIDATE_WORK_TABLE_HEADERS = (
    "| Key | Part | Driver | Date | Date basis | Qty required | Affected LRUs | Qualified alternate | "
    "Candidate alternates | Work implied | Confidence |"
)

DEFERRED_REPORTS_NOTE = """\
One report from the source specification is deferred in this version, and is
named here rather than omitted silently:

- **Report 9 — Sustainment trend digest.** Its "new", "changed" and "declining"
  categories are comparative and need run-to-run state, which this platform does
  not keep. Deferred until change detection exists; recency in this pack is
  derived from evidence dates instead.
"""

REPORTS: list[ReportSpec] = [
    ReportSpec(
        number=1,
        title="Sustainment intelligence report",
        opening="scqa",
        must_include=(
            "The operating-tier line first, then the Governing Insight. Then: top reliability risks; top "
            "obsolescence risks by time to impact (from the computed runout and last-time-buy dates); fleet "
            "health summary; knowledge and capability risks; and an '## Options' section -- engineering "
            "options with their evidence, never selections, and never a buy-versus-phase-out "
            "recommendation. For each at-risk component say which of the four kinds of work is open to it: "
            "a sourcing change (customer-qualified alternate exists), a qualification project (only "
            "candidate alternates), a redesign (no candidate found), or accepting the risk. Cap every list "
            "at what the evidence supports and state the count. The platform inserts the consolidated "
            "candidate work table after your text. Close with the deferred-reports note, verbatim."
        ),
        exhibit="The computed candidate work table is inserted by the platform; refer to items by key (PS-<part>).",
        computed="candidate_work",
    ),
    ReportSpec(
        number=2,
        title="Obsolescence report",
        opening="key_insights",
        must_include=(
            "Scope: every part with a risk flag or non-Active lifecycle status, plus any part whose runout "
            "falls inside the forecast horizon. Per part: lifecycle status from the most current source; "
            "risk category; last-time-buy window; the customer's qualified alternate if any; candidate "
            "alternates found in research, each labelled 'candidate for qualification' with its evidence "
            "and limits; confidence. A separate section for single-source, custom and at-risk-region parts, "
            "which have standing exposure and no buy window. The platform inserts the computed table of "
            "flagged components, including those with no runout date, after your text."
        ),
        exhibit="The computed flagged-components table is inserted by the platform.",
        computed="obsolescence",
    ),
    ReportSpec(
        number=3,
        title="Field performance and failure trend report",
        opening="key_insights",
        must_include=(
            "Ranked table: component or subsystem, failure mode, frequency, MTBF/MTTR where maintenance "
            "data supports it, trend (improving / stable / degrading) with evidence, safety impact, "
            "confidence. Frequency only from counts; without counts, report clusters unranked and say why. "
            "State, for every LRU-level figure, whether it was observed at the LRU or rolled up from an "
            "assembly, and which LRUs it reached. Without reliability documents or maintenance records, "
            "state that failure clustering, MTBF and MTTR are unavailable."
        ),
        exhibit=(
            f"Failure trend series as a table with exactly these headers: {FAILURE_TREND_TABLE_HEADERS} -- "
            "one row per series per period (e.g. 2026-Q1), Value numeric, Measure naming what is counted. "
            "Only from counted evidence; omit the table rather than estimate."
        ),
    ),
    ReportSpec(
        number=4,
        title="Supplier and component risk report",
        opening="key_insights",
        must_include=(
            "Supplier financial and operational risk indicators where publicly available; component shortage "
            "risk; single-source dependencies and what each reaches. Read the supplier watch list. '## "
            "Options' for mitigation, with evidence -- never selections. The platform inserts the computed "
            "exposure map for flagged components after your text."
        ),
        exhibit="The computed dependency and exposure map is inserted by the platform.",
        computed="single_source",
    ),
    ReportSpec(
        number=5,
        title="Aging fleet report",
        opening="key_insights",
        must_include=(
            "Fleet age distribution, utilisation intensity by segment, reliability correlation with age and "
            "utilisation, units at elevated risk by age or environment. Correlation is not causation -- "
            "state which the evidence supports. Without a fleet roster, state the analysis is unavailable."
        ),
        exhibit="A colour-coded table of fleet units or cohorts by age band, environment and risk.",
    ),
    ReportSpec(
        number=6,
        title="Service intelligence report",
        opening="key_insights",
        must_include=(
            "Service bulletin summary; maintenance schedule and inspection interval changes indicated by the "
            "evidence, as '## Options' with the evidence; configuration drift (as-maintained against "
            "as-designed) where configuration data exists, otherwise state drift analysis is unavailable."
        ),
        exhibit="A colour-coded table of service findings and options with their evidence.",
    ),
    ReportSpec(
        number=7,
        title="Knowledge and capability loss report",
        opening="key_insights",
        must_include=(
            "Knowledge concentration risks, affected components or processes, estimated impact if realised, "
            "documentation and succession '## Options'. Requires the customer's knowledge assessment. "
            "Without one, state that the analysis is unavailable -- never infer it from headcount or age."
        ),
        exhibit="A table of capabilities, people count, documentation status and components affected.",
    ),
    ReportSpec(
        number=8,
        title="Lifecycle intelligence dashboard",
        opening="key_insights",
        must_include=(
            "A short reading of the exhibits: obsolescence exposure timeline, inventory depletion, which "
            "LRUs flagged components reach, and reliability trends where data supports them. Sustainment "
            "cost trend only where data supports it. The platform inserts the computed depletion series and "
            "exposure map after your text."
        ),
        exhibit=f"Reliability trend series, where evidence supports them, as {FAILURE_TREND_TABLE_HEADERS}.",
        computed="dashboard",
    ),
    ReportSpec(
        number=10,
        title="Component runout and inventory bridge report",
        opening="key_insights",
        must_include=(
            "Interpret the computed runout table: which components are Critical (runout on or before the "
            "last-time-buy window closes -- the current buy is the only one remaining), Watch (within the "
            "12-month margin after it closes), OK; what each position rests on (on-hand versus open orders "
            "-- a position 80% on open POs is not the position 80% on hand); where the lead-time check "
            "flagged that immediate PO arrival may not hold; every competing LRU where demand exceeds "
            "supply, with no allocation assumed; and the components with insufficient data, which are "
            "listed, never omitted. Quantities required are 'through the end of the supplied forecast "
            "horizon', never 'through end of life'. The platform inserts the computed tables after your "
            "text."
        ),
        exhibit="The computed runout, competing-demand and insufficient-data tables are inserted by the platform.",
        computed="runout",
    ),
]
