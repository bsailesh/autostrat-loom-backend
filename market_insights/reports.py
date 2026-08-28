"""
The nine required outputs for the Market Insights agent.

Each entry captures, close to verbatim from the spec's "Required Outputs" and
"Visualization Requirements" sections:
  - the report's plain descriptive title (kept as the spec names it)
  - what the report must include
  - the named exhibit type the spec requires for that report, if any
  - whether it opens with the SCQA Governing Insight (Report 1 only) or a
    Key Insights box (every other report)
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReportSpec:
    number: int
    title: str
    opening: str  # "scqa" or "key_insights"
    must_include: str
    exhibit: str


REPORTS: list[ReportSpec] = [
    ReportSpec(
        number=1,
        title="Executive Market Summary",
        opening="scqa",
        must_include=(
            "Significant market developments; competitive activity; customer demand "
            "changes; macroeconomic observations; industry shifts; confidence summary."
        ),
        exhibit=(
            "Open with the Governing Insight in Situation / Complication / Question / "
            "Answer form (a claim, not a topic label). Include at least one visual — "
            "a color-coded table of the most significant developments and their "
            "confidence is the natural choice."
        ),
    ),
    ReportSpec(
        number=2,
        title="Market Landscape Report",
        opening="key_insights",
        must_include=(
            "Industry overview; market segmentation; geographic trends; growth "
            "observations; declining markets; industry consolidation; emerging "
            "applications."
        ),
        exhibit=(
            "REQUIRED exhibits: (a) TAM / SAM / SOM as nested concentric rings "
            "rendered in text/ASCII, each ring labelled with its value and a "
            "bottom-up formula footnote (e.g. Number of Accounts × Annual Contract "
            "Value); (b) whenever public sources disagree on market size, a bar "
            "chart (Markdown table with a bar column) comparing the size estimate by "
            "source. Market size MUST be triangulated per the Triangulation "
            "Requirement — report the range, build one bottom-up internal estimate "
            "with every assumption listed and sourced, reconcile it against the "
            "external range, and confidence-tag it. An unweighted average is not "
            "triangulation."
        ),
    ),
    ReportSpec(
        number=3,
        title="Competitor Intelligence Report",
        opening="key_insights",
        must_include=(
            "Competitor profiles; new product announcements; partnerships; "
            "acquisitions; public product positioning; market observations."
        ),
        exhibit=(
            "Include a color-coded competitor activity table (competitor × activity "
            "type × date × confidence) and/or an industry timeline of M&A, "
            "partnerships and launches over the last 5 years."
        ),
    ),
    ReportSpec(
        number=4,
        title="Competitive Feature Comparison Matrix",
        opening="key_insights",
        must_include=(
            "Compare the current product plus up to four competitors. Include ONLY "
            "verifiable public information. Do not speculate about undisclosed "
            "capabilities. If no single 'current product' is defined by the subject, "
            "state that and compare the leading vendors' flagship offerings, naming "
            "which one is treated as the reference."
        ),
        exhibit=(
            "REQUIRED exhibit: a Harvey Ball grid (rows = features such as product "
            "portfolio, performance specs, positioning, digital capabilities, "
            "connectivity, service offerings, warranty, sustainability claims, public "
            "differentiators; columns = the reference product + up to 4 competitors). "
            "Render Harvey Balls with the legend: ● full / ◕ strong / ◑ partial / "
            "◔ limited / ○ none / — undisclosed. Every filled cell must be traceable "
            "to a cited public source; use — where the capability is undisclosed."
        ),
    ),
    ReportSpec(
        number=5,
        title="Customer Demand Report",
        opening="key_insights",
        must_include=(
            "Demand shifts; customer buying trends; industry purchasing patterns; "
            "market adoption observations; customer segment changes."
        ),
        exhibit=(
            "Include a customer-segment distribution table or a demand-direction "
            "table (segment × demand direction [Growth/Stable/Emerging/Declining] × "
            "evidence × confidence)."
        ),
    ),
    ReportSpec(
        number=6,
        title="Market Trends Report",
        opening="key_insights",
        must_include=(
            "Emerging trends; stable trends; declining trends; seasonal patterns; "
            "long-term shifts. Provide evidence for each."
        ),
        exhibit=(
            "REQUIRED exhibit: a table with one row per trend and a trend-indicator "
            "column valued Increasing / Stable / Declining / Emerging, plus evidence "
            "and confidence columns."
        ),
    ),
    ReportSpec(
        number=7,
        title="Market SWOT",
        opening="key_insights",
        must_include=(
            "Strengths; Weaknesses; Opportunities; Threats. Market-based SWOT only. "
            "Each item shall contain: Observation; Supporting evidence; Source; "
            "Observation date; Confidence. Do NOT include recommendations."
        ),
        exhibit=(
            "REQUIRED exhibit: a 2×2 SWOT quadrant rendered as a Markdown table "
            "(Strengths | Weaknesses on the top row, Opportunities | Threats on the "
            "bottom), then the fully-attributed item list beneath it."
        ),
    ),
    ReportSpec(
        number=8,
        title="Market Intelligence Digest",
        opening="key_insights",
        must_include=(
            "A concise executive digest of: market observations; competitive "
            "observations; customer observations; external market forces; knowledge "
            "gaps; data quality; confidence summary. NO recommendations."
        ),
        exhibit=(
            "Include a color-coded confidence / data-quality table across the "
            "intelligence areas (area × key observation × data quality × confidence)."
        ),
    ),
    ReportSpec(
        number=9,
        title="Industry Trends",
        opening="key_insights",
        must_include=(
            "Current industry trends in the three-column format. For each trend: "
            "Catalyst (what is changing in the technology or consumer-behaviour "
            "landscape) — Market Shift (how the industry is reacting right now) — "
            "Commercial Impact (the direct opportunity or threat to the business). "
            "Include up-to-date data points, growth percentages (CAGR), or "
            "authoritative analyst quotes (e.g. Gartner, IDC)."
        ),
        exhibit=(
            "REQUIRED exhibit: a 3-column grid (Catalyst | Market Shift | Commercial "
            "Impact) as a Markdown table, one row per trend, each cell carrying its "
            "own confidence tag and at least one cited data point or analyst quote."
        ),
    ),
]

assert len(REPORTS) == 9
