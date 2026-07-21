"""Windows DLL search-path registration for native deps (torchcodec/FFmpeg).

Since Python 3.8, Windows no longer resolves ctypes/extension-module DLL
dependencies from PATH — torchcodec's decoder cannot find the FFmpeg shared
DLLs (avcodec/avformat/avutil) even when the launcher prepends FFMPEG_DIR to
PATH. `os.add_dll_directory` is the supported mechanism.

Must run BEFORE any import that transitively pulls in torchcodec (whisperx).
"""

from __future__ import annotations

import os
import sys


def register_ffmpeg_dll_dir() -> None:
    """Register FFMPEG_DIR with the Windows DLL loader (no-op elsewhere)."""
    if sys.platform != "win32":
        return

    ffmpeg_dir = os.environ.get("FFMPEG_DIR", "")
    if not ffmpeg_dir or not os.path.isdir(ffmpeg_dir):
        return

    os.add_dll_directory(ffmpeg_dir)
