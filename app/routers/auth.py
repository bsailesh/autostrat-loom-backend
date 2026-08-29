from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user, issue_session_token, require_admin_key
from app.database import get_db
from app.models import ApiKey, SignupAllowlist, Tenant, User
from app.schemas import (
    LoginRequest,
    LoginResponse,
    MeResponse,
    SignupRequest,
    UserCreate,
    UserOut,
)
from app.security import hash_password, verify_password

router = APIRouter(tags=["auth"])


def _login_response(token: str, tenant: Tenant, user: User, expires_at: datetime) -> LoginResponse:
    return LoginResponse(
        token=token,
        tenant_id=tenant.id,
        tenant_name=tenant.name,
        user_email=user.email,
        role=user.role,
        expires_at=expires_at,
    )


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


@router.post("/auth/signup", response_model=LoginResponse, status_code=201)
def signup(payload: SignupRequest, db: Session = Depends(get_db)):
    """
    Self-serve signup. Every account is a tenant: this creates a new tenant and
    a single owner user for it, in one transaction, and returns a session token
    so the caller is immediately logged in.
    """
    email = payload.email.strip().lower()

    # Pre-Phase 6 stopgap: signups are invite-only until there's billing. Only
    # emails an operator has added to the allowlist can create a new account.
    # Existing accounts are unaffected — this gates new signups only.
    if not db.query(SignupAllowlist).filter(SignupAllowlist.email == email).first():
        raise HTTPException(status_code=403, detail="Signups are currently invite-only.")

    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="A user with this email already exists")

    tenant_name = payload.tenant_name.strip() or f"{email}'s workspace"

    tenant = Tenant(name=tenant_name)
    db.add(tenant)
    db.flush()  # need tenant.id

    user = User(
        tenant_id=tenant.id,
        email=email,
        password_hash=hash_password(payload.password),
        role="owner",
    )
    db.add(user)
    db.flush()  # need user.id for the session token

    session_key = issue_session_token(db, user=user, tenant=tenant)
    db.commit()
    return _login_response(session_key.key, tenant, user, session_key.expires_at)


@router.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.strip().lower()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        # Same error for "no such user" and "wrong password" — don't leak
        # which one it was.
        raise HTTPException(status_code=401, detail="Invalid email or password")

    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    session_key = issue_session_token(db, user=user, tenant=tenant)
    db.commit()
    return _login_response(session_key.key, tenant, user, session_key.expires_at)


@router.get("/auth/me", response_model=MeResponse)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
    return MeResponse(
        user_id=user.id,
        email=user.email,
        role=user.role,
        tenant_id=user.tenant_id,
        tenant_name=tenant.name if tenant else "",
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
