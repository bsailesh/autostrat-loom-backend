"""
Pydantic schemas.

Two jobs happen here:
1. Normal API request/response validation (the FastAPI-facing schemas).
2. Structured-output contracts for each agent's Claude call. Each agent uses
   its schema's JSON Schema representation as a forced tool definition, so
   Claude's response is always parseable structured data, never free text we
   have to regex out of a paragraph.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# ---------- Users / login ----------

class UserCreate(BaseModel):
    email: str
    password: str = Field(min_length=8)
    role: str = "member"


class UserOut(BaseModel):
    id: str
    email: str
    role: str
    created_at: datetime

    model_config = {"from_attributes": True}


class LoginRequest(BaseModel):
    email: str
    password: str


class SignupRequest(BaseModel):
    """Self-serve signup: always creates a tenant with the signer as its owner."""
    email: str
    password: str = Field(min_length=8)
    tenant_name: str = Field(default="", description="Workspace name; defaults to '<email>'s workspace'")


class LoginResponse(BaseModel):
    token: str
    tenant_id: str
    tenant_name: str
    user_email: str
    role: str
    expires_at: datetime


class MeResponse(BaseModel):
    user_id: str
    email: str
    role: str
    tenant_id: str
    tenant_name: str


class InviteCreate(BaseModel):
    email: str
    role: str = Field(default="member", description="owner | admin | member")


class InviteOut(BaseModel):
    id: str
    email: str
    role: str
    token: str  # returned here because there's no email delivery in this phase
    tenant_id: str
    expires_at: datetime
    accepted_at: datetime | None = None

    model_config = {"from_attributes": True}


class InviteAcceptRequest(BaseModel):
    token: str
    password: str = Field(min_length=8)


# ---------- Market Insights agent ----------

class AgentScopeUpsertRequest(BaseModel):
    """PUT body for the standing agent scope. product_line is required; the
    handler returns 400 if it's missing or blank."""
    product_line: str | None = Field(default=None, description="Required. Product line / market this agent tracks.")
    competitors: str | None = Field(
        default=None,
        description=(
            "Optional. Competitors the user wants explicitly covered. Does not limit "
            "which competitors the agent discovers."
        ),
    )
    geography: str | None = Field(default=None, description="Optional. Geographic focus.")


class AgentScopeResponse(BaseModel):
    configured: bool
    agent_type: str
    product_line: str | None = None
    competitors: str | None = None
    geography: str | None = None
    updated_at: datetime | None = None


class MarketInsightsRunRequest(BaseModel):
    """The run takes no subject — it uses the tenant's configured scope. These
    are optional execution tweaks only."""
    model: str | None = Field(default=None, description="Optional model override (e.g. claude-sonnet-5)")
    max_searches: int | None = Field(default=None, ge=1, le=40)
    research_rounds: int | None = Field(default=None, ge=1, le=4)


class AgentRunOut(BaseModel):
    id: str
    agent_type: str
    subject: str
    status: str
    error: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AgentReportSummary(BaseModel):
    id: str
    run_id: str
    report_number: int
    title: str
    confidence_summary: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AgentReportOut(BaseModel):
    id: str
    run_id: str
    report_number: int
    title: str
    content: str
    confidence_summary: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------- Strategy Synthesis agent ----------

class CapacityBucketIn(BaseModel):
    bucket_key: str = Field(description="Used verbatim as a CSV column header -- letters/digits/underscore, starts with a letter")
    bucket_name: str
    contractable: str = Field(default="no", description="yes | partial | no")
    note: str = ""


class CapacityBucketsUpsertRequest(BaseModel):
    """PUT body: the complete set of buckets for this tenant, 2-8 entries.
    Replaces whatever was previously declared."""
    buckets: list[CapacityBucketIn]


class CapacityBucketOut(BaseModel):
    id: str
    bucket_key: str
    bucket_name: str
    contractable: str
    note: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class IngestIssueOut(BaseModel):
    severity: str  # "error" | "warning"
    row: int | None
    field: str | None
    message: str


class IngestResultOut(BaseModel):
    file_type: str
    row_count: int
    stored: bool
    validation_status: str
    errors: list[IngestIssueOut]
    warnings: list[IngestIssueOut]
    columns: list[str]


class BriefFileOut(BaseModel):
    id: str
    file_type: str
    filename: str
    as_of: datetime | None
    uploaded_by: str
    row_count: int
    validation_status: str
    issues: list[IngestIssueOut]
    columns: list[str]
    is_stale: bool
    created_at: datetime


class StrategyRunRequest(BaseModel):
    """Optional execution tweaks. fiscal_year defaults to the tenant's
    current fiscal year (from strategy_config, or the sole fiscal year
    present in capacity data) when omitted. A run is never blocked by an
    incomplete brief -- see GET /readiness for what's missing and why."""
    fiscal_year: str | None = None
    upstream_run_overrides: dict[str, str] | None = Field(
        default=None,
        description="agent_type -> run_id, overriding the default most-recent-successful selection per agent",
    )
    model: str | None = Field(default=None, description="Optional model override (e.g. claude-sonnet-5)")


class EffortBandIn(BaseModel):
    band_name: str
    min_units: float | None = None
    max_units: float | None = None


class EffortBandOut(BaseModel):
    id: str
    band_name: str
    min_units: float | None
    max_units: float | None

    model_config = {"from_attributes": True}


class StrategyRuleIn(BaseModel):
    rule_type: str
    value: str = ""
    note: str = ""


class StrategyRuleOut(BaseModel):
    id: str
    rule_type: str
    value: str
    note: str

    model_config = {"from_attributes": True}


class StrategyConfigUpsertRequest(BaseModel):
    effort_unit: str = "weeks"
    fiscal_year_start_month: int = Field(default=1, ge=1, le=12)
    fiscal_year_label_format: str = "FY{yy}"
    project_types: list[str] = Field(default_factory=list)
    effort_bands: list[EffortBandIn] = Field(default_factory=list)
    rules: list[StrategyRuleIn] = Field(default_factory=list)


class StrategyConfigResponse(BaseModel):
    configured: bool
    effort_unit: str
    fiscal_year_start_month: int
    fiscal_year_label_format: str
    project_types: list[str]
    effort_bands: list[EffortBandOut]
    rules: list[StrategyRuleOut]


class StrategicObjectiveIn(BaseModel):
    objective_key: str
    text: str
    horizon: str = ""
    owner: str = ""
    measure: str = ""


class StrategicObjectivesUpsertRequest(BaseModel):
    objectives: list[StrategicObjectiveIn]


class StrategicObjectiveOut(BaseModel):
    id: str
    objective_key: str
    text: str
    horizon: str
    owner: str
    measure: str

    model_config = {"from_attributes": True}


class ProposedProjectIn(BaseModel):
    project_key: str
    name: str
    proposed_by: str = ""
    description: str = ""
    rationale: str = ""


class ProposedProjectsUpsertRequest(BaseModel):
    proposals: list[ProposedProjectIn]


class ProposedProjectOut(BaseModel):
    id: str
    project_key: str
    name: str
    proposed_by: str
    description: str
    rationale: str

    model_config = {"from_attributes": True}


class PrioritizationCriterionIn(BaseModel):
    """Weight is a fraction of 1.0 (e.g. 0.25 for 25%), not a percentage
    (e.g. 25) -- the `le=1` bound rejects the latter at the endpoint rather
    than letting it reach compute.py's weights-sum-to-1.0 check. A
    framework's criteria weights must sum to 1.0; see put_framework."""
    criterion: str
    weight: float = Field(ge=0, le=1)
    source_agent: str = ""


class FrameworkUpsertRequest(BaseModel):
    framework: str = "weighted_scoring"
    criteria: list[PrioritizationCriterionIn]


class PrioritizationCriterionOut(BaseModel):
    criterion: str
    weight: float
    source_agent: str

    model_config = {"from_attributes": True}


class FrameworkResponse(BaseModel):
    configured: bool
    framework: str
    criteria: list[PrioritizationCriterionOut]


class ScenarioWeightIn(BaseModel):
    """A per-criterion override on top of the framework's declared weight
    (see ScenarioWeight in app/models.py) -- a fraction of 1.0, same
    convention as PrioritizationCriterionIn.weight."""
    criterion: str
    weight: float = Field(ge=0, le=1)


class ScenarioIn(BaseModel):
    name: str
    emphasis: str = ""
    weights: list[ScenarioWeightIn]


class ScenariosUpsertRequest(BaseModel):
    scenarios: list[ScenarioIn]


class ScenarioWeightOut(BaseModel):
    criterion: str
    weight: float

    model_config = {"from_attributes": True}


class ScenarioOut(BaseModel):
    id: str
    name: str
    emphasis: str
    weights: list[ScenarioWeightOut]


class ReadinessItemOut(BaseModel):
    item: str
    status: str  # "set" | "missing"
    consequence: str


class CitationOut(BaseModel):
    agent: str
    report_number: int
    section: str
    classification: str
    confidence: str
    summary: str


class CandidatePatchRequest(BaseModel):
    status: str = Field(description="under_review | scoped | dismissed")
    dismissal_reason: str = ""


class CandidateScopeRequest(BaseModel):
    """Scopes a candidate into the roadmap as a committed project. No score
    or rank is carried over -- the candidate's evidence supported discovery,
    not prioritization; the new project is ranked from scratch, like any
    other roadmap entry, next run."""
    project_type: str = ""
    target_fy: str = ""
    target_gate: str = ""
    owner: str = ""
    effort_by_bucket: dict[str, float] = Field(min_length=1)


class LinkedCandidateWorkOut(BaseModel):
    """The Tech & Regulation candidate work item an Agent 5 candidate was
    derived from, read live from tr_candidate_work rather than copied.

    Its `status` is independent of the Agent 5 candidate's: this one answers
    "is this finding real and relevant", the other answers "would we scope
    this as a project". A finding dismissed in Tech & Regulation whose
    candidate is still active in Agent 5 is a disagreement between two
    judgements, and the UI shows it rather than hiding it."""
    candidate_key: str
    driver: str
    work_date: str | None
    date_basis: str
    status: str
    dismissal_reason: str


class DiscoveredCandidateOut(BaseModel):
    id: str
    candidate_key: str
    name: str
    origin: str
    problem_addressed: str
    evidence_summary: str
    support_classification: str
    source_citations: list[CitationOut]
    status: str
    dismissal_reason: str
    created_at: datetime
    updated_at: datetime
    # Present only for candidates carried from structured candidate work.
    # None for prose-derived ones, which is how the UI tells them apart.
    linked_candidate_work: LinkedCandidateWorkOut | None = None

    model_config = {"from_attributes": True}


# ---------- Contact form ----------

class ContactRequest(BaseModel):
    full_name: str
    work_email: str
    company: str = ""
    role: str = ""
    interest: str = "Agent subscription"
    message: str


class ContactAck(BaseModel):
    status: str = "received"


# ---------- Tenants / auth ----------

class TenantCreate(BaseModel):
    name: str


class TenantOut(BaseModel):
    id: str
    name: str
    created_at: datetime
    api_key: str  # only ever returned once, at creation time

    model_config = {"from_attributes": True}


# ---------- Initiatives ----------

class InitiativeCreate(BaseModel):
    title: str
    description: str = ""
    category: str = Field(description="growth | irad | customer_funded | sustainment | obsolescence")


class InitiativeOut(BaseModel):
    id: str
    title: str
    description: str
    category: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------- Prioritize agent ----------

class PrioritizeRequest(BaseModel):
    initiative_id: str


class PrioritizeScoreSchema(BaseModel):
    """Structured output contract for the Prioritize agent's Claude call."""
    reach: float = Field(ge=0, le=10, description="How many customers/segments this affects, 0-10")
    impact: float = Field(ge=0, le=10, description="Magnitude of value if delivered, 0-10")
    confidence: float = Field(ge=0, le=10, description="Confidence in the reach/impact estimate, 0-10")
    effort: float = Field(ge=0.5, le=10, description="Relative implementation effort, 0.5-10")
    rationale: str = Field(description="2-4 sentence explanation of the score, written for a PM audience")


class ScoreOut(BaseModel):
    id: str
    initiative_id: str
    reach: float
    impact: float
    confidence: float
    effort: float
    composite_score: float
    rationale: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------- Discover agent ----------

class DiscoverRequest(BaseModel):
    source_type: str = Field(description="support_ticket | sales_call | review | other")
    raw_text: str


class DiscoverExtractionSchema(BaseModel):
    """Structured output contract for the Discover agent's Claude call."""
    is_validated_problem: bool = Field(description="True only if the text describes a concrete customer problem, not noise")
    extracted_problem: str = Field(description="One or two sentence statement of the underlying problem, in the customer's terms")
    suggested_category: str = Field(description="growth | irad | customer_funded | sustainment | obsolescence")
    confidence: float = Field(ge=0, le=10, description="Confidence this is a real, distinct, actionable problem")


class SignalOut(BaseModel):
    id: str
    source_type: str
    raw_text: str
    extracted_problem: str
    suggested_category: str
    confidence: float
    is_validated: bool
    linked_initiative_id: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------- Sustain agent ----------

class AssetCreate(BaseModel):
    name: str
    asset_type: str = Field(description="part | platform | dependency")
    eol_date: str | None = None
    criticality: str = "medium"


class AssetOut(BaseModel):
    id: str
    name: str
    asset_type: str
    eol_date: str | None
    criticality: str
    created_at: datetime

    model_config = {"from_attributes": True}


class SustainRequest(BaseModel):
    asset_id: str


class SustainAssessmentSchema(BaseModel):
    """Structured output contract for the Sustain agent's Claude call."""
    risk_level: str = Field(description="low | medium | high | critical")
    recommended_action: str = Field(description="One concrete next step, one sentence")
    rationale: str = Field(description="2-3 sentence explanation of the risk assessment")


class SustainAssessmentOut(BaseModel):
    id: str
    asset_id: str
    risk_level: str
    recommended_action: str
    rationale: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------- Align agent ----------

class AlignRequest(BaseModel):
    title: str = "Roadmap Update"
    initiative_ids: list[str]


class AlignDraftSchema(BaseModel):
    """Structured output contract for the Align agent's Claude call."""
    exec_summary: str = Field(description="3-5 sentence summary for a leadership audience")
    narrative: str = Field(description="Fuller roadmap narrative in markdown, organized by theme or priority")


class RoadmapDocOut(BaseModel):
    id: str
    title: str
    exec_summary: str
    narrative: str
    included_initiative_ids: list[str]
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------- Brief agent ----------

class BriefRequest(BaseModel):
    title: str = "Portfolio Brief"
    notes: str = ""  # optional freeform steer, e.g. "focus on obsolescence risk this quarter"


class BriefDraftSchema(BaseModel):
    """Structured output contract for the Brief agent's Claude call."""
    content: str = Field(description="Board-ready markdown report covering portfolio status, top risks, and recommendations")


class BriefDocOut(BaseModel):
    id: str
    title: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------- Audit log ----------

class AuditLogOut(BaseModel):
    id: str
    actor_label: str
    agent_name: str
    action: str
    input_summary: str
    output_summary: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------- Technology & Regulatory Intelligence agent (Agent 3) ----------
#
# The eight scoping dimensions are each a GET/PUT list: the PUT replaces that
# dimension wholesale, which keeps the form-based UI simple (edit the rows,
# save the section) and avoids per-row id juggling for an envelope this
# small. Controlled vocabularies are validated here rather than in the
# database, matching app/models.py's convention of no DB-level enums.


class TrProductCategoryIn(BaseModel):
    category_key: str = Field(min_length=1, max_length=64)
    category_name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)


class TrJurisdictionIn(BaseModel):
    jurisdiction: str = Field(min_length=1, max_length=200)
    role: Literal["primary", "secondary", "export_only"] = "primary"


class TrCertificationBasisIn(BaseModel):
    category_key: str = Field(min_length=1, max_length=64)
    # Controlled list with a free-text fallback: TSO, ETSO, CS, Part,
    # MIL-STD, STC, PMA and Standard are not interchangeable and the agent
    # needs to know which is which. Where "Other", basis_identifier is used
    # verbatim.
    basis_type: Literal["TSO", "ETSO", "CS", "Part", "MIL-STD", "STC", "PMA", "Standard", "Other"]
    basis_identifier: str = Field(min_length=1, max_length=200)
    status: str = Field(default="", max_length=100)
    held_since: str = Field(default="", max_length=32)


class TrPlatformIn(BaseModel):
    platform: str = Field(min_length=1, max_length=200)
    platform_class: str = Field(default="", max_length=200)
    relationship: Literal["shipping", "pursuing", "in_service", "sunsetting"] = "shipping"
    programme_status: str = Field(default="", max_length=200)


class TrStandardHeldIn(BaseModel):
    standard_id: str = Field(min_length=1, max_length=100)
    revision: str = Field(default="", max_length=32)
    scope: str = Field(default="", max_length=500)
    status: Literal["compliant", "certified", "in_progress", "lapsed", ""] = ""


class TrSupplierIn(BaseModel):
    supplier: str = Field(min_length=1, max_length=200)
    what_they_supply: str = Field(default="", max_length=500)
    criticality: Literal["single_source", "dual_sourced", "multi_source", ""] = ""


class TrDomainIn(BaseModel):
    domain: str = Field(min_length=1, max_length=200)


class TrExclusionIn(BaseModel):
    exclusion_type: Literal["platform_class", "jurisdiction", "domain", "category"]
    value: str = Field(min_length=1, max_length=200)
    reason: str = Field(default="", max_length=1000)


class TrScopeStateItemOut(BaseModel):
    """One envelope dimension, its status, and what its absence costs.

    `consequence` is empty whenever `status` is "set". The missing-case
    warning shown next to a populated dimension is the bug fixed in b4f3282
    for Agent 5's /readiness -- it reads as an alarm about something that is
    actually fine, and it trains the user to ignore the column."""
    key: str
    label: str
    status: str  # "set" | "missing"
    count: int
    consequence: str


class TrScopeStateOut(BaseModel):
    operating_state: str  # scoped | partially_scoped | unscoped
    statement: str  # the first-line statement the run itself will carry
    items: list[TrScopeStateItemOut]


class TechRegulationRunRequest(BaseModel):
    """Everything the agent needs comes from the stored envelope; these are
    optional execution tweaks only. Note there is no "force" or "confirm"
    flag: a run is never blocked by incomplete scoping, it degrades and says
    so."""
    model: str | None = Field(default=None, description="Optional model override (e.g. claude-sonnet-5)")
    max_searches: int | None = Field(default=None, ge=1, le=40)
    research_rounds: int | None = Field(default=None, ge=1, le=4)


class TrCandidateWorkOut(BaseModel):
    candidate_key: str
    driver: str
    work_date: str | None
    date_basis: str
    date_absent_reason: str
    applicability: dict
    work_implied: str
    work_implied_description: str
    platform_relationship: str | None
    classification: str
    confidence: str
    source: str
    source_date: str
    status: str
    dismissal_reason: str
    first_seen_run_id: str | None
    last_seen_run_id: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TrCandidateWorkPatchRequest(BaseModel):
    """Triage only. The evidence fields are the agent's output and are
    refreshed by the next run, so they are not editable here -- an edit would
    be silently overwritten, which is worse than not offering it."""
    status: Literal["new", "under_review", "accepted", "dismissed"]
    dismissal_reason: str = Field(default="", max_length=2000)


# ---------- Voice of Customer agent (Agent 1) ----------
#
# Controlled lists are Literal here and plain String in the database,
# matching app/models.py's convention of no DB-level enums. The evidence
# file_type list lives in voice_of_customer/context.py (FILE_TYPES) and is
# validated at the endpoint, since it is the package's vocabulary.


class VocSegmentIn(BaseModel):
    segment_key: str = Field(min_length=1, max_length=64)
    segment_name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    # None means unknown -- a legitimate answer, and never coerced to 0.
    approximate_count: int | None = Field(default=None, ge=0)

    model_config = {"from_attributes": True}


class VocChannelIn(BaseModel):
    channel: str = Field(min_length=1, max_length=200)
    direction: Literal["inbound", "outbound", "both"] = "inbound"
    note: str = Field(default="", max_length=2000)

    model_config = {"from_attributes": True}


class VocCustomerIn(BaseModel):
    customer_name: str = Field(min_length=1, max_length=200)
    segment_key: str = Field(default="", max_length=64)
    products: str = Field(default="", max_length=2000)
    relationship_status: str = Field(default="", max_length=200)

    model_config = {"from_attributes": True}


class VocKnownPainPointIn(BaseModel):
    pain_point: str = Field(min_length=1, max_length=2000)
    segment_key: str = Field(default="", max_length=64)
    category_key: str = Field(default="", max_length=64)
    their_assessment: str = Field(default="", max_length=2000)

    model_config = {"from_attributes": True}


class VocConfigIn(BaseModel):
    attribution_policy: Literal["segment_only", "role_and_segment", "named"] = "segment_only"

    model_config = {"from_attributes": True}


class VocProductCategoryIn(BaseModel):
    """A VoC-specific addition. Categories already declared for Tech &
    Regulation are read through and are not re-entered here."""
    category_key: str = Field(min_length=1, max_length=64)
    category_name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)

    model_config = {"from_attributes": True}


class VocCategoryOut(BaseModel):
    category_key: str
    category_name: str
    description: str
    source: Literal["tech-regulation", "voice-of-customer"]


class VocContextStateItemOut(BaseModel):
    """`consequence` is empty whenever `status` is "set" (b4f3282)."""
    key: str
    label: str
    status: str  # "set" | "missing"
    count: int
    consequence: str


class VocAnalysisOut(BaseModel):
    key: str
    label: str
    available: bool
    enabled_by: list[str]
    minimum_source: str
    note: str


class VocContextStateOut(BaseModel):
    operating_tier: str  # tier_2 | tier_1_partial | tier_1_substantial
    tier_label: str
    run_label: str  # "External Customer-Context Analysis" at Tier 2, else "Voice of Customer"
    statement: str  # the first-line statement the run itself will carry
    items: list[VocContextStateItemOut]
    analyses: list[VocAnalysisOut]


class VocEvidenceFileOut(BaseModel):
    id: str
    file_type: str
    file_format: str
    filename: str
    content_type: str
    size_bytes: int
    as_of: str
    period_start: str
    period_end: str
    is_sample: bool
    sample_description: str
    segment_coverage: list[str]
    row_unit: str
    columns: list[str]
    column_roles: dict[str, str]
    row_count: int | None
    page_count: int | None
    char_count: int
    ingest_status: str
    issues: list[dict]
    created_at: datetime

    model_config = {"from_attributes": True}


class VocEvidencePatchRequest(BaseModel):
    """Metadata only -- the content is never edited after ingest. Used to
    confirm the CSV column mapping once the detected columns are seen."""
    file_type: str | None = None
    as_of: str | None = Field(default=None, max_length=32)
    period_start: str | None = Field(default=None, max_length=32)
    period_end: str | None = Field(default=None, max_length=32)
    is_sample: bool | None = None
    sample_description: str | None = Field(default=None, max_length=2000)
    segment_coverage: list[str] | None = None
    row_unit: str | None = Field(default=None, max_length=64)
    column_roles: dict[str, str] | None = None


class VoiceOfCustomerRunRequest(BaseModel):
    """Optional execution tweaks only. No force/confirm flag: a run is never
    blocked -- without evidence it degrades to Tier 2 and says so."""
    model: str | None = Field(default=None, description="Optional model override (e.g. claude-sonnet-5)")
    max_searches: int | None = Field(default=None, ge=1, le=40)
    research_rounds: int | None = Field(default=None, ge=1, le=4)


class VocRunOut(BaseModel):
    id: str
    agent_type: str
    subject: str
    status: str
    error: str | None = None
    created_at: datetime
    # From voc_run_meta; null until the run has succeeded.
    operating_tier: str | None = None
    run_label: str | None = None
    sampling_notes: list[str] = Field(default_factory=list)
