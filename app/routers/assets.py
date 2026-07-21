from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agents import SustainAgent
from app.auth import get_current_tenant, get_current_api_key
from app.database import get_db
from app.models import ApiKey, Asset, SustainAssessment, Tenant
from app.schemas import AssetCreate, AssetOut, SustainAssessmentOut
from app.tenant_scope import get_or_404, scoped_query

router = APIRouter(prefix="/assets", tags=["assets"])

_sustain_agent = SustainAgent()


@router.post("", response_model=AssetOut)
def create_asset(
    payload: AssetCreate,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    asset = Asset(tenant_id=tenant.id, **payload.model_dump())
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


@router.get("", response_model=list[AssetOut])
def list_assets(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    return scoped_query(db, Asset, tenant).order_by(Asset.created_at.desc()).all()


@router.post("/{asset_id}/assess", response_model=SustainAssessmentOut)
def assess_asset(
    asset_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    api_key: ApiKey = Depends(get_current_api_key),
    db: Session = Depends(get_db),
):
    """Runs the Sustain agent against one tracked asset."""
    asset = get_or_404(db, Asset, tenant, asset_id)
    return _sustain_agent.run(db, tenant=tenant, asset=asset, actor_label=api_key.label)


@router.get("/{asset_id}/assessments", response_model=list[SustainAssessmentOut])
def list_assessments(
    asset_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    get_or_404(db, Asset, tenant, asset_id)
    return (
        db.query(SustainAssessment)
        .filter(SustainAssessment.tenant_id == tenant.id, SustainAssessment.asset_id == asset_id)
        .order_by(SustainAssessment.created_at.desc())
        .all()
    )
