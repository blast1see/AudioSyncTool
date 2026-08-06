"""Nothing used to check the file that was actually written.

Every stage reported what it intended to do — the analyzer its measurement, the
filter its arguments, the encoder its bitrate — and the run finished with
"completed" regardless of what came out. A wrong measurement, a filter that
silently did nothing, or an encoder shifting the track by its own lookahead all
produced the same confident message.

The verification pass reads a few seconds from a few places in the finished file
and measures it against the reference it was aligned to.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from audio_sync.config import SYNC_CONFIG, PcmCodec
from audio_sync.core.analyzer import AudioAnalyzer
from audio_sync.core.models import (
    AnalysisResult,
    AudioInfo,
    MatchVerdict,
    NoMatchError,
)
from audio_sync.core.pipeline import SyncPipeline, SyncRequest

RATE = SYNC_CONFIG.analysis_sample_rate
AUDIO_INFO = AudioInfo(2, PcmCodec.S16LE, 16, 48_000)


# ── The measurement itself ───────────────────────────────────────────────────


def _noise(seconds: float, seed: int = 3) -> np.ndarray:
    rng = np.random.default_rng(seed)
    signal = rng.normal(0.0, 0.2, size=int(seconds * RATE))
    for start in range(0, signal.size - RATE, RATE * 2):
        signal[start:start + RATE // 3] *= 5.0
    return np.clip(signal, -1.0, 1.0) * 28000.0


def test_an_aligned_pair_measures_near_zero() -> None:
    search = 2.0
    reference = _noise(15.0)
    padding = np.zeros(int(search * RATE))
    produced = np.concatenate((padding, reference, padding))

    found = AudioAnalyzer().residual_offset_ms(
        RATE, reference.astype(np.int16), produced.astype(np.int16), search_sec=search,
    )
    assert found is not None
    assert found[0] == pytest.approx(0.0, abs=1.0)


def test_a_track_left_ahead_reports_a_positive_residual() -> None:
    """Positive means the produced audio still arrives early."""
    search = 2.0
    shift = int(0.25 * RATE)  # 250 ms early
    reference = _noise(15.0)
    padding = np.zeros(int(search * RATE))
    produced = np.concatenate((padding, reference, padding))
    produced = np.concatenate((produced[shift:], np.zeros(shift)))

    found = AudioAnalyzer().residual_offset_ms(
        RATE, reference.astype(np.int16), produced.astype(np.int16), search_sec=search,
    )
    assert found is not None
    assert found[0] == pytest.approx(250.0, abs=2.0)


# ── The pipeline step ────────────────────────────────────────────────────────


class VerifyingFFmpeg:
    """Just enough of the wrapper for the verification stage."""

    def __init__(self, residual_ms: float = 0.0, duration: float = 600.0) -> None:
        self.residual_ms = residual_ms
        self.duration = duration
        self._signal = _noise(900.0, seed=5)

    def probe_duration_sec(self, _path: str) -> float:
        return self.duration

    def decode_probe_mono_pcm(self, path, start_sec, duration_sec, **_kwargs):
        start = int(start_sec * RATE)
        length = int(duration_sec * RATE)
        if "output" in str(path):
            # A residual of +250 ms means the produced track runs early, so the
            # content found at a given timestamp is what belongs 250 ms later.
            start += int(self.residual_ms / 1000.0 * RATE)
        start = max(0, min(start, self._signal.size - length))
        return self._signal[start:start + length].astype(np.int16)


def test_a_clean_output_is_reported_as_verified() -> None:
    lines: list[str] = []
    pipeline = SyncPipeline(ffmpeg=VerifyingFFmpeg(residual_ms=0.0))
    residual, probes = pipeline._verify_output(
        "source.mkv", "output.wav", log=lines.append,
    )
    assert residual == pytest.approx(0.0, abs=2.0)
    assert probes >= 2
    assert any("✓" in line for line in lines)


def test_an_output_that_is_still_out_says_so() -> None:
    lines: list[str] = []
    pipeline = SyncPipeline(ffmpeg=VerifyingFFmpeg(residual_ms=250.0))
    residual, probes = pipeline._verify_output(
        "source.mkv", "output.wav", log=lines.append,
    )
    assert residual == pytest.approx(250.0, abs=5.0)
    assert probes >= 2
    assert any("⚠" in line for line in lines)


class BrokenFFmpeg:
    def probe_duration_sec(self, _path: str) -> float:
        raise RuntimeError("injected probe failure")


def test_a_failing_check_never_fails_the_run() -> None:
    """The check exists to add confidence, not a new way to lose a finished file."""
    lines: list[str] = []
    residual, probes = SyncPipeline(ffmpeg=BrokenFFmpeg())._verify_output(
        "source.mkv", "output.wav", log=lines.append,
    )
    assert (residual, probes) == (None, 0)
    assert lines


# ── Refusing to write from a measurement that means nothing ──────────────────


NO_MATCH = AnalysisResult(
    delay_ms=-1_820_320.0,
    coarse_ms=-2_010_304.0,
    confidence=1.87,
    total_segments=57,
    used_segments=29,
    drift_ms_per_min=-57.5,
    skip_fallback=False,
    verdict=MatchVerdict.NO_MATCH,
    verdict_reasons=("reason_offset_implausible", "reason_confidence_floor"),
)


class RejectingAnalyzer:
    def calculate_delay_from_pcm_files(self, *_args, **_kwargs):
        return NO_MATCH


class RecordingFFmpeg:
    def __init__(self) -> None:
        self.sync_called = False

    def probe_audio(self, _path):
        return AUDIO_INFO

    def probe_duration_sec(self, _path):
        return 600.0

    def decode_probe_mono_pcm(self, *_args, **_kwargs):
        return np.zeros(0, dtype=np.int16)

    def decode_mono_pcm_to_file(self, _path, *, prefix, temp_dir, **_kwargs):
        pcm = Path(temp_dir) / f"{prefix}audio.s16le"
        pcm.write_bytes(b"\0\0" * 64)
        return 8_000, str(pcm), 64

    def apply_sync(self, _source, _sync, _delay, _info, _sr, output, **_kwargs):
        self.sync_called = True
        Path(output).write_bytes(b"RIFF-synchronized")
        return "sync command"


def _request(tmp_path: Path, **overrides) -> SyncRequest:
    source = tmp_path / "source.wav"
    sync = tmp_path / "sync.wav"
    source.write_bytes(b"input audio")
    sync.write_bytes(b"input audio")
    return SyncRequest(
        source_path=str(source),
        sync_path=str(sync),
        output_path=str(tmp_path / "out.wav"),
        # The rejected result carries a nonsense drift figure, and chasing it
        # into a frame-rate conversion is not what these tests are about.
        auto_fps_conversion=False,
        **overrides,
    )


def test_no_match_stops_before_anything_is_written(tmp_path, monkeypatch) -> None:
    from audio_sync.core.ffmpeg_wrapper import FFmpegWrapper

    monkeypatch.setattr(FFmpegWrapper, "check_availability", staticmethod(lambda: None))
    ffmpeg = RecordingFFmpeg()
    pipeline = SyncPipeline(ffmpeg=ffmpeg, analyzer=RejectingAnalyzer())

    with pytest.raises(NoMatchError):
        pipeline.run(_request(tmp_path))

    assert not ffmpeg.sync_called
    assert not (tmp_path / "out.wav").exists()


def test_the_refusal_can_be_overridden(tmp_path, monkeypatch) -> None:
    """Refusing has to be a default, not a wall — the caller may know better."""
    from audio_sync.core.ffmpeg_wrapper import FFmpegWrapper

    monkeypatch.setattr(FFmpegWrapper, "check_availability", staticmethod(lambda: None))
    ffmpeg = RecordingFFmpeg()
    pipeline = SyncPipeline(ffmpeg=ffmpeg, analyzer=RejectingAnalyzer())

    outcome = pipeline.run(_request(tmp_path, allow_no_match=True))
    assert ffmpeg.sync_called
    assert outcome.analysis.verdict is MatchVerdict.NO_MATCH
