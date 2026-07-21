from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from audio_sync.config import SYNC_CONFIG
from audio_sync.core.analyzer import AudioAnalyzer

RATE = 8_000
CONFIG = replace(
    SYNC_CONFIG,
    min_audio_duration_sec=3,
    segment_duration_sec=2.0,
    local_search_sec=1.0,
    analysis_sample_rate=RATE,
    fingerprint_enabled=False,
    offset_map_bucket_sec=3.0,
    offset_map_min_spacing_sec=1.0,
)


def rich_signal(seconds: int = 12) -> np.ndarray:
    rng = np.random.default_rng(20260721)
    signal = rng.normal(0, 0.24, RATE * seconds)
    time = np.arange(signal.size) / RATE
    signal += 0.18 * np.sin(2 * np.pi * (180 + 35 * time) * time)
    envelope = 0.35 + 0.65 * (np.sin(2 * np.pi * 0.73 * time) ** 2)
    return np.asarray(np.clip(signal * envelope, -1, 1) * 30_000, dtype=np.int16)


def shifted(signal: np.ndarray, samples: int) -> np.ndarray:
    if samples > 0:
        return np.concatenate((np.zeros(samples, dtype=signal.dtype), signal[:-samples]))
    if samples < 0:
        amount = abs(samples)
        return np.concatenate((signal[amount:], np.zeros(amount, dtype=signal.dtype)))
    return signal.copy()


@pytest.mark.parametrize("delay_ms", [0, 250, -250])
def test_synthetic_zero_positive_and_negative_offsets(delay_ms: int) -> None:
    source = rich_signal()
    # A delayed sync track produces a negative result; an early track is positive.
    sync = shifted(source, -int(delay_ms * RATE / 1000))
    result = AudioAnalyzer(CONFIG).calculate_delay_from_arrays(
        RATE, source, sync, skip_intro_sec=0, total_segments=8
    )
    assert result.delay_ms == pytest.approx(delay_ms, abs=25)
    assert result.used_segments > 0


def test_short_audio_and_mismatched_rates_are_rejected() -> None:
    analyzer = AudioAnalyzer(CONFIG)
    short = rich_signal(seconds=2)
    with pytest.raises(RuntimeError, match="cok kisa"):
        analyzer.calculate_delay_from_arrays(RATE, short, short, skip_intro_sec=0)
    with pytest.raises(RuntimeError, match="eslesmiyor"):
        analyzer.calculate_delay_from_arrays(
            RATE, rich_signal(), rich_signal(), sync_rate=44_100, skip_intro_sec=0
        )


def test_skip_fallback_and_disk_pcm_match_memory(tmp_path: Path) -> None:
    source = rich_signal()
    sync = shifted(source, 1_200)
    analyzer = AudioAnalyzer(CONFIG)
    memory = analyzer.calculate_delay_from_arrays(
        RATE, source, sync, skip_intro_sec=999, total_segments=8
    )
    source_path = tmp_path / "source.s16le"
    sync_path = tmp_path / "sync.s16le"
    source.tofile(source_path)
    sync.tofile(sync_path)
    disk = analyzer.calculate_delay_from_pcm_files(
        RATE,
        str(source_path),
        str(sync_path),
        skip_intro_sec=999,
        total_segments=8,
    )
    assert memory.skip_fallback and disk.skip_fallback
    assert disk.delay_ms == pytest.approx(memory.delay_ms, abs=15)


def test_weak_outlier_segment_does_not_move_dominant_lag_and_drift_is_reported() -> None:
    analyzer = AudioAnalyzer(CONFIG)
    rows = [
        {"center_sec": float(index * 10), "lag": float(20 + index), "score": 12.0}
        for index in range(6)
    ]
    rows.append({"center_sec": 65.0, "lag": 900.0, "score": 1.1})
    result = analyzer._compute_final_result(
        rows,
        coarse_lag_fine=20,
        coarse_ms=200,
        coarse_score=3,
        fine_rate=100,
        total_segments=len(rows),
        skip_fallback=False,
        local_search_sec=1.0,
    )
    assert result.delay_ms < 300
    assert result.drift_ms_per_min == pytest.approx(60, rel=0.15)
