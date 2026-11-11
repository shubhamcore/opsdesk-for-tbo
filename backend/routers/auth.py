"""Authentication, identity and the demo role switcher."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.deps import agency_payload, user_payload
from backend.api.schemas import DemoLoginRequest, LoginRequest, RoleSwitchRequest
from backend.config import settings
from backend.database import get_db
from backend.models import Agency, User
from backend.security import create_access_token, get_current_user, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _session_payload(user: User, db: Session) -> dict:
    return {
        "access_token": create_access_token(user),
        "token_type": "bearer",
        "user": user_payload(user),
        "agency": agency_payload(db.get(Agency, user.agency_id) if user.agency_id else None),
    }


@router.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> dict:
    # Browser autofill and copy-paste frequently append a trailing space; trimming is
    # safe here because seeded credentials never contain surrounding whitespace, and it
    # turns a confusing "Invalid email or password" into a successful sign-in.
    email = payload.email.strip().lower()
    password = payload.password.strip()
    user = db.scalar(select(User).where(User.email == email))
    if user is None or user.is_deleted or not verify_password(password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    return _session_payload(user, db)


@router.post("/demo-login")
def demo_login(payload: DemoLoginRequest, db: Session = Depends(get_db)) -> dict:
    """One-click sign-in for the seeded synthetic demo accounts.

    Available only when ``OPSDESK_ENABLE_ROLE_SWITCH`` is enabled. The token is
    still minted server-side after a real password verification, so RBAC and the
    audit trail behave exactly as they do for a typed password.
    """
    if not settings.enable_demo_role_switch:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Demo sign-in is disabled on this deployment")
    if not payload.email:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "email is required")
    user = db.scalar(select(User).where(User.email == payload.email.strip().lower()))
    if user is None or user.is_deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown demo identity {payload.email}")
    if not verify_password(settings.demo_password, user.hashed_password):
        raise HTTPException(status.HTTP_409_CONFLICT, "Seeded password does not match OPSDESK_DEMO_PASSWORD")
    return _session_payload(user, db)


@router.get("/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return {
        "user": user_payload(user),
        "agency": agency_payload(db.get(Agency, user.agency_id) if user.agency_id else None),
    }


@router.post("/switch-role")
def switch_role(
    payload: RoleSwitchRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Demo convenience: sign in as another seeded identity.

    Disabled with ``OPSDESK_ENABLE_ROLE_SWITCH=false`` in a real deployment —
    the token is still minted server-side, so RBAC remains enforced.
    """
    if not settings.enable_demo_role_switch:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Role switching is disabled on this deployment")

    query = select(User).where(User.role == payload.role, User.is_deleted.is_(False))
    if payload.role == "AGENCY_REQUESTER":
        if not payload.agency_code:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "agency_code is required for requesters")
        agency = db.scalar(select(Agency).where(Agency.code == payload.agency_code))
        if agency is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown agency {payload.agency_code}")
        query = query.where(User.agency_id == agency.id)
    target = db.scalars(query.order_by(User.id)).first()
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No seeded user for role {payload.role}")
    return _session_payload(target, db)


@router.get("/identities")
def identities(db: Session = Depends(get_db)) -> dict:
    """Seeded demo identities for the login screen (no secrets beyond the
    documented demo password)."""
    users = db.scalars(select(User).where(User.is_deleted.is_(False)).order_by(User.role, User.id)).all()
    agencies = db.scalars(select(Agency).order_by(Agency.id)).all()
    return {
        "identities": [
            {
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role,
                "region": user.region,
                "agency_code": next((a.code for a in agencies if a.id == user.agency_id), None),
            }
            for user in users
        ],
        "agencies": [agency_payload(a) for a in agencies],
        "demo_password_hint": (
            f"Demo password: {settings.demo_password}"
            if settings.enable_demo_role_switch
            else "Contact your administrator"
        ),
    }
