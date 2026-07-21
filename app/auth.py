"""
Auth.

Every request that touches tenant data must go through `get_current_tenant`,
which resolves the caller's API key to exactly one tenant. There is no code
path in the routers that accepts a tenant_id from the request body or query
string for data access — the tenant is always derived server-side from the
key, never trusted from client input. That's the core of the tenant
isolation guarantee here: a caller cannot ask for another tenant's data by
changing a parameter, because no parameter for that exists.
"""
from fastapi import Header, HTTPException, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ApiKey, Tenant
from app.config import get_settings


def get_current_tenant(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Tenant:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header. Use: Bearer <api_key>")

    key = authorization.removeprefix("Bearer ").strip()
    api_key = db.query(ApiKey).filter(ApiKey.key == key).first()
    if not api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    tenant = db.query(Tenant).filter(Tenant.id == api_key.tenant_id).first()
    if not tenant:
        # Orphaned key — shouldn't happen given the FK, but fail closed.
        raise HTTPException(status_code=401, detail="Invalid API key")

    return tenant


def get_current_api_key(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> ApiKey:
    """Like get_current_tenant, but returns the key row (for role checks / audit labeling)."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header. Use: Bearer <api_key>")

    key = authorization.removeprefix("Bearer ").strip()
    api_key = db.query(ApiKey).filter(ApiKey.key == key).first()
    if not api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return api_key


def require_admin_key(x_admin_key: str | None = Header(default=None)) -> None:
    """Gate for platform-admin-only routes, like creating a new tenant."""
    settings = get_settings()
    if not x_admin_key or x_admin_key not in settings.admin_keys:
        raise HTTPException(status_code=403, detail="Missing or invalid X-Admin-Key")
