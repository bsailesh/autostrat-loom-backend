"""
Technology & Regulatory Intelligence Agent (Agent 3) — the nine reports.

Same 5-field ReportSpec shape as market_insights/reports.py and
strategy_synthesis/reports.py, declared locally rather than imported: it is
a trivial struct, and coupling this agent's report list to another's buys
nothing.

**Nine in v1, not eleven.** Report 9 (technology and regulatory timeline)
recombines content from 4, 6, 7 and 8; Report 10 (digest) needs run-to-run
change detection the platform does not have. Both are noted as deferred in
the output rather than silently dropped -- see DEFERRED_REPORTS_NOTE, which
Report 1 carries. Report 11 stays, and keeps its number: competitor
*technical* capability is genuinely distinct from Market Insights'
commercial and structural view of the same competitors, and renumbering it
to 9 would make this pack's report numbers disagree with the spec that
describes them.

**Exhibit contract.** Four reports carry visual exhibits, and the contract
between this agent and the renderer is the table header row: the model
emits an ordinary Markdown table with the exact headers below, and the
frontend's per-agent exhibit registry claims it by matching them, falling
back to a themed table when it cannot. That is the same mechanism Agent 5's
exhibits use. No ASCII art, ever -- the fallback is a table, never
character art.
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


# ---------------------------------------------------------------------------
# Exhibit table contracts -- the header rows the renderers match on.
# Changing one of these is a breaking change for
# frontend/src/techRegulation/exhibits/.
# ---------------------------------------------------------------------------

CANDIDATE_WORK_TABLE_HEADERS = (
    "| Key | Driver | Date | Date basis | Applicability | Work implied | Classification | "
    "Confidence | Status |"
)

MATURITY_LADDER_TABLE_HEADERS = "| Tier | Technology | Maturity | Trend | Evidence | Confidence |"

EVOLUTION_TIMELINE_TABLE_HEADERS = "| Year | Label | Stage | Source | Confidence |"

ECOSYSTEM_NODES_TABLE_HEADERS = "| Node | Node type | Role | Evidence | Confidence |"

ECOSYSTEM_EDGES_TABLE_HEADERS = "| From | To | Relationship | Evidence | Confidence |"


DEFERRED_REPORTS_NOTE = """\
Two reports from the source specification are deferred in this version, and are
named here rather than omitted silently:

- **Report 9 — Technology and regulatory timeline.** Recombines content already
  present in Reports 4, 6, 7 and 8. Deferred pending a decision on whether it is
  a distinct deliverable or a generated view over those four.
- **Report 10 — Technology and regulatory intelligence digest.** Its "new",
  "changed" and "accelerating" categories are comparative and require run-to-run
  state, which this platform does not keep. Deferred until change detection
  exists; recency in this pack is derived from evidence dates instead, and that
  is the meaning in use throughout.
"""


REPORTS: list[ReportSpec] = [
    ReportSpec(
        number=1,
        title="Executive technology and regulatory intelligence summary",
        opening="scqa",
        must_include=(
            "The operating state, stated in the very first line before anything else. "
            "Then: significant technology developments; regulatory developments; the "
            "evidence behind each. Then a CONSOLIDATED LIST OF ALL CANDIDATE WORK "
            "surfaced in this run -- every item from the structured candidate work "
            "payload, none added and none omitted -- as the single place a reader sees "
            "everything that might need doing. Order that list BY DATE, soonest first, "
            "which is factual; never by importance, which would be a ranking. Items with "
            "no date go last, under a 'No date established' subheading, with their stated "
            "reason. Close with the deferred-reports note supplied in the prompt, verbatim."
        ),
        exhibit=(
            "A candidate work table with exactly these headers: "
            f"{CANDIDATE_WORK_TABLE_HEADERS} -- one row per candidate work item, ordered "
            "by date, soonest first."
        ),
    ),
    ReportSpec(
        number=2,
        title="Technology landscape",
        opening="key_insights",
        must_include=(
            "Domains in scope; major technologies; emerging technologies; maturity "
            "classification per technology; key organisations; research activity; "
            "commercial activity; adoption evidence; how the landscape is evolving. "
            "Classify maturity only where the evidence permits, on the descriptive scale "
            "(concept, laboratory, prototype, demonstration, pilot, commercial "
            "introduction, commercially deployed, mature). A formal TRL 1-9 appears ONLY "
            "where a source establishes it."
        ),
        exhibit=(
            "A colour-coded status table of technologies against domain, maturity and "
            "trend, using the standard colour semantics."
        ),
    ),
    ReportSpec(
        number=3,
        title="Technology maturity ladder",
        opening="key_insights",
        must_include=(
            "Four tiers, in this order: Investigate (emerging technology), Monitor (early "
            "development), Demonstrated (pilot / prototype), Deployed (commercial use). "
            "Per entry: tier, technology, the evidence, maturity classification and trend. "
            "State explicitly, in the report body: this describes observed maturity and "
            "activity, and is NOT an investment recommendation."
        ),
        exhibit=(
            "A maturity ladder table with exactly these headers: "
            f"{MATURITY_LADDER_TABLE_HEADERS} -- Tier must be one of Investigate, Monitor, "
            "Demonstrated, Deployed. This renders as four stacked tiers, NOT a radar or "
            "radial chart."
        ),
    ),
    ReportSpec(
        number=4,
        title="Technology evolution timeline",
        opening="key_insights",
        must_include=(
            "A chronological view across the analysis window, with stage progression: "
            "research, prototype, pilot, demonstration, launch, adoption. Each entry "
            "carries its source and confidence. Forward-looking entries are labelled "
            "FORECAST and never presented as fact. Where patent material appears, give "
            "the patent evidence scope's required statement verbatim -- this is not a "
            "patent-database search -- and state which patent search axes ran and which "
            "did not, naming axis 2 unavailable where supplier names are anonymised. "
            "No filing counts, family sizes, assignee rankings or clustering."
        ),
        exhibit=(
            "An evolution timeline table with exactly these headers: "
            f"{EVOLUTION_TIMELINE_TABLE_HEADERS} -- Stage must be one of research, "
            "prototype, pilot, demonstration, launch, adoption. Renders as a horizontal "
            "timeline on a year axis."
        ),
    ),
    ReportSpec(
        number=5,
        title="Technology ecosystem map",
        opening="key_insights",
        must_include=(
            "OEMs, tier suppliers, startups, universities, government bodies, research "
            "institutions, partnerships, joint ventures, investors and funding programmes. "
            "ONLY EVIDENCED RELATIONSHIPS -- an edge on a map reads as verified fact, so "
            "every edge carries the evidence for that specific relationship. Where a "
            "relationship is rumoured or inferred, say so in prose and leave it off the "
            "edge list."
        ),
        exhibit=(
            "Two tables, nodes then edges, with exactly these headers: "
            f"{ECOSYSTEM_NODES_TABLE_HEADERS} and {ECOSYSTEM_EDGES_TABLE_HEADERS}. "
            "Node type is one of OEM, tier supplier, startup, university, government, "
            "research institution, investor, programme."
        ),
    ),
    ReportSpec(
        number=6,
        title="Regulatory landscape",
        opening="key_insights",
        must_include=(
            "Regulations, proposed regulations, standards, certification requirements, "
            "jurisdictions, effective dates, compliance deadlines and status. SCOPED TO "
            "THE APPLICABILITY ENVELOPE -- and where the run is unscoped, say so in the "
            "first line of this report as well. Always distinguish proposed, final, "
            "effective and enforced; these are routinely conflated in secondary reporting "
            "and the distinction is material. Jurisdiction role matters: a finding from a "
            "primary market and one from an export-only market carry different weight, and "
            "you say which."
        ),
        exhibit=(
            "A colour-coded regulatory status table: regulation, jurisdiction, status "
            "(proposed / final / effective / enforced), effective date, applicability to "
            "this customer's certification basis."
        ),
    ),
    ReportSpec(
        number=7,
        title="Regulatory change report",
        opening="key_insights",
        must_include=(
            "Per significant change: the mandate (name, jurisdiction, enforcement date); "
            "the status source, primary where available; previous state to new state; "
            "applicability assessed AGAINST THE CUSTOMER'S CERTIFICATION BASIS rather than "
            "generically; the burden where documented; and the catalyst -- whether the "
            "change forces buyers to adopt new equipment, software or services. Reference "
            "the candidate work item by its key where one arises from the change, drawing "
            "only on the structured payload supplied. NO LEGAL CONCLUSIONS: report what the "
            "regulation says and to what it applies, never an interpretation of obligation "
            "beyond the document."
        ),
        exhibit=(
            "A per-change table: change, jurisdiction, previous state, new state, status, "
            "effective date, applicability, candidate work key."
        ),
    ),
    ReportSpec(
        number=8,
        title="Standards and certification report",
        opening="key_insights",
        must_include=(
            "Per standard: identifier, revision, issuing organisation, previous and current "
            "version, what changed, publication and effective dates, and the certification "
            "implications. Mark each HELD or NOT HELD from the envelope's standards-held "
            "list. A revision to a standard the customer holds is dated candidate work and "
            "must reference its candidate work key; a revision to one they do not hold is "
            "background and is reported as such rather than at equal weight. Certification "
            "implications are factual -- what the change requires -- never recommendations "
            "about how to respond."
        ),
        exhibit=(
            "A per-standard table: standard, revision, issuing organisation, held / not "
            "held, what changed, publication date, effective date, candidate work key."
        ),
    ),
    ReportSpec(
        number=11,
        title="Competitor technology landscape",
        opening="key_insights",
        must_include=(
            "Per competitor and technology: domain, technology, evidence type, publication "
            "date, maturity, claimed capability, evidence strength, related organisations, "
            "products and trend. Label technology evidence observed, reported, "
            "demonstrated, projected or speculative. This report covers TECHNICAL "
            "CAPABILITY AND ITS EVIDENCE; the commercial and structural view of the same "
            "competitors belongs to Market Insights and is not duplicated here. Distinguish "
            "a claimed capability from a demonstrated one, and patent activity from a "
            "working product."
        ),
        exhibit=(
            "A per-competitor technology table: competitor, domain, technology, maturity, "
            "evidence type, evidence strength, trend."
        ),
    ),
]
