"""Lock tests for ``app.core.file_extensions`` (SSOT).

These tests guarantee:
* No drift between the multipart-upload validator (``Config.ALLOWED_EXTENSIONS``)
  and the streaming/TUS validator (``upload_config.ALLOWED_UPLOAD_EXTENSIONS``).
* ``.flac`` and ``.webm`` are accepted — guard against a regression of
  the bug where audio uploads with these extensions were rejected at the
  classic ``/speech-to-text`` endpoint.
"""

from __future__ import annotations

from app.core.config import Config
from app.core.file_extensions import (
    ALLOWED_EXTENSIONS,
    AUDIO_EXTENSIONS,
    VIDEO_EXTENSIONS,
)
from app.core.upload_config import ALLOWED_UPLOAD_EXTENSIONS


def test_flac_is_allowed_audio_extension() -> None:
    """Regression guard — .flac uploads must not be rejected as unsupported."""
    assert ".flac" in AUDIO_EXTENSIONS
    assert ".flac" in ALLOWED_EXTENSIONS
    assert ".flac" in ALLOWED_UPLOAD_EXTENSIONS
    assert ".flac" in Config.ALLOWED_EXTENSIONS


def test_webm_is_allowed_video_extension() -> None:
    assert ".webm" in VIDEO_EXTENSIONS
    assert ".webm" in ALLOWED_EXTENSIONS
    assert ".webm" in ALLOWED_UPLOAD_EXTENSIONS
    assert ".webm" in Config.ALLOWED_EXTENSIONS


def test_audio_and_video_sets_disjoint() -> None:
    assert AUDIO_EXTENSIONS.isdisjoint(VIDEO_EXTENSIONS)


def test_allowed_is_union_of_audio_and_video() -> None:
    assert ALLOWED_EXTENSIONS == AUDIO_EXTENSIONS | VIDEO_EXTENSIONS


def test_upload_validator_matches_multipart_validator() -> None:
    """SSOT contract — drift between the two validators must fail CI."""
    assert ALLOWED_UPLOAD_EXTENSIONS == set(ALLOWED_EXTENSIONS)
    assert Config.ALLOWED_EXTENSIONS == set(ALLOWED_EXTENSIONS)
