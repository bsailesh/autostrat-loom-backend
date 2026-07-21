from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import get_current_tenant
from app.database import get_db
from app.models import AuditLog, Tenant
from app.schemas import AuditLogOut
from app.tenant_scope import scoped_query

router = APIRouter(prefix="/audit-log", tags=["audit"])


@router.get("", response_model=list[AuditLogOut])
def list_audit_log(
    limit: int = 100,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    return (
        scoped_query(db, AuditLog, tenant)
        .order_by(AuditLog.created_at.desc())
        .limit(min(limit, 500))
        .all()
    )
