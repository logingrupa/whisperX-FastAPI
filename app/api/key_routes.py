"""API key management routes — POST/GET/DELETE /api/keys (Phase 13).

Per CONTEXT §80-84:
  - POST: returns plaintext exactly once (KEY-04)
  - GET:  list active+revoked keys with no plaintext
  - DELETE: soft-delete (revoked_at = now); cross-user → 404 opaque
  - Multiple active keys allowed (KEY-06)
  - First-key creation starts trial countdown (RATE-08)
"""
from __future__ import annotations
import logging
from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.dependencies import (
    get_authenticated_user,
    get_auth_service,
    get_key_service,
)
from app.api.schemas.key_schemas import (
    CreateKeyRequest,
    CreateKeyResponse,
    ListKeyItem,
)
from app.domain.entities.user import User
from app.services.auth import AuthService, KeyService

logger = logging.getLogger(__name__)

key_router = APIRouter(prefix="/api/keys", tags=["API Keys"])


def _to_list_item(api_key) -> ListKeyItem:
    return ListKeyItem(
        id=int(api_key.id),
        name=api_key.name,
        prefix=api_key.prefix,
        created_at=api_key.created_at,
        last_used_at=api_key.last_used_at,
        status="active" if api_key.is_active() else "revoked",
    )


@key_router.post("", status_code=status.HTTP_201_CREATED, response_model=CreateKeyResponse)
async def create_key(
    body: CreateKeyRequest,
    user: User = Depends(get_authenticated_user),
    key_service: KeyService = Depends(get_key_service),
    auth_service: AuthService = Depends(get_auth_service),
) -> CreateKeyResponse:
    """Create a new API key. Plaintext shown ONCE."""
    plaintext, api_key = key_service.create_key(int(user.id), body.name)
    # RATE-08: start trial on first key creation
    all_keys = key_service.list_for_user(int(user.id))
    auth_service.start_trial_if_first_key(int(user.id), len(all_keys))
    return CreateKeyResponse(
        id=int(api_key.id),
        name=api_key.name,
        prefix=api_key.prefix,
        key=plaintext,
        created_at=api_key.created_at,
        status="active",
    )


@key_router.get("", response_model=list[ListKeyItem])
async def list_keys(
    user: User = Depends(get_authenticated_user),
    key_service: KeyService = Depends(get_key_service),
) -> list[ListKeyItem]:
    """List all keys (active + revoked) for the authenticated user."""
    keys = key_service.list_for_user(int(user.id))
    return [_to_list_item(k) for k in keys]


@key_router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_key(
    key_id: int,
    user: User = Depends(get_authenticated_user),
    key_service: KeyService = Depends(get_key_service),
) -> Response:
    """Soft-delete (revoke) an API key. Cross-user requests return 404 opaque."""
    # Cross-user check: list user's keys, scope to this id
    owned = next((k for k in key_service.list_for_user(int(user.id)) if int(k.id) == key_id), None)
    if owned is None:
        # Either doesn't exist OR belongs to another user — opaque 404 (no enumeration)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key not found")
    key_service.revoke_key(key_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
