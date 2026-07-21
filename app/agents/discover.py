"""
Loom Discover.

Reads a raw piece of input (support ticket, sales call note, review) and
extracts a validated, concretely-stated customer problem — or flags that the
text doesn't actually contain one, so noise doesn't pollute the backlog.
"""
from sqlalchemy.orm import Session

from app.agents.base import BaseAgent
from app.models import Signal, Tenant
from app.schemas import DiscoverExtractionSchema

SYSTEM_PROMPT = """You are Loom Discover, a product management agent that
mines raw customer input for validated problems.

Given a piece of text (support ticket, sales call note, or review), decide:
1. Does this text describe a concrete, specific customer problem — not a
   vague complaint, a one-off rant, or a feature request with no underlying
   problem stated?
2. If yes, restate the underlying problem in one or two sentences, in the
   customer's terms, stripped of tone.
3. Suggest which portfolio category it most likely belongs to: growth,
   irad, customer_funded, sustainment, or obsolescence.
4. Give a confidence score (0-10) for how clearly this text supports that
   read.

Be skeptical. Most raw text is not a validated problem. If it's just
sentiment with no specifics, or a request already covered by an obvious
existing feature, set is_validated_problem to false."""


class DiscoverAgent(BaseAgent):
    name = "discover"

    def run(self, db: Session, *, tenant: Tenant, source_type: str, raw_text: str, actor_label: str) -> Signal:
        user_prompt = f"Source type: {source_type}\n\nText:\n{raw_text}"

        result = self.call_claude_structured(
            system=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            output_schema=DiscoverExtractionSchema,
        )

        signal = Signal(
            tenant_id=tenant.id,
            source_type=source_type,
            raw_text=raw_text,
            extracted_problem=result.extracted_problem,
            suggested_category=result.suggested_category,
            confidence=result.confidence,
            is_validated=result.is_validated_problem,
        )
        db.add(signal)

        self.log(
            db,
            tenant=tenant,
            actor_label=actor_label,
            action=f"analyzed {source_type} input",
            input_summary=raw_text,
            output_summary=f"validated={result.is_validated_problem} | {result.extracted_problem}",
        )

        db.commit()
        db.refresh(signal)
        return signal
