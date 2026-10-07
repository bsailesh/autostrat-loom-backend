"""
Product Sustainment Agent (Agent 4) — the candidate work contract.

Two models, deliberately separate:

  * `ModelCandidateWorkOutput` -- what the model returns from the one
    structured call. It carries JUDGEMENT only: which part, the named driver
    and its source, the work implied, candidate alternates with their
    evidence, classification and confidence. It has no field for a
    quantity, a date or applicability, so the model cannot emit one.
  * `CandidateWorkItem` -- what is persisted and what Agent 5 reads: the
    model's judgement merged with the NUMBERS from compute.py (runout or
    last-time-buy date, quantity required, every affected LRU and assembly)
    and the customer's own qualified alternate. See validation.py.

The lessons from Agent 5's Pass 1 failure, structurally:
  * `items` has NO default -- a truncated tool input coerced to a fragment
    fails validation instead of validating as empty.
  * `extra="forbid"` on both levels -- a misnamed or wrapped field fails by
    name, and that name reaches the retry prompt. The tool schema carries
    additionalProperties: false.

There is no field for effort, duration, cost, priority, rank or a
recommendation. This agent supplies options; Agent 5 decides.
"""
from pydantic import BaseModel, ConfigDict, Field

WORK_IMPLIED_KINDS = ("last_time_buy", "alternate_qualification", "redesign", "inventory_rebalance", "monitor")
CLASSIFICATIONS = ("FACT", "OBSERVATION", "INTERPRETATION", "FORECAST", "UNKNOWN")
CONFIDENCES = ("High", "Medium", "Low")
ALTERNATE_BASES = ("manufacturer_replacement", "pin_compatible_family", "distributor_cross_reference", "other")
DATE_BASES = ("runout", "window_closes", "none_established")


class CandidateAlternate(BaseModel):
    """An AGENT-FOUND part that might replace the at-risk one. Always a
    candidate for qualification, never qualified: there is no status field,
    because no public source knows the customer's qualification evidence."""
    model_config = ConfigDict(extra="forbid")

    part_number: str = Field(description="Manufacturer part number of the candidate")
    manufacturer: str = Field(default="")
    basis: str = Field(description="manufacturer_replacement | pin_compatible_family | distributor_cross_reference | other")
    evidence: str = Field(description="What the source says about compatibility")
    limits: str = Field(description="What the evidence does NOT establish -- e.g. not environmentally qualified, "
                                    "package or thermal differences, unverified pinout")
    source: str = Field(description="The source, named")
    source_date: str = Field(default="")


class ModelCandidateWorkItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    part_id: str = Field(description="The at-risk part's id exactly as in the part masters")
    driver: str = Field(description="The named part, its risk type, and the source -- a PCN number, an EOL "
                                    "notice, a supplier statement")
    work_implied: str = Field(description="last_time_buy | alternate_qualification | redesign | "
                                          "inventory_rebalance | monitor")
    work_implied_description: str = Field(default="", description="Factual. Never sized, ranked or recommended")
    candidate_alternates: list[CandidateAlternate] = Field(default_factory=list)
    date_absent_reason: str = Field(
        default="",
        description="REQUIRED when the computed results give this part no runout within the horizon and no "
                    "last-time-buy date: why no date exists (e.g. standing single-source exposure)",
    )
    classification: str = Field(description="FACT | OBSERVATION | INTERPRETATION | FORECAST | UNKNOWN")
    confidence: str = Field(description="High | Medium | Low -- reflecting completeness of the BOM, inventory "
                                        "and demand data, not the arithmetic, which is exact")
    source: str = Field(description="The source of the risk, named")
    source_date: str = Field(default="")


class ModelCandidateWorkOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # No default, deliberately -- see this module's docstring.
    items: list[ModelCandidateWorkItem]


class CandidateWorkItem(BaseModel):
    """The persisted item: model judgement + computed numbers + customer
    qualified alternate."""
    candidate_key: str
    part_id: str
    driver: str
    work_date: str | None
    date_basis: str
    date_absent_reason: str = ""
    applicability: dict
    quantity_required: int | None
    quantity_basis: str
    qualified_alternate_part_id: str | None
    candidate_alternates: list[dict]
    work_implied: str
    work_implied_description: str
    classification: str
    confidence: str
    source: str
    source_date: str
