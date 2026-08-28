"""
ORM models.

Tenant isolation strategy: every business table carries a `tenant_id` column
and is queried exclusively through the scoped-session helpers in
app/tenant_scope.py. This is "logical" (shared-database, tenant_id-scoped)
isolation rather than one-database-per-tenant. It's the standard pattern for
mid-market/enterprise multi-tenant SaaS, and it's easier to operate than
per-tenant databases — but it depends entirely on discipline in the query
layer, which is why that layer is centralized and every write path in this
codebase goes through it instead of raw db.query(Model) calls.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, Float, ForeignKey, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    api_keys: Mapped[list["ApiKey"]] = relationship(back_populates="tenant", cascade="all, delete-orphan")


class ApiKey(Base):
    """
    Auth model for this demo: bearer API keys, one or more per tenant, each
    with a role. This is intentionally simple. Before onboarding real
    enterprise customers, this is the layer to replace/extend with SSO
    (SAML/OIDC) — the rest of the app only depends on "give me the current
    tenant_id and role," so swapping the auth mechanism underneath doesn't
    ripple through the agents or routers.
    """
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    key: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), nullable=False)
    label: Mapped[str] = mapped_column(String, default="default")
    role: Mapped[str] = mapped_column(String, default="member")  # "admin" | "member"
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    # Set only for keys minted by /auth/login ("session tokens"). Long-lived
    # keys created via /admin/tenants (or for machine-to-machine use) leave
    # both null and never expire.
    user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    tenant: Mapped["Tenant"] = relationship(back_populates="api_keys")


class User(Base):
    """A human who can log in to a tenant's workspace via the front end."""
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, default="member")  # "admin" | "member"
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Invite(Base):
    """
    A pending invitation for someone to join an *existing* tenant. Created by an
    owner/admin; accepting one creates a User attached to `tenant_id` — never a
    new tenant. The token is the capability: whoever holds it and knows the
    invited email can accept, once, before it expires.
    """
    __tablename__ = "invites"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    email: Mapped[str] = mapped_column(String, index=True, nullable=False)
    role: Mapped[str] = mapped_column(String, default="member")  # role the accepted user gets
    token: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    invited_by_user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AgentRun(Base):
    """
    One invocation of a long-running agent (Phase 2: Market Insights) for a
    tenant. The heavy work happens in a background task; `status` tracks it:
    pending -> running -> succeeded | failed.
    """
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    agent_type: Mapped[str] = mapped_column(String, nullable=False)  # "market-insights"
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, default="pending")  # pending | running | succeeded | failed
    error: Mapped[str | None] = mapped_column(Text, nullable=True)  # populated only when status == "failed"
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class AgentReport(Base):
    """
    One report produced by an AgentRun. For Market Insights there are nine per
    successful run. `tenant_id` is denormalized from the parent run (same
    pattern as Score/Signal carrying tenant_id alongside their parent FK) so
    every read goes through the standard tenant-scoped query helpers.
    """
    __tablename__ = "agent_reports"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    run_id: Mapped[str] = mapped_column(String, ForeignKey("agent_runs.id"), index=True, nullable=False)
    report_number: Mapped[int] = mapped_column(nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    confidence_summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class ContactMessage(Base):
    """
    A submission from the public contact form. Not tenant-scoped — the
    person submitting it isn't a customer yet. Stored regardless of whether
    the notification email succeeds, so a submission is never silently lost
    to an SMTP outage.
    """
    __tablename__ = "contact_messages"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    full_name: Mapped[str] = mapped_column(String)
    work_email: Mapped[str] = mapped_column(String)
    company: Mapped[str] = mapped_column(String, default="")
    role: Mapped[str] = mapped_column(String, default="")
    interest: Mapped[str] = mapped_column(String, default="")
    message: Mapped[str] = mapped_column(Text)
    email_sent: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Initiative(Base):
    """A unit of work competing for roadmap space: a feature, fix, or bet."""
    __tablename__ = "initiatives"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String, nullable=False)  # growth | irad | customer_funded | sustainment | obsolescence
    status: Mapped[str] = mapped_column(String, default="new")  # new | scored | roadmapped | done
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class Score(Base):
    """Output of the Prioritize agent for one initiative at one point in time."""
    __tablename__ = "scores"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    initiative_id: Mapped[str] = mapped_column(String, ForeignKey("initiatives.id"), index=True, nullable=False)
    reach: Mapped[float] = mapped_column(Float)
    impact: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    effort: Mapped[float] = mapped_column(Float)
    composite_score: Mapped[float] = mapped_column(Float)
    rationale: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Signal(Base):
    """Output of the Discover agent: a customer problem extracted from raw input."""
    __tablename__ = "signals"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    source_type: Mapped[str] = mapped_column(String)  # support_ticket | sales_call | review | other
    raw_text: Mapped[str] = mapped_column(Text)
    extracted_problem: Mapped[str] = mapped_column(Text)
    suggested_category: Mapped[str] = mapped_column(String)
    confidence: Mapped[float] = mapped_column(Float)
    is_validated: Mapped[bool] = mapped_column(default=False)
    linked_initiative_id: Mapped[str | None] = mapped_column(String, ForeignKey("initiatives.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Asset(Base):
    """A tracked part/platform/dependency for the Sustain agent to monitor."""
    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    asset_type: Mapped[str] = mapped_column(String)  # part | platform | dependency
    eol_date: Mapped[str | None] = mapped_column(String, nullable=True)  # ISO date string, nullable if unknown
    criticality: Mapped[str] = mapped_column(String, default="medium")  # low | medium | high
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class SustainAssessment(Base):
    """Output of the Sustain agent for one asset."""
    __tablename__ = "sustain_assessments"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    asset_id: Mapped[str] = mapped_column(String, ForeignKey("assets.id"), index=True, nullable=False)
    risk_level: Mapped[str] = mapped_column(String)  # low | medium | high | critical
    recommended_action: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class RoadmapDoc(Base):
    """Output of the Align agent: a drafted roadmap + exec summary."""
    __tablename__ = "roadmap_docs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String)
    exec_summary: Mapped[str] = mapped_column(Text)
    narrative: Mapped[str] = mapped_column(Text)
    included_initiative_ids: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class BriefDoc(Base):
    """Output of the Brief agent: board-ready portfolio report."""
    __tablename__ = "brief_docs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class AuditLog(Base):
    """
    Append-only log of every agent action. Never updated, never deleted from
    the API surface (no DELETE route is exposed for this table on purpose).
    This is what "every scoring change, roadmap edit, and agent action is
    attributed and timestamped" (from the marketing site) actually is.
    """
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    actor_label: Mapped[str] = mapped_column(String)
    agent_name: Mapped[str] = mapped_column(String)
    action: Mapped[str] = mapped_column(String)
    input_summary: Mapped[str] = mapped_column(Text)
    output_summary: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
