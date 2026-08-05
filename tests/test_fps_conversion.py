"""Frame-rate conversion arithmetic, and recognising a drift as an FPS problem.

A frame-rate mismatch is a fixed-ratio speed error, so it drifts by a very
specific amount: ~60 ms/min for 24 vs 23.976, ~2.5 s/min for PAL.  A measured
slope landing on one of those is not a coincidence, and saying so turns "your
audio drifts" into a setting the user can pick.
"""

from __future__ import annotations

import pytest

from audio_sync.config import FpsConversion, match_drift_to_fps
from audio_sync.core.models import AnalysisResult
from audio_sync.core.pipeline import SyncPipeline


@pytest.mark.parametrize("conversion", list(FpsConversion))
def test_tempo_ratio_is_the_inverse_of_the_applied_tempo(conversion) -> None:
    """``apply_fps_conversion`` feeds ffmpeg ``1 / tempo_ratio``."""
    assert 1.0 / conversion.tempo_ratio == pytest.approx(
        conversion.target_fps / conversion.source_fps
    )


@pytest.mark.parametrize("conversion", list(FpsConversion))
def test_a_conversion_undoes_the_drift_it_claims_to(conversion) -> None:
    """The two must agree, or the hint below would point at the wrong entry."""
    applied_tempo = 1.0 / conversion.tempo_ratio
    assert conversion.corrects_drift_ms_per_min == pytest.approx(
        (1.0 - applied_tempo) * 60_000.0
    )


def test_the_ntsc_pair_is_about_sixty_milliseconds_a_minute() -> None:
    """The number every 24 vs 23.976 mismatch produces — an hour off by 3.6 s."""
    assert FpsConversion.FPS_24_TO_23976.corrects_drift_ms_per_min == pytest.approx(
        60.0, abs=0.5
    )
    assert FpsConversion.FPS_23976_TO_24.corrects_drift_ms_per_min == pytest.approx(
        -60.1, abs=0.5
    )


@pytest.mark.parametrize(
    ("measured", "expected"),
    [
        (60.97, FpsConversion.FPS_24_TO_23976),   # measured on a real 24 fps dub
        (-60.4, FpsConversion.FPS_23976_TO_24),   # measured on a real 132-min film
        (2457.0, FpsConversion.FPS_25_TO_23976),  # PAL speed-up
        (-2562.0, FpsConversion.FPS_23976_TO_25),
    ],
)
def test_real_measurements_are_identified(measured: float, expected) -> None:
    assert match_drift_to_fps(measured) is expected


@pytest.mark.parametrize("measured", [0.0, 0.07, -2.03, 7.13, 25.0, -500.0])
def test_ordinary_drift_is_not_blamed_on_frame_rates(measured: float) -> None:
    """Most drift is just clock skew; a wrong hint is worse than none."""
    assert match_drift_to_fps(measured) is None


def test_the_tolerance_is_configurable() -> None:
    assert match_drift_to_fps(50.0) is None
    assert match_drift_to_fps(50.0, tolerance_ms_per_min=15.0) is FpsConversion.FPS_24_TO_23976


def test_the_nearest_conversion_wins() -> None:
    """25->24 and 25->23.976 are close; the closer one must be chosen."""
    near = FpsConversion.FPS_25_TO_24.corrects_drift_ms_per_min
    assert match_drift_to_fps(near + 0.5) is FpsConversion.FPS_25_TO_24


# ── the direct probe, and how the two signals combine ────────────────────────


def result_with(**overrides) -> AnalysisResult:
    base = dict(
        delay_ms=0.0, coarse_ms=0.0, confidence=3.0, total_segments=20,
        used_segments=15, drift_ms_per_min=None, skip_fallback=False,
    )
    base.update(overrides)
    return AnalysisResult(**base)


def test_the_direct_probe_is_trusted_over_the_slope() -> None:
    """The probe works where the slope cannot be measured at all.

    On a 132-minute pair the offset slid 7.8 s and the fitted slope came back as
    -2 ms/min — useless — while resampling the coarse features identified the
    conversion correctly.
    """
    analysis = result_with(
        suspected_fps_conversion="FPS_23976_TO_24", drift_ms_per_min=-2.03
    )
    assert SyncPipeline.suspected_fps_conversion(analysis) is FpsConversion.FPS_23976_TO_24


def test_the_slope_still_answers_when_the_probe_is_silent() -> None:
    analysis = result_with(drift_ms_per_min=60.97)
    assert SyncPipeline.suspected_fps_conversion(analysis) is FpsConversion.FPS_24_TO_23976


def test_no_signal_means_no_suggestion() -> None:
    assert SyncPipeline.suspected_fps_conversion(result_with()) is None
    assert SyncPipeline.suspected_fps_conversion(
        result_with(drift_ms_per_min=0.07)
    ) is None


def test_an_unknown_stored_name_does_not_crash_the_run() -> None:
    analysis = result_with(suspected_fps_conversion="FPS_FROM_THE_FUTURE")
    assert SyncPipeline.suspected_fps_conversion(analysis) is None


def test_resampling_features_stretches_the_time_axis() -> None:
    import numpy as np

    from audio_sync.core.analyzer import AudioAnalyzer

    features = np.arange(100, dtype=np.float32)
    stretched = AudioAnalyzer._resample_features(features, 2.0)
    assert stretched.size == 200
    # Endpoints are preserved; the middle is interpolated.
    assert stretched[0] == pytest.approx(0.0)
    assert stretched[-1] == pytest.approx(99.0)
    assert stretched[100] == pytest.approx(49.5, abs=1.0)


def test_the_probe_finds_a_ratio_it_was_given() -> None:
    import numpy as np

    from audio_sync.core.analyzer import AudioAnalyzer

    rng = np.random.default_rng(21)
    reference = rng.normal(0, 1, 6_000).astype(np.float32)
    for position in range(30, 5_970, 53):
        reference[position] += 8.0

    conversion = FpsConversion.FPS_24_TO_23976
    # A target running at the wrong rate is the reference compressed by it.
    target = AudioAnalyzer._resample_features(reference, 1.0 / conversion.tempo_ratio)

    found = AudioAnalyzer().detect_rate_mismatch(reference, target)
    assert found is not None
    assert found[0] is conversion


# ── acting on the detection ──────────────────────────────────────────────────


def test_a_conversion_that_helps_is_kept() -> None:
    logs: list[str] = []
    before = result_with(used_segments=31, residual_mad_ms=200.0)
    after = result_with(used_segments=38, residual_mad_ms=20.0)

    chosen, applied = SyncPipeline._better_analysis(
        before, after, FpsConversion.FPS_23976_TO_24, logs.append
    )
    assert chosen is after
    assert applied is FpsConversion.FPS_23976_TO_24
    assert any("200" in line and "20" in line for line in logs)


def test_a_conversion_that_does_not_help_is_discarded() -> None:
    """Detection has been reliable, but acting on it changes the audio."""
    logs: list[str] = []
    before = result_with(used_segments=40, residual_mad_ms=0.0)
    after = result_with(used_segments=12, residual_mad_ms=180.0)

    chosen, applied = SyncPipeline._better_analysis(
        before, after, FpsConversion.FPS_25_TO_24, logs.append
    )
    assert chosen is before
    assert applied is None
    assert any("did not improve" in line for line in logs)


def test_a_tie_is_broken_by_how_many_windows_validated() -> None:
    before = result_with(used_segments=20, residual_mad_ms=20.0)
    after = result_with(used_segments=35, residual_mad_ms=20.0)

    chosen, applied = SyncPipeline._better_analysis(
        before, after, FpsConversion.FPS_24_TO_23976, lambda _m: None
    )
    assert chosen is after
    assert applied is FpsConversion.FPS_24_TO_23976


def test_a_tie_with_no_extra_windows_keeps_the_original_audio() -> None:
    same = result_with(used_segments=20, residual_mad_ms=20.0)
    chosen, applied = SyncPipeline._better_analysis(
        same, result_with(used_segments=20, residual_mad_ms=20.0),
        FpsConversion.FPS_24_TO_23976, lambda _m: None,
    )
    assert chosen is same
    assert applied is None


def test_matching_content_at_the_same_rate_reports_nothing() -> None:
    import numpy as np

    from audio_sync.core.analyzer import AudioAnalyzer

    rng = np.random.default_rng(5)
    reference = rng.normal(0, 1, 6_000).astype(np.float32)
    for position in range(30, 5_970, 53):
        reference[position] += 8.0

    assert AudioAnalyzer().detect_rate_mismatch(reference, reference.copy()) is None
