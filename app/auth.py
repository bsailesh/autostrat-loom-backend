"""
Auth.

Every request that touches tenant data must go through `get_current_tenant`,
which resolves the caller's API key to exactly one tenant. There is no code
path in the routers that accepts a tenant_id from the request body or query
string for data access — the tenant is always derived server-side from the
key, never trusted from client input. That's the core of the tenant
isolation guarantee here: a caller cannot ask for another tenant's data by
changing a parameter, because no parameter for that exists.

Two kinds of bearer tokens share the same api_keys table and the same
lookup path: long-lived keys created via /admin/tenants (no expiry), and
short-lived session tokens minted by /auth/login (expires_at set). Both are
validated the same way here, so routers never need to know which kind
they're looking at.
"""
from datetime import datetime, timezone

from fastapi import Header, HTTPException, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ApiKey, Tenant
from app.config import get_settings


def _resolve_api_key(authorization: str | None, db: Session) -> ApiKey:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header. Use: Bearer <token>")

    key = authorization.removeprefix("Bearer ").strip()
    api_key = db.query(ApiKey).filter(ApiKey.key == key).first()
    if not api_key:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    if api_key.expires_at is not None:
        expires_at = api_key.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=401, detail="Invalid or expired token")

    return api_key


def get_current_tenant(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Tenant:
    api_key = _resolve_api_key(authorization, db)
    tenant = db.query(Tenant).filter(Tenant.id == api_key.tenant_id).first()
    if not tenant:
        # Orphaned key — shouldn't happen given the FK, but fail closed.
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return tenant


def get_current_api_key(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> ApiKey:
    """Like get_current_tenant, but returns the key row (for role checks / audit labeling)."""
    return _resolve_api_key(authorization, db)


def require_admin_key(x_admin_key: str | None = Header(default=None)) -> None:
    """Gate for platform-admin-only routes, like creating a new tenant."""
    settings = get_settings()
    if not x_admin_key or x_admin_key not in settings.admin_keys:
        raise HTTPException(status_code=403, detail="Missing or invalid X-Admin-Key")
