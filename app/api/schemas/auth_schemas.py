"""Pydantic v2 schemas for ``/auth/*`` routes (Phase 13).

Single source of truth for register/login DTOs and the post-auth response
shape. Routes import these names directly — never duplicate field
definitions inline.
"""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    """POST /auth/register body."""

    email: EmailStr = Field(
        ..., description="User email (unique identifier)"
    )
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Plain password (Argon2id-hashed server-side)",
    )


class LoginRequest(BaseModel):
    """POST /auth/login body."""

    email: EmailStr = Field(..., description="User email")
    password: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Plain password",
    )


class AuthResponse(BaseModel):
    """Body returned by both register and login (cookies carry the session)."""

    user_id: int
    plan_tier: str
