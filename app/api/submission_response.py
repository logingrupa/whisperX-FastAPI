"""HTTP reply for a file submit: the queued task, or the in-flight twin it matched."""

from app.api.constants import (
    TASK_ALREADY_QUEUED_MESSAGE,
    TASK_QUEUED_MESSAGE,
    TASK_SCHEDULED_LOG_FORMAT,
)
from app.core.logging import logger
from app.schemas import Response
from app.services.task_submission_service import SubmissionOutcome


def submission_response(outcome: SubmissionOutcome) -> Response:
    """Build the submit reply; logs the scheduling of a new task."""
    if outcome.is_duplicate:
        return Response(
            identifier=outcome.identifier, message=TASK_ALREADY_QUEUED_MESSAGE
        )
    logger.info(TASK_SCHEDULED_LOG_FORMAT, outcome.identifier)
    return Response(identifier=outcome.identifier, message=TASK_QUEUED_MESSAGE)
