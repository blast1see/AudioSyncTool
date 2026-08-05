"""Real FFmpeg checks for piecewise splicing.

Unit tests assert the shape of the filter graph; only FFmpeg can say whether the
graph actually produces an aligned track of the right length.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
from scipy.io import wavfile

from audio_sync.config import PcmCodec
from audio_sync.core.ffmpeg_wrapper import FFmpegWrapper
from audio_sync.core.models import AudioInfo, OffsetRegion, OutputSampleRate

pytestmark = pytest.mark.integration

RATE = 16_000
INFO = AudioInfo(1, PcmCodec.S16LE, 16, RATE)
KEEP = OutputSampleRate.decide(RATE, RATE, False)


@pytest.fixture(scope="module")
def wrapper() -> FFmpegWrapper:
    try:
        FFmpegWrapper.check_availability()
    except OSError as exc:
        pytest.skip(str(exc))
    return FFmpegWrapper()


def clicky_signal(seconds: int) -> np.ndarray:
    """Sparse bursts — easy to locate exactly, unlike continuous noise."""
    rng = np.random.default_rng(20260805)
    audio = np.zeros(RATE * seconds, dtype=np.float64)
    for start in range(RATE // 2, audio.size - RATE, RATE // 2):
        length = RATE // 20
        audio[start:start + length] = rng.normal(0, 0.6, length)
    return np.asarray(np.clip(audio, -1, 1) * 26_000, dtype=np.int16)


def measure_offset_ms(reference: np.ndarray, produced: np.ndarray) -> float:
    """Positive when ``produced`` runs late relative to ``reference``."""
    size = min(reference.size, produced.size)
    a = reference[:size].astype(np.float64)
    b = produced[:size].astype(np.float64)
    a -= a.mean()
    b -= b.mean()
    length = 1 << int(math.ceil(math.log2(2 * size)))
    corr = np.fft.irfft(np.fft.rfft(a, length) * np.conj(np.fft.rfft(b, length)), length)
    window = RATE * 3
    corr = np.concatenate([corr[-window:], corr[:window + 1]])
    lags = np.arange(-window, window + 1)
    return float(lags[int(np.argmax(corr))]) / RATE * 1000.0


def test_piecewise_output_aligns_both_regions(tmp_path: Path, wrapper) -> None:
    """A track whose offset jumps midway must come back aligned throughout."""
    seconds = 120
    boundary_sec = 60.0
    lag_a_ms, lag_b_ms = -400.0, -900.0

    reference = clicky_signal(seconds)
    # Build the target the way a differently-cut dub behaves.  A negative lag
    # means the target runs late, so its content sits later than the reference
    # by that much: 400 ms for the first stretch, then an extra 500 ms of
    # inserted material pushes the rest out to 900 ms.
    cut = int(boundary_sec * RATE)
    lead = np.zeros(int(0.400 * RATE), dtype=np.int16)
    insert = np.zeros(int(0.500 * RATE), dtype=np.int16)
    target = np.concatenate((lead, reference[:cut], insert, reference[cut:]))

    source_path = tmp_path / "reference.wav"
    target_path = tmp_path / "target.wav"
    out_path = tmp_path / "spliced.wav"
    wavfile.write(source_path, RATE, reference)
    wavfile.write(target_path, RATE, target)

    regions = (
        OffsetRegion(0.0, boundary_sec, lag_a_ms, 10, 5.0),
        OffsetRegion(boundary_sec, math.inf, lag_b_ms, 10, 5.0),
    )
    summary = wrapper.apply_sync(
        str(source_path), str(target_path), 0.0, INFO, KEEP, str(out_path),
        offset_regions=regions,
    )
    assert "piecewise" in summary

    _rate, produced = wavfile.read(out_path)
    assert produced.size > 0

    # Each region has to be checked on its own; a single global measurement
    # would average the two and hide a failure in either.
    for label, start, stop in (("first", 5, 55), ("second", 65, 115)):
        ref_slice = reference[start * RATE:stop * RATE]
        out_slice = produced[start * RATE:stop * RATE]
        offset = measure_offset_ms(ref_slice, out_slice)
        assert abs(offset) <= 30.0, f"{label} region off by {offset:.1f} ms"


def test_piecewise_preserves_the_reference_timeline_length(
    tmp_path: Path, wrapper
) -> None:
    """Pieces are cut in reference time, so the output must span it exactly."""
    seconds = 90
    reference = clicky_signal(seconds)
    source_path = tmp_path / "reference.wav"
    target_path = tmp_path / "target.wav"
    out_path = tmp_path / "spliced.wav"
    wavfile.write(source_path, RATE, reference)
    wavfile.write(target_path, RATE, reference)

    regions = (
        OffsetRegion(0.0, 30.0, -200.0, 8, 5.0),
        OffsetRegion(30.0, math.inf, -500.0, 8, 5.0),
    )
    wrapper.apply_sync(
        str(source_path), str(target_path), 0.0, INFO, KEEP, str(out_path),
        offset_regions=regions,
    )

    _rate, produced = wavfile.read(out_path)
    # 30 s of first region plus whatever remains of the source after 0.5 s.
    expected = 30.0 + (seconds - 0.5 - 30.0)
    assert abs(produced.size / RATE - expected) < 0.2


def test_a_region_reaching_before_the_track_start_is_padded(
    tmp_path: Path, wrapper
) -> None:
    """A positive lag means the reference begins first; that gap is silence."""
    reference = clicky_signal(60)
    source_path = tmp_path / "reference.wav"
    target_path = tmp_path / "target.wav"
    out_path = tmp_path / "spliced.wav"
    wavfile.write(source_path, RATE, reference)
    wavfile.write(target_path, RATE, reference)

    regions = (
        OffsetRegion(0.0, 30.0, 750.0, 8, 5.0),
        OffsetRegion(30.0, math.inf, 250.0, 8, 5.0),
    )
    wrapper.apply_sync(
        str(source_path), str(target_path), 0.0, INFO, KEEP, str(out_path),
        offset_regions=regions,
    )

    _rate, produced = wavfile.read(out_path)
    head = produced[:int(0.7 * RATE)]
    assert int(np.max(np.abs(head))) == 0, "leading gap must be silent, not seeked"
