"""Mapper functions for converting between domain and ORM User models."""

from __future__ import annotations

from app.domain.entities.user import User as DomainUser
from app.infrastructure.database.models import User as ORMUser


def to_domain(orm_user: ORMUser) -> DomainUser:
    """Convert ORM User to domain User entity.

    Args:
        orm_user: SQLAlchemy ORM User row.

    Returns:
        DomainUser: Framework-free domain entity.
    """
    return DomainUser(
        id=orm_user.id,
        email=orm_user.email,
        password_hash=orm_user.password_hash,
        plan_tier=orm_user.plan_tier,
        stripe_customer_id=orm_user.stripe_customer_id,
        token_version=orm_user.token_version,
        trial_started_at=orm_user.trial_started_at,
        created_at=orm_user.created_at,
        updated_at=orm_user.updated_at,
    )


def to_orm(domain_user: DomainUser) -> ORMUser:
    """Convert domain User to ORM User (id is set by SQLAlchemy on insert).

    Args:
        domain_user: Domain User entity.

    Returns:
        ORMUser: SQLAlchemy ORM model instance ready for ``session.add``.
    """
    return ORMUser(
        email=domain_user.email,
        password_hash=domain_user.password_hash,
        plan_tier=domain_user.plan_tier,
        stripe_customer_id=domain_user.stripe_customer_id,
        token_version=domain_user.token_version,
        trial_started_at=domain_user.trial_started_at,
        created_at=domain_user.created_at,
        updated_at=domain_user.updated_at,
    )
