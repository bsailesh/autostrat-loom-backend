from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agents import AlignAgent
from app.auth import get_current_tenant, get_current_api_key
from app.database import get_db
from app.models import ApiKey, Initiative, RoadmapDoc, Tenant
from app.schemas import AlignRequest, RoadmapDocOut
from app.tenant_scope import scoped_query

router = APIRouter(prefix="/roadmaps", tags=["roadmaps"])

_align_agent = AlignAgent()


@router.post("", response_model=RoadmapDocOut)
def draft_roadmap(
    payload: AlignRequest,
    tenant: Tenant = Depends(get_current_tenant),
    api_key: ApiKey = Depends(get_current_api_key),
    db: Session = Depends(get_db),
):
    """Runs the Align agent over a chosen set of this tenant's initiatives."""
    initiatives = (
        db.query(Initiative)
        .filter(Initiative.tenant_id == tenant.id, Initiative.id.in_(payload.initiative_ids))
        .all()
    )
    if not initiatives:
        raise HTTPException(status_code=404, detail="None of the given initiative_ids belong to this tenant")
    if len(initiatives) != len(set(payload.initiative_ids)):
        raise HTTPException(status_code=404, detail="One or more initiative_ids don't belong to this tenant")

    return _align_agent.run(db, tenant=tenant, title=payload.title, initiatives=initiatives, actor_label=api_key.label)


@router.get("", response_model=list[RoadmapDocOut])
def list_roadmaps(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    return scoped_query(db, RoadmapDoc, tenant).order_by(RoadmapDoc.created_at.desc()).all()
