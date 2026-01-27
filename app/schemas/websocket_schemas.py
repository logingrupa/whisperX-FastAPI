"""WebSocket message schemas for real-time task progress updates.

This module defines Pydantic models for WebSocket communication during
long-running transcription operations. The schemas follow the existing
patterns in app/schemas.py with str Enum for string-valued enumerations.
"""

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class ProgressStage(str, Enum):
    """Enum for task progress stages during transcription processing.

    These stages represent the sequential steps in the audio processing pipeline:
    - uploading: File upload in progress
    - queued: Task queued, waiting for processing to begin
    - transcribing: WhisperX transcription in progress
    - aligning: Word-level alignment being performed
    - diarizing: Speaker diarization in progress
    - complete: All processing finished successfully
    """

    uploading = "uploading"
    queued = "queued"
    transcribing = "transcribing"
    aligning = "aligning"
    diarizing = "diarizing"
    complete = "complete"


class ProgressMessage(BaseModel):
    """Progress update message sent to WebSocket clients.

    Sent during task processing to inform connected clients of the current
    stage and completion percentage.

    Attributes:
        type: Message type identifier, always "progress".
        task_id: UUID of the task being processed.
        stage: Current processing stage from ProgressStage enum.
        percentage: Completion percentage (0-100).
        message: Optional descriptive message about current activity.
        timestamp: Server timestamp when this update was generated.
    """

    type: Literal["progress"] = Field(default="progress", description="Message type identifier")
    task_id: str = Field(..., description="UUID of the task being processed")
    stage: ProgressStage = Field(..., description="Current processing stage")
    percentage: int = Field(..., ge=0, le=100, description="Completion percentage (0-100)")
    message: str | None = Field(default=None, description="Optional descriptive message")
    timestamp: datetime = Field(..., description="Server timestamp for this update")


class ErrorMessage(BaseModel):
    """Error message sent to WebSocket clients when processing fails.

    Provides both user-friendly and technical error information for
    debugging and display purposes.

    Attributes:
        type: Message type identifier, always "error".
        task_id: UUID of the task that encountered an error.
        error_code: Machine-readable error code for client handling.
        user_message: Human-readable error message for display.
        technical_detail: Optional technical details for debugging.
        timestamp: Server timestamp when the error occurred.
    """

    type: Literal["error"] = Field(default="error", description="Message type identifier")
    task_id: str = Field(..., description="UUID of the task that failed")
    error_code: str = Field(..., description="Machine-readable error code")
    user_message: str = Field(..., description="Human-readable error message for display")
    technical_detail: str | None = Field(default=None, description="Technical details for debugging")
    timestamp: datetime = Field(..., description="Server timestamp when error occurred")


class HeartbeatMessage(BaseModel):
    """Heartbeat message sent periodically to keep connections alive.

    Sent every 30 seconds to prevent proxy timeouts during long-running
    transcription operations (5-30 minutes).

    Attributes:
        type: Message type identifier, always "heartbeat".
        timestamp: Server timestamp when heartbeat was sent.
    """

    type: Literal["heartbeat"] = Field(default="heartbeat", description="Message type identifier")
    timestamp: datetime = Field(..., description="Server timestamp for heartbeat")
