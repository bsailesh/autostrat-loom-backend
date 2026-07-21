"""
Centralized tenant-scoped query helpers.

Every read or write of a tenant-owned row goes through one of these
functions instead of raw `db.query(Model)...` calls scattered across
routers. The reason: tenant isolation is a "every single query got it right"
property, and the easiest way to keep that true as the codebase grows is to
make the correct thing the only convenient thing.
"""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Tenant


def scoped_query(db: Session, model, tenant: Tenant):
    """Return a query for `model` pre-filtered to the given tenant."""
    return db.query(model).filter(model.tenant_id == tenant.id)


def get_or_404(db: Session, model, tenant: Tenant, row_id: str):
    """Fetch a single row by id, scoped to tenant, or raise 404.

    Deliberately returns 404 (not 403) when a row exists but belongs to a
    different tenant — this avoids confirming to a caller that a given ID
    exists at all outside their own tenant.
    """
    row = scoped_query(db, model, tenant).filter(model.id == row_id).first()
    if not row:
        raise HTTPException(status_code=404, detail=f"{model.__name__} not found")
    return row
