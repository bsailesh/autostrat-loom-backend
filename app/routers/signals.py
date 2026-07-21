from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agents import DiscoverAgent
from app.auth import get_current_tenant, get_current_api_key
from app.database import get_db
from app.models import ApiKey, Signal, Tenant
from app.schemas import DiscoverRequest, SignalOut
from app.tenant_scope import scoped_query

router = APIRouter(prefix="/signals", tags=["signals"])

_discover_agent = DiscoverAgent()


@router.post("/discover", response_model=SignalOut)
def discover_signal(
    payload: DiscoverRequest,
    tenant: Tenant = Depends(get_current_tenant),
    api_key: ApiKey = Depends(get_current_api_key),
    db: Session = Depends(get_db),
):
    """Runs the Discover agent on a raw piece of text (ticket, call note, review)."""
    return _discover_agent.run(
        db,
        tenant=tenant,
        source_type=payload.source_type,
        raw_text=payload.raw_text,
        actor_label=api_key.label,
    )


@router.get("", response_model=list[SignalOut])
def list_signals(
    validated_only: bool = False,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    q = scoped_query(db, Signal, tenant)
    if validated_only:
        q = q.filter(Signal.is_validated == True)  # noqa: E712
    return q.order_by(Signal.created_at.desc()).all()
