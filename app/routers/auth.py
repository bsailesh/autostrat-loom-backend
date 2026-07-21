import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.auth import require_admin_key
from app.config import get_settings
from app.database import get_db
from app.models import ApiKey, Tenant, User
from app.schemas import LoginRequest, LoginResponse, UserCreate, UserOut
from app.security import hash_password, verify_password

router = APIRouter(tags=["auth"])


@router.post("/admin/tenants/{tenant_id}/users", response_model=UserOut, dependencies=[Depends(require_admin_key)])
def create_user(tenant_id: str, payload: UserCreate, db: Session = Depends(get_db)):
    """Platform-admin-only: create a login user for a given tenant."""
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="A user with this email already exists")

    user = User(
        tenant_id=tenant.id,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        # Same error for "no such user" and "wrong password" — don't leak
        # which one it was.
        raise HTTPException(status_code=401, detail="Invalid email or password")

    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    settings = get_settings()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.session_ttl_hours)
    session_key = ApiKey(
        tenant_id=tenant.id,
        key=f"loom_sess_{secrets.token_urlsafe(32)}",
        label=f"session:{user.email}",
        role=user.role,
        user_id=user.id,
        expires_at=expires_at,
    )
    db.add(session_key)
    db.commit()

    return LoginResponse(
        token=session_key.key,
        tenant_id=tenant.id,
        tenant_name=tenant.name,
        user_email=user.email,
        role=user.role,
        expires_at=expires_at,
    )


@router.post("/auth/logout")
def logout(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    """Invalidate the current session token. No-op (still 200) if it's already gone."""
    if authorization and authorization.startswith("Bearer "):
        key = authorization.removeprefix("Bearer ").strip()
        api_key = db.query(ApiKey).filter(ApiKey.key == key).first()
        if api_key:
            db.delete(api_key)
            db.commit()
    return {"status": "ok"}
