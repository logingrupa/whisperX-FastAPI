"""Unit tests for the submit-path audio helpers: probe without decode, background decode."""

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from app import audio as audio_module
from app.core.exceptions import AudioProcessingError, FileValidationError, InfrastructureError
from app.infrastructure.ml.model_registry import evict_on_cuda_error

SAMPLE_MP3 = Path(__file__).resolve().parents[1] / "test_files" / "audio_en.mp3"


@pytest.fixture
def upload(tmp_path: Path) -> Path:
    path = tmp_path / "upload.ogg"
    path.write_bytes(b"container bytes")
    return path


def _ffprobe_reporting(
    report: dict[str, Any] | None = None, *, stderr: str = "", returncode: int = 0
) -> Any:
    stdout = json.dumps(report if report is not None else {})

    def run(*_args: Any, **_kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)

    return run


def _decode_must_not_run(_path: str) -> Any:
    raise AssertionError("probe must not decode when ffprobe reports an exact duration")


def _three_second_decode(_path: str) -> Any:
    return np.zeros(audio_module.SAMPLE_RATE * 3, dtype=np.float32)


def _ffmpeg_tools_available() -> bool:
    try:
        audio_module._ffprobe_path()
    except InfrastructureError:
        return False
    return audio_module._ffmpeg_path() is not None


def _ffmpeg(*arguments: str) -> None:
    ffmpeg_path = audio_module._ffmpeg_path()
    assert ffmpeg_path is not None
    subprocess.run(
        [ffmpeg_path, "-v", "error", "-y", *arguments], check=True, capture_output=True
    )


@pytest.fixture
def fake_ffprobe(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setattr(audio_module, "_ffprobe_path", lambda: "ffprobe")

    def install(run: Any, decode: Any = _decode_must_not_run) -> None:
        monkeypatch.setattr(audio_module.subprocess, "run", run)
        monkeypatch.setattr(audio_module, "process_audio_file", decode)

    return install


@pytest.mark.unit
class TestProbeAudioDuration:
    def test_returns_audio_stream_duration_without_decoding(
        self, upload: Path, fake_ffprobe: Any
    ) -> None:
        fake_ffprobe(
            _ffprobe_reporting(
                {"streams": [{"duration": "7131.000000"}], "format": {"duration": "7200.0"}}
            )
        )

        assert audio_module.probe_audio_duration(str(upload)) == pytest.approx(7131.0)

    def test_uses_container_duration_when_audio_is_the_only_stream(
        self, upload: Path, fake_ffprobe: Any
    ) -> None:
        fake_ffprobe(
            _ffprobe_reporting({"streams": [{}], "format": {"duration": "60.5", "nb_streams": 1}})
        )

        assert audio_module.probe_audio_duration(str(upload)) == pytest.approx(60.5)

    def test_audio_only_matroska_uses_its_track_tag_from_its_own_start(
        self, upload: Path, fake_ffprobe: Any
    ) -> None:
        fake_ffprobe(
            _ffprobe_reporting(
                {
                    "streams": [
                        {
                            "duration": "600.0",
                            "start_time": "3.000",
                            "tags": {"DURATION-eng": "00:01:03.023000000"},
                        }
                    ],
                    "format": {"duration": "600.0", "nb_streams": 1, "format_name": "matroska,webm"},
                }
            )
        )

        assert audio_module.probe_audio_duration(str(upload)) == pytest.approx(60.023)

    def test_multi_stream_matroska_is_decoded(self, upload: Path, fake_ffprobe: Any) -> None:
        fake_ffprobe(
            _ffprobe_reporting(
                {
                    "streams": [{"duration": "60.0", "tags": {"DURATION": "00:00:36.023000000"}}],
                    "format": {"duration": "60.0", "nb_streams": 2, "format_name": "matroska,webm"},
                }
            ),
            decode=_three_second_decode,
        )

        assert audio_module.probe_audio_duration(str(upload)) == pytest.approx(3.0)

    def test_video_container_length_is_never_trusted_for_audio(
        self, upload: Path, fake_ffprobe: Any
    ) -> None:
        fake_ffprobe(
            _ffprobe_reporting({"streams": [{}], "format": {"duration": "600.0", "nb_streams": 2}}),
            decode=_three_second_decode,
        )

        assert audio_module.probe_audio_duration(str(upload)) == pytest.approx(3.0)

    def test_multi_stream_asf_is_decoded(self, upload: Path, fake_ffprobe: Any) -> None:
        fake_ffprobe(
            _ffprobe_reporting(
                {
                    "streams": [{"duration": "600.046"}],
                    "format": {"duration": "600.046", "nb_streams": 2, "format_name": "asf"},
                }
            ),
            decode=_three_second_decode,
        )

        assert audio_module.probe_audio_duration(str(upload)) == pytest.approx(3.0)

    def test_bitrate_estimate_falls_back_to_decode(self, upload: Path, fake_ffprobe: Any) -> None:
        fake_ffprobe(
            _ffprobe_reporting(
                {"streams": [{"duration": "2301.6"}], "format": {"duration": "2301.6"}},
                stderr="[aac @ 0x1] Estimating duration from bitrate, this may be inaccurate",
            ),
            decode=_three_second_decode,
        )

        assert audio_module.probe_audio_duration(str(upload)) == pytest.approx(3.0)

    def test_no_duration_anywhere_falls_back_to_decode(
        self, upload: Path, fake_ffprobe: Any
    ) -> None:
        fake_ffprobe(
            _ffprobe_reporting({"streams": [{"duration": "N/A"}], "format": {}}),
            decode=_three_second_decode,
        )

        assert audio_module.probe_audio_duration(str(upload)) == pytest.approx(3.0)

    def test_ffprobe_failure_falls_back_to_decode(self, upload: Path, fake_ffprobe: Any) -> None:
        fake_ffprobe(_ffprobe_reporting(returncode=1), decode=_three_second_decode)

        assert audio_module.probe_audio_duration(str(upload)) == pytest.approx(3.0)

    def test_file_without_audio_track_is_rejected(self, upload: Path, fake_ffprobe: Any) -> None:
        fake_ffprobe(_ffprobe_reporting({"streams": [], "format": {"duration": "5.0"}}))

        with pytest.raises(FileValidationError, match="no audio track"):
            audio_module.probe_audio_duration(str(upload))

    def test_missing_file_fails_loudly(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            audio_module.probe_audio_duration(str(tmp_path / "gone.ogg"))


@pytest.mark.unit
@pytest.mark.skipif(not _ffmpeg_tools_available(), reason="ffmpeg/ffprobe not installed")
class TestProbeAgainstRealFfmpeg:
    def test_agrees_with_decoded_length(self) -> None:
        probed = audio_module.probe_audio_duration(str(SAMPLE_MP3))
        decoded = audio_module.get_audio_duration(
            audio_module.process_audio_file(str(SAMPLE_MP3))
        )

        assert probed == pytest.approx(decoded, abs=0.1)

    def test_adts_aac_with_a_quiet_start_is_measured_not_estimated(self, tmp_path: Path) -> None:
        quiet_start = tmp_path / "quiet_start.aac"
        _ffmpeg(
            "-f", "lavfi", "-i", "sine=frequency=440:duration=120",
            "-af", "volume=enable='lt(t,30)':volume=0",
            "-c:a", "aac", "-b:a", "64k", str(quiet_start),
        )  # fmt: skip

        assert audio_module.probe_audio_duration(str(quiet_start)) == pytest.approx(120.0, abs=0.5)

    def test_video_audio_track_length_wins_over_container_length(self, tmp_path: Path) -> None:
        short_audio = tmp_path / "video10_audio3.mp4"
        _ffmpeg(
            "-f", "lavfi", "-i", "color=c=black:s=64x64:d=10",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
            "-c:v", "mpeg4", "-c:a", "aac", str(short_audio),
        )  # fmt: skip

        assert audio_module.probe_audio_duration(str(short_audio)) == pytest.approx(3.0, abs=0.1)

    @pytest.mark.parametrize(
        ("container", "video_codec", "audio_codec"),
        [("mkv", "mpeg4", "aac"), ("wmv", "wmv2", "wmav2")],
    )
    def test_short_audio_in_other_video_containers(
        self, tmp_path: Path, container: str, video_codec: str, audio_codec: str
    ) -> None:
        short_audio = tmp_path / f"video10_audio3.{container}"
        _ffmpeg(
            "-f", "lavfi", "-i", "color=c=black:s=64x64:d=10",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
            "-c:v", video_codec, "-c:a", audio_codec, str(short_audio),
        )  # fmt: skip

        assert audio_module.probe_audio_duration(str(short_audio)) == pytest.approx(3.0, abs=0.15)

    def test_late_starting_audio_in_matroska_is_measured(self, tmp_path: Path) -> None:
        late_audio = tmp_path / "audio_starts_late.mkv"
        _ffmpeg(
            "-f", "lavfi", "-i", "color=c=black:s=64x64:d=60",
            "-itsoffset", "6", "-f", "lavfi", "-i", "sine=frequency=440:duration=30",
            "-c:v", "mpeg4", "-c:a", "aac", str(late_audio),
        )  # fmt: skip
        decoded = audio_module.get_audio_duration(audio_module.process_audio_file(str(late_audio)))

        assert audio_module.probe_audio_duration(str(late_audio)) == pytest.approx(decoded, abs=0.2)

    def test_video_without_audio_is_rejected_before_any_job(self, tmp_path: Path) -> None:
        silent_video = tmp_path / "no_audio.mp4"
        _ffmpeg("-f", "lavfi", "-i", "color=c=black:s=64x64:d=5", "-c:v", "mpeg4", str(silent_video))

        with pytest.raises(FileValidationError, match="no audio track"):
            audio_module.probe_audio_duration(str(silent_video))


@pytest.mark.unit
class TestDecodeSavedUpload:
    def test_ffmpeg_failure_is_an_audio_error_not_a_cuda_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def failing_decode(_path: str) -> Any:
            raise RuntimeError(
                "Failed to load audio: ffmpeg version n7.1 configuration: --enable-cuda-llvm"
            )

        monkeypatch.setattr(audio_module, "process_audio_file", failing_decode)

        with pytest.raises(AudioProcessingError) as raised:
            audio_module.decode_saved_upload("upload.mp4")

        assert evict_on_cuda_error(raised.value) is False

    def test_returns_the_decoded_waveform(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(audio_module, "process_audio_file", _three_second_decode)

        waveform = audio_module.decode_saved_upload("upload.ogg")

        assert audio_module.get_audio_duration(waveform) == pytest.approx(3.0)
