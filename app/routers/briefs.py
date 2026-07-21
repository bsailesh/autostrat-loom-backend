from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agents import BriefAgent
from app.auth import get_current_tenant, get_current_api_key
from app.database import get_db
from app.models import ApiKey, BriefDoc, Tenant
from app.schemas import BriefRequest, BriefDocOut
from app.tenant_scope import scoped_query

router = APIRouter(prefix="/briefs", tags=["briefs"])

_brief_agent = BriefAgent()


@router.post("", response_model=BriefDocOut)
def generate_brief(
    payload: BriefRequest,
    tenant: Tenant = Depends(get_current_tenant),
    api_key: ApiKey = Depends(get_current_api_key),
    db: Session = Depends(get_db),
):
    """Runs the Brief agent across this tenant's full current portfolio."""
    return _brief_agent.run(db, tenant=tenant, title=payload.title, notes=payload.notes, actor_label=api_key.label)


@router.get("", response_model=list[BriefDocOut])
def list_briefs(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    return scoped_query(db, BriefDoc, tenant).order_by(BriefDoc.created_at.desc()).all()
