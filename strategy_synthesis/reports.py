"""
Strategy Synthesis Agent (Agent 5) — the seven report specs.

Same 5-field shape as market_insights/reports.py's ReportSpec, defined
locally rather than imported -- it's a trivial struct, and there's no
reason to couple this package's report list to Market Insights' own.

`opening` has a THIRD value beyond market_insights' "scqa"/"key_insights":
"plain". `agent5_test_output_v2.md` (the reference output) shows Report 1
opening with "### Key insights" and Report 7 with "### Governing insight"
(S/C/Q/A) -- the reverse of Market Insights' convention where report 1 is
the SCQA one. Reports 2-6 have neither heading in the reference output.
The docx export's markdown parser detects these two headings by their
text, not by report position (confirmed in Part 1's research), so "plain"
(neither heading) is safe -- those reports just render as ordinary blocks.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReportSpec:
    number: int
    title: str
    opening: str  # "scqa" | "key_insights" | "plain" | "executive_summary"
    must_include: str
    exhibit: str


# Report 0 is written last, from the finished reports, and presented first.
# report_number is stored and the export iterates it, so 0 rather than a
# renumbering: every existing number stays stable.
EXECUTIVE_SUMMARY_REPORT_NUMBER = 0


REPORTS: list[ReportSpec] = [
    ReportSpec(
        number=EXECUTIVE_SUMMARY_REPORT_NUMBER,
        title="Executive Summary",
        opening="executive_summary",
        must_include=(
            "A single Markdown bullet list of up to ten bullets and nothing else -- no "
            "heading, no preamble, no closing line. Fewer is better; most packs produce "
            "five or six. Draw only on the finished reports supplied. "
            "This is the page the decision-maker reads, and it draws on everything: the "
            "ranking, the capacity position, objective coverage, candidates worth "
            "scoping, and the upstream findings the reports carry. Where a bullet comes "
            "from another agent's evidence, state it as a fact about the business, not "
            "as 'Technology & Regulation found...'. Candidates are never ranked here "
            "either."
        ),
        exhibit="None. Bullets only -- no tables, exhibits or structured data.",
    ),
    ReportSpec(
        number=1,
        title="Project Universe",
        opening="key_insights",
        must_include=(
            "Two clearly separated sections. Committed projects (from the roadmap): "
            "project, type, origin, status, effort remaining (by bucket and total), "
            "mandatory flag, evidence support. Candidates (discovered or unscoped, "
            "pre-sorted by evidence strength -- preserve that order): candidate, "
            "origin, problem addressed, evidence, support classification. State the "
            "count of each. State plainly that candidates are not ranked because they "
            "lack validated effort, and state the ordering basis."
        ),
        exhibit="Tables as specified above, from the computed/Pass 1 data given -- no ASCII art.",
    ),
    ReportSpec(
        number=2,
        title="Project strategic context",
        opening="plain",
        must_include=(
            "For every project, committed and candidate, synthesise across agents: "
            "customer, market, technology, regulatory, sustainment and business "
            "rationale, with evidence and confidence, drawn from the upstream report "
            "text given to you. Where an agent has not run, state that plainly rather "
            "than leaving the field blank or filling it from an adjacent source."
        ),
        exhibit="One rationale table per project.",
    ),
    ReportSpec(
        number=3,
        title="Prioritised portfolio",
        opening="plain",
        must_include=(
            "Committed projects only -- open with the count of excluded candidates "
            "and why. State the framework and any criterion substitutions. Ranked "
            "table (already computed: rank, score, ties as ties) with project, "
            "financial metric if supplied, effort remaining, class "
            "(mandatory/conditional/discretionary, already computed), key driver, "
            "confidence. Show the underlying dimension values for at least the top "
            "projects -- a score with no visible components is not auditable. Then "
            "the capacity section: per-bucket utilisation table (already computed), "
            "and where any bucket is over 100%, the full bottleneck finding (overage, "
            "mandatory share, deferral set, agreement with rank, contractability) -- "
            "all already computed, narrate all of it. Aggregate utilisation may be "
            "shown alongside per-bucket figures, never instead of them, with an "
            "explicit statement of whether it is misleading."
        ),
        exhibit="Ranked table and per-bucket utilisation table, from the computed data given -- no ASCII art.",
    ),
    ReportSpec(
        number=4,
        title="Mandatory, strategic, discretionary",
        opening="plain",
        must_include=(
            "Three sections using the already-computed classification, mandatory "
            "first, each mandatory project with its declared driver and deadline. "
            "Note explicitly any mandatory project falling below the funding line or "
            "inside a constrained bucket -- that is an escalation, not a ranking "
            "outcome. Then objective coverage: every objective, the committed "
            "projects serving it (from objectives_served), and every objective in "
            "the computed coverage-gap list stated as a finding regardless of how "
            "healthy the ranking looks -- check whether any candidate addresses a "
            "gapped objective and name them."
        ),
        exhibit="Three classified sections, then an objective coverage table -- no ASCII art.",
    ),
    ReportSpec(
        number=5,
        title="Dependency and sequencing",
        opening="plain",
        must_include=(
            "Technical, regulatory, platform, supplier and resource dependencies. "
            "Emit as structured data: for each project, its prerequisites, what it "
            "blocks, and whether it can run in parallel -- the rendering layer draws "
            "the graph. Mark inferred dependencies as inferred and flag them for "
            "confirmation. Name every case where sequence differs from rank, with "
            "the reason (priority is not prerequisite)."
        ),
        exhibit="Structured dependency data (prerequisites/blocks/parallel-safe per project). Do not draw the graph in characters -- no ASCII art.",
    ),
    ReportSpec(
        number=6,
        title="Scenario analysis",
        opening="plain",
        must_include=(
            "Rankings across the customer's defined scenarios (already computed). "
            "Each scenario needs a quantified consequence: which projects move and "
            "by how much, how many clear the funding threshold, the effect on "
            "constrained buckets, the portfolio-level outcome. Null-result rule: "
            "where a scenario produces no material reordering, say so and explain "
            "why rather than manufacturing a difference. Then the cross-scenario "
            "prerequisite check (already computed) -- state every violation "
            "explicitly: the scenario sequences a project ahead of its own "
            "prerequisite."
        ),
        exhibit="Per-scenario ranking table and movement summary, from the computed data given -- no ASCII art.",
    ),
    ReportSpec(
        number=7,
        title="Decision brief",
        opening="scqa",
        must_include=(
            "Decision-ready. Governing insight (Situation/Complication/Question/"
            "Answer). Top committed projects and why they rank, with financial "
            "metric where supplied. What would change the decision: key "
            "assumptions, missing evidence, score sensitivities with thresholds "
            "(e.g. \"rank changes if effort exceeds 18 engineer-months\"), critical "
            "dependencies. Key trade-offs, critical dependencies, major "
            "uncertainties. Decisions required, each addressed to a role, each with "
            "why now. What to scope next: candidates with the strongest evidence, "
            "what each needs to enter the ranked portfolio, and who would supply it "
            "-- the bridge between the two populations and the most actionable "
            "section for a product leader. Human decision gates. Confidence "
            "summary, including what running a missing agent would change."
        ),
        exhibit="Emit \"why this rank\" breakdowns as structured values -- the rendering layer draws any bars. No ASCII charts.",
    ),
]

assert len(REPORTS) == 8
