"""
Simple authentication service for authorized personnel.

In production this would use OAuth2 / LDAP / hospital SSO.
For the prototype we use a pre-seeded user list with hashed passwords
and JWT-like session tokens.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import time
from typing import Optional

from pydantic import BaseModel

from app.config import DASHBOARD_USERNAME, DASHBOARD_PASSWORD

logger = logging.getLogger(__name__)


class UserAccount(BaseModel):
    username: str
    password_hash: str
    full_name: str
    role: str  # "doctor", "nurse", "dispatcher", "admin"
    organization: str
    active: bool = True


class AuthSession(BaseModel):
    token: str
    username: str
    full_name: str
    role: str
    organization: str
    created_at: float


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


# ── Pre-seeded authorized accounts ──────────────────────────

_AUTHORIZED_USERS: dict[str, UserAccount] = {}

_SEED_USERS = [
    (DASHBOARD_USERNAME, DASHBOARD_PASSWORD, "System Administrator", "admin", "Emergency HQ"),
    ("dr.ahmed", "triage2024", "Dr. Ahmed Hassan", "doctor", "Central Hospital"),
    ("nurse.sara", "triage2024", "Sara Al-Rashid", "nurse", "Central Hospital"),
    ("dispatch1", "triage2024", "Dispatch Unit 1", "dispatcher", "Civil Defense"),
    ("redcross", "triage2024", "Red Cross Operator", "dispatcher", "Red Cross"),
]

for _u, _p, _name, _role, _org in _SEED_USERS:
    _AUTHORIZED_USERS[_u] = UserAccount(
        username=_u,
        password_hash=_hash_password(_p),
        full_name=_name,
        role=_role,
        organization=_org,
    )


# ── Active sessions ─────────────────────────────────────────

_sessions: dict[str, AuthSession] = {}

SESSION_TTL = 8 * 3600  # 8 hours


def login(username: str, password: str) -> Optional[AuthSession]:
    """Validate credentials and create a session. Returns None on failure."""
    user = _AUTHORIZED_USERS.get(username.lower().strip())
    if user is None or not user.active:
        logger.warning("Login failed: unknown user %s", username)
        return None

    if not hmac.compare_digest(user.password_hash, _hash_password(password)):
        logger.warning("Login failed: wrong password for %s", username)
        return None

    token = secrets.token_urlsafe(32)
    session = AuthSession(
        token=token,
        username=user.username,
        full_name=user.full_name,
        role=user.role,
        organization=user.organization,
        created_at=time.time(),
    )
    _sessions[token] = session
    logger.info("Login success: %s (%s)", user.full_name, user.role)
    return session


def validate_token(token: str) -> Optional[AuthSession]:
    """Validate a session token. Returns None if invalid or expired."""
    session = _sessions.get(token)
    if session is None:
        return None
    if time.time() - session.created_at > SESSION_TTL:
        _sessions.pop(token, None)
        return None
    return session


def logout(token: str) -> bool:
    """Invalidate a session."""
    return _sessions.pop(token, None) is not None


def get_all_users() -> list[dict]:
    """Return list of all accounts (without passwords)."""
    return [
        {
            "username": u.username,
            "full_name": u.full_name,
            "role": u.role,
            "organization": u.organization,
            "active": u.active,
        }
        for u in _AUTHORIZED_USERS.values()
    ]
