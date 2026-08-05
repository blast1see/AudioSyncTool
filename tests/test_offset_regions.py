"""Step detection and piecewise splicing.

A broadcast dub is often not one delay away from the reference: an ad break cut
differently, a reel change, or a different edit leaves a *step* partway through
the film. Neither a constant offset nor a straight line describes that.
"""

from __future__ import annotations

import math

import pytest

from audio_sync.config import SYNC_CONFIG, PcmCodec, SyncConfig, SyncMode
from audio_sync.core.analyzer import AudioAnalyzer
from audio_sync.core.ffmpeg_wrapper import FFmpegWrapper
from audio_sync.core.models import AnalysisResult, AudioInfo, OffsetRegion, OutputSampleRate
from audio_sync.core.pipeline import SyncPipeline

FINE_RATE = 50.0
INFO = AudioInfo(2, PcmCodec.S16LE, 16, 48_000)
KEEP_RATE = OutputSampleRate.decide(48_000, 48_000, False)


def window(center_sec: float, lag_ms: float, score: float = 5.0) -> dict[str, float]:
    lag = lag_ms / 1000.0 * FINE_RATE
    return {
        "center_sec": center_sec,
        "lag": lag,
        "predicted_lag": lag,
        "residual_lag": lag,
        "score": score,
    }


def series(spec: list[tuple[float, float, float]]) -> list[dict[str, float]]:
    """Build windows from (start_sec, end_sec, lag_ms) runs, one per 30 s."""
    rows: list[dict[str, float]] = []
    for start, end, lag in spec:
        t = start
        while t < end:
            rows.append(window(t, lag))
            t += 30.0
    return rows


# ── detection ────────────────────────────────────────────────────────────────


def test_detects_the_real_step_from_the_reference_film() -> None:
    """~110 min at -9490 ms, then ~18 min at -9630 ms — measured on real files."""
    rows = series([(120.0, 6600.0, -9490.0), (6600.0, 8280.0, -9630.0)])
    regions = AudioAnalyzer()._detect_offset_regions(rows, FINE_RATE)

    assert len(regions) == 2, regions
    assert regions[0].lag_ms == pytest.approx(-9490.0, abs=5.0)
    assert regions[1].lag_ms == pytest.approx(-9630.0, abs=5.0)
    assert 6500.0 < regions[1].start_sec < 6700.0
    assert regions[0].start_sec == 0.0
    assert math.isinf(regions[-1].end_sec)


def test_a_clean_constant_offset_yields_no_regions() -> None:
    rows = series([(120.0, 8000.0, -1200.0)])
    assert AudioAnalyzer()._detect_offset_regions(rows, FINE_RATE) == ()


def test_noise_around_one_offset_does_not_fabricate_a_step() -> None:
    import numpy as np

    rng = np.random.default_rng(7)
    rows = [
        window(120.0 + i * 30.0, -1200.0 + float(rng.normal(0, 12.0)))
        for i in range(260)
    ]
    assert AudioAnalyzer()._detect_offset_regions(rows, FINE_RATE) == ()


def test_a_gradual_drift_is_not_mistaken_for_a_step() -> None:
    """Drift is handled by the tempo path; splicing it would be wrong."""
    rows = [window(120.0 + i * 30.0, -1000.0 + i * 0.5) for i in range(260)]
    regions = AudioAnalyzer()._detect_offset_regions(rows, FINE_RATE)
    # A ramp has no single jump large enough to beat the cost threshold.
    assert len(regions) <= 2, [r.lag_ms for r in regions]


def test_a_step_below_the_threshold_is_left_alone() -> None:
    """20 ms is inaudible; cutting the audio for it is a net loss."""
    rows = series([(120.0, 4000.0, -1200.0), (4000.0, 8000.0, -1220.0)])
    assert AudioAnalyzer()._detect_offset_regions(rows, FINE_RATE) == ()


def test_a_short_region_is_not_split_off() -> None:
    """A 40 s tail cannot outvote the film; it is more likely bad windows."""
    rows = series([(120.0, 7800.0, -1200.0), (7800.0, 7840.0, -1400.0)])
    assert AudioAnalyzer()._detect_offset_regions(rows, FINE_RATE) == ()


def test_detection_can_be_disabled() -> None:
    rows = series([(120.0, 6600.0, -9490.0), (6600.0, 8280.0, -9630.0)])
    analyzer = AudioAnalyzer(config=SyncConfig(step_detection_enabled=False))
    assert analyzer._detect_offset_regions(rows, FINE_RATE) == ()


def test_three_regions_are_found_when_there_are_three() -> None:
    rows = series([
        (120.0, 2600.0, -500.0),
        (2600.0, 5200.0, -700.0),
        (5200.0, 8000.0, -900.0),
    ])
    regions = AudioAnalyzer()._detect_offset_regions(rows, FINE_RATE)
    assert len(regions) == 3, [r.lag_ms for r in regions]
    assert [round(r.lag_ms, -1) for r in regions] == [-500.0, -700.0, -900.0]


# ── outlier rejection ────────────────────────────────────────────────────────


def test_one_wild_lag_does_not_hijack_the_segmentation() -> None:
    """The real failure: a lone -7720 ms window with score 176.

    Splitting that window off removed more L1 cost than the genuine 133 ms step
    did, so the greedy search took it and the real boundary was never found.
    """
    rows = series([(120.0, 6600.0, -9490.0), (6600.0, 8280.0, -9620.0)])
    rows.append(window(8256.0, -7720.0, 176.5))
    rows.sort(key=lambda r: r["center_sec"])

    regions = AudioAnalyzer()._detect_offset_regions(rows, FINE_RATE)
    assert len(regions) == 2, [r.lag_ms for r in regions]
    assert regions[0].lag_ms == pytest.approx(-9490.0, abs=10.0)
    assert regions[1].lag_ms == pytest.approx(-9620.0, abs=10.0)


def test_neighbouring_outliers_do_not_take_good_windows_with_them() -> None:
    """Rejecting everything in one sweep discarded the windows near the step.

    Two bad lags poison the neighbourhood median of the good windows beside
    them, and those are exactly the windows closest to the boundary.
    """
    import numpy as np

    lags = np.array(
        [-9490.0] * 8 + [-9890.0, -9556.0] + [-9474.0, -9480.0] + [-9620.0] * 8
    )
    keep = AudioAnalyzer()._reject_isolated_outliers(lags)

    assert not keep[8] and not keep[9], "the two bad lags must go"
    assert keep[10] and keep[11], "the good windows beside them must stay"


def test_rejection_cannot_eat_most_of_the_data() -> None:
    import numpy as np

    rng = np.random.default_rng(3)
    lags = rng.normal(0.0, 400.0, 40)
    keep = AudioAnalyzer()._reject_isolated_outliers(lags)
    assert keep.sum() >= len(lags) * 0.6


# ── gating ───────────────────────────────────────────────────────────────────


def analysis(regions: tuple[OffsetRegion, ...]) -> AnalysisResult:
    return AnalysisResult(
        delay_ms=-9490.0, coarse_ms=-9490.0, confidence=5.0,
        total_segments=40, used_segments=35, drift_ms_per_min=2.0,
        skip_fallback=False, drift_intercept_ms=-9490.0, drift_r2=0.95,
        drift_span_sec=7000.0, offset_regions=regions,
    )


REGIONS = (
    OffsetRegion(0.0, 6600.0, -9490.0, 20, 5.0),
    OffsetRegion(6600.0, math.inf, -9630.0, 6, 5.0),
)


def test_regions_are_used_when_present_and_enabled() -> None:
    assert SyncPipeline.resolve_offset_regions(analysis(REGIONS), enabled=True) == REGIONS


def test_regions_can_be_switched_off() -> None:
    assert SyncPipeline.resolve_offset_regions(analysis(REGIONS), enabled=False) == ()


def test_a_single_region_is_not_a_step() -> None:
    one = (OffsetRegion(0.0, math.inf, -9490.0, 30, 5.0),)
    assert SyncPipeline.resolve_offset_regions(analysis(one), enabled=True) == ()


def test_drift_correction_stands_down_when_the_offset_steps() -> None:
    """Fitting a line through a step produces a slope that means nothing."""
    stepped = analysis(REGIONS)
    # The measurement exists and looks good on its own terms — R² 0.95 — which
    # is exactly why the step has to veto it rather than the fit quality.
    assert stepped.has_drift_measurement
    assert stepped.drift_r2 > SYNC_CONFIG.drift_correction_min_r2

    drift, _delay = SyncPipeline.resolve_drift_correction(
        stepped, enabled=True, config=SYNC_CONFIG
    )
    assert drift is None


# ── the filter graph ─────────────────────────────────────────────────────────


def command_for(monkeypatch, regions, **kwargs) -> list[str]:
    monkeypatch.setattr("audio_sync.core.ffmpeg_wrapper.resolve_tool", lambda name: name)
    cmd, _summary = FFmpegWrapper().build_sync_command(
        "sync.wav", 0.0, INFO, KEEP_RATE, "out.wav", offset_regions=regions, **kwargs
    )
    return cmd


def chain_for(monkeypatch, regions, **kwargs) -> str:
    cmd = command_for(monkeypatch, regions, **kwargs)
    return cmd[cmd.index("-filter_complex") + 1]


def test_piecewise_graph_trims_each_region_and_concatenates(monkeypatch) -> None:
    chain = chain_for(monkeypatch, REGIONS)
    # The splice ends at [spliced] so shared tail stages can still be appended.
    assert "concat=n=2:v=0:a=1[spliced]" in chain
    assert chain.rstrip().endswith("[out]")
    assert chain.count("atrim=start=") == 2


def test_each_region_reads_its_own_input(monkeypatch) -> None:
    """Sharing one decoder via ``asplit`` deadlocks on some FFmpeg builds.

    ``concat`` drains the first piece while the later branches are handed frames
    they cannot use yet. It ran in under a second locally and hung for over half
    an hour on the FFmpeg shipped with Ubuntu, so each region gets its own input.
    """
    cmd = command_for(monkeypatch, REGIONS)
    chain = cmd[cmd.index("-filter_complex") + 1]

    assert "asplit" not in chain
    assert cmd.count("-i") == len(REGIONS)
    for index in range(len(REGIONS)):
        assert f"[{index}:a]" in chain


def test_mode_tail_still_applies_to_a_spliced_track(monkeypatch) -> None:
    """Repair timestamps answers a question orthogonal to how many offsets exist."""
    chain = chain_for(monkeypatch, REGIONS, sync_mode=SyncMode.ARESAMPLE)
    assert "concat=n=2:v=0:a=1[spliced]" in chain
    assert "[spliced]aresample=async=1[out]" in chain


def test_each_region_is_cut_at_its_own_offset(monkeypatch) -> None:
    chain = chain_for(monkeypatch, REGIONS)
    # Region 0 covers reference 0–6600 s at -9490 ms, so it reads the source
    # from 9.490 s (the reference starts 9.49 s into this track).
    assert "atrim=start=9.490000:end=6609.490000" in chain
    # Region 1 starts at reference 6600 s with a different offset, and runs out.
    assert "atrim=start=6609.630000" in chain
    assert "atrim=start=6609.630000:end=" not in chain


def test_internal_joins_are_faded_to_avoid_clicks(monkeypatch) -> None:
    chain = chain_for(monkeypatch, REGIONS)
    assert "afade=t=out" in chain
    assert "afade=t=in:st=0" in chain
    # The outer edges of the whole track must not be faded.
    assert chain.count("afade=t=in") == 1
    assert chain.count("afade=t=out") == 1


def test_a_region_starting_before_the_track_is_padded_not_seeked(monkeypatch) -> None:
    """A positive lag means the reference begins before this track does."""
    regions = (
        OffsetRegion(0.0, 3000.0, 400.0, 20, 5.0),
        OffsetRegion(3000.0, math.inf, 600.0, 20, 5.0),
    )
    chain = chain_for(monkeypatch, regions)
    assert "atrim=start=0.000000" in chain
    assert "adelay=400.000|400.000:all=1" in chain


def test_piecewise_needs_at_least_two_regions() -> None:
    with pytest.raises(ValueError, match="at least two"):
        FFmpegWrapper().build_piecewise_filter(
            (OffsetRegion(0.0, math.inf, 0.0, 5, 5.0),), 2
        )


def test_regions_take_precedence_over_a_single_delay(monkeypatch) -> None:
    monkeypatch.setattr("audio_sync.core.ffmpeg_wrapper.resolve_tool", lambda name: name)
    cmd, summary = FFmpegWrapper().build_sync_command(
        "sync.wav", 1234.0, INFO, KEEP_RATE, "out.wav",
        drift_ms_per_min=50.0, offset_regions=REGIONS,
    )
    chain = cmd[cmd.index("-filter_complex") + 1]
    assert "atempo" not in chain
    assert "adelay=1234" not in chain
    assert "piecewise" in summary
