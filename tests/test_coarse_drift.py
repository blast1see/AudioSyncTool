"""The coarse drift bracket.

Segment validation searches ``local_search_sec`` around a single coarse lag.
When two encodes run at different clock rates, the offset at the end of a
feature film can be seconds away from the offset at the start, so most of the
file falls outside that window and never validates.  Correlating the first and
last thirds separately gives two lags far enough apart to define a line, which
is handed to validation as anchors.
"""

from __future__ import annotations

import numpy as np
import pytest

from audio_sync.config import SYNC_CONFIG, SyncConfig
from audio_sync.core.analyzer import AudioAnalyzer

COARSE_RATE = 12.5  # 80 ms hop, the production value
FINE_RATE = 50.0


def sparse_features(frames: int, seed: int = 4) -> np.ndarray:
    """Feature stream with isolated peaks at irregular spacing.

    The spacing has to be irregular: evenly spaced peaks make the stream
    periodic, and a periodic signal correlates equally well at every multiple
    of its period, so the peak the search finds is arbitrary.
    """
    rng = np.random.default_rng(seed)
    feat = rng.normal(0.0, 0.05, frames)
    position = 20
    while position < frames - 20:
        feat[position] += 6.0
        position += int(rng.integers(25, 70))
    return feat.astype(np.float32)


def drifting_pair(frames: int, head_lag: int, tail_lag: int):
    """Reference plus a target whose lag ramps from head_lag to tail_lag."""
    reference = sparse_features(frames + 400)
    target = np.zeros_like(reference)
    for index in range(frames):
        lag = head_lag + (tail_lag - head_lag) * (index / max(1, frames - 1))
        source = int(round(index - lag))
        if 0 <= source < reference.size:
            target[index] = reference[source]
    return reference, target


def build(analyzer: AudioAnalyzer, reference, target):
    return analyzer._coarse_drift_candidate(
        reference, target, COARSE_RATE, FINE_RATE, skip_samples=0, rate=16_000
    )


def test_a_constant_offset_produces_no_drift_candidate() -> None:
    """The ordinary candidate already covers this; a line would only mislead."""
    reference = sparse_features(4_000)
    target = np.concatenate((np.zeros(25, dtype=np.float32), reference[:-25]))
    assert build(AudioAnalyzer(), reference, target) is None


def measured_ends(analyzer: AudioAnalyzer, reference, target):
    """What the two end-slices actually report, on the reference timeline."""
    length = min(reference.size, target.size)
    third = length // 3
    head = analyzer._lag_within(reference, target, 0, third)
    tail = analyzer._lag_within(reference, target, length - third, length)
    return head, tail, third, length


def test_a_slide_between_the_ends_produces_two_ordered_anchors() -> None:
    """The candidate composes the two end measurements into a line."""
    analyzer = AudioAnalyzer(config=SyncConfig(coarse_drift_max_spread_sec=10_000.0))
    reference, target = drifting_pair(4_000, head_lag=-40, tail_lag=40)
    head, tail, third, length = measured_ends(analyzer, reference, target)
    assert head is not None and tail is not None

    candidate = build(analyzer, reference, target)
    assert candidate is not None
    assert len(candidate.anchors) == 2

    early, late = candidate.anchors
    assert early.center_frame < late.center_frame

    # Anchors carry exactly what the end slices measured, rescaled to the fine
    # grid — the candidate's job is composition, not its own measurement.
    scale = FINE_RATE / COARSE_RATE
    assert early.lag_frame == pytest.approx(head[0] * scale)
    assert late.lag_frame == pytest.approx(tail[0] * scale)
    assert early.center_frame == pytest.approx(third / 2.0 * scale)
    assert late.center_frame == pytest.approx((length - third / 2.0) * scale)


def test_the_candidate_midpoint_sits_between_the_two_ends() -> None:
    analyzer = AudioAnalyzer(config=SyncConfig(coarse_drift_max_spread_sec=10_000.0))
    reference, target = drifting_pair(4_000, head_lag=-40, tail_lag=40)
    head, tail, _third, _length = measured_ends(analyzer, reference, target)
    candidate = build(analyzer, reference, target)

    assert candidate is not None
    expected_ms = (head[0] + tail[0]) / 2.0 / COARSE_RATE * 1000.0
    assert candidate.coarse_ms == pytest.approx(expected_ms)
    assert candidate.score == pytest.approx(min(head[1], tail[1]))


def test_an_absurd_spread_is_rejected() -> None:
    """Beyond a couple of minutes the two ends are not the same content."""
    analyzer = AudioAnalyzer(config=SyncConfig(coarse_drift_max_spread_sec=1.0))
    reference, target = drifting_pair(4_000, head_lag=-40, tail_lag=40)
    assert build(analyzer, reference, target) is None


def test_a_too_short_stream_is_skipped() -> None:
    tiny = sparse_features(100)
    assert build(AudioAnalyzer(), tiny, tiny) is None


def test_lag_within_offsets_by_the_slice_start() -> None:
    reference = sparse_features(3_000)
    target = np.concatenate((np.zeros(30, dtype=np.float32), reference[:-30]))

    analyzer = AudioAnalyzer()
    whole = analyzer._lag_within(reference, target, 0, reference.size)
    later = analyzer._lag_within(reference, target, 1_000, 2_000)

    assert whole is not None and later is not None
    # Same physical offset, measured from two different slices.
    assert later[0] == pytest.approx(whole[0], abs=3.0)


def test_lag_within_rejects_a_flat_slice() -> None:
    flat = np.zeros(2_000, dtype=np.float32)
    assert AudioAnalyzer()._lag_within(flat, flat, 0, 500) is None


def test_thresholds_come_from_config() -> None:
    assert SYNC_CONFIG.coarse_drift_min_spread_sec > 0
    assert SYNC_CONFIG.coarse_drift_max_spread_sec > SYNC_CONFIG.coarse_drift_min_spread_sec
