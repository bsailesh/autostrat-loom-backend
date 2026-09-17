"""
Strategy Synthesis Agent (Agent 5) — Pass 1's structured-output contract.

Pydantic, not app/schemas.py: market_insights/ imports nothing from app/
("deliberately decoupled from the FastAPI app... Phase 1's only job is to
prove the agent produces good, spec-compliant output as real code" -- its
own __init__.py docstring), and this package is built to keep the same
independence, so its own Pass 1 schema lives here rather than in the app's
shared schemas file. A later part's router can import these directly, or
re-export them from app/schemas.py, without this package ever depending on
app/.
"""

from pydantic import BaseModel, Field


class Pass1Citation(BaseModel):
    agent: str = Field(description="Upstream agent type, e.g. 'market-insights'")
    report_number: int
    section: str = Field(description="Section/heading within that report")
    classification: str = Field(description="FACT | OBSERVATION | INTERPRETATION | FORECAST | UNKNOWN")
    confidence: str = Field(description="High | Medium | Low")
    summary: str = Field(description="One sentence: what this citation supports")


class Pass1Candidate(BaseModel):
    key: str = Field(description="e.g. 'C-01' for discovered, 'U-01' for customer-proposed")
    name: str
    origin: str = Field(description="e.g. 'Discovered -- Market', 'Customer -- VP Sales'")
    problem: str
    evidence_summary: str
    support_classification: str = Field(
        description="evidence-supported | partially supported | user-provided, no supporting evidence found"
    )
    evidence_strength_rank: int = Field(description="Lower is stronger. Ordering basis only -- never a score.")
    source_citations: list[Pass1Citation] = Field(default_factory=list)


class Pass1DimensionScore(BaseModel):
    criterion: str
    score: float = Field(ge=1, le=10)
    basis: str = Field(description="measured | calculated | source-derived | estimated | user-provided | assumed")
    reason: str = Field(description="One line: what in the evidence drove this number")


class Pass1ProjectScore(BaseModel):
    project_key: str
    dimensions: list[Pass1DimensionScore]
    objectives_served: list[str] = Field(
        default_factory=list,
        description="Strategic objective keys this committed project serves, for deterministic coverage-gap checking",
    )
    confidence: str = Field(description="High | Medium | Low, overall")


class Pass1CriterionSubstitution(BaseModel):
    criterion: str
    declared_source_agent: str
    substituted_source: str
    rationale: str


class Pass1InferredDependency(BaseModel):
    project_key: str
    depends_on: str
    reason: str


class Pass1Output(BaseModel):
    candidates: list[Pass1Candidate] = Field(default_factory=list)
    project_scores: list[Pass1ProjectScore] = Field(default_factory=list)
    criterion_substitutions: list[Pass1CriterionSubstitution] = Field(default_factory=list)
    inferred_dependencies: list[Pass1InferredDependency] = Field(default_factory=list)
