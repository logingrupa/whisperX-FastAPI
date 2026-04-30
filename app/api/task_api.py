"""This module contains the task management routes for the FastAPI application."""

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_scoped_task_management_service
from app.api.mappers.task_mapper import TaskMapper
from app.api.schemas.task_schemas import TaskListResponse
from app.core.exceptions import TaskNotFoundError
from app.core.logging import logger
from app.schemas import Metadata, Response, Result, TaskProgress
from app.services.task_management_service import TaskManagementService

task_router = APIRouter()


@task_router.get("/task/all", tags=["Tasks Management"])
async def get_all_tasks_status(
    q: str | None = Query(
        None,
        description="Substring match against file_name (case-insensitive)",
        max_length=200,
    ),
    status: str | None = Query(
        None,
        description="Filter by task status (processing|completed|failed)",
        max_length=32,
    ),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(
        50, ge=1, le=200, description="Items per page (1..200)"
    ),
    service: TaskManagementService = Depends(get_scoped_task_management_service),
) -> TaskListResponse:
    """
    Retrieve a paginated, optionally filtered list of tasks (Plan 15-ux).

    Pagination + search is server-side so the queue can scale beyond a few
    hundred rows without dragging the whole table to the browser. The
    user-scope filter (Phase 13-07) still applies — callers see only their
    own tasks.

    Args:
        q: Case-insensitive substring match against file_name.
        status: Exact-match status filter (processing|completed|failed).
        page: 1-indexed page number; Pydantic ``ge=1`` rejects 0/negatives.
        page_size: Items per page, 1..200; out-of-range -> 422.
        service: Task management service dependency (scoped to caller).

    Returns:
        TaskListResponse: ``{tasks, total, page, page_size}``.
    """
    logger.info(
        "Retrieving tasks: q=%s status=%s page=%d page_size=%d",
        q,
        status,
        page,
        page_size,
    )
    tasks, total = service.list_tasks_paginated(
        q=q, status=status, page=page, page_size=page_size
    )
    task_summaries = [TaskMapper.to_summary(task) for task in tasks]
    return TaskListResponse(
        tasks=task_summaries, total=total, page=page, page_size=page_size
    )


@task_router.get("/task/{identifier}", tags=["Tasks Management"])
async def get_transcription_status(
    identifier: str,
    service: TaskManagementService = Depends(get_scoped_task_management_service),
) -> Result:
    """
    Retrieve the status of a specific task by its identifier.

    Args:
        identifier (str): The identifier of the task.
        service: Task management service dependency.

    Returns:
        Result: The status of the task.

    Raises:
        TaskNotFoundError: If the identifier is not found.
    """
    logger.info("Retrieving status for task ID: %s", identifier)
    task = service.get_task(identifier)

    if task is None:
        logger.error("Task ID not found: %s", identifier)
        raise TaskNotFoundError(identifier)

    logger.info("Status retrieved for task ID: %s", identifier)
    return Result(
        status=task.status,
        result=task.result,
        metadata=Metadata(
            task_type=task.task_type,
            task_params=task.task_params,
            language=task.language,
            file_name=task.file_name,
            url=task.url,
            callback_url=task.callback_url,
            duration=task.duration,
            audio_duration=task.audio_duration,
            start_time=task.start_time,
            end_time=task.end_time,
        ),
        error=task.error,
    )


@task_router.delete("/task/{identifier}/delete", tags=["Tasks Management"])
async def delete_task(
    identifier: str,
    service: TaskManagementService = Depends(get_scoped_task_management_service),
) -> Response:
    """
    Delete a specific task by its identifier.

    Args:
        identifier (str): The identifier of the task.
        service: Task management service dependency.

    Returns:
        Response: Confirmation message of task deletion.

    Raises:
        TaskNotFoundError: If the task is not found.
    """
    logger.info("Deleting task ID: %s", identifier)
    if service.delete_task(identifier):
        logger.info("Task deleted: ID %s", identifier)
        return Response(identifier=identifier, message="Task deleted")
    else:
        logger.error("Task not found: ID %s", identifier)
        raise TaskNotFoundError(identifier)


@task_router.get(
    "/tasks/{identifier}/progress",
    response_model=TaskProgress,
    tags=["Tasks Management"],
    summary="Get task progress",
    description="Get current progress for a task. Use this as fallback when WebSocket is unavailable.",
)
async def get_task_progress(
    identifier: str,
    service: TaskManagementService = Depends(get_scoped_task_management_service),
) -> TaskProgress:
    """
    Get current progress for a task.

    Returns progress percentage, current stage, and status.
    Use this endpoint as fallback when WebSocket connection fails.

    Args:
        identifier: The task identifier (UUID)
        service: Task management service (injected)

    Returns:
        TaskProgress with current progress information

    Raises:
        TaskNotFoundError: If task with identifier doesn't exist
    """
    logger.info("Retrieving progress for task ID: %s", identifier)
    task = service.get_task(identifier)

    if task is None:
        logger.error("Task ID not found: %s", identifier)
        raise TaskNotFoundError(identifier)

    return TaskProgress(
        identifier=task.uuid,
        status=task.status,
        progress_percentage=task.progress_percentage or 0,
        progress_stage=task.progress_stage,
        error=task.error,
    )
