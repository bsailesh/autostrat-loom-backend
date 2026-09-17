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
