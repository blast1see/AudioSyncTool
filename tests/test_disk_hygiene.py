"""Nothing large may be left behind without the user being told.

Every run writes intermediates the size of the film's audio — decoded PCM, a
synchronized WAV, an FPS-converted WAV, deew's scratch directory.  Silent
leftovers accumulate until a disk fills up.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from audio_sync.config import EncodingPipeline, PcmCodec
from audio_sync.core.models import (
    AnalysisResult,
    AudioInfo,
    EncodingError,
    OperationCancelledError,
)
from audio_sync.core.pipeline import EncodingRequest, SyncPipeline, SyncRequest

AUDIO_INFO = AudioInfo(2, PcmCodec.S16LE, 16, 44_100)
ANALYSIS = AnalysisResult(25.0, 24.0, 8.0, 12, 10, 0.1, False)


class FakeAnalyzer:
    def calculate_delay_from_pcm_files(self, *_args, **_kwargs):
        return ANALYSIS


class FakeFFmpeg:
    def __init__(self, fail_encode: bool = False) -> None:
        self.fail_encode = fail_encode

    def probe_audio(self, _path):
        return AUDIO_INFO

    def decode_mono_pcm_to_file(self, _path, *, prefix, temp_dir, **_kwargs):
        pcm = Path(temp_dir) / f"{prefix}audio.s16le"
        pcm.write_bytes(b"\0\0" * 4096)
        return 8_000, str(pcm), 4096

    def apply_sync(self, _source, _sync, _delay, _info, _sr, output, **_kwargs):
        Path(output).write_bytes(b"RIFF" + b"\0" * 8192)
        return "sync command"

    def encode_to_aac(self, _input_path, _output_path, **_kwargs):
        raise RuntimeError("injected encoder failure")


@pytest.fixture(autouse=True)
def no_tool_probe(monkeypatch):
    monkeypatch.setattr(
        "audio_sync.core.pipeline.FFmpegWrapper.check_availability", lambda: None
    )


def make_inputs(tmp_path: Path) -> tuple[str, str]:
    source = tmp_path / "source.wav"
    sync = tmp_path / "sync.wav"
    source.write_bytes(b"source audio")
    sync.write_bytes(b"sync audio")
    return str(source), str(sync)


def leftovers(folder: Path, output_name: str) -> list[str]:
    return sorted(
        path.name for path in folder.iterdir() if path.name not in {
            "source.wav", "sync.wav", output_name
        }
    )


def test_a_successful_run_leaves_nothing_behind(tmp_path: Path) -> None:
    source, sync = make_inputs(tmp_path)
    SyncPipeline(ffmpeg=FakeFFmpeg(), analyzer=FakeAnalyzer()).run(
        SyncRequest(source, sync, str(tmp_path / "out.wav"), skip_intro_sec=0)
    )
    assert leftovers(tmp_path, "out.wav") == []


def test_a_cancelled_run_leaves_nothing_behind(tmp_path: Path) -> None:
    """Cancellation is the common case for a long job — it must not litter."""
    source, sync = make_inputs(tmp_path)
    cancel = threading.Event()
    cancel.set()

    with pytest.raises(OperationCancelledError):
        SyncPipeline(ffmpeg=FakeFFmpeg(), analyzer=FakeAnalyzer()).run(
            SyncRequest(source, sync, str(tmp_path / "out.wav"), skip_intro_sec=0),
            cancel_event=cancel,
        )
    assert leftovers(tmp_path, "out.wav") == []


def test_the_staged_output_never_survives_a_failure(tmp_path: Path) -> None:
    source, sync = make_inputs(tmp_path)
    with pytest.raises(EncodingError):
        SyncPipeline(ffmpeg=FakeFFmpeg(), analyzer=FakeAnalyzer()).run(
            SyncRequest(
                source, sync, str(tmp_path / "out.wav"), skip_intro_sec=0,
                encoding=EncodingRequest(pipeline=EncodingPipeline.FFMPEG),
            )
        )
    assert not list(tmp_path.glob(".*staged-*"))
    assert not list(tmp_path.glob("audiosync_work_*"))


def test_the_preserved_wav_is_announced_with_its_size(tmp_path: Path) -> None:
    """It is kept on purpose, but it is uncompressed and film-length."""
    source, sync = make_inputs(tmp_path)
    with pytest.raises(EncodingError) as caught:
        SyncPipeline(ffmpeg=FakeFFmpeg(), analyzer=FakeAnalyzer()).run(
            SyncRequest(
                source, sync, str(tmp_path / "out.wav"), skip_intro_sec=0,
                encoding=EncodingRequest(pipeline=EncodingPipeline.FFMPEG),
            )
        )

    message = str(caught.value)
    assert "sync-fallback" in message
    assert "delete it" in message
    # The size is the point: a user cannot judge whether to keep a file whose
    # size they were never told.
    assert any(unit in message for unit in ("B)", "KB)", "MB)", "GB)")), message
    assert Path(caught.value.fallback_path).exists()


@pytest.mark.parametrize(
    ("size", "expected"),
    [(512, "512 B"), (2048, "2.0 KB"), (5 * 1024**2, "5.0 MB"), (3 * 1024**3, "3.0 GB")],
)
def test_sizes_are_reported_in_readable_units(tmp_path: Path, size, expected) -> None:
    probe = tmp_path / "probe.bin"
    probe.write_bytes(b"\0" * size)
    assert SyncPipeline._describe_size(probe) == expected
