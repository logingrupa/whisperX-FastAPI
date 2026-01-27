"""Streaming upload endpoint for large audio/video files."""

import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, status
from streaming_form_data import StreamingFormDataParser
from streaming_form_data.targets import ValueTarget
from streaming_form_data.validators import ValidationError

from app.core.logging import logger
from app.core.upload_config import (
    ALLOWED_UPLOAD_EXTENSIONS,
    MAX_FILE_SIZE,
    UPLOAD_DIR,
)
from app.infrastructure.storage.streaming_target import StreamingFileTarget

streaming_upload_router = APIRouter(prefix="/upload", tags=["Upload"])


@streaming_upload_router.post("/stream")
async def streaming_upload(request: Request) -> dict[str, str | int]:
    """
    Stream large file upload directly to disk.

    This endpoint handles files up to 5GB without loading them into memory.
    The file is streamed directly to disk as chunks arrive.

    Args:
        request: FastAPI Request object for accessing raw stream

    Returns:
        dict with upload_id, filename, and size_bytes

    Raises:
        HTTPException: 400 for invalid content-type or file format
        HTTPException: 413 for files exceeding 5GB limit
    """
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" not in content_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Content-Type must be multipart/form-data",
        )

    # Generate unique upload ID
    upload_id = str(uuid.uuid4())
    temp_path = UPLOAD_DIR / f"{upload_id}.tmp"

    # Ensure upload directory exists
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    # Create streaming parser
    parser = StreamingFormDataParser(headers={"Content-Type": content_type})

    # Register targets for file and optional filename field
    file_target = StreamingFileTarget(temp_path)
    filename_target = ValueTarget()

    parser.register("file", file_target)
    parser.register("filename", filename_target)

    try:
        # Stream chunks directly to parser (and thus to disk)
        async for chunk in request.stream():
            parser.data_received(chunk)

    except ValidationError:
        # Size limit exceeded - clean up partial file
        temp_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size: {MAX_FILE_SIZE / (1024**3):.1f}GB",
        )

    # Get filename from multipart or fallback
    original_filename = file_target.multipart_filename
    if not original_filename:
        # Try the separate filename field
        filename_value = filename_target.value
        if filename_value:
            original_filename = filename_value.decode("utf-8")
        else:
            original_filename = f"{upload_id}.bin"

    # Validate extension
    extension = Path(original_filename).suffix.lower()
    if extension not in ALLOWED_UPLOAD_EXTENSIONS:
        # Clean up the uploaded file
        temp_path.unlink(missing_ok=True)
        allowed_list = ", ".join(sorted(ALLOWED_UPLOAD_EXTENSIONS))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format: {extension}. Allowed: {allowed_list}",
        )

    # Rename temp file with proper extension
    final_path = UPLOAD_DIR / f"{upload_id}{extension}"
    temp_path.rename(final_path)

    logger.info(
        "Streaming upload complete: %s -> %s (%d bytes)",
        original_filename,
        final_path,
        file_target.bytes_written,
    )

    return {
        "upload_id": upload_id,
        "filename": original_filename,
        "size_bytes": file_target.bytes_written,
        "path": str(final_path),
    }
