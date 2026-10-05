"""
Voice of Customer Agent (Agent 1) — the customer context, as plain data, and
the operating tier it implies.

Why this agent's input problem is different (input spec): markets are
publicly discussed, customer voice mostly is not. Context without evidence
produces an external customer-context analysis -- real, useful, and not a
voice of customer analysis -- and the output must say which it is, in the
first line and, at Tier 2, in the title.

Assembling a `CustomerContext` from the database is the service layer's job
(app/voice_of_customer_service.py), exactly as tech_regulation/scoping.py
takes an assembled envelope. This package never sees a DB session, so the
tier and degradation logic below is testable without one.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Controlled lists
# ---------------------------------------------------------------------------

# Input spec §2.1, in its order, plus `feature_request_logs`: prompt v2 Part 1
# names "CRM opportunity notes, request logs" as the minimum source for
# feature request ranking, and §2.1 has no type that carries them -- without
# it, feature ranking could only ever be enabled by dealer feedback.
FILE_TYPES: dict[str, str] = {
    "support_tickets": "Support tickets",
    "warranty_claims": "Warranty claims",
    "service_reports": "Service and field reports",
    "survey_responses": "Survey responses and verbatims",
    "nps_detail": "NPS detail",
    "win_loss_reports": "Win/loss reports",
    "visit_interview_notes": "Customer visit and interview notes",
    "call_centre_logs": "Call centre logs",
    "meeting_minutes": "Meeting minutes and programme reviews",
    "dealer_feedback": "Dealer and distributor feedback",
    "product_reviews_public": "Product reviews, public",
    "field_investigation_reports": "Field investigation reports",
    "feature_request_logs": "Feature request logs and CRM opportunity notes",
}

ATTRIBUTION_POLICIES = ("segment_only", "role_and_segment", "named")
DEFAULT_ATTRIBUTION_POLICY = "segment_only"

# Roles a CSV column can be mapped to. Optional -- an unmapped file still
# ingests, and unmapped columns are passed through. `customer` is not in the
# briefing's list; it is added because the output attribution check needs to
# know which values are customer names, and because a distinct-customer count
# is how a single-source finding is recognised.
COLUMN_ROLES = ("date", "segment", "product", "customer", "description", "category", "severity", "status")


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Segment:
    segment_key: str
    segment_name: str
    description: str = ""
    approximate_count: int | None = None  # None = unknown, stated as such, never 0


@dataclass(frozen=True)
class Channel:
    channel: str
    direction: str = "inbound"  # inbound | outbound | both
    note: str = ""


@dataclass(frozen=True)
class Customer:
    customer_name: str
    segment_key: str = ""
    products: str = ""
    relationship_status: str = ""


@dataclass(frozen=True)
class KnownPainPoint:
    pain_point: str
    segment_key: str = ""
    category_key: str = ""
    their_assessment: str = ""


@dataclass(frozen=True)
class ProductCategory:
    category_key: str
    category_name: str
    description: str = ""
    source: str = "voice-of-customer"  # "tech-regulation" when read through


@dataclass(frozen=True)
class EvidenceFile:
    """What the agent knows about one ingested file before reading it. The
    content itself is rendered separately by evidence.py."""
    file_id: str
    file_type: str
    file_format: str  # text | pdf | csv
    filename: str
    as_of: str = ""
    period_start: str = ""
    period_end: str = ""
    is_sample: bool = False
    sample_description: str = ""
    segment_coverage: tuple[str, ...] = ()
    row_unit: str = ""
    columns: tuple[str, ...] = ()
    column_roles: dict[str, str] = field(default_factory=dict)
    row_count: int | None = None
    page_count: int | None = None
    char_count: int = 0

    @property
    def type_label(self) -> str:
        return FILE_TYPES.get(self.file_type, self.file_type)


@dataclass(frozen=True)
class CustomerContext:
    segments: list[Segment] = field(default_factory=list)
    channels: list[Channel] = field(default_factory=list)
    customers: list[Customer] = field(default_factory=list)
    known_pain_points: list[KnownPainPoint] = field(default_factory=list)
    categories: list[ProductCategory] = field(default_factory=list)
    attribution_policy: str = DEFAULT_ATTRIBUTION_POLICY
    evidence: list[EvidenceFile] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Per-analysis availability (prompt v2 Part 1 table)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Analysis:
    key: str
    label: str
    minimum_source: str
    enabling_types: frozenset[str]


ANALYSES: list[Analysis] = [
    Analysis(
        "pain_point_frequency",
        "Pain point ranking by frequency",
        "Support tickets, warranty claims, service reports",
        frozenset({"support_tickets", "warranty_claims", "service_reports", "call_centre_logs"}),
    ),
    Analysis(
        "sentiment",
        "Sentiment scoring",
        "Survey verbatims, tickets, interview notes, reviews",
        frozenset(
            {
                "survey_responses",
                "nps_detail",
                "support_tickets",
                "call_centre_logs",
                "visit_interview_notes",
                "product_reviews_public",
            }
        ),
    ),
    Analysis(
        "personas",
        "Personas",
        "Visit reports, interview notes, CRM with role data",
        frozenset({"visit_interview_notes"}),
    ),
    Analysis(
        "feature_requests",
        "Feature request ranking",
        "CRM opportunity notes, request logs, dealer feedback",
        frozenset({"feature_request_logs", "dealer_feedback"}),
    ),
    Analysis(
        "win_loss",
        "Win/loss rationale",
        "Win/loss reports",
        frozenset({"win_loss_reports"}),
    ),
    Analysis(
        "segment_clustering",
        "Segment clustering",
        "Any customer-attributed dataset with firmographics",
        frozenset(),  # enabled by attribution, not by type -- see _enabling_files
    ),
    Analysis(
        "belief_testing",
        "Belief testing",
        "Any evidence bearing on a stated pain point",
        frozenset(),  # any evidence at all -- see _enabling_files
    ),
]

# The six analyses that need customer evidence of a particular kind. Belief
# testing is excluded from the count because any evidence enables it.
_TIERING_ANALYSES = [a for a in ANALYSES if a.key != "belief_testing"]

# Tier 1 substantial = at least this many of the six enabled. A judgement,
# not from the spec, which leaves the line undefined: five of six means the
# run is missing at most one kind of evidence, and "full analysis" is then a
# fair description.
SUBSTANTIAL_MIN_ANALYSES = 5

TIER_2 = "tier_2"
TIER_1_PARTIAL = "tier_1_partial"
TIER_1_SUBSTANTIAL = "tier_1_substantial"


def _is_customer_attributed(f: EvidenceFile) -> bool:
    return bool(f.segment_coverage) or "segment" in f.column_roles or "customer" in f.column_roles


def _enabling_files(analysis: Analysis, evidence: list[EvidenceFile]) -> list[EvidenceFile]:
    if analysis.key == "segment_clustering":
        return [f for f in evidence if _is_customer_attributed(f)]
    if analysis.key == "belief_testing":
        return list(evidence)
    return [f for f in evidence if f.file_type in analysis.enabling_types]


@dataclass(frozen=True)
class AnalysisAvailability:
    key: str
    label: str
    available: bool
    enabled_by: list[str]  # filenames
    minimum_source: str
    note: str  # why unavailable, or a qualification (sample-only, no beliefs)


def analysis_availability(context: CustomerContext) -> list[AnalysisAvailability]:
    out: list[AnalysisAvailability] = []
    for analysis in ANALYSES:
        files = _enabling_files(analysis, context.evidence)
        available = bool(files)
        note = ""
        if analysis.key == "belief_testing" and not context.known_pain_points:
            available = False
            note = "No known pain points were recorded, so there are no beliefs to test."
        elif not files:
            note = f"Needs: {analysis.minimum_source}."
        elif all(f.is_sample for f in files):
            note = "Enabled by sample files only -- any frequency is 'in the sample supplied', never a census."
        out.append(
            AnalysisAvailability(
                key=analysis.key,
                label=analysis.label,
                available=available,
                enabled_by=[f.filename for f in files],
                minimum_source=analysis.minimum_source,
                note=note,
            )
        )
    return out


def operating_tier(context: CustomerContext) -> str:
    if not context.evidence:
        return TIER_2
    enabled = sum(1 for a in _TIERING_ANALYSES if _enabling_files(a, context.evidence))
    return TIER_1_SUBSTANTIAL if enabled >= SUBSTANTIAL_MIN_ANALYSES else TIER_1_PARTIAL


TIER_LABELS = {
    TIER_2: "Tier 2 — external customer-context analysis",
    TIER_1_PARTIAL: "Tier 1 partial",
    TIER_1_SUBSTANTIAL: "Tier 1 substantial",
}

# A reader must never mistake one for the other (prompt v2 Part 1): a Tier 2
# run carries this in the title, not only in the first line.
TIER_2_TITLE = "External customer-context analysis"


def report_title(tier: str, title: str) -> str:
    return f"{TIER_2_TITLE} — {title}" if tier == TIER_2 else title


def run_label(tier: str) -> str:
    """Cover-page / run-list label. The title is the unmissable signal."""
    return "External Customer-Context Analysis" if tier == TIER_2 else "Voice of Customer"


_TIER_2_UNAVAILABLE = (
    "sentiment scores (there is no customer feedback to score); pain points ranked by "
    "frequency (no counts exist); validated personas (persona hypotheses to validate are "
    "given instead); feature request frequency; win/loss rationale; segment-specific problem "
    "clustering; and any corroboration or contradiction of the customer's stated beliefs"
)


def operating_tier_statement(context: CustomerContext) -> str:
    """The first line of every run."""
    tier = operating_tier(context)
    if tier == TIER_2:
        return (
            "**Operating tier: TIER 2 — EXTERNAL CUSTOMER-CONTEXT ANALYSIS.** No customer "
            "evidence was supplied, so this run is built from public sources alone and is NOT a "
            "voice of customer analysis. Unavailable, and stated as such rather than produced as "
            f"thin versions: {_TIER_2_UNAVAILABLE}. Uploading tickets, claims, surveys, visit "
            "notes or win/loss reports is what converts this into a voice of customer analysis."
        )

    availability = analysis_availability(context)
    enabled = "; ".join(
        f"{a.label} (from {', '.join(a.enabled_by)})" for a in availability if a.available
    )
    missing = "; ".join(
        f"{a.label} — {a.note}" for a in availability if not a.available
    )
    head = (
        "**Operating tier: TIER 1 SUBSTANTIAL.** Customer evidence supports the full analysis; "
        "public evidence is used for external forces and competitive context only."
        if tier == TIER_1_SUBSTANTIAL
        else "**Operating tier: TIER 1 PARTIAL.** Customer evidence was supplied, and each "
        "analysis below is enabled only by its specific source."
    )
    parts = [head, f"Enabled: {enabled}."]
    if missing:
        parts.append(f"Not available: {missing}")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Degradation -- input spec Part 4, verbatim consequences
# ---------------------------------------------------------------------------

_TICKET_OR_CLAIM = {"support_tickets", "warranty_claims", "service_reports", "call_centre_logs"}
_SURVEY_OR_VERBATIM = {"survey_responses", "nps_detail", "product_reviews_public", "call_centre_logs"}


@dataclass(frozen=True)
class ContextItem:
    """One input, its status, and what its absence costs.

    `consequence` is empty whenever the item is set -- the bug fixed in
    b4f3282 for Agent 5's /readiness, where a missing-case warning beside a
    satisfied item read as an alarm about something that was fine."""
    key: str
    label: str
    status: str  # "set" | "missing"
    count: int
    consequence: str


def context_items(context: CustomerContext) -> list[ContextItem]:
    ev = context.evidence

    def of_types(types: set[str]) -> int:
        return sum(1 for f in ev if f.file_type in types)

    rows: list[tuple[str, str, int, str]] = [
        (
            "segments", "Segments", len(context.segments),
            "Findings cannot be grouped or attributed; frequency is meaningless.",
        ),
        (
            "products", "Products", len(context.categories),
            "Feedback cannot be attached to a product line.",
        ),
        (
            "channels", "Channels", len(context.channels),
            "Cannot identify which feedback routes are unrepresented.",
        ),
        (
            "known_pain_points", "Known pain points", len(context.known_pain_points),
            "No corroboration or contradiction testing — the highest-value analysis is unavailable.",
        ),
        (
            "evidence", "All evidence documents", len(ev),
            "Tier 2 run. Sentiment, frequency, personas and win/loss unavailable. The single most "
            "consequential omission.",
        ),
        (
            "ticket_or_claim", "Ticket or claim data", of_types(_TICKET_OR_CLAIM),
            "Pain points reported unranked.",
        ),
        (
            "survey_or_verbatim", "Survey or verbatim data", of_types(_SURVEY_OR_VERBATIM),
            "Qualitative themes only; no sentiment score.",
        ),
        (
            "win_loss", "Win/loss reports", of_types({"win_loss_reports"}),
            "No win/loss rationale.",
        ),
        (
            "visit_or_interview", "Visit or interview notes", of_types({"visit_interview_notes"}),
            "Persona hypotheses rather than validated personas.",
        ),
    ]
    return [
        ContextItem(
            key=key,
            label=label,
            status="set" if count > 0 else "missing",
            count=count,
            consequence="" if count > 0 else consequence,
        )
        for key, label, count, consequence in rows
    ]


# ---------------------------------------------------------------------------
# Rendering for the prompt
# ---------------------------------------------------------------------------

_POLICY_TEXT = {
    "segment_only": (
        "segment_only — attribute every finding to a segment, never to a named customer, and "
        "never by a detail that identifies one (a programme name, a platform unique to one "
        "customer, or a quoted phrase that would be recognised)."
    ),
    "role_and_segment": (
        "role_and_segment — attribute by role and segment (\"a programme manager at a Tier 1 "
        "integrator reports…\"), never by customer name."
    ),
    "named": "named — customers may be named directly; the customer has confirmed this is permitted.",
}


def render_context_text(context: CustomerContext, *, include_customers: bool = True) -> str:
    """Plain-text rendering for the prompts. Customer vocabulary verbatim --
    segment keys, category keys and channel names are quoted back, so they
    are never normalised.

    `include_customers=False` is used for the research phase, whose prompt
    drives live web search queries: named customers stay out of anything
    sent to a search provider. The synthesis phase sees them, because the
    agent needs to recognise that three documents concern the same customer
    to identify a single-source finding."""

    def _lines(items, fmt):
        return "\n".join(fmt(i) for i in items) or "(none supplied)"

    tier = operating_tier(context)
    sections = [
        f"Operating tier: {TIER_LABELS[tier]}.",
        "## Customer segments\n"
        + _lines(
            context.segments,
            lambda s: f"- {s.segment_key}: {s.segment_name}"
            + (f" — {s.description}" if s.description else "")
            + f" (approximate count: {s.approximate_count if s.approximate_count is not None else 'unknown'})",
        ),
        "## Product categories\n"
        + _lines(
            context.categories,
            lambda c: f"- {c.category_key}: {c.category_name}"
            + (f" — {c.description}" if c.description else ""),
        ),
        "## Channels\n"
        + _lines(
            context.channels,
            lambda c: f"- {c.channel} ({c.direction})" + (f" — {c.note}" if c.note else ""),
        ),
    ]
    if include_customers:
        sections.append(
            "## Named customers (confidential — for attribution inside the analysis only)\n"
            + _lines(
                context.customers,
                lambda c: f"- {c.customer_name}"
                + (f" [segment {c.segment_key}]" if c.segment_key else "")
                + (f", products: {c.products}" if c.products else "")
                + (f", relationship: {c.relationship_status}" if c.relationship_status else ""),
            )
        )
    sections += [
        "## Attribution policy (honour exactly)\n" + _POLICY_TEXT.get(
            context.attribution_policy, _POLICY_TEXT[DEFAULT_ATTRIBUTION_POLICY]
        ),
        "## Known pain points — the customer's own beliefs, to be TESTED, not assumed\n"
        + _lines(
            context.known_pain_points,
            lambda k: f"- \"{k.pain_point}\""
            + (f" [segment {k.segment_key}]" if k.segment_key else "")
            + (f" [product {k.category_key}]" if k.category_key else "")
            + (f" — their assessment: {k.their_assessment}" if k.their_assessment else ""),
        ),
        "## Analysis availability (state per analysis which source enabled it and which are missing)\n"
        + _lines(
            analysis_availability(context),
            lambda a: f"- {a.label}: "
            + ("AVAILABLE" if a.available else "UNAVAILABLE")
            + (f" — enabled by {', '.join(a.enabled_by)}" if a.available and a.enabled_by else "")
            + (f" — {a.note}" if a.note else ""),
        ),
        "## What is missing from this context, and what it costs\n"
        + _lines(
            [i for i in context_items(context) if i.status == "missing"],
            lambda i: f"- {i.label}: {i.consequence}",
        ),
    ]
    return "\n\n".join(sections)
