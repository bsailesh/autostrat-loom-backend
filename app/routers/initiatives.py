from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agents import PrioritizeAgent
from app.auth import get_current_tenant, get_current_api_key
from app.database import get_db
from app.models import ApiKey, Initiative, Tenant
from app.schemas import InitiativeCreate, InitiativeOut, ScoreOut
from app.tenant_scope import get_or_404, scoped_query

router = APIRouter(prefix="/initiatives", tags=["initiatives"])

_prioritize_agent = PrioritizeAgent()


@router.post("", response_model=InitiativeOut)
def create_initiative(
    payload: InitiativeCreate,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    initiative = Initiative(tenant_id=tenant.id, **payload.model_dump())
    db.add(initiative)
    db.commit()
    db.refresh(initiative)
    return initiative


@router.get("", response_model=list[InitiativeOut])
def list_initiatives(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    return scoped_query(db, Initiative, tenant).order_by(Initiative.created_at.desc()).all()


@router.get("/{initiative_id}", response_model=InitiativeOut)
def get_initiative(
    initiative_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    return get_or_404(db, Initiative, tenant, initiative_id)


@router.post("/{initiative_id}/prioritize", response_model=ScoreOut)
def prioritize_initiative(
    initiative_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    api_key: ApiKey = Depends(get_current_api_key),
    db: Session = Depends(get_db),
):
    """Runs the Prioritize agent against one initiative and stores a new score."""
    initiative = get_or_404(db, Initiative, tenant, initiative_id)
    return _prioritize_agent.run(db, tenant=tenant, initiative=initiative, actor_label=api_key.label)


@router.get("/{initiative_id}/scores", response_model=list[ScoreOut])
def list_scores_for_initiative(
    initiative_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    from app.models import Score  # local import avoids a circular import at module load

    get_or_404(db, Initiative, tenant, initiative_id)  # 404s if it's not this tenant's
    return (
        db.query(Score)
        .filter(Score.tenant_id == tenant.id, Score.initiative_id == initiative_id)
        .order_by(Score.created_at.desc())
        .all()
    )
