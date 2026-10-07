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

from sqlalchemy import String, Text, Float, ForeignKey, ForeignKeyConstraint, DateTime, JSON, UniqueConstraint
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


class SignupAllowlist(Base):
    """
    Emails permitted to create a brand-new account via /auth/signup. A stopgap
    access gate for the period before billing exists: without it, a deployed
    signup page lets anyone create a tenant and trigger real, paid API usage.

    This is not the per-tenant invite flow (see `Invite`, which adds a second
    user to an *existing* tenant) and it is not retroactive — it only gates new
    signups. Managed from the command line via `manage_allowlist.py`.
    """
    __tablename__ = "signup_allowlist"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    # Stored lowercased so the signup check is case-insensitive.
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


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


class AgentScope(Base):
    """
    The standing research scope for one agent, one per tenant per agent_type.
    This product runs an agent continuously against a single configured scope,
    not an ad-hoc topic per request — so the scope lives here and the run
    endpoint reads it instead of taking a subject in the request body.

    `product_line` is required (a run cannot proceed without it); `competitors`
    and `geography` are optional refinements.
    """
    __tablename__ = "agent_scopes"
    __table_args__ = (
        UniqueConstraint("tenant_id", "agent_type", name="uq_agent_scope_tenant_agent"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    agent_type: Mapped[str] = mapped_column(String, nullable=False)  # "market-insights"
    product_line: Mapped[str] = mapped_column(Text, nullable=False)
    competitors: Mapped[str] = mapped_column(Text, default="")
    geography: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


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


# ---------- Strategy Synthesis agent (Agent 5) ----------
#
# Reuses `AgentRun`/`AgentReport` above (agent_type="strategy-synthesis") --
# no dedicated run/report tables. Everything below is the decision-inputs
# brief, persisted so it survives across runs instead of being re-uploaded.
#
# `bucket_key` and `project_key` are natural, customer-declared business keys
# (validated unique per tenant) used directly as join columns in the tables
# below, rather than routed through each row's `id` -- this matches
# `strategy_synthesis/compute.py`'s pure-function inputs exactly (e.g.
# `ProjectEffort.bucket_key: str`), and `bucket_key` doubles as a CSV column
# header, so it needs to be a stable string the customer chose, not a UUID.
#
# project_key/bucket_key references below carry composite ForeignKeyConstraints
# to portfolio_projects/capacity_buckets (a first for this file -- every other
# FK here is a simple String -> id; these instead target the composite
# UniqueConstraints on those two tables). CONFIRMED before adding these:
# app/database.py has no `PRAGMA foreign_keys=ON` listener, and
# settings.database_url defaults to sqlite:///./loom.db with no override
# found anywhere under deploy/ -- so SQLite is not enforcing ANY foreign key
# in this schema today, existing 17-table ones included. These composite FKs
# are therefore inert until/unless that pragma is enabled app-wide (a
# separate, unreviewed decision -- it would newly enforce every existing FK
# too, not just these, and needs its own check of insert/delete ordering
# elsewhere in the app first). Adding them now is zero-cost and makes them
# active for free the moment that pragma is ever turned on; until then, the
# only real loud-failure mechanism is CSV-ingest validation (Part 2 of
# agent5_build_briefing.md, not built yet: "Dependency references resolve to
# known project keys", "every roadmap effort column matches a declared
# bucket_key", both Error severity). compute.py's compute_bucket_utilisation
# also degrades safely on an orphan today, by silently excluding effort rows
# whose project_key isn't in committed_project_keys -- but that silent
# exclusion is not a substitute for the ingest-time check.


class StrategyConfig(Base):
    """Tenant-wide Agent 5 configuration. One row per tenant, set via
    GET/PUT /agents/strategy/config."""
    __tablename__ = "strategy_config"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), unique=True, index=True, nullable=False)
    effort_unit: Mapped[str] = mapped_column(String, default="weeks")  # used verbatim in output
    fiscal_year_start_month: Mapped[int] = mapped_column(default=1)  # 1-12
    fiscal_year_label_format: Mapped[str] = mapped_column(String, default="FY{yy}")
    project_types: Mapped[list] = mapped_column(JSON, default=list)  # customer-defined, e.g. ["Compliance", ...]
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class CapacityBucket(Base):
    """A customer-declared capacity bucket (e.g. "Hardware",
    "Certification"), 2-8 per tenant."""
    __tablename__ = "capacity_buckets"
    __table_args__ = (
        UniqueConstraint("tenant_id", "bucket_key", name="uq_capacity_bucket_tenant_key"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    # Used verbatim as a CSV column header. Uniqueness is enforced here (DB);
    # "safe as a column header" (charset/length) is NOT -- that's application
    # validation on the PUT /agents/strategy/buckets endpoint, not built yet.
    # Flagging so it isn't lost: no DB CHECK, matching this file's convention
    # of zero DB-level enums/checks anywhere.
    bucket_key: Mapped[str] = mapped_column(String, nullable=False)
    bucket_name: Mapped[str] = mapped_column(String, nullable=False)
    contractable: Mapped[str] = mapped_column(String, default="no")  # yes | partial | no
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class EffortBand(Base):
    """Optional customer-defined effort calibration band, e.g. "Small" =
    under 40 weeks."""
    __tablename__ = "effort_bands"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    band_name: Mapped[str] = mapped_column(String, nullable=False)
    min_units: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_units: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class StrategicObjective(Base):
    """A strategic objective, e.g. "SO-1"."""
    __tablename__ = "strategic_objectives"
    __table_args__ = (
        UniqueConstraint("tenant_id", "objective_key", name="uq_strategic_objective_tenant_key"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    objective_key: Mapped[str] = mapped_column(String, nullable=False)  # e.g. "SO-1"
    text: Mapped[str] = mapped_column(Text, nullable=False)
    horizon: Mapped[str] = mapped_column(String, default="")  # e.g. "2030", "FY28", "Ongoing"
    owner: Mapped[str] = mapped_column(String, default="")
    measure: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class ProductFleetRow(Base):
    """One row per product x platform in the customer's installed base.
    Platform granularity is required. Unique on (tenant_id, product_key,
    platform), not just (tenant_id, product_key) -- one product legitimately
    spans many platform rows (see strawman: MR-CVR20 across five platforms).
    This is a DB-level backstop against a duplicate re-upload doubling
    units_in_service (which feeds reach/customer-value scoring), regardless
    of what ingest replacement strategy Part 2 ends up using."""
    __tablename__ = "products_fleet"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "product_key", "platform", name="uq_product_fleet_tenant_product_platform"
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    product_key: Mapped[str] = mapped_column(String, nullable=False)  # e.g. "MR-CVR20"
    product: Mapped[str] = mapped_column(String, nullable=False)  # display name
    platform: Mapped[str] = mapped_column(String, nullable=False)
    platform_class: Mapped[str] = mapped_column(String, default="")
    units_in_service: Mapped[float] = mapped_column(Float, default=0)
    avg_age_years: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String, default="")  # e.g. Current | Sunsetting
    region: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class CapacityRow(Base):
    """Engineering capacity for one fiscal year x bucket. `capacity_units` is
    nullable -- a blank future year is unplanned, never zero;
    strategy_synthesis.compute depends on that distinction. Named `CapacityRow`
    (table `capacity`) to avoid colliding with compute.py's `Capacity` dataclass."""
    __tablename__ = "capacity"
    __table_args__ = (
        UniqueConstraint("tenant_id", "fiscal_year", "bucket_key", name="uq_capacity_tenant_fy_bucket"),
        ForeignKeyConstraint(
            ["tenant_id", "bucket_key"],
            ["capacity_buckets.tenant_id", "capacity_buckets.bucket_key"],
            name="fk_capacity_tenant_bucket",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    fiscal_year: Mapped[str] = mapped_column(String, nullable=False)  # e.g. "FY27"
    bucket_key: Mapped[str] = mapped_column(String, nullable=False)
    fte: Mapped[float | None] = mapped_column(Float, nullable=True)
    capacity_units: Mapped[float | None] = mapped_column(Float, nullable=True)  # null = unplanned
    budget: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class PortfolioProject(Base):
    """A committed project from the customer's roadmap. `mandatory` is a
    customer declaration and must never be inferred by the agent."""
    __tablename__ = "portfolio_projects"
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_key", name="uq_portfolio_project_tenant_key"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    project_key: Mapped[str] = mapped_column(String, nullable=False)  # e.g. "P-01"
    name: Mapped[str] = mapped_column(String, nullable=False)
    project_type: Mapped[str] = mapped_column(String, default="")  # customer-defined; see strategy_config.project_types
    status: Mapped[str] = mapped_column(String, default="")
    pct_complete: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_gate: Mapped[str] = mapped_column(String, default="")
    target_fy: Mapped[str] = mapped_column(String, default="")
    owner: Mapped[str] = mapped_column(String, default="")
    mandatory: Mapped[bool] = mapped_column(default=False)
    mandatory_driver: Mapped[str] = mapped_column(Text, default="")
    mandatory_deadline: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class ProjectEffortRow(Base):
    """Effort remaining/total for one project x bucket. Effort remaining is
    what feeds scoring and strategy_synthesis.compute. Named `ProjectEffortRow`
    (table `project_effort`) to avoid colliding with compute.py's
    `ProjectEffort` dataclass."""
    __tablename__ = "project_effort"
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_key", "bucket_key", name="uq_project_effort_tenant_project_bucket"),
        ForeignKeyConstraint(
            ["tenant_id", "project_key"],
            ["portfolio_projects.tenant_id", "portfolio_projects.project_key"],
            name="fk_project_effort_tenant_project",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "bucket_key"],
            ["capacity_buckets.tenant_id", "capacity_buckets.bucket_key"],
            name="fk_project_effort_tenant_bucket",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    project_key: Mapped[str] = mapped_column(String, nullable=False)
    bucket_key: Mapped[str] = mapped_column(String, nullable=False)
    effort_remaining: Mapped[float] = mapped_column(Float, nullable=False)
    effort_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class ProjectDependency(Base):
    """A prerequisite edge between two projects. `source` distinguishes a
    customer-supplied dependencies.csv row from one inferred by the agent,
    which must be flagged for confirmation."""
    __tablename__ = "project_dependencies"
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_key", "depends_on_key", name="uq_project_dependency_tenant_edge"),
        ForeignKeyConstraint(
            ["tenant_id", "project_key"],
            ["portfolio_projects.tenant_id", "portfolio_projects.project_key"],
            name="fk_project_dependency_tenant_project",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "depends_on_key"],
            ["portfolio_projects.tenant_id", "portfolio_projects.project_key"],
            name="fk_project_dependency_tenant_depends_on",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    project_key: Mapped[str] = mapped_column(String, nullable=False)
    depends_on_key: Mapped[str] = mapped_column(String, nullable=False)
    dependency_type: Mapped[str] = mapped_column(String, default="prerequisite")
    note: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String, default="inferred")  # customer | inferred
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class ProjectFinancialsRow(Base):
    """Revenue/cost projections for one project, feeding
    strategy_synthesis.compute.compute_financial_metrics. Never merged into
    the composite score. Named `ProjectFinancialsRow` (table
    `project_financials`) to avoid colliding with compute.py's
    `ProjectFinancials` dataclass."""
    __tablename__ = "project_financials"
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_key", name="uq_project_financials_tenant_project"),
        ForeignKeyConstraint(
            ["tenant_id", "project_key"],
            ["portfolio_projects.tenant_id", "portfolio_projects.project_key"],
            name="fk_project_financials_tenant_project",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    project_key: Mapped[str] = mapped_column(String, nullable=False)
    revenue_impact: Mapped[list] = mapped_column(JSON, default=list)  # [y1..y5], nulls allowed for unknown years
    capex: Mapped[float | None] = mapped_column(Float, nullable=True)
    opex_annual: Mapped[float | None] = mapped_column(Float, nullable=True)
    discount_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String, default="USD")
    basis: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class ProposedProject(Base):
    """A user-proposed project with no effort estimate. Never enters the
    ranked portfolio."""
    __tablename__ = "proposed_projects"
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_key", name="uq_proposed_project_tenant_key"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    project_key: Mapped[str] = mapped_column(String, nullable=False)  # e.g. "U-01"
    name: Mapped[str] = mapped_column(String, nullable=False)
    proposed_by: Mapped[str] = mapped_column(String, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    rationale: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class PrioritizationFramework(Base):
    """The prioritization framework selection. `run_id` is null for the
    tenant's current/default selection (set via GET/PUT
    /agents/strategy/framework) and set when a run snapshots the framework it
    actually used, for audit."""
    __tablename__ = "prioritization_frameworks"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    run_id: Mapped[str | None] = mapped_column(String, ForeignKey("agent_runs.id"), nullable=True)
    framework: Mapped[str] = mapped_column(String, default="weighted_scoring")  # weighted_scoring | wsjf | ...
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class PrioritizationCriterion(Base):
    """One weighted criterion within a PrioritizationFramework, e.g.
    "Customer value", 25%, source_agent "Voice of Customer"."""
    __tablename__ = "prioritization_criteria"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    framework_id: Mapped[str] = mapped_column(
        String, ForeignKey("prioritization_frameworks.id"), index=True, nullable=False
    )
    criterion: Mapped[str] = mapped_column(String, nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    source_agent: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class ScenarioRow(Base):
    """A named re-weighting scenario, e.g. "Growth", "Sustainment". Named
    `ScenarioRow` (table `scenarios`) to avoid colliding with compute.py's
    `Scenario` dataclass."""
    __tablename__ = "scenarios"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_scenario_tenant_name"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)  # "Base" | "Growth" | "Sustainment" | ...
    emphasis: Mapped[str] = mapped_column(Text, default="")  # qualitative description
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class ScenarioWeight(Base):
    """One criterion weight override within a ScenarioRow. Feeds
    strategy_synthesis.compute.Scenario.weights."""
    __tablename__ = "scenario_weights"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "scenario_id", "criterion", name="uq_scenario_weight_tenant_scenario_criterion"
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    scenario_id: Mapped[str] = mapped_column(String, ForeignKey("scenarios.id"), index=True, nullable=False)
    criterion: Mapped[str] = mapped_column(String, nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class StrategyRule(Base):
    """An exclusion rule or threshold, e.g. "mandatory projects are never cut
    without escalation"."""
    __tablename__ = "strategy_rules"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    rule_type: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[str] = mapped_column(Text, default="")
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class DiscoveredCandidate(Base):
    """A candidate project discovered from upstream evidence or proposed by
    the customer, persisted across runs so a dismissed candidate is never
    re-presented as new."""
    __tablename__ = "discovered_candidates"
    __table_args__ = (
        UniqueConstraint("tenant_id", "candidate_key", name="uq_discovered_candidate_tenant_key"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    candidate_key: Mapped[str] = mapped_column(String, nullable=False)  # e.g. "C-01"
    name: Mapped[str] = mapped_column(String, nullable=False)
    origin: Mapped[str] = mapped_column(String, default="")  # e.g. "Discovered - Market", "Customer - VP Sales"
    problem_addressed: Mapped[str] = mapped_column(Text, default="")
    evidence_summary: Mapped[str] = mapped_column(Text, default="")
    support_classification: Mapped[str] = mapped_column(String, default="")  # FACT | OBSERVATION | INTERPRETATION | FORECAST | UNKNOWN
    # Serialized Pass1Citation list (agent, report_number, section,
    # classification, confidence, summary). Not present in Part 1's
    # original column set -- added in Part 5 once Pass 1's schema
    # (strategy_synthesis/schemas.py) made clear what a citation is.
    source_citations: Mapped[list] = mapped_column(JSON, default=list)
    first_seen_run_id: Mapped[str | None] = mapped_column(String, ForeignKey("agent_runs.id"), nullable=True)
    status: Mapped[str] = mapped_column(String, default="new")  # new | under_review | scoped | dismissed
    dismissal_reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class BriefFile(Base):
    """One uploaded decision-inputs CSV. Staleness is flagged in output at
    180 days, matching the evidence staleness convention used elsewhere.
    `as_of` is DateTime (not the String-ISO-date pattern used by
    Asset.eol_date elsewhere) because this field is actually computed
    against for staleness, not just displayed."""
    __tablename__ = "brief_files"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    file_type: Mapped[str] = mapped_column(String, nullable=False)  # e.g. "products_fleet", "roadmap_fy26"
    filename: Mapped[str] = mapped_column(String, nullable=False)
    as_of: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    uploaded_by: Mapped[str] = mapped_column(String, default="")
    row_count: Mapped[int] = mapped_column(default=0)
    validation_status: Mapped[str] = mapped_column(String, default="pending")  # pending | valid | valid_with_warnings | invalid
    # Serialized IngestIssue list (severity, row, field, message) from the
    # last upload attempt, so GET /agents/strategy/files can show why it
    # failed (or what it warned about) without re-parsing the file.
    issues: Mapped[list] = mapped_column(JSON, default=list)
    # The CSV's header row, captured at upload time -- so the decision inputs
    # screen can show "detected columns" without keeping the raw file around.
    columns: Mapped[list] = mapped_column(JSON, default=list)
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


# ---------------------------------------------------------------------------
# Agent 3 (Technology & Regulatory Intelligence) — the applicability envelope
#
# Eight scoping tables plus candidate work. Per
# tech_regulation_scoping_input_spec.md Part 5, three of these fields are
# wanted by more than one agent (product categories, platforms, supplier
# watch list) and a shared Product Profile is the eventual shape -- but they
# are built here as Agent 3's own tables deliberately, so the shared
# abstraction is extracted once two agents actually use it rather than
# designed before anything flows through it. The column names below are the
# names that spec uses, so a later extraction is a move, not a rename.
#
# `agent_runs` and `agent_reports` are reused as-is via the `agent_type`
# discriminator ("tech-regulation") -- no new columns on either, so
# Base.metadata.create_all is sufficient to deploy all of this.
# ---------------------------------------------------------------------------


class TrProductCategory(Base):
    """What the customer makes, in their own words. The field that decides
    whether a run is about this customer at all: without it every other
    dimension has nothing to attach findings to, and the run degrades to an
    industry survey."""
    __tablename__ = "tr_product_categories"
    __table_args__ = (
        UniqueConstraint("tenant_id", "category_key", name="uq_tr_product_category_tenant_key"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    category_key: Mapped[str] = mapped_column(String, nullable=False)  # e.g. "EMA-FIN"
    category_name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class TrJurisdiction(Base):
    """Where the product is sold, certified or operated. `role` is load-bearing:
    a regulator in a primary market and one in an export-only market produce
    findings of different weight, and the agent says which."""
    __tablename__ = "tr_jurisdictions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "jurisdiction", name="uq_tr_jurisdiction_tenant_key"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String, nullable=False)  # e.g. "European Union"
    role: Mapped[str] = mapped_column(String, default="primary")  # primary | secondary | export_only
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class TrCertificationBasis(Base):
    """What each product category is approved under -- the highest-leverage
    field in the envelope, and the one that decides whether a regulatory
    finding is intelligence or a newsletter.

    `basis_type` is a controlled list with a free-text fallback (TSO, ETSO,
    CS, Part, MIL-STD, STC, PMA, Standard, Other). These are not
    interchangeable and the agent needs to know which is which; where
    `Other`, `basis_identifier` is used verbatim. Not a DB enum -- this file
    has no DB-level enums or checks anywhere, and the vocabulary is validated
    at the endpoint.

    One category carries several bases (Arden's utility actuation holds both
    TSO-C196b and a 14 CFR Part 25 installation approval), so the natural key
    is the triple, not the category."""
    __tablename__ = "tr_certification_basis"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "category_key", "basis_type", "basis_identifier",
            name="uq_tr_certification_basis_tenant_key",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    # Not an FK to tr_product_categories.category_key: that column is unique
    # per tenant but not a primary key, and the rest of this file keys
    # customer-supplied vocabularies by string the same way (ProjectEffort ->
    # bucket_key). Referential integrity is the endpoint's job.
    category_key: Mapped[str] = mapped_column(String, nullable=False)
    basis_type: Mapped[str] = mapped_column(String, nullable=False)
    basis_identifier: Mapped[str] = mapped_column(String, nullable=False)  # e.g. "TSO-C196b"
    status: Mapped[str] = mapped_column(String, default="")  # e.g. qualified | approved | installed on
    # String, not DateTime: displayed and reasoned about by the model, never
    # computed against -- the Asset.eol_date convention, not BriefFile.as_of's.
    held_since: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class TrPlatform(Base):
    """What the product goes on. `relationship` changes how a finding reads
    and must survive to the output: a regulatory change on a platform the
    customer ships is a cost against existing revenue, the same change on one
    they are pursuing is an entry condition on a design-in window."""
    __tablename__ = "tr_platforms"
    __table_args__ = (
        UniqueConstraint("tenant_id", "platform", name="uq_tr_platform_tenant_key"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    platform: Mapped[str] = mapped_column(String, nullable=False)  # e.g. "Narrowbody commercial"
    platform_class: Mapped[str] = mapped_column(String, default="")  # e.g. "Part 25 transport"
    # Shadows the module-level sqlalchemy `relationship` import inside this
    # class body only, which is safe because this class declares none. Named
    # for the scoping spec rather than renamed to avoid the shadow, since the
    # agent's prompts, the API payloads and the spec all call it this.
    relationship: Mapped[str] = mapped_column(String, default="shipping")  # shipping | pursuing | in_service | sunsetting
    programme_status: Mapped[str] = mapped_column(String, default="")  # e.g. "design-in window"
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class TrStandardHeld(Base):
    """Standards the customer is compliant with or certified against. A
    revision to one of these is dated candidate work; a revision to one they
    do not hold is background, and is reported as such rather than at equal
    weight."""
    __tablename__ = "tr_standards_held"
    __table_args__ = (
        UniqueConstraint("tenant_id", "standard_id", "revision", name="uq_tr_standard_held_tenant_key"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    standard_id: Mapped[str] = mapped_column(String, nullable=False)  # e.g. "DO-160"
    revision: Mapped[str] = mapped_column(String, default="")  # e.g. "G"; empty where none is issued
    scope: Mapped[str] = mapped_column(Text, default="")  # e.g. "Environmental qualification"
    status: Mapped[str] = mapped_column(String, default="")  # compliant | certified | in_progress | lapsed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class TrSupplier(Base):
    """Suppliers whose developments and discontinuations matter. Shared with
    Product Sustainment, which needs the same list for obsolescence
    monitoring (scoping spec Part 5). Watch-list suppliers are reported even
    when a development is minor; others only when significant."""
    __tablename__ = "tr_suppliers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "supplier", name="uq_tr_supplier_tenant_key"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    supplier: Mapped[str] = mapped_column(String, nullable=False)
    what_they_supply: Mapped[str] = mapped_column(Text, default="")
    criticality: Mapped[str] = mapped_column(String, default="")  # single_source | dual_sourced | multi_source
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class TrDomain(Base):
    """Technology domains to monitor, from the per-industry list plus free
    text. Without any, domains are inferred from product categories, which
    works but misses adjacencies the customer watches deliberately."""
    __tablename__ = "tr_domains"
    __table_args__ = (
        UniqueConstraint("tenant_id", "domain", name="uq_tr_domain_tenant_key"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    domain: Mapped[str] = mapped_column(String, nullable=False)  # e.g. "Advanced air mobility"
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class TrExclusion(Base):
    """What not to report. A scoping input that can only add scope produces
    noise. Exclusions are stated in the output -- "excluded at your
    direction" -- never silently applied, because an exclusion that turns out
    to be wrong is itself a finding."""
    __tablename__ = "tr_exclusions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "exclusion_type", "value", name="uq_tr_exclusion_tenant_key"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    exclusion_type: Mapped[str] = mapped_column(String, nullable=False)  # platform_class | jurisdiction | domain | category
    value: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class TrCandidateWork(Base):
    """One piece of work a finding implies -- this agent's contract with
    Agent 5, and the reason it is a table rather than prose inside a report.
    Agent 5 reads these rows directly, so there is no second parser of an
    undocumented contract (the failure this codebase has already hit with the
    Word export markdown parser and with Agent 5's own report consumption).

    This row is the single home of `driver` and `work_date`. Agent 5's linked
    DiscoveredCandidate deliberately stores neither and reaches them through
    the `candidate_key` carried in its `origin`, so a corrected date here is
    the corrected date everywhere, with nothing to refresh and nowhere for a
    stale copy to live.

    Note what is absent and must stay absent: no effort, duration, cost,
    reach, priority or rank. This agent cannot see the customer's capacity or
    what competes for it, so naming the work is its job and sizing it is
    Agent 5's. The omission is structural, not just a prompt instruction.

    Persistence mirrors DiscoveredCandidate -- additive, keyed by
    `candidate_key`, refreshing evidence fields on an existing key, never
    resurrecting a dismissed item as new. Unlike DiscoveredCandidate it
    carries `last_seen_run_id` as well as `first_seen_run_id`: Agent 5 reads
    "the candidate work for this upstream run", which has to include items a
    run re-surfaced and not only ones it discovered, or a corrected item
    would vanish from the run that corrected it."""
    __tablename__ = "tr_candidate_work"
    __table_args__ = (
        UniqueConstraint("tenant_id", "candidate_key", name="uq_tr_candidate_work_tenant_key"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    candidate_key: Mapped[str] = mapped_column(String, nullable=False)  # e.g. "TR-01"

    # -- the five required fields ------------------------------------------
    # The named regulation, standard revision, supplier notice or development,
    # with its identifier.
    driver: Mapped[str] = mapped_column(Text, nullable=False)
    # String, not DateTime: these are external dates of mixed precision
    # ("14 Mar 2028", "Q3 FY28", "2028") that are read and clustered by the
    # model, not computed against -- the Asset.eol_date convention.
    work_date: Mapped[str | None] = mapped_column(String, nullable=True)
    date_basis: Mapped[str] = mapped_column(String, default="")  # effective | compliance_deadline | runout | transition_end | window_closes | none_established
    # Required whenever work_date is null. Enforced in the agent's
    # completeness validation and at the endpoint, not by a DB check.
    date_absent_reason: Mapped[str] = mapped_column(Text, default="")
    # Which categories, bases or platforms this touches, from the envelope.
    applicability: Mapped[dict] = mapped_column(JSON, default=dict)
    work_implied: Mapped[str] = mapped_column(String, nullable=False)  # requalification | new_approval | design_change | standards_participation | supplier_qualification | documentation | other
    work_implied_description: Mapped[str] = mapped_column(Text, default="")
    # Carried from the platform where it differs -- a pursued platform makes
    # the work an entry condition rather than a cost against revenue.
    platform_relationship: Mapped[str | None] = mapped_column(String, nullable=True)

    # -- evidence basis ----------------------------------------------------
    classification: Mapped[str] = mapped_column(String, default="")  # FACT | OBSERVATION | INTERPRETATION | FORECAST | UNKNOWN
    confidence: Mapped[str] = mapped_column(String, default="")  # High | Medium | Low
    source: Mapped[str] = mapped_column(Text, default="")
    source_date: Mapped[str] = mapped_column(String, default="")

    # -- triage ------------------------------------------------------------
    # Independent of the linked DiscoveredCandidate's status: this one answers
    # "is this finding real and relevant", that one answers "would we scope
    # this as a project". A disagreement between them is shown, not hidden.
    status: Mapped[str] = mapped_column(String, default="new")  # new | under_review | accepted | dismissed
    dismissal_reason: Mapped[str] = mapped_column(Text, default="")

    first_seen_run_id: Mapped[str | None] = mapped_column(String, ForeignKey("agent_runs.id"), nullable=True)
    last_seen_run_id: Mapped[str | None] = mapped_column(String, ForeignKey("agent_runs.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


# ---------------------------------------------------------------------------
# Agent 1 (Voice of Customer) — customer context and evidence
#
# Two parts doing different jobs (voice_of_customer_input_spec.md): the
# context tables say who the customers are, so findings can be attributed;
# the evidence tables hold the customer voice itself. Without evidence the
# agent runs at Tier 2 and is titled an external customer-context analysis.
#
# Product categories are NOT duplicated here. Tech & Regulation already owns
# `tr_product_categories`, and VoC reads them through, with its own additions
# in `voc_product_categories`. This is the second agent needing that list,
# which is the point at which a shared Product Profile stops being premature
# -- extract it after this agent ships, not during.
#
# `agent_runs` and `agent_reports` are reused via agent_type
# "voice-of-customer". Every table below is new, so create_all is sufficient
# to deploy all of this -- no ALTER TABLE on production.
# ---------------------------------------------------------------------------


class VocSegment(Base):
    """Who findings are attributed to. `approximate_count` is nullable on
    purpose: `unknown` is a legitimate answer and must never become zero,
    because the agent says when a finding rests on a segment of unstated
    size."""
    __tablename__ = "voc_segments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "segment_key", name="uq_voc_segment_tenant_key"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    segment_key: Mapped[str] = mapped_column(String, nullable=False)  # e.g. "OEM-TIER1"
    segment_name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    approximate_count: Mapped[int | None] = mapped_column(nullable=True)  # None = unknown, never 0
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class VocChannel(Base):
    """How feedback arrives. A declared channel with no evidence from it is
    itself a finding -- absent feedback is not the same as no complaints."""
    __tablename__ = "voc_channels"
    __table_args__ = (
        UniqueConstraint("tenant_id", "channel", name="uq_voc_channel_tenant_channel"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    channel: Mapped[str] = mapped_column(String, nullable=False)
    direction: Mapped[str] = mapped_column(String, default="inbound")  # inbound | outbound | both
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class VocCustomer(Base):
    """Named customers. Optional and sensitive: used for attribution inside
    the system, and as the name list the output attribution check scans
    for. How a name may appear in output is set by VocConfig."""
    __tablename__ = "voc_customers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "customer_name", name="uq_voc_customer_tenant_name"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    customer_name: Mapped[str] = mapped_column(String, nullable=False)
    segment_key: Mapped[str] = mapped_column(String, default="")
    products: Mapped[str] = mapped_column(Text, default="")
    relationship_status: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class VocKnownPainPoint(Base):
    """What the customer believes their customers complain about --
    deliberately a hypothesis, not evidence. The input to the highest-value
    analysis this agent performs (corroborated / contradicted / not found),
    which is unavailable unless the belief was recorded before the run."""
    __tablename__ = "voc_known_pain_points"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    pain_point: Mapped[str] = mapped_column(Text, nullable=False)
    segment_key: Mapped[str] = mapped_column(String, default="")
    category_key: Mapped[str] = mapped_column(String, default="")
    their_assessment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class VocConfig(Base):
    """One row per tenant. Absent row = defaults (segment_only)."""
    __tablename__ = "voc_config"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False, unique=True)
    attribution_policy: Mapped[str] = mapped_column(String, default="segment_only")  # segment_only | role_and_segment | named
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class VocProductCategory(Base):
    """VoC-specific additions to the product categories read through from
    tr_product_categories. Where a key exists in both, the read-through
    wins, so the customer never maintains the same category twice."""
    __tablename__ = "voc_product_categories"
    __table_args__ = (
        UniqueConstraint("tenant_id", "category_key", name="uq_voc_product_category_tenant_key"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    category_key: Mapped[str] = mapped_column(String, nullable=False)
    category_name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class VocEvidenceFile(Base):
    """One uploaded evidence document. The content lives in VocEvidenceItem
    rows, never on this row, so listing files never loads evidence.

    `is_sample` is load-bearing: a sample is not a census, and the agent must
    never report frequency from one as though it were. It is carried into
    the prompt header of every rendering of this file."""
    __tablename__ = "voc_evidence_files"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    file_type: Mapped[str] = mapped_column(String, nullable=False)  # voice_of_customer.context.FILE_TYPES
    file_format: Mapped[str] = mapped_column(String, nullable=False)  # text | pdf | csv
    filename: Mapped[str] = mapped_column(String, nullable=False)
    content_type: Mapped[str] = mapped_column(String, default="")
    size_bytes: Mapped[int] = mapped_column(default=0)
    # String ISO dates, display and prompt only (the Asset.eol_date
    # convention): nothing computes against them.
    as_of: Mapped[str] = mapped_column(String, default="")
    period_start: Mapped[str] = mapped_column(String, default="")
    period_end: Mapped[str] = mapped_column(String, default="")
    is_sample: Mapped[bool] = mapped_column(default=False)
    sample_description: Mapped[str] = mapped_column(Text, default="")
    segment_coverage: Mapped[list] = mapped_column(JSON, default=list)  # segment keys, where known
    # CSV only. What one row represents ("ticket", "claim", "comment") -- a
    # count is meaningless without it.
    row_unit: Mapped[str] = mapped_column(String, default="")
    columns: Mapped[list] = mapped_column(JSON, default=list)  # detected header row
    column_roles: Mapped[dict] = mapped_column(JSON, default=dict)  # role -> column name, optional
    row_count: Mapped[int | None] = mapped_column(nullable=True)  # CSV
    page_count: Mapped[int | None] = mapped_column(nullable=True)  # PDF
    char_count: Mapped[int] = mapped_column(default=0)  # all formats -- sizes the prompt budget
    ingest_status: Mapped[str] = mapped_column(String, default="pending")  # pending | ingested | rejected
    issues: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class VocEvidenceItem(Base):
    """One unit of evidence content: a CSV row (`cells`, keyed by header) or
    a page / section of a text or PDF document (`text`). Stored row-wise so
    a run iterates a cursor rather than loading a whole export -- the
    production instance has 414MB of RAM and ticket exports can be large."""
    __tablename__ = "voc_evidence_items"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    file_id: Mapped[str] = mapped_column(String, ForeignKey("voc_evidence_files.id"), index=True, nullable=False)
    seq: Mapped[int] = mapped_column(nullable=False)  # row number / page number, 1-based
    cells: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    text: Mapped[str] = mapped_column(Text, default="")


class VocRunMeta(Base):
    """What a VoC run was, frozen at run time: its tier (which drives the
    title and the Word cover label), the attribution policy it ran under,
    how evidence was sampled into the prompt, and what the output
    attribution check replaced. A new table rather than columns on
    agent_runs, so no ALTER TABLE is needed."""
    __tablename__ = "voc_run_meta"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    run_id: Mapped[str] = mapped_column(String, ForeignKey("agent_runs.id"), index=True, nullable=False, unique=True)
    tier: Mapped[str] = mapped_column(String, nullable=False)  # tier_2 | tier_1_partial | tier_1_substantial
    attribution_policy: Mapped[str] = mapped_column(String, default="segment_only")
    sampling_notes: Mapped[list] = mapped_column(JSON, default=list)
    # Replacement counts per report number only -- never the names, which
    # would put them back into a table the API serves.
    attribution_replacements: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


# ---------------------------------------------------------------------------
# Agent 4 (Product Sustainment) — product structure, inventory, demand, risk
#
# The BOM is exactly three levels (LRU -> Level 1 -> Level 2) and both joins
# are MANY-TO-MANY. The two mappings are uploaded as matrices but stored here
# as edges (ps_lru_level1, ps_level1_level2); product_sustainment/compute.py
# treats them as matrices and never traverses them as a tree.
#
# `agent_runs` and `agent_reports` are reused via agent_type
# "product-sustainment". Every table below is new, so create_all is
# sufficient to deploy all of this -- no ALTER TABLE on production.
# ---------------------------------------------------------------------------


class PsLru(Base):
    __tablename__ = "ps_lrus"
    __table_args__ = (UniqueConstraint("tenant_id", "lru_id", name="uq_ps_lru_tenant_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    lru_id: Mapped[str] = mapped_column(String, nullable=False)
    lru_name: Mapped[str] = mapped_column(String, default="")
    product_line: Mapped[str] = mapped_column(String, default="")
    program: Mapped[str] = mapped_column(String, default="")
    status: Mapped[str] = mapped_column(String, default="")


class PsLevel1(Base):
    __tablename__ = "ps_level1"
    __table_args__ = (UniqueConstraint("tenant_id", "level1_id", name="uq_ps_level1_tenant_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    level1_id: Mapped[str] = mapped_column(String, nullable=False)
    level1_name: Mapped[str] = mapped_column(String, default="")
    description: Mapped[str] = mapped_column(Text, default="")


class PsLevel2(Base):
    __tablename__ = "ps_level2"
    __table_args__ = (UniqueConstraint("tenant_id", "level2_id", name="uq_ps_level2_tenant_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    level2_id: Mapped[str] = mapped_column(String, nullable=False)
    level2_name: Mapped[str] = mapped_column(String, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    manufacturer: Mapped[str] = mapped_column(String, default="")
    manufacturer_part_number: Mapped[str] = mapped_column(String, default="")


class PsLruLevel1(Base):
    """One cell of the LRU -> Level 1 matrix: quantity of an assembly per LRU."""
    __tablename__ = "ps_lru_level1"
    __table_args__ = (UniqueConstraint("tenant_id", "lru_id", "level1_id", name="uq_ps_lru_level1_edge"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    lru_id: Mapped[str] = mapped_column(String, nullable=False)
    level1_id: Mapped[str] = mapped_column(String, nullable=False)
    quantity_per_unit: Mapped[int] = mapped_column(nullable=False)


class PsLevel1Level2(Base):
    """One cell of the Level 1 -> Level 2 matrix: quantity of a component per assembly."""
    __tablename__ = "ps_level1_level2"
    __table_args__ = (UniqueConstraint("tenant_id", "level1_id", "level2_id", name="uq_ps_level1_level2_edge"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    level1_id: Mapped[str] = mapped_column(String, nullable=False)
    level2_id: Mapped[str] = mapped_column(String, nullable=False)
    quantity_per_unit: Mapped[int] = mapped_column(nullable=False)


class PsInventory(Base):
    """`location` and `form` are the customer's own strings, used verbatim --
    no controlled list."""
    __tablename__ = "ps_inventory"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    part_id: Mapped[str] = mapped_column(String, nullable=False)
    part_level: Mapped[str] = mapped_column(String, nullable=False)  # lru | level1 | level2
    location: Mapped[str] = mapped_column(String, default="")
    form: Mapped[str] = mapped_column(String, default="")
    quantity: Mapped[int] = mapped_column(nullable=False)
    as_of: Mapped[str] = mapped_column(String, default="")


class PsPipeline(Base):
    __tablename__ = "ps_pipeline"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    part_id: Mapped[str] = mapped_column(String, nullable=False)
    open_po_qty: Mapped[int] = mapped_column(default=0)
    supplier_qty: Mapped[int] = mapped_column(default=0)
    supplier_on_order_qty: Mapped[int] = mapped_column(default=0)
    supplier_wip_qty: Mapped[int] = mapped_column(default=0)
    as_of: Mapped[str] = mapped_column(String, default="")


class PsLeadTime(Base):
    __tablename__ = "ps_lead_times"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    part_id: Mapped[str] = mapped_column(String, nullable=False)
    lead_time_days: Mapped[int] = mapped_column(nullable=False)


class PsDemand(Base):
    """One row per LRU per year. A missing row is ZERO demand that year, not
    missing data; an LRU with no rows still appears in reporting."""
    __tablename__ = "ps_demand"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    lru_id: Mapped[str] = mapped_column(String, nullable=False)
    year: Mapped[int] = mapped_column(nullable=False)
    quantity: Mapped[int] = mapped_column(nullable=False)


class PsDirectDemand(Base):
    """Spares or aftermarket demand at any level, ADDED to derived demand and
    flowing downward through the matrices exactly as derived demand does."""
    __tablename__ = "ps_direct_demand"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    part_id: Mapped[str] = mapped_column(String, nullable=False)
    part_level: Mapped[str] = mapped_column(String, nullable=False)
    year: Mapped[int] = mapped_column(nullable=False)
    quantity: Mapped[int] = mapped_column(nullable=False)


class PsRiskFlag(Base):
    """`lifecycle_status` carries the manufacturer's own designation (NFND,
    MXSTK, ...) as free text -- early warning, not yet EOL."""
    __tablename__ = "ps_risk_flags"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    part_id: Mapped[str] = mapped_column(String, nullable=False)
    risk_type: Mapped[str] = mapped_column(String, nullable=False)  # end_of_life | single_source | custom | at_risk_region
    risk_detail: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(Text, default="")
    source_date: Mapped[str] = mapped_column(String, default="")
    lifecycle_status: Mapped[str] = mapped_column(String, default="")
    last_time_buy_date: Mapped[str] = mapped_column(String, default="")  # ISO date, validated at ingest
    last_delivery_date: Mapped[str] = mapped_column(String, default="")


class PsQualifiedAlternate(Base):
    """CUSTOMER-SUPPLIED ONLY: a second source already through the customer's
    own qualification. Agent-found candidates never land here -- they live on
    ps_candidate_work.candidate_alternates, labelled as candidates."""
    __tablename__ = "ps_qualified_alternates"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    part_id: Mapped[str] = mapped_column(String, nullable=False)
    alternate_part_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)  # qualified | in_qualification | approved_for_new_design_only
    qualified_date: Mapped[str] = mapped_column(String, default="")


class PsFleet(Base):
    __tablename__ = "ps_fleet"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    unit_id: Mapped[str] = mapped_column(String, nullable=False)
    lru_id: Mapped[str] = mapped_column(String, default="")
    in_service_date: Mapped[str] = mapped_column(String, default="")
    utilisation: Mapped[str] = mapped_column(String, default="")
    environment: Mapped[str] = mapped_column(String, default="")
    operator_segment: Mapped[str] = mapped_column(String, default="")


class PsMaintenance(Base):
    __tablename__ = "ps_maintenance"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    unit_id: Mapped[str] = mapped_column(String, nullable=False)
    lru_id: Mapped[str] = mapped_column(String, default="")
    event_date: Mapped[str] = mapped_column(String, default="")
    event_type: Mapped[str] = mapped_column(String, default="")
    time_in_service: Mapped[str] = mapped_column(String, default="")
    downtime: Mapped[str] = mapped_column(String, default="")


class PsConfiguration(Base):
    __tablename__ = "ps_configuration"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    unit_id: Mapped[str] = mapped_column(String, nullable=False)
    lru_id: Mapped[str] = mapped_column(String, default="")
    as_maintained_config: Mapped[str] = mapped_column(Text, default="")
    as_designed_baseline: Mapped[str] = mapped_column(Text, default="")


class PsKnowledge(Base):
    """Customer judgement; no data source produces it. Without it the
    knowledge analysis is unavailable -- never inferred from headcount."""
    __tablename__ = "ps_knowledge"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    capability: Mapped[str] = mapped_column(Text, nullable=False)
    components_affected: Mapped[str] = mapped_column(Text, default="")
    people_count: Mapped[int | None] = mapped_column(nullable=True)
    documentation_status: Mapped[str] = mapped_column(String, default="")


class PsFile(Base):
    """The last upload of each structured file type (matrices and data
    files), so GET /files shows what was loaded and why it failed."""
    __tablename__ = "ps_files"
    __table_args__ = (UniqueConstraint("tenant_id", "file_type", name="uq_ps_file_tenant_type"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    file_type: Mapped[str] = mapped_column(String, nullable=False)
    filename: Mapped[str] = mapped_column(String, default="")
    as_of: Mapped[str] = mapped_column(String, default="")
    row_count: Mapped[int] = mapped_column(default=0)
    validation_status: Mapped[str] = mapped_column(String, default="pending")  # valid | valid_with_warnings | invalid
    issues: Mapped[list] = mapped_column(JSON, default=list)
    columns: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class PsEvidenceFile(Base):
    """Free-text reliability and quality evidence. Same shape as
    VocEvidenceFile, deliberately -- one pattern, not two."""
    __tablename__ = "ps_evidence_files"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    file_type: Mapped[str] = mapped_column(String, nullable=False)
    file_format: Mapped[str] = mapped_column(String, nullable=False)  # text | pdf | csv
    filename: Mapped[str] = mapped_column(String, nullable=False)
    content_type: Mapped[str] = mapped_column(String, default="")
    size_bytes: Mapped[int] = mapped_column(default=0)
    as_of: Mapped[str] = mapped_column(String, default="")
    period_start: Mapped[str] = mapped_column(String, default="")
    period_end: Mapped[str] = mapped_column(String, default="")
    is_sample: Mapped[bool] = mapped_column(default=False)
    sample_description: Mapped[str] = mapped_column(Text, default="")
    row_unit: Mapped[str] = mapped_column(String, default="")
    columns: Mapped[list] = mapped_column(JSON, default=list)
    column_roles: Mapped[dict] = mapped_column(JSON, default=dict)
    row_count: Mapped[int | None] = mapped_column(nullable=True)
    page_count: Mapped[int | None] = mapped_column(nullable=True)
    char_count: Mapped[int] = mapped_column(default=0)
    ingest_status: Mapped[str] = mapped_column(String, default="pending")
    issues: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class PsEvidenceItem(Base):
    __tablename__ = "ps_evidence_items"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    file_id: Mapped[str] = mapped_column(String, ForeignKey("ps_evidence_files.id"), index=True, nullable=False)
    seq: Mapped[int] = mapped_column(nullable=False)
    cells: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    text: Mapped[str] = mapped_column(Text, default="")


class PsCandidateWork(Base):
    """Mirrors TrCandidateWork, with the fields a runout needs. Agent 5 reads
    these rows directly.

    The numbers -- quantity_required, a runout work_date, and applicability
    -- are written from compute.py, never from the model. The model names the
    driver, the work implied and any candidate alternates.

    `qualified_alternate_part_id` comes only from ps_qualified_alternates;
    `candidate_alternates` are agent-found and are never qualified.

    Additive, keyed by candidate_key; a re-run refreshes evidence fields but
    never status or dismissal_reason, so a dismissal survives re-discovery."""
    __tablename__ = "ps_candidate_work"
    __table_args__ = (UniqueConstraint("tenant_id", "candidate_key", name="uq_ps_candidate_work_tenant_key"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    candidate_key: Mapped[str] = mapped_column(String, nullable=False)  # "PS-<part_id>"
    part_id: Mapped[str] = mapped_column(String, nullable=False)
    driver: Mapped[str] = mapped_column(Text, nullable=False)
    work_date: Mapped[str | None] = mapped_column(String, nullable=True)
    date_basis: Mapped[str] = mapped_column(String, default="")  # runout | window_closes | none_established
    date_absent_reason: Mapped[str] = mapped_column(Text, default="")
    applicability: Mapped[dict] = mapped_column(JSON, default=dict)  # {"lrus": [...], "level1": [...]}
    quantity_required: Mapped[int | None] = mapped_column(nullable=True)
    quantity_basis: Mapped[str] = mapped_column(Text, default="")
    qualified_alternate_part_id: Mapped[str | None] = mapped_column(String, nullable=True)
    candidate_alternates: Mapped[list] = mapped_column(JSON, default=list)
    work_implied: Mapped[str] = mapped_column(String, nullable=False)  # last_time_buy | alternate_qualification | redesign | inventory_rebalance | monitor
    work_implied_description: Mapped[str] = mapped_column(Text, default="")
    classification: Mapped[str] = mapped_column(String, default="")
    confidence: Mapped[str] = mapped_column(String, default="")
    source: Mapped[str] = mapped_column(Text, default="")
    source_date: Mapped[str] = mapped_column(String, default="")
    status: Mapped[str] = mapped_column(String, default="new")  # new | under_review | accepted | dismissed
    dismissal_reason: Mapped[str] = mapped_column(Text, default="")
    first_seen_run_id: Mapped[str | None] = mapped_column(String, ForeignKey("agent_runs.id"), nullable=True)
    last_seen_run_id: Mapped[str | None] = mapped_column(String, ForeignKey("agent_runs.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class PsRunMeta(Base):
    """Frozen at run time: the tier (drives the title and Word cover label),
    the computation notes, and any candidate work dropped as incomplete."""
    __tablename__ = "ps_run_meta"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True, nullable=False)
    run_id: Mapped[str] = mapped_column(String, ForeignKey("agent_runs.id"), index=True, nullable=False, unique=True)
    tier: Mapped[str] = mapped_column(String, nullable=False)
    notes: Mapped[list] = mapped_column(JSON, default=list)
    candidate_work_dropped: Mapped[list] = mapped_column(JSON, default=list)
    # The complete computed position set. Reports carry only the most urgent
    # rows (a 4,000-component table cannot live in report markdown), so the
    # full filterable view reads from here.
    horizon_years: Mapped[list] = mapped_column(JSON, default=list)
    runout_rows: Mapped[list] = mapped_column(JSON, default=list)
    insufficient_rows: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
