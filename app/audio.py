"""This module provides functions for processing audio files."""

import json
import os
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import numpy as np
from whisperx import load_audio
from whisperx.audio import SAMPLE_RATE

from app.core.exceptions import (
    AudioProcessingError,
    FileValidationError,
    InfrastructureError,
)
from app.core.logging import logger
from app.files import VIDEO_EXTENSIONS, check_file_extension

FFPROBE_TIMEOUT_SECONDS = 60
BITRATE_ESTIMATE_WARNING = "Estimating duration from bitrate"
# With a second stream present these containers misstate the audio length:
# ASF reports every stream at the file's length, and ffprobe fills Matroska
# audio from the container while its DURATION tag can be off by a late start.
MULTI_STREAM_DECODE_FAMILIES = ("asf", "matroska")


@lru_cache(maxsize=1)
def _ffmpeg_path() -> str | None:
    """Resolve ffmpeg executable.

    Resolution order: env var FFMPEG_BINARY (absolute path) → PATH lookup.
    Side effect: when FFMPEG_BINARY resolves, prepend its directory to
    os.environ["PATH"] so subprocesses spawned by third-party libs
    (whisperx.audio.load_audio) that hardcode bare "ffmpeg" also resolve.
    """
    env_binary = os.environ.get("FFMPEG_BINARY", "").strip()
    if env_binary and Path(env_binary).is_file():
        bin_dir = str(Path(env_binary).parent)
        current_path = os.environ.get("PATH", "")
        if bin_dir not in current_path.split(os.pathsep):
            os.environ["PATH"] = bin_dir + os.pathsep + current_path
        return env_binary
    return shutil.which("ffmpeg")


def _require_ffmpeg() -> None:
    if _ffmpeg_path() is None:
        raise InfrastructureError(
            "ffmpeg binary not found; set FFMPEG_BINARY in .env or install ffmpeg on PATH and restart the server",
            code="FFMPEG_MISSING",
        )


def convert_video_to_audio(file: str) -> str:
    """
    Convert a video file to an audio file.

    Args:
        file (str): The path to the video file.

    Returns:
        str: The path to the audio file.
    """
    _require_ffmpeg()
    temp_filename = NamedTemporaryFile(delete=False).name
    subprocess.call(
        [
            "ffmpeg",
            "-y",  # Overwrite output file if it exists"
            "-i",
            file,
            "-vn",
            "-ac",
            "1",  # Mono audio
            "-ar",
            "16000",  # Sample rate of 16kHz
            "-f",
            "wav",  # Output format WAV
            temp_filename,
        ]
    )
    return temp_filename


def process_audio_file(audio_file: str) -> np.ndarray[Any, np.dtype[np.float32]]:
    """
    Check file if it is audio file, if it is video file, convert it to audio file.

    Args:
        audio_file (str): The path to the audio file.
    Returns:
        Audio: The processed audio.
    """
    _require_ffmpeg()
    file_extension = check_file_extension(audio_file)
    if file_extension in VIDEO_EXTENSIONS:
        audio_file = convert_video_to_audio(audio_file)
    return load_audio(audio_file)  # type: ignore[no-any-return]


def get_audio_duration(audio: np.ndarray[Any, np.dtype[np.float32]]) -> float:
    """
    Get the duration of the audio file.

    Args:
        audio_file (str): The path to the audio file.
    Returns:
        float: The duration of the audio file.
    """
    return len(audio) / SAMPLE_RATE  # type: ignore[no-any-return]


def _ffprobe_path() -> str:
    """Resolve ffprobe: the sibling of the resolved ffmpeg, else PATH."""
    ffmpeg_path = _ffmpeg_path()
    if ffmpeg_path is not None:
        sibling = Path(ffmpeg_path).with_name("ffprobe" + Path(ffmpeg_path).suffix)
        if sibling.is_file():
            return str(sibling)
    ffprobe_on_path = shutil.which("ffprobe")
    if ffprobe_on_path is None:
        raise InfrastructureError(
            "ffprobe binary not found next to ffmpeg or on PATH",
            code="FFPROBE_MISSING",
        )
    return ffprobe_on_path


def _positive_seconds(reported: str | None) -> float | None:
    """Positive seconds from an ffprobe duration field, else None ("N/A", absent)."""
    if reported is None:
        return None
    try:
        seconds = float(reported)
    except ValueError:
        return None
    return seconds if seconds > 0 else None


def _tagged_seconds(stream_tags: dict[str, str], start_seconds: float) -> float | None:
    """Matroska/WebM track length from its ``DURATION`` tag, else None.

    The tag (``HH:MM:SS.fffffffff``) is the track's END time, so a track that
    starts late is measured from its own start.
    """
    tagged = stream_tags.get("DURATION") or stream_tags.get("DURATION-eng")
    if tagged is None:
        return None
    try:
        hours, minutes, seconds = tagged.split(":")
        end_seconds = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    except ValueError:
        return None
    track_seconds = end_seconds - start_seconds
    return track_seconds if track_seconds > 0 else None


def _single_stream_container_seconds(container: dict[str, Any]) -> float | None:
    """Container duration, trusted only when the audio is the file's only stream."""
    if int(container.get("nb_streams", 0)) != 1:
        return None
    return _positive_seconds(container.get("duration"))


def _exact_probed_duration(
    audio_file: str, completed: subprocess.CompletedProcess[str]
) -> float | None:
    """Audio-stream seconds from ffprobe's JSON, or None when only a decode can tell."""
    if completed.returncode != 0 or BITRATE_ESTIMATE_WARNING in completed.stderr:
        return None
    report = json.loads(completed.stdout)
    audio_streams = report.get("streams", [])
    if not audio_streams:
        raise FileValidationError(
            filename=Path(audio_file).name, reason="the file has no audio track"
        )
    container = report.get("format", {})
    container_family = str(container.get("format_name", "")).split(",")[0]
    if container_family in MULTI_STREAM_DECODE_FAMILIES and int(container.get("nb_streams", 1)) > 1:
        return None
    audio_stream = audio_streams[0]
    # Matroska stores no per-stream duration; ffprobe fills in the container's.
    stream_seconds = (
        None if container_family == "matroska" else _positive_seconds(audio_stream.get("duration"))
    )
    start_seconds = _positive_seconds(audio_stream.get("start_time")) or 0.0
    return (
        stream_seconds
        or _tagged_seconds(audio_stream.get("tags", {}), start_seconds)
        or _single_stream_container_seconds(container)
    )


def probe_audio_duration(audio_file: str) -> float:
    """
    Read the audio stream's duration from the container, without decoding.

    Request handlers gate on duration and leave the decode to the background
    job. Uses the audio stream's own duration (or its Matroska DURATION tag);
    the container's duration only when the audio is the file's only stream,
    because a video's container length can exceed its audio. Falls back to a
    full decode when ffprobe has no exact figure: none reported, one it
    estimated from the bitrate (ADTS aac, VBR mp3 without a Xing header), or
    a multi-stream ASF or Matroska file.

    Args:
        audio_file (str): The path to the audio or video file.
    Returns:
        float: The duration in seconds.
    Raises:
        FileNotFoundError: The file does not exist.
        FileValidationError: The file has no audio track.
    """
    if not Path(audio_file).is_file():
        raise FileNotFoundError(f"Audio file not found: {audio_file}")
    completed = subprocess.run(
        [
            _ffprobe_path(),
            "-v",
            "warning",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=duration,start_time:stream_tags:format=duration,nb_streams,format_name",
            "-of",
            "json",
            audio_file,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=FFPROBE_TIMEOUT_SECONDS,
        check=False,
    )
    probed_duration = _exact_probed_duration(audio_file, completed)
    if probed_duration is not None:
        return probed_duration
    logger.warning(
        "ffprobe gave no exact duration for %s (exit %d); decoding to measure it",
        audio_file,
        completed.returncode,
    )
    return get_audio_duration(process_audio_file(audio_file))


def decode_saved_upload(audio_file: str) -> np.ndarray[Any, np.dtype[np.float32]]:
    """
    Decode a saved upload inside a background job.

    ffmpeg failures surface as AudioProcessingError, not RuntimeError: the
    workers' CUDA-error check matches "cuda" in RuntimeError text, and the
    ffmpeg banner in load_audio's message carries "--enable-cuda-llvm".

    Args:
        audio_file (str): The saved upload.
    Returns:
        Audio: The decoded 16 kHz mono waveform.
    """
    try:
        return process_audio_file(audio_file)
    except RuntimeError as error:
        raise AudioProcessingError(
            reason=f"could not decode {Path(audio_file).name}", original_error=error
        ) from error
