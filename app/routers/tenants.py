"""
Platform-admin routes. Gated by X-Admin-Key, not a tenant API key — these
manage tenants themselves, so they can't be scoped to a tenant.

For a real launch this becomes a proper onboarding flow (signup, email
verification, billing hookup). This is the minimum needed to stand up a new
tenant for a demo or pilot.
"""
import secrets

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import require_admin_key
from app.database import get_db
from app.models import ApiKey, Tenant
from app.schemas import TenantCreate, TenantOut

router = APIRouter(prefix="/admin/tenants", tags=["admin"])


@router.post("", response_model=TenantOut, dependencies=[Depends(require_admin_key)])
def create_tenant(payload: TenantCreate, db: Session = Depends(get_db)):
    tenant = Tenant(name=payload.name)
    db.add(tenant)
    db.flush()  # get tenant.id before creating the key

    key_value = f"loom_{secrets.token_urlsafe(32)}"
    api_key = ApiKey(tenant_id=tenant.id, key=key_value, label="primary", role="admin")
    db.add(api_key)
    db.commit()
    db.refresh(tenant)

    return TenantOut(id=tenant.id, name=tenant.name, created_at=tenant.created_at, api_key=key_value)
