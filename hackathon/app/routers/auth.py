"""
Authentication endpoints for authorized personnel login.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.auth import login, logout, validate_token

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    full_name: str
    role: str
    organization: str


class ValidateResponse(BaseModel):
    valid: bool
    full_name: str | None = None
    role: str | None = None
    organization: str | None = None


@router.post("/login", response_model=LoginResponse)
async def auth_login(body: LoginRequest):
    """Authenticate an authorized user."""
    session = login(body.username, body.password)
    if session is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials. Access restricted to authorized personnel.",
        )
    return LoginResponse(
        token=session.token,
        full_name=session.full_name,
        role=session.role,
        organization=session.organization,
    )


@router.post("/logout")
async def auth_logout(token: str = ""):
    """Logout and invalidate session."""
    logout(token)
    return {"ok": True}


@router.get("/validate", response_model=ValidateResponse)
async def auth_validate(token: str = ""):
    """Validate a session token."""
    session = validate_token(token)
    if session is None:
        return ValidateResponse(valid=False)
    return ValidateResponse(
        valid=True,
        full_name=session.full_name,
        role=session.role,
        organization=session.organization,
    )
