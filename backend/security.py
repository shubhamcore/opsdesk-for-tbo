"""Password hashing (PBKDF2-HMAC-SHA256), JWT issuance and RBAC dependencies."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
from datetime import timedelta

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import get_db
from backend.models import User
from backend.models.base import utcnow

_PBKDF2_ROUNDS = 260_000
_ALGO = "HS256"

# ------------------------------------------------------------------ passwords


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ROUNDS)
    return "pbkdf2_sha256${}${}${}".format(
        _PBKDF2_ROUNDS, base64.b64encode(salt).decode(), base64.b64encode(digest).decode()
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, rounds, salt_b64, digest_b64 = stored.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), base64.b64decode(salt_b64), int(rounds)
        )
        return hmac.compare_digest(digest, base64.b64decode(digest_b64))
    except (ValueError, TypeError):
        return False


# ------------------------------------------------------------------ tokens


def create_access_token(user: User) -> str:
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role,
        "agency_id": user.agency_id,
        "exp": utcnow() + timedelta(minutes=settings.token_ttl_minutes),
        "iat": utcnow(),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=_ALGO)


_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    try:
        payload = jwt.decode(credentials.credentials, settings.secret_key, algorithms=[_ALGO])
    except JWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid token: {exc}") from exc
    user = db.get(User, int(payload["sub"]))
    if user is None or user.is_deleted:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User no longer exists")
    return user


def require_roles(*roles: str):
    """Dependency factory enforcing role-based access control server-side."""

    async def _dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Role {user.role} is not permitted. Requires one of: {', '.join(roles)}",
            )
        return user

    return _dep


# Convenience role groups
OPS_ROLES = ("OPS_AGENT", "ESCALATION_MANAGER", "OPS_LEAD")
ANY_ROLE = ("AGENCY_REQUESTER", "OPS_AGENT", "ESCALATION_MANAGER", "OPS_LEAD")
