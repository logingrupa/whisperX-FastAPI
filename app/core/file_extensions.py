"""Single source of truth for allowed media file extensions.

Both ``app.core.config`` (multipart upload validator) and
``app.core.upload_config`` (streaming/TUS upload validator) import from
this module to guarantee the two validators never drift apart. Keep this
file free of imports from other ``app.core.*`` modules to stay
circular-import safe.
"""

from __future__ import annotations

AUDIO_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".mp3",
        ".wav",
        ".awb",
        ".aac",
        ".ogg",
        ".oga",
        ".m4a",
        ".wma",
        ".amr",
        ".flac",
    }
)

VIDEO_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".mp4",
        ".mov",
        ".avi",
        ".wmv",
        ".mkv",
        ".webm",
    }
)

ALLOWED_EXTENSIONS: frozenset[str] = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS
