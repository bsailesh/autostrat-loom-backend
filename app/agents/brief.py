"""
Loom Brief.

Aggregates current portfolio state — initiatives, their latest scores,
recent unvalidated-vs-validated signals, and outstanding sustainment risk —
into a single board-ready report. This is the only agent that reads across
all the others' output tables, which is why it belongs last in the pipeline
conceptually: Prioritize, Discover, Align, and Sustain produce the raw
material; Brief just reports on it.
"""
from sqlalchemy.orm import Session

from app.agents.base import BaseAgent
from app.models import Asset, BriefDoc, Initiative, Score, SustainAssessment, Tenant
from app.schemas import BriefDraftSchema
from app.tenant_scope import scoped_query

SYSTEM_PROMPT = """You are Loom Brief, a product management agent that
writes board-ready portfolio reports.

Given a snapshot of a product portfolio — initiatives by category and
status, their latest scores, and outstanding sustainment risk — write a
markdown report with these sections:
1. Portfolio Status (initiative counts by category and status)
2. Top Priorities (highest-scored initiatives, with why)
3. Sustainment & Obsolescence Risk (highest-risk assets, with recommended action)
4. Recommendations (2-4 concrete next steps for leadership)

Only use the data given. If a section has nothing to report, say so plainly
rather than padding it."""


class BriefAgent(BaseAgent):
    name = "brief"

    def run(self, db: Session, *, tenant: Tenant, title: str, notes: str, actor_label: str) -> BriefDoc:
        initiatives = scoped_query(db, Initiative, tenant).all()
        assets = scoped_query(db, Asset, tenant).all()

        init_lines = []
        for init in initiatives:
            latest_score = (
                db.query(Score)
                .filter(Score.initiative_id == init.id, Score.tenant_id == tenant.id)
                .order_by(Score.created_at.desc())
                .first()
            )
            score_str = f"score {latest_score.composite_score}" if latest_score else "unscored"
            init_lines.append(f"- [{init.category}/{init.status}] {init.title} ({score_str})")

        asset_lines = []
        for asset in assets:
            latest_assessment = (
                db.query(SustainAssessment)
                .filter(SustainAssessment.asset_id == asset.id, SustainAssessment.tenant_id == tenant.id)
                .order_by(SustainAssessment.created_at.desc())
                .first()
            )
            risk_str = f"risk={latest_assessment.risk_level}" if latest_assessment else "not yet assessed"
            asset_lines.append(f"- {asset.name} ({asset.asset_type}, {risk_str})")

        user_prompt = (
            f"Report title: {title}\n"
            f"Steer notes from requester: {notes or '(none)'}\n\n"
            f"Initiatives ({len(initiatives)} total):\n" + ("\n".join(init_lines) or "(none)") + "\n\n"
            f"Tracked assets ({len(assets)} total):\n" + ("\n".join(asset_lines) or "(none)")
        )

        result = self.call_claude_structured(
            system=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            output_schema=BriefDraftSchema,
            max_tokens=2500,
        )

        doc = BriefDoc(tenant_id=tenant.id, title=title, content=result.content)
        db.add(doc)

        self.log(
            db,
            tenant=tenant,
            actor_label=actor_label,
            action=f"generated brief '{title}'",
            input_summary=user_prompt,
            output_summary=result.content[:500],
        )

        db.commit()
        db.refresh(doc)
        return doc
