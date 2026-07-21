"""
Loom Align.

Takes a set of initiatives (with their latest scores, where available) and
drafts a roadmap narrative plus an exec-ready summary. This agent doesn't
decide what's in scope — the caller passes in the initiative_ids — it turns
an already-selected set into a coherent, presentable document.
"""
from sqlalchemy.orm import Session

from app.agents.base import BaseAgent
from app.models import Initiative, RoadmapDoc, Score, Tenant
from app.schemas import AlignDraftSchema

SYSTEM_PROMPT = """You are Loom Align, a product management agent that turns
a prioritized list of initiatives into a roadmap narrative and an
exec-ready summary.

Given a list of initiatives (with title, category, description, and score
where available), produce:
- exec_summary: 3-5 sentences a leadership audience can read in 20 seconds,
  covering what's prioritized and why, in plain language.
- narrative: a fuller markdown document organized by theme or priority
  order, referencing specific initiatives, that a product team could use
  as an actual roadmap communication.

Do not invent initiatives that weren't given to you. Do not invent scores or
dates that weren't provided."""


class AlignAgent(BaseAgent):
    name = "align"

    def run(
        self,
        db: Session,
        *,
        tenant: Tenant,
        title: str,
        initiatives: list[Initiative],
        actor_label: str,
    ) -> RoadmapDoc:
        lines = []
        for init in initiatives:
            latest_score = (
                db.query(Score)
                .filter(Score.initiative_id == init.id, Score.tenant_id == tenant.id)
                .order_by(Score.created_at.desc())
                .first()
            )
            score_str = f"composite score {latest_score.composite_score}" if latest_score else "not yet scored"
            lines.append(
                f"- [{init.category}] {init.title} ({score_str}): {init.description or 'no description'}"
            )

        user_prompt = f"Roadmap title: {title}\n\nInitiatives:\n" + "\n".join(lines)

        result = self.call_claude_structured(
            system=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            output_schema=AlignDraftSchema,
            max_tokens=2500,
        )

        doc = RoadmapDoc(
            tenant_id=tenant.id,
            title=title,
            exec_summary=result.exec_summary,
            narrative=result.narrative,
            included_initiative_ids=[i.id for i in initiatives],
        )
        db.add(doc)

        for init in initiatives:
            init.status = "roadmapped"

        self.log(
            db,
            tenant=tenant,
            actor_label=actor_label,
            action=f"drafted roadmap '{title}' from {len(initiatives)} initiatives",
            input_summary=user_prompt,
            output_summary=result.exec_summary,
        )

        db.commit()
        db.refresh(doc)
        return doc
