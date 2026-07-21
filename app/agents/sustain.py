"""
Loom Sustain.

Assesses obsolescence/end-of-life risk for a tracked part, platform, or
dependency, and recommends a next action before the risk becomes an outage
or compliance problem.
"""
from sqlalchemy.orm import Session

from app.agents.base import BaseAgent
from app.models import Asset, SustainAssessment, Tenant
from app.schemas import SustainAssessmentSchema

SYSTEM_PROMPT = """You are Loom Sustain, a product management agent that
tracks obsolescence and end-of-life risk for parts, platforms, and
dependencies used in a product.

Given an asset's name, type, end-of-life date (if known), and stated
criticality, assess:
- risk_level: low | medium | high | critical
- recommended_action: one concrete next step (a single sentence — e.g.
  "identify a drop-in replacement supplier within 6 months")
- rationale: 2-3 sentences explaining the risk level

Weigh criticality heavily: a high-criticality asset with an unknown or
distant EOL date is still worth flagging as medium risk, because "unknown"
is itself a risk for something critical. A low-criticality asset with a
known near-term EOL date is often still low-to-medium risk if it's easy to
replace — use judgment, don't just read the date mechanically."""


class SustainAgent(BaseAgent):
    name = "sustain"

    def run(self, db: Session, *, tenant: Tenant, asset: Asset, actor_label: str) -> SustainAssessment:
        user_prompt = f"""Asset: {asset.name}
Type: {asset.asset_type}
End-of-life date: {asset.eol_date or "unknown"}
Criticality: {asset.criticality}"""

        result = self.call_claude_structured(
            system=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            output_schema=SustainAssessmentSchema,
        )

        assessment = SustainAssessment(
            tenant_id=tenant.id,
            asset_id=asset.id,
            risk_level=result.risk_level,
            recommended_action=result.recommended_action,
            rationale=result.rationale,
        )
        db.add(assessment)

        self.log(
            db,
            tenant=tenant,
            actor_label=actor_label,
            action=f"assessed asset '{asset.name}'",
            input_summary=user_prompt,
            output_summary=f"risk={result.risk_level} | {result.recommended_action}",
        )

        db.commit()
        db.refresh(assessment)
        return assessment
