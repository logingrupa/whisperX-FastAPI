"""Pydantic schemas for /api/keys/* routes (Phase 13)."""
from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, Field


class CreateKeyRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64, description="User-supplied label")


class CreateKeyResponse(BaseModel):
    """Response on POST /api/keys — `key` field is plaintext shown ONCE.

    After this response is delivered, the plaintext is unrecoverable. Server
    stores only prefix + sha256 hash. To rotate: POST a new key + DELETE old.
    """
    id: int
    name: str
    prefix: str
    key: str = Field(..., description="Plaintext API key (whsk_*) — shown ONCE")
    created_at: datetime
    status: str = "active"


class ListKeyItem(BaseModel):
    """Item in GET /api/keys — no plaintext (plaintext is unrecoverable)."""
    id: int
    name: str
    prefix: str
    created_at: datetime
    last_used_at: datetime | None = None
    status: str  # "active" | "revoked"
