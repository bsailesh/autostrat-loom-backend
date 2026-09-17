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


class BriefFileOut(BaseModel):
    id: str
    file_type: str
    filename: str
    as_of: datetime | None
    uploaded_by: str
    row_count: int
    validation_status: str
    issues: list[IngestIssueOut]
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
