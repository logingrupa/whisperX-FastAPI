"""Schemas package for Pydantic models.

This package consolidates all Pydantic schemas for the application.
The original schemas from app/schemas.py are in core_schemas.py,
and WebSocket-specific schemas are in websocket_schemas.py.
"""

# Re-export all core schemas for backward compatibility
from app.schemas.core_schemas import (
    AlignedTranscription,
    AlignmentParams,
    AlignmentSegment,
    ASROptions,
    ComputeType,
    Device,
    DiarizationParams,
    DiarizationSegment,
    DiarizedTranscript,
    InterpolateMethod,
    Metadata,
    Response,
    Result,
    ResultTasks,
    Segment,
    SpeechToTextProcessingParams,
    TaskEnum,
    TaskEventReceived,
    TaskProgress,
    TaskProgressStage,
    TaskSimple,
    TaskStatus,
    TaskType,
    Transcript,
    TranscriptionSegment,
    TranscriptInput,
    VADOptions,
    WhisperModel,
    WhisperModelParams,
    Word,
)

# WebSocket-specific schemas
from app.schemas.websocket_schemas import (
    ErrorMessage,
    HeartbeatMessage,
    ProgressMessage,
    ProgressStage,
)

__all__ = [
    # Core schemas
    "AlignedTranscription",
    "AlignmentParams",
    "AlignmentSegment",
    "ASROptions",
    "ComputeType",
    "Device",
    "DiarizationParams",
    "DiarizationSegment",
    "DiarizedTranscript",
    "InterpolateMethod",
    "Metadata",
    "Response",
    "Result",
    "ResultTasks",
    "Segment",
    "SpeechToTextProcessingParams",
    "TaskEnum",
    "TaskEventReceived",
    "TaskProgress",
    "TaskProgressStage",
    "TaskSimple",
    "TaskStatus",
    "TaskType",
    "Transcript",
    "TranscriptionSegment",
    "TranscriptInput",
    "VADOptions",
    "WhisperModel",
    "WhisperModelParams",
    "Word",
    # WebSocket schemas
    "ProgressStage",
    "ProgressMessage",
    "ErrorMessage",
    "HeartbeatMessage",
]
