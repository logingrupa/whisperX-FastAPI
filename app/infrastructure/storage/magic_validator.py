"""Magic byte validation for uploaded files."""

from pathlib import Path
from typing import Optional

import puremagic

from app.core.logging import logger

# Map of magic byte detected extensions to our allowed canonical extensions
# puremagic may return variants (.oga, .ogv, .mkv) that we normalize
MAGIC_TO_CANONICAL: dict[str, str] = {
    # Audio formats
    ".mp3": ".mp3",
    ".wav": ".wav",
    ".aac": ".aac",
    ".ogg": ".ogg",
    ".oga": ".ogg",  # OGG audio variant
    ".m4a": ".m4a",
    ".wma": ".wma",
    ".amr": ".amr",
    ".flac": ".flac",
    ".awb": ".awb",
    # Video formats
    ".mp4": ".mp4",
    ".m4v": ".mp4",  # MPEG-4 video variant
    ".mov": ".mov",
    ".qt": ".mov",  # QuickTime variant
    ".avi": ".avi",
    ".wmv": ".wmv",
    ".mkv": ".mkv",
    ".webm": ".webm",
    ".ogv": ".webm",  # OGG video -> treat as webm family
}

# Extensions we accept (must match upload_config.ALLOWED_UPLOAD_EXTENSIONS)
ALLOWED_MAGIC_EXTENSIONS = set(MAGIC_TO_CANONICAL.values())


def get_file_type_from_magic(file_header: bytes) -> Optional[str]:
    """
    Detect file type from magic bytes.

    Args:
        file_header: First 2048+ bytes of the file

    Returns:
        Canonical extension (e.g., ".mp3") if detected and allowed, None otherwise
    """
    if not file_header:
        return None

    try:
        results = puremagic.magic_string(file_header)
        if not results:
            logger.debug("No magic byte match found")
            return None

        # Results are sorted by confidence (highest first)
        for result in results:
            extension = result.extension.lower()
            if not extension.startswith("."):
                extension = f".{extension}"

            # Check if this is a known type
            canonical = MAGIC_TO_CANONICAL.get(extension)
            if canonical:
                logger.debug(
                    "Magic byte detection: %s -> %s (mime: %s)",
                    extension,
                    canonical,
                    result.mime_type,
                )
                return canonical

        # Log what we found but couldn't match
        logger.debug(
            "Magic bytes found non-audio/video type: %s",
            [r.extension for r in results[:3]],
        )
        return None

    except Exception as error:
        logger.warning("Magic byte detection failed: %s", error)
        return None


def validate_magic_bytes(
    file_path: Path,
    claimed_extension: str,
) -> tuple[bool, str, Optional[str]]:
    """
    Validate that file's magic bytes match claimed extension.

    Args:
        file_path: Path to the file to validate
        claimed_extension: The extension claimed by the upload (e.g., ".mp3")

    Returns:
        Tuple of (is_valid, message, detected_type)
        - is_valid: True if magic matches claimed extension
        - message: Human-readable result message
        - detected_type: The detected file type or None
    """
    # Read file header for magic detection
    try:
        with open(file_path, "rb") as file_handle:
            header = file_handle.read(8192)  # Read 8KB for reliable detection
    except OSError as error:
        return False, f"Could not read file: {error}", None

    if not header:
        return False, "File is empty", None

    # Detect actual type
    detected_type = get_file_type_from_magic(header)

    if detected_type is None:
        return (
            False,
            "Unknown file format. Expected audio/video file, got unrecognized format.",
            None,
        )

    # Normalize claimed extension
    claimed_normalized = claimed_extension.lower()
    if not claimed_normalized.startswith("."):
        claimed_normalized = f".{claimed_normalized}"

    # Get canonical form of claimed extension
    claimed_canonical = MAGIC_TO_CANONICAL.get(claimed_normalized, claimed_normalized)

    # Compare canonical forms
    if detected_type == claimed_canonical:
        return True, f"Valid {detected_type} file", detected_type

    # Extension mismatch - possible spoofing attempt
    return (
        False,
        f"File format mismatch: claimed {claimed_extension} but detected {detected_type}",
        detected_type,
    )


def validate_magic_bytes_from_header(
    header: bytes,
    claimed_extension: str,
) -> tuple[bool, str, Optional[str]]:
    """
    Validate magic bytes from raw header bytes (for in-stream validation).

    Args:
        header: First bytes of the file (minimum 2048 recommended)
        claimed_extension: The extension claimed by the upload

    Returns:
        Tuple of (is_valid, message, detected_type)
    """
    if not header:
        return False, "No data to validate", None

    detected_type = get_file_type_from_magic(header)

    if detected_type is None:
        return (
            False,
            "Unknown file format. Expected audio/video file.",
            None,
        )

    # Normalize and compare
    claimed_normalized = claimed_extension.lower()
    if not claimed_normalized.startswith("."):
        claimed_normalized = f".{claimed_normalized}"

    claimed_canonical = MAGIC_TO_CANONICAL.get(claimed_normalized, claimed_normalized)

    if detected_type == claimed_canonical:
        return True, f"Valid {detected_type} file", detected_type

    return (
        False,
        f"File format mismatch: claimed {claimed_extension} but detected {detected_type}",
        detected_type,
    )
