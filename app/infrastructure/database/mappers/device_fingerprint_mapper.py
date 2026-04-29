"""Mapper functions for converting between domain and ORM DeviceFingerprint models."""

from __future__ import annotations

from app.domain.entities.device_fingerprint import DeviceFingerprint as DomainFp
from app.infrastructure.database.models import DeviceFingerprint as ORMFp


def to_domain(orm_fp: ORMFp) -> DomainFp:
    """Convert ORM DeviceFingerprint to domain DeviceFingerprint entity."""
    return DomainFp(
        id=orm_fp.id,
        user_id=orm_fp.user_id,
        cookie_hash=orm_fp.cookie_hash,
        ua_hash=orm_fp.ua_hash,
        ip_subnet=orm_fp.ip_subnet,
        device_id=orm_fp.device_id,
        created_at=orm_fp.created_at,
    )


def to_orm(domain_fp: DomainFp) -> ORMFp:
    """Convert domain DeviceFingerprint to ORM DeviceFingerprint."""
    return ORMFp(
        user_id=domain_fp.user_id,
        cookie_hash=domain_fp.cookie_hash,
        ua_hash=domain_fp.ua_hash,
        ip_subnet=domain_fp.ip_subnet,
        device_id=domain_fp.device_id,
        created_at=domain_fp.created_at,
    )
