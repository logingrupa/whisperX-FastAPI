"""Mapper functions for converting between domain and ORM models."""

from typing import Any

from app.domain.entities.task import Task as DomainTask
from app.infrastructure.database.models import Task as ORMTask


def to_domain(orm_task: ORMTask) -> DomainTask:
    """
    Convert an ORM Task model to a domain Task entity.

    Args:
        orm_task: The SQLAlchemy ORM Task model

    Returns:
        DomainTask: The domain Task entity
    """
    return _build_domain_task(orm_task, result=orm_task.result)


def to_domain_without_result(orm_task: ORMTask) -> DomainTask:
    """
    Convert an ORM Task loaded with ``result`` deferred (list views).

    ``result`` holds the full transcript (up to several MB per row) and is
    never read here, so the deferred column is not loaded.

    Args:
        orm_task: The SQLAlchemy ORM Task model

    Returns:
        DomainTask: The domain Task entity with ``result=None``
    """
    return _build_domain_task(orm_task, result=None)


def _build_domain_task(orm_task: ORMTask, result: dict[str, Any] | None) -> DomainTask:
    """Copy every non-result column of ``orm_task`` into a domain Task."""
    return DomainTask(
        uuid=orm_task.uuid,
        status=orm_task.status,
        task_type=orm_task.task_type,
        result=result,
        file_name=orm_task.file_name,
        url=orm_task.url,
        callback_url=orm_task.callback_url,
        audio_duration=orm_task.audio_duration,
        language=orm_task.language,
        task_params=orm_task.task_params,
        duration=orm_task.duration,
        start_time=orm_task.start_time,
        end_time=orm_task.end_time,
        error=orm_task.error,
        created_at=orm_task.created_at,
        updated_at=orm_task.updated_at,
        progress_percentage=orm_task.progress_percentage,
        progress_stage=orm_task.progress_stage,
        user_id=orm_task.user_id,
        api_key_id=orm_task.api_key_id,
        submission_key=orm_task.submission_key,
    )


def to_orm(domain_task: DomainTask) -> ORMTask:
    """
    Convert a domain Task entity to an ORM Task model.

    Args:
        domain_task: The domain Task entity

    Returns:
        ORMTask: The SQLAlchemy ORM Task model
    """
    orm_task = ORMTask(
        uuid=domain_task.uuid,
        status=domain_task.status,
        task_type=domain_task.task_type,
        result=domain_task.result,
        file_name=domain_task.file_name,
        url=domain_task.url,
        callback_url=domain_task.callback_url,
        audio_duration=domain_task.audio_duration,
        language=domain_task.language,
        task_params=domain_task.task_params,
        duration=domain_task.duration,
        start_time=domain_task.start_time,
        end_time=domain_task.end_time,
        error=domain_task.error,
        created_at=domain_task.created_at,
        updated_at=domain_task.updated_at,
        progress_percentage=domain_task.progress_percentage,
        progress_stage=domain_task.progress_stage,
        user_id=domain_task.user_id,
        api_key_id=domain_task.api_key_id,
        submission_key=domain_task.submission_key,
    )
    return orm_task
