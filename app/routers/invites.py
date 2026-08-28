"""
Tenant invitations.

An owner or admin issues an invite bound to their own tenant_id and an email
address. Accepting it creates a User on that *existing* tenant — there is no
code path here that creates a new tenant, so "invite a colleague" can never
fork the account.

There is no email delivery in this phase, so POST /invites returns the token in
the response body; in a later phase that token is emailed instead.
"""
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user, issue_session_token
from app.database import get_db
from app.models import Invite, Tenant, User
from app.schemas import InviteAcceptRequest, InviteCreate, InviteOut, LoginResponse

router = APIRouter(prefix="/invites", tags=["invites"])

_INVITE_TTL_DAYS = 7
_ASSIGNABLE_ROLES = {"admin", "member"}  # an invite can't mint another owner


@router.post("", response_model=InviteOut, status_code=201)
def create_invite(
    payload: InviteCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only an owner or admin can invite users")

    role = payload.role.strip().lower()
    if role not in _ASSIGNABLE_ROLES:
        raise HTTPException(status_code=422, detail=f"role must be one of {sorted(_ASSIGNABLE_ROLES)}")

    email = payload.email.strip().lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="A user with this email already exists")

    # Supersede any earlier un-accepted invite for the same email on this tenant.
    (
        db.query(Invite)
        .filter(
            Invite.tenant_id == user.tenant_id,
            Invite.email == email,
            Invite.accepted_at.is_(None),
        )
        .delete()
    )

    invite = Invite(
        tenant_id=user.tenant_id,
        email=email,
        role=role,
        token=f"loom_inv_{secrets.token_urlsafe(32)}",
        invited_by_user_id=user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=_INVITE_TTL_DAYS),
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)
    return invite


@router.post("/accept", response_model=LoginResponse, status_code=201)
def accept_invite(payload: InviteAcceptRequest, db: Session = Depends(get_db)):
    """Public: turn a valid invite token into a real user on the invite's tenant."""
    invite = db.query(Invite).filter(Invite.token == payload.token).first()
    if not invite or invite.accepted_at is not None:
        raise HTTPException(status_code=404, detail="Invite not found or already used")

    expires_at = invite.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Invite has expired")

    tenant = db.query(Tenant).filter(Tenant.id == invite.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Invite not found or already used")

    if db.query(User).filter(User.email == invite.email).first():
        raise HTTPException(status_code=409, detail="A user with this email already exists")

    from app.security import hash_password

    user = User(
        tenant_id=invite.tenant_id,  # the existing tenant — never a new one
        email=invite.email,
        password_hash=hash_password(payload.password),
        role=invite.role,
    )
    db.add(user)
    invite.accepted_at = datetime.now(timezone.utc)
    db.flush()

    session_key = issue_session_token(db, user=user, tenant=tenant)
    db.commit()

    return LoginResponse(
        token=session_key.key,
        tenant_id=tenant.id,
        tenant_name=tenant.name,
        user_email=user.email,
        role=user.role,
        expires_at=session_key.expires_at,
    )
