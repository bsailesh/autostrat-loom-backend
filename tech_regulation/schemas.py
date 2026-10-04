"""
Technology & Regulatory Intelligence Agent (Agent 3) — the candidate work
contract, as Pydantic.

This is the structured output of the agent's one non-narrative call, and the
shape Agent 5 reads directly. It exists so candidate work is generated once,
structurally, and then narrated into the reports -- rather than written as
prose and re-parsed afterwards by whoever needs it, which is a second parser
of an undocumented contract and the failure this codebase has already hit
twice (the Word export markdown parser, and Agent 5's own report
consumption).

Two deliberate schema properties, both load-bearing:

1. `items` has NO default. Every field on Agent 5's Pass1Output defaults to
   [], which is why a tool input truncated at the output ceiling -- coerced
   by the API to a fragment like `{"context": {}}` -- validated cleanly into
   an output with nothing in it and flowed into compute (fixed in fff5b4a).
   Here, that same fragment fails validation outright, so the schema itself
   catches the case rather than relying on the caller to notice. The caller
   checks `stop_reason` first anyway; this is the second line.

2. There is no field for effort, duration, cost, reach, priority or rank,
   and there must never be one. This agent cannot see the customer's
   engineering capacity, how they would scope the work, or what else
   competes for it. Naming the work is its job; sizing and ranking it is
   Agent 5's, against inputs this agent has no visibility into. A model
   cannot emit a field that does not exist, which makes the rule structural
   instead of a prompt instruction it can drift away from.
"""

from pydantic import BaseModel, Field

# Controlled vocabularies. Validated in validation.py rather than as Literal
# types: an out-of-vocabulary value should drop that one item with a readable
# reason and let the rest of the payload through, not fail the whole call the
# way a Literal mismatch would.
DATE_BASES = (
    "effective",
    "compliance_deadline",
    "runout",
    "transition_end",
    "window_closes",
    "none_established",
)

WORK_IMPLIED_KINDS = (
    "requalification",
    "new_approval",
    "design_change",
    "standards_participation",
    "supplier_qualification",
    "documentation",
    "other",
)

CLASSIFICATIONS = ("FACT", "OBSERVATION", "INTERPRETATION", "FORECAST", "UNKNOWN")

CONFIDENCES = ("High", "Medium", "Low")

PLATFORM_RELATIONSHIPS = ("shipping", "pursuing", "in_service", "sunsetting")


class CandidateWorkApplicability(BaseModel):
    """What the work touches, drawn from the applicability envelope rather
    than invented. At least one of the three lists must be non-empty -- work
    that applies to nothing in the customer's envelope is not this customer's
    work, and is a finding to state rather than work to name."""

    categories: list[str] = Field(
        default_factory=list, description="category_key values from the envelope, e.g. ['EMA-UTIL']"
    )
    certification_bases: list[str] = Field(
        default_factory=list, description="basis_identifier values, e.g. ['TSO-C196b']"
    )
    platforms: list[str] = Field(
        default_factory=list, description="platform values from the envelope"
    )
    note: str = Field(
        default="", description="One line on the boundary of applicability, e.g. what it does NOT touch"
    )


class CandidateWorkItem(BaseModel):
    candidate_key: str = Field(description="e.g. 'TR-01', unique within this run")
    driver: str = Field(
        description="The named regulation, standard revision, supplier notice, certification "
        "requirement or technology development, WITH its identifier"
    )
    work_date: str | None = Field(
        default=None,
        description="Effective date, compliance deadline, runout date, transition end, or the "
        "date a design-in window closes. Null ONLY where no date genuinely exists",
    )
    date_basis: str = Field(
        description="Which kind of date this is: effective | compliance_deadline | runout | "
        "transition_end | window_closes | none_established"
    )
    date_absent_reason: str = Field(
        default="",
        description="REQUIRED when work_date is null: why no date exists. An undated candidate is "
        "standing context rather than a scheduled item, and that has to be an honest "
        "absence, not an omission",
    )
    applicability: CandidateWorkApplicability
    work_implied: str = Field(
        description="requalification | new_approval | design_change | standards_participation | "
        "supplier_qualification | documentation | other"
    )
    work_implied_description: str = Field(
        default="", description="Factual description of the activity. Never sized, never ranked"
    )
    platform_relationship: str | None = Field(
        default=None,
        description="Carried from the platform where it differs: work driven by a 'pursuing' "
        "platform is an entry condition, not a cost against existing revenue",
    )
    classification: str = Field(description="FACT | OBSERVATION | INTERPRETATION | FORECAST | UNKNOWN")
    confidence: str = Field(description="High | Medium | Low")
    source: str = Field(description="The source, named. Primary regulatory sources outrank secondary reporting")
    source_date: str = Field(default="", description="Publication date of the source")


class CandidateWorkOutput(BaseModel):
    # No default, deliberately -- see this module's docstring, property 1.
    items: list[CandidateWorkItem]
