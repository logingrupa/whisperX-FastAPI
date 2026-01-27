"""Storage infrastructure for file uploads."""

from app.infrastructure.storage.magic_validator import (
    get_file_type_from_magic,
    validate_magic_bytes,
    validate_magic_bytes_from_header,
)
from app.infrastructure.storage.streaming_target import StreamingFileTarget

__all__ = [
    "StreamingFileTarget",
    "get_file_type_from_magic",
    "validate_magic_bytes",
    "validate_magic_bytes_from_header",
]
