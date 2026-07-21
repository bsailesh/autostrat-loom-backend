"""
Loom Prioritize.

Scores an initiative on a RICE-style framework (Reach, Impact, Confidence,
Effort) and stores a composite score plus a written rationale. Composite
score is computed in Python, not by Claude — the LLM estimates the four
inputs with reasoning attached; the arithmetic on top of those inputs is
deterministic so the same four numbers always produce the same ranking.
"""
from sqlalchemy.orm import Session

from app.agents.base import BaseAgent
from app.models import Initiative, Score, Tenant
from app.schemas import PrioritizeScoreSchema

SYSTEM_PROMPT = """You are Loom Prioritize, a product management scoring agent.

Score the given initiative using a RICE-style framework:
- Reach (0-10): how many customers/segments this affects
- Impact (0-10): magnitude of value if delivered
- Confidence (0-10): confidence in the reach/impact estimate given the information provided
- Effort (0.5-10): relative implementation effort (higher = more effort)

Be calibrated, not generous. Most initiatives should NOT score near the top
of every dimension. Write the rationale for a product leader who will use it
to defend the ranking in a portfolio review — be specific about what in the
description drove each number, and name the biggest uncertainty."""


class PrioritizeAgent(BaseAgent):
    name = "prioritize"

    def run(self, db: Session, *, tenant: Tenant, initiative: Initiative, actor_label: str) -> Score:
        user_prompt = f"""Initiative to score:

Title: {initiative.title}
Category: {initiative.category}
Description: {initiative.description or "(no description provided)"}"""

        result = self.call_claude_structured(
            system=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            output_schema=PrioritizeScoreSchema,
        )

        composite = round(
            (result.reach * result.impact * result.confidence) / max(result.effort, 0.5), 2
        )

        score = Score(
            tenant_id=tenant.id,
            initiative_id=initiative.id,
            reach=result.reach,
            impact=result.impact,
            confidence=result.confidence,
            effort=result.effort,
            composite_score=composite,
            rationale=result.rationale,
        )
        db.add(score)
        initiative.status = "scored"

        self.log(
            db,
            tenant=tenant,
            actor_label=actor_label,
            action=f"scored initiative '{initiative.title}'",
            input_summary=user_prompt,
            output_summary=f"composite={composite} | {result.rationale}",
        )

        db.commit()
        db.refresh(score)
        return score
