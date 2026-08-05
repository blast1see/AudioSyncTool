from __future__ import annotations

import threading
from pathlib import Path

import pytest

from audio_sync.config import (
    EncodingPipeline,
    FFmpegEncodeConfig,
    FFmpegOutputFormat,
    PcmCodec,
)
from audio_sync.core.models import (
    AnalysisResult,
    AudioInfo,
    EncodingError,
    OperationCancelledError,
    UnsafeOutputPathError,
)
from audio_sync.core.pipeline import EncodingRequest, SyncPipeline, SyncRequest

AUDIO_INFO = AudioInfo(2, PcmCodec.S16LE, 16, 44_100)
ANALYSIS = AnalysisResult(25.0, 24.0, 8.0, 12, 10, 0.1, False)


class FakeAnalyzer:
    def calculate_delay_from_pcm_files(self, *_args, **_kwargs):
        return ANALYSIS


class FakeFFmpeg:
    def __init__(self, fail_sync: bool = False, fail_final_probe: bool = False) -> None:
        self.fail_sync = fail_sync
        self.fail_final_probe = fail_final_probe
        self.applied_output_rate = None
        self.sync_kwargs: dict = {}
        self.sync_delay: float | None = None

    def probe_audio(self, path: str):
        if self.fail_final_probe and ".staged-" in Path(path).name:
            raise RuntimeError("injected final probe failure")
        return AUDIO_INFO

    def decode_mono_pcm_to_file(self, _path, *, prefix, temp_dir, **_kwargs):
        pcm = Path(temp_dir) / f"{prefix}audio.s16le"
        pcm.write_bytes(b"\0\0" * 64)
        return 8_000, str(pcm), 64

    def apply_sync(self, _source, _sync, delay, _info, output_sr, output, **kwargs):
        self.applied_output_rate = output_sr
        self.sync_delay = delay
        self.sync_kwargs = kwargs
        if self.fail_sync:
            raise RuntimeError("injected sync failure")
        Path(output).write_bytes(b"RIFF-synchronized")
        return "sync command"

    def _encoded(self, name, _input, output, **_kwargs):
        Path(output).write_bytes(f"encoded:{name}".encode())
        return name

    def encode_to_aac(self, input_path, output_path, **kwargs):
        return self._encoded("aac", input_path, output_path, **kwargs)

    def encode_to_flac(self, input_path, output_path, **kwargs):
        return self._encoded("flac", input_path, output_path, **kwargs)

    def encode_to_opus(self, input_path, output_path, **kwargs):
        return self._encoded("opus", input_path, output_path, **kwargs)

    def encode_to_ac3_eac3(self, input_path, output_path, *, fmt, **kwargs):
        return self._encoded(fmt.cli_value, input_path, output_path, **kwargs)


def make_input(path: Path) -> str:
    path.write_bytes(b"input audio")
    return str(path)


@pytest.fixture(autouse=True)
def no_real_tool_probe(monkeypatch):
    monkeypatch.setattr(
        "audio_sync.core.pipeline.FFmpegWrapper.check_availability", lambda: None
    )


def test_pipeline_hands_regions_to_ffmpeg_and_drops_the_drift(tmp_path: Path) -> None:
    """A stepped file must be spliced, not stretched, and not both."""
    import math

    from audio_sync.core.models import OffsetRegion

    regions = (
        OffsetRegion(0.0, 3000.0, -9484.0, 20, 5.0),
        OffsetRegion(3000.0, math.inf, -9616.0, 9, 4.6),
    )
    stepped = AnalysisResult(
        delay_ms=-9500.0, coarse_ms=-9500.0, confidence=5.0,
        total_segments=40, used_segments=29, drift_ms_per_min=8.0,
        skip_fallback=False, drift_intercept_ms=-9500.0, drift_r2=0.95,
        drift_span_sec=6000.0, offset_regions=regions,
    )

    class SteppedAnalyzer:
        def calculate_delay_from_pcm_files(self, *_args, **_kwargs):
            return stepped

    fake = FakeFFmpeg()
    source = make_input(tmp_path / "source.wav")
    sync = make_input(tmp_path / "sync.wav")
    outcome = SyncPipeline(ffmpeg=fake, analyzer=SteppedAnalyzer()).run(
        SyncRequest(source, sync, str(tmp_path / "out.wav"), skip_intro_sec=0)
    )

    assert fake.sync_kwargs["offset_regions"] == regions
    assert fake.sync_kwargs["drift_ms_per_min"] is None, (
        "a tempo correction fitted through a step is meaningless"
    )
    assert outcome.offset_regions_applied == regions


def test_pipeline_can_be_told_to_ignore_regions(tmp_path: Path) -> None:
    import math

    from audio_sync.core.models import OffsetRegion

    regions = (
        OffsetRegion(0.0, 3000.0, -9484.0, 20, 5.0),
        OffsetRegion(3000.0, math.inf, -9616.0, 9, 4.6),
    )
    stepped = AnalysisResult(
        delay_ms=-9500.0, coarse_ms=-9500.0, confidence=5.0,
        total_segments=40, used_segments=29, drift_ms_per_min=None,
        skip_fallback=False, offset_regions=regions,
    )

    class SteppedAnalyzer:
        def calculate_delay_from_pcm_files(self, *_args, **_kwargs):
            return stepped

    fake = FakeFFmpeg()
    source = make_input(tmp_path / "source.wav")
    sync = make_input(tmp_path / "sync.wav")
    SyncPipeline(ffmpeg=fake, analyzer=SteppedAnalyzer()).run(
        SyncRequest(
            source, sync, str(tmp_path / "out.wav"),
            skip_intro_sec=0, correct_steps=False,
        )
    )

    assert fake.sync_kwargs["offset_regions"] == ()
    assert fake.sync_delay == -9500.0


def test_pipeline_atomically_replaces_output_only_after_success(tmp_path: Path) -> None:
    source = make_input(tmp_path / "source.wav")
    sync = make_input(tmp_path / "sync.wav")
    output = tmp_path / "result.wav"
    output.write_bytes(b"existing")
    fake = FakeFFmpeg()
    pipeline = SyncPipeline(ffmpeg=fake, analyzer=FakeAnalyzer())

    outcome = pipeline.run(SyncRequest(source, sync, str(output), skip_intro_sec=0))

    assert output.read_bytes() == b"RIFF-synchronized"
    assert outcome.output_path == str(output.resolve())
    assert outcome.analysis is ANALYSIS
    assert fake.applied_output_rate.rate is None
    assert not list(tmp_path.glob(".*.staged-*"))


def test_pipeline_preserves_existing_output_on_sync_failure(tmp_path: Path) -> None:
    source = make_input(tmp_path / "source.wav")
    sync = make_input(tmp_path / "sync.wav")
    output = tmp_path / "result.wav"
    output.write_bytes(b"do not overwrite")
    pipeline = SyncPipeline(ffmpeg=FakeFFmpeg(fail_sync=True), analyzer=FakeAnalyzer())

    with pytest.raises(RuntimeError, match="injected sync failure"):
        pipeline.run(SyncRequest(source, sync, str(output), skip_intro_sec=0))
    assert output.read_bytes() == b"do not overwrite"


def test_pipeline_preserves_existing_output_when_final_validation_fails(
    tmp_path: Path,
) -> None:
    source = make_input(tmp_path / "source.wav")
    sync = make_input(tmp_path / "sync.wav")
    output = tmp_path / "result.wav"
    output.write_bytes(b"validated existing")
    pipeline = SyncPipeline(
        ffmpeg=FakeFFmpeg(fail_final_probe=True), analyzer=FakeAnalyzer()
    )

    with pytest.raises(RuntimeError, match="injected final probe failure"):
        pipeline.run(SyncRequest(source, sync, str(output), skip_intro_sec=0))
    assert output.read_bytes() == b"validated existing"


def test_pipeline_rejects_both_input_paths_as_output(tmp_path: Path) -> None:
    source = make_input(tmp_path / "source.wav")
    sync = make_input(tmp_path / "sync.wav")
    for output in (source, sync):
        with pytest.raises(UnsafeOutputPathError):
            SyncPipeline.validate_request(SyncRequest(source, sync, output))


def test_relative_paths_become_absolute_before_reaching_ffmpeg(
    tmp_path: Path, monkeypatch
) -> None:
    """FFmpeg reads a leading ``name:`` on a relative path as a protocol."""
    make_input(tmp_path / "sample:source.wav")
    make_input(tmp_path / "sample:sync.wav")
    monkeypatch.chdir(tmp_path)

    normalized = SyncPipeline.normalize_request(
        SyncRequest("sample:source.wav", "sample:sync.wav", "out.wav", skip_intro_sec=0)
    )

    for path in (
        normalized.source_path,
        normalized.sync_path,
        normalized.output_path,
    ):
        assert Path(path).is_absolute()
    assert Path(normalized.source_path).name == "sample:source.wav"


def test_relative_input_matching_output_is_still_rejected(
    tmp_path: Path, monkeypatch
) -> None:
    """The overwrite guard must survive a relative/absolute path mismatch."""
    make_input(tmp_path / "source.wav")
    make_input(tmp_path / "sync.wav")
    monkeypatch.chdir(tmp_path)
    pipeline = SyncPipeline(ffmpeg=FakeFFmpeg(), analyzer=FakeAnalyzer())

    with pytest.raises(UnsafeOutputPathError):
        pipeline.run(
            SyncRequest("source.wav", "sync.wav", str(tmp_path / "source.wav"))
        )


def test_pipeline_preserves_existing_output_on_cancel(tmp_path: Path) -> None:
    source = make_input(tmp_path / "source.wav")
    sync = make_input(tmp_path / "sync.wav")
    output = tmp_path / "result.wav"
    output.write_bytes(b"existing")
    cancelled = threading.Event()
    cancelled.set()

    with pytest.raises(OperationCancelledError):
        SyncPipeline(ffmpeg=FakeFFmpeg(), analyzer=FakeAnalyzer()).run(
            SyncRequest(source, sync, str(output)), cancel_event=cancelled
        )
    assert output.read_bytes() == b"existing"


def test_encoding_failure_keeps_collision_free_fallback(tmp_path: Path, monkeypatch) -> None:
    source = make_input(tmp_path / "source.wav")
    sync = make_input(tmp_path / "sync.wav")
    output = tmp_path / "result.m4a"
    output.write_bytes(b"existing final")
    first_fallback = tmp_path / "result.sync-fallback.wav"
    first_fallback.write_bytes(b"previous fallback")
    pipeline = SyncPipeline(ffmpeg=FakeFFmpeg(), analyzer=FakeAnalyzer())

    def fail_encode(*_args, **_kwargs):
        raise RuntimeError("injected encoder failure")

    monkeypatch.setattr(pipeline, "_encode", fail_encode)
    request = SyncRequest(
        source,
        sync,
        str(output),
        skip_intro_sec=0,
        encoding=EncodingRequest(pipeline=EncodingPipeline.FFMPEG),
    )
    with pytest.raises(EncodingError) as caught:
        pipeline.run(request)

    assert output.read_bytes() == b"existing final"
    assert first_fallback.read_bytes() == b"previous fallback"
    fallback = Path(caught.value.fallback_path)
    assert fallback.name == "result.sync-fallback-2.wav"
    assert fallback.stat().st_size > 0


def test_encoded_output_validation_failure_also_preserves_fallback(tmp_path: Path) -> None:
    source = make_input(tmp_path / "source.wav")
    sync = make_input(tmp_path / "sync.wav")
    output = tmp_path / "result.m4a"
    output.write_bytes(b"existing final")
    request = SyncRequest(
        source,
        sync,
        str(output),
        skip_intro_sec=0,
        encoding=EncodingRequest(pipeline=EncodingPipeline.FFMPEG),
    )

    with pytest.raises(EncodingError) as caught:
        SyncPipeline(
            ffmpeg=FakeFFmpeg(fail_final_probe=True), analyzer=FakeAnalyzer()
        ).run(request)

    assert output.read_bytes() == b"existing final"
    fallback = Path(caught.value.fallback_path)
    assert fallback.name == "result.sync-fallback.wav"
    assert fallback.stat().st_size > 0


@pytest.mark.parametrize(
    ("fmt", "suffix", "summary"),
    [
        (FFmpegOutputFormat.AAC, ".m4a", "aac"),
        (FFmpegOutputFormat.FLAC, ".flac", "flac"),
        (FFmpegOutputFormat.OPUS, ".opus", "opus"),
        (FFmpegOutputFormat.AC3, ".ac3", "dd"),
        (FFmpegOutputFormat.EAC3, ".eac3", "ddp"),
    ],
)
def test_pipeline_dispatches_all_ffmpeg_encoders(
    tmp_path: Path, fmt: FFmpegOutputFormat, suffix: str, summary: str
) -> None:
    input_wav = tmp_path / "input.wav"
    input_wav.write_bytes(b"wav")
    output = tmp_path / f"output{suffix}"
    pipeline = SyncPipeline(ffmpeg=FakeFFmpeg(), analyzer=FakeAnalyzer())
    request = EncodingRequest(
        pipeline=EncodingPipeline.FFMPEG,
        ffmpeg=FFmpegEncodeConfig(format=fmt),
    )
    actual = pipeline._encode(request, input_wav, output, threading.Event(), lambda _m: None)
    assert actual == summary
    assert output.stat().st_size > 0
