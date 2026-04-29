"""Mapper functions for converting between domain and ORM ApiKey models."""

from __future__ import annotations

from app.domain.entities.api_key import ApiKey as DomainApiKey
from app.infrastructure.database.models import ApiKey as ORMApiKey


def to_domain(orm_key: ORMApiKey) -> DomainApiKey:
    """Convert ORM ApiKey to domain ApiKey entity."""
    return DomainApiKey(
        id=orm_key.id,
        user_id=orm_key.user_id,
        name=orm_key.name,
        prefix=orm_key.prefix,
        hash=orm_key.hash,
        scopes=orm_key.scopes,
        created_at=orm_key.created_at,
        last_used_at=orm_key.last_used_at,
        revoked_at=orm_key.revoked_at,
    )


def to_orm(domain_key: DomainApiKey) -> ORMApiKey:
    """Convert domain ApiKey to ORM ApiKey (id is set by SQLAlchemy on insert)."""
    return ORMApiKey(
        user_id=domain_key.user_id,
        name=domain_key.name,
        prefix=domain_key.prefix,
        hash=domain_key.hash,
        scopes=domain_key.scopes,
        created_at=domain_key.created_at,
        last_used_at=domain_key.last_used_at,
        revoked_at=domain_key.revoked_at,
    )
