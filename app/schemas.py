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


class LoginResponse(BaseModel):
    token: str
    tenant_id: str
    tenant_name: str
    user_email: str
    role: str
    expires_at: datetime


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
