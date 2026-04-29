"""Exception handlers for FastAPI application.

This module defines handlers that map domain exceptions to HTTP responses,
ensuring consistent error formatting and proper separation of concerns.
"""

import logging
import uuid

from fastapi import Request, status
from fastapi.responses import JSONResponse

from app.core.exceptions import (
    ConcurrencyLimitError,
    DomainError,
    FreeTierViolationError,
    InfrastructureError,
    InvalidCredentialsError,
    RateLimitExceededError,
    TaskNotFoundError,
    TrialExpiredError,
    ValidationError,
)

logger = logging.getLogger(__name__)


async def domain_error_handler(
    request: Request, exc: DomainError | Exception
) -> JSONResponse:
    """Handle domain errors (business logic violations).

    Domain errors typically indicate that a business rule was violated or
    a domain operation cannot be completed. These map to HTTP 400 Bad Request.

    Args:
        request: FastAPI request object
        exc: Domain error exception

    Returns:
        JSONResponse with error details and HTTP 400 status
    """
    # Cast to DomainError since we know it will be that type
    domain_exc = exc if isinstance(exc, DomainError) else DomainError(str(exc))

    logger.warning(
        "Domain error: %s",
        domain_exc.message,
        extra={
            "correlation_id": domain_exc.correlation_id,
            "code": domain_exc.code,
            "path": request.url.path,
        },
    )

    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST, content=domain_exc.to_dict()
    )


async def validation_error_handler(
    request: Request, exc: ValidationError | Exception
) -> JSONResponse:
    """Handle validation errors.

    Validation errors indicate that user input failed validation rules.
    These map to HTTP 422 Unprocessable Entity.

    Args:
        request: FastAPI request object
        exc: Validation error exception

    Returns:
        JSONResponse with error details and HTTP 422 status
    """
    # Cast to ValidationError since we know it will be that type
    val_exc = exc if isinstance(exc, ValidationError) else ValidationError(str(exc))

    logger.info(
        "Validation error: %s",
        val_exc.message,
        extra={"correlation_id": val_exc.correlation_id, "path": request.url.path},
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=val_exc.to_dict()
    )


async def task_not_found_handler(
    request: Request, exc: TaskNotFoundError | Exception
) -> JSONResponse:
    """Handle task not found errors.

    Task not found errors indicate that a requested task doesn't exist.
    These map to HTTP 404 Not Found.

    Args:
        request: FastAPI request object
        exc: Task not found error exception

    Returns:
        JSONResponse with error details and HTTP 404 status
    """
    # Cast to TaskNotFoundError since we know it will be that type
    task_exc = (
        exc if isinstance(exc, TaskNotFoundError) else TaskNotFoundError("unknown")
    )

    logger.info(
        "Task not found: %s",
        task_exc.details.get("identifier"),
        extra={"correlation_id": task_exc.correlation_id, "path": request.url.path},
    )

    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND, content=task_exc.to_dict()
    )


async def infrastructure_error_handler(
    request: Request, exc: InfrastructureError | Exception
) -> JSONResponse:
    """Handle infrastructure errors (external system failures).

    Infrastructure errors indicate that an external dependency has failed.
    These map to HTTP 503 Service Unavailable. Internal details are hidden
    from users for security, but logged for debugging.

    Args:
        request: FastAPI request object
        exc: Infrastructure error exception

    Returns:
        JSONResponse with error details and HTTP 503 status
    """
    # Cast to InfrastructureError since we know it will be that type
    infra_exc = (
        exc if isinstance(exc, InfrastructureError) else InfrastructureError(str(exc))
    )

    logger.error(
        "Infrastructure error: %s",
        infra_exc.message,
        extra={
            "correlation_id": infra_exc.correlation_id,
            "code": infra_exc.code,
            "path": request.url.path,
        },
        exc_info=True,
    )

    # Don't expose internal details to users
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "error": {
                "message": "A temporary system error occurred. Please try again later.",
                "code": infra_exc.code,
                "correlation_id": infra_exc.correlation_id,
            }
        },
    )


async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected errors.

    This is a catch-all handler for exceptions that don't match other handlers.
    These map to HTTP 500 Internal Server Error. Full details are logged but
    only a generic message is shown to users.

    Args:
        request: FastAPI request object
        exc: Exception that was raised

    Returns:
        JSONResponse with generic error message and HTTP 500 status
    """
    correlation_id = str(uuid.uuid4())

    logger.error(
        "Unexpected error: %s",
        str(exc),
        extra={"correlation_id": correlation_id, "path": request.url.path},
        exc_info=True,
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "message": "An unexpected error occurred. Please contact support if the problem persists.",
                "code": "INTERNAL_ERROR",
                "correlation_id": correlation_id,
            }
        },
    )


async def invalid_credentials_handler(
    request: Request, exc: InvalidCredentialsError | Exception
) -> JSONResponse:
    """Map InvalidCredentialsError -> HTTP 401 (Phase 13 / AUTH-03).

    Generic 401 body — anti-enumeration: identical shape on either
    wrong-email or wrong-password (T-13-10). Registered alongside
    DualAuthMiddleware in plan 13-09.
    """
    ic_exc = (
        exc if isinstance(exc, InvalidCredentialsError) else InvalidCredentialsError()
    )

    logger.info(
        "Authentication failed: invalid_credentials",
        extra={"correlation_id": ic_exc.correlation_id, "path": request.url.path},
    )

    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED, content=ic_exc.to_dict()
    )


# ---------------------------------------------------------------------------
# Phase 13-08 — free-tier gate / billing handlers (RATE-01..12, BILL-01).
# Registration in app/main.py wiring (plan 13-09).
# ---------------------------------------------------------------------------


async def trial_expired_handler(
    request: Request, exc: TrialExpiredError | Exception
) -> JSONResponse:
    """Map TrialExpiredError -> HTTP 402 Payment Required (RATE-09)."""
    te_exc = exc if isinstance(exc, TrialExpiredError) else TrialExpiredError()
    logger.info(
        "Trial expired",
        extra={"correlation_id": te_exc.correlation_id, "path": request.url.path},
    )
    return JSONResponse(
        status_code=status.HTTP_402_PAYMENT_REQUIRED, content=te_exc.to_dict()
    )


async def free_tier_violation_handler(
    request: Request, exc: FreeTierViolationError | Exception
) -> JSONResponse:
    """Map FreeTierViolationError -> HTTP 403 Forbidden.

    Covers model rejection, file-too-long, diarize-not-allowed.
    """
    ft_exc = (
        exc
        if isinstance(exc, FreeTierViolationError)
        else FreeTierViolationError("violation")
    )
    logger.info(
        "Free-tier violation: %s",
        ft_exc.details.get("reason", ""),
        extra={"correlation_id": ft_exc.correlation_id, "path": request.url.path},
    )
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN, content=ft_exc.to_dict()
    )


async def rate_limit_exceeded_handler(
    request: Request, exc: RateLimitExceededError | Exception
) -> JSONResponse:
    """Map RateLimitExceededError -> HTTP 429 + Retry-After header (RATE-12)."""
    rl_exc = (
        exc
        if isinstance(exc, RateLimitExceededError)
        else RateLimitExceededError("unknown", 60)
    )
    retry_after = int(rl_exc.details.get("retry_after_seconds", 60))
    logger.info(
        "Rate limit exceeded",
        extra={"correlation_id": rl_exc.correlation_id, "path": request.url.path},
    )
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content=rl_exc.to_dict(),
        headers={"Retry-After": str(retry_after)},
    )


async def concurrency_limit_handler(
    request: Request, exc: ConcurrencyLimitError | Exception
) -> JSONResponse:
    """Map ConcurrencyLimitError -> HTTP 429 + Retry-After header (W1)."""
    cl_exc = (
        exc if isinstance(exc, ConcurrencyLimitError) else ConcurrencyLimitError()
    )
    retry_after = int(cl_exc.details.get("retry_after_seconds", 60))
    logger.info(
        "Concurrency limit reached",
        extra={"correlation_id": cl_exc.correlation_id, "path": request.url.path},
    )
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content=cl_exc.to_dict(),
        headers={"Retry-After": str(retry_after)},
    )
