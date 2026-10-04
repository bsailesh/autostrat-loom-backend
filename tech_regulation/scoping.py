"""
Technology & Regulatory Intelligence Agent (Agent 3) — the applicability
envelope, as plain data.

Why this agent needs scoping more than the others, from the scoping spec:
Market Insights works on a free-text product line because markets are
publicly discussed -- name a market and there is a market to research.
Regulation does not work that way. Without knowing what the customer makes,
where they sell it and what it is approved under, the agent can only report
that FAA, EASA and ICAO exist.

Assembling a `ScopingEnvelope` from the database is the service layer's job,
exactly as `strategy_synthesis/brief.py` takes an assembled DecisionBrief
and `app/strategy_synthesis_service.py` does the assembling. This package
never sees a DB session, so the operating-state and degradation logic below
is testable without one.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Envelope
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProductCategory:
    category_key: str
    category_name: str
    description: str = ""


@dataclass(frozen=True)
class Jurisdiction:
    jurisdiction: str
    role: str = "primary"  # primary | secondary | export_only


@dataclass(frozen=True)
class CertificationBasis:
    category_key: str
    basis_type: str  # TSO | ETSO | CS | Part | MIL-STD | STC | PMA | Standard | Other
    basis_identifier: str
    status: str = ""
    held_since: str = ""


@dataclass(frozen=True)
class Platform:
    platform: str
    platform_class: str = ""
    relationship: str = "shipping"  # shipping | pursuing | in_service | sunsetting
    programme_status: str = ""


@dataclass(frozen=True)
class StandardHeld:
    standard_id: str
    revision: str = ""
    scope: str = ""
    status: str = ""  # compliant | certified | in_progress | lapsed


@dataclass(frozen=True)
class Supplier:
    supplier: str
    what_they_supply: str = ""
    criticality: str = ""  # single_source | dual_sourced | multi_source


@dataclass(frozen=True)
class Exclusion:
    exclusion_type: str  # platform_class | jurisdiction | domain | category
    value: str
    reason: str = ""


@dataclass(frozen=True)
class ScopingEnvelope:
    categories: list[ProductCategory] = field(default_factory=list)
    jurisdictions: list[Jurisdiction] = field(default_factory=list)
    certification_basis: list[CertificationBasis] = field(default_factory=list)
    platforms: list[Platform] = field(default_factory=list)
    standards_held: list[StandardHeld] = field(default_factory=list)
    suppliers: list[Supplier] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    exclusions: list[Exclusion] = field(default_factory=list)
    # Tier 1 evidence is optional and deepens rather than scopes (scoping spec
    # Part 3). The agent states which were supplied; none of them makes an
    # unscoped run scoped.
    tier1_evidence_supplied: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Operating state and degradation
# ---------------------------------------------------------------------------

SCOPED = "scoped"
PARTIALLY_SCOPED = "partially_scoped"
UNSCOPED = "unscoped"

# Verbatim from the scoping spec's Part 4 degradation table. Ordered with the
# most consequential omission second, as the spec emphasises it.
_CONSEQUENCES: list[tuple[str, str, str]] = [
    (
        "product_categories",
        "Product categories",
        "Unscoped run -- industry landscape, not your obligations. Said so at the top.",
    ),
    (
        "certification_basis",
        "Certification basis",
        "Regulatory changes reported without applicability. The single most consequential omission.",
    ),
    (
        "jurisdictions",
        "Jurisdictions",
        "All major regulators reported; relevance not assessed.",
    ),
    (
        "platforms",
        "Platforms and applications",
        "Findings cannot be connected to programmes or revenue.",
    ),
    (
        "standards_held",
        "Standards held",
        "Standards changes reported without requalification consequence.",
    ),
    (
        "suppliers",
        "Supplier watch list",
        "Supplier developments limited to what reaches trade press.",
    ),
    (
        "domains",
        "Technology domains",
        "Inferred from product categories; deliberate adjacencies missed.",
    ),
    (
        "exclusions",
        "Exclusions",
        "No filtering; expect noise from adjacent markets.",
    ),
]


@dataclass(frozen=True)
class ScopeItem:
    """One dimension of the envelope, its status, and what its absence costs.

    `consequence` is empty whenever the item is set. That is the bug fixed in
    b4f3282 for Agent 5's /readiness -- consequence text alongside a
    satisfied item reads as a warning about something that is actually
    fine."""
    key: str
    label: str
    status: str  # "set" | "missing"
    count: int
    consequence: str


def scope_items(envelope: ScopingEnvelope) -> list[ScopeItem]:
    counts = {
        "product_categories": len(envelope.categories),
        "certification_basis": len(envelope.certification_basis),
        "jurisdictions": len(envelope.jurisdictions),
        "platforms": len(envelope.platforms),
        "standards_held": len(envelope.standards_held),
        "suppliers": len(envelope.suppliers),
        "domains": len(envelope.domains),
        "exclusions": len(envelope.exclusions),
    }
    items: list[ScopeItem] = []
    for key, label, consequence in _CONSEQUENCES:
        count = counts[key]
        is_set = count > 0
        items.append(
            ScopeItem(
                key=key,
                label=label,
                status="set" if is_set else "missing",
                count=count,
                consequence="" if is_set else consequence,
            )
        )
    return items


def operating_state(envelope: ScopingEnvelope) -> str:
    """scoped | partially_scoped | unscoped.

    Product categories are the hinge: without them there is nothing to attach
    a finding to, and the degradation table calls that an unscoped run
    outright. With them, any other missing dimension degrades the run but
    does not unscope it -- the reader is told which dimension is missing and
    what it costs, which is the difference between a degraded answer and a
    misleading one."""
    if not envelope.categories:
        return UNSCOPED
    if any(item.status == "missing" for item in scope_items(envelope)):
        return PARTIALLY_SCOPED
    return SCOPED


def missing_labels(envelope: ScopingEnvelope) -> list[str]:
    return [item.label for item in scope_items(envelope) if item.status == "missing"]


# A reader must never mistake an industry survey for their own regulatory
# obligations, so an unscoped run is marked in the report title as well as
# stated in the first line (briefing Part 2, "unscoped must be unmissable").
UNSCOPED_TITLE_PREFIX = "UNSCOPED INDUSTRY SURVEY — "


def report_title(state: str, title: str) -> str:
    return f"{UNSCOPED_TITLE_PREFIX}{title}" if state == UNSCOPED else title


def operating_state_statement(envelope: ScopingEnvelope) -> str:
    """The first line of every run."""
    state = operating_state(envelope)

    if state == UNSCOPED:
        return (
            "**Operating state: UNSCOPED.** No applicability envelope was supplied, so this run "
            "is an industry survey of the technology and regulatory environment — it is NOT an "
            "assessment of this customer's obligations. Nothing below has been checked against "
            "any product category, certification basis or platform, and no finding here should "
            "be read as binding on the customer. Supplying product categories and certification "
            "basis is what converts this into an applicability assessment."
        )

    missing = missing_labels(envelope)
    if state == PARTIALLY_SCOPED:
        gaps = "; ".join(
            f"{item.label} — {item.consequence}"
            for item in scope_items(envelope)
            if item.status == "missing"
        )
        return (
            f"**Operating state: PARTIALLY SCOPED.** Findings are assessed against the supplied "
            f"envelope, but {len(missing)} dimension(s) are missing and each costs something "
            f"specific: {gaps}"
        )

    return (
        "**Operating state: SCOPED.** The applicability envelope is complete, so findings below "
        "are assessed against this customer's own approvals, standards and platforms rather "
        "than against the industry generally."
    )


# ---------------------------------------------------------------------------
# Rendering for the prompt
# ---------------------------------------------------------------------------


def render_envelope_text(envelope: ScopingEnvelope) -> str:
    """Plain-text rendering for the prompts. Customer vocabulary verbatim --
    category keys, platform names, basis identifiers and domain names are
    never translated, normalised or prettified, because the agent has to
    quote them back and the customer has to recognise them."""

    def _lines(items, fmt):
        return "\n".join(fmt(i) for i in items) or "(none supplied)"

    state = operating_state(envelope)

    sections = [
        f"Operating state: {state}.",
        "## Product categories (what the customer makes)\n"
        + _lines(
            envelope.categories,
            lambda c: f"- {c.category_key}: {c.category_name}"
            + (f" — {c.description}" if c.description else ""),
        ),
        "## Jurisdictions\n"
        + _lines(envelope.jurisdictions, lambda j: f"- {j.jurisdiction} (role: {j.role})"),
        "## Certification basis (what each category is approved under)\n"
        + _lines(
            envelope.certification_basis,
            lambda b: f"- {b.category_key}: {b.basis_type} {b.basis_identifier}"
            + (f", status {b.status}" if b.status else "")
            + (f", held since {b.held_since}" if b.held_since else ""),
        ),
        "## Platforms and applications\n"
        + _lines(
            envelope.platforms,
            lambda p: f"- {p.platform} ({p.platform_class}) — relationship: {p.relationship}"
            + (f", {p.programme_status}" if p.programme_status else ""),
        ),
        "## Standards held\n"
        + _lines(
            envelope.standards_held,
            lambda s: f"- {s.standard_id}"
            + (f" rev {s.revision}" if s.revision else "")
            + (f" ({s.scope})" if s.scope else "")
            + (f" — status: {s.status}" if s.status else ""),
        ),
        "## Supplier watch list\n"
        + _lines(
            envelope.suppliers,
            lambda s: f"- {s.supplier}: {s.what_they_supply}"
            + (f" — criticality: {s.criticality}" if s.criticality else ""),
        ),
        "## Technology domains to monitor\n" + _lines(envelope.domains, lambda d: f"- {d}"),
        "## Exclusions (honour these, and STATE them as excluded at the customer's direction)\n"
        + _lines(
            envelope.exclusions,
            lambda e: f"- {e.exclusion_type}: {e.value}" + (f" — {e.reason}" if e.reason else ""),
        ),
        "## Tier 1 evidence supplied\n"
        + _lines(envelope.tier1_evidence_supplied, lambda t: f"- {t}")
        + "\n(Tier 1 evidence deepens the analysis; it never substitutes for the envelope. "
        "State which were supplied.)",
        "## What is missing from this envelope, and what it costs\n"
        + (
            _lines(
                [i for i in scope_items(envelope) if i.status == "missing"],
                lambda i: f"- {i.label}: {i.consequence}",
            )
        ),
    ]
    return "\n\n".join(sections)
