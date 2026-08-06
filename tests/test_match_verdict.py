"""The analyzer has to be able to say "these two tracks do not match".

Correlation always has a maximum, so an answer always comes out.  Handed the
English audio of one film and the Turkish dub of another, the tool reported
``-1820320 ms`` at confidence 1.87, printed it in the largest type on the
screen, and left the synchronize button enabled — a 30-minute offset between
two feature-length tracks, which is not a delay anyone could ever want.

Every signal needed to catch that was already computed: the confidence sat at
the noise floor, the windows disagreed, and the offset was a quarter of the
runtime.  None of them was consulted.  These tests consult them.
"""

from __future__ import annotations

import numpy as np
import pytest

from audio_sync.config import SYNC_CONFIG
from audio_sync.core.analyzer import AudioAnalyzer
from audio_sync.core.models import AnalysisResult, MatchVerdict, OffsetRegion

RUNTIME = 6547.0


def result(**overrides) -> AnalysisResult:
    base = {
        "delay_ms": -1200.0,
        "coarse_ms": -1200.0,
        "confidence": 6.0,
        "total_segments": 24,
        "used_segments": 22,
        "drift_ms_per_min": None,
        "skip_fallback": False,
        "lag_spread_ms": 12.0,
        "phat_probes": 10,
        "phat_sharpness": 20.0,
    }
    base.update(overrides)
    return AnalysisResult(**base)


def verdict_for(**overrides) -> AnalysisResult:
    return AudioAnalyzer().assess_match(
        result(**overrides),
        src_duration_sec=RUNTIME,
        sync_duration_sec=RUNTIME,
    )


def test_a_clean_measurement_is_reliable() -> None:
    assessed = verdict_for()
    assert assessed.verdict is MatchVerdict.RELIABLE
    assert assessed.verdict_reasons == ()


def test_an_offset_larger_than_the_film_is_no_match() -> None:
    """The reproduction of the reported failure, in one assertion."""
    assessed = verdict_for(delay_ms=-1820320.0, confidence=1.87, lag_spread_ms=89571.0,
                           phat_probes=0, phat_sharpness=0.0)
    assert assessed.verdict is MatchVerdict.NO_MATCH
    assert "reason_offset_implausible" in assessed.verdict_reasons
    assert not assessed.is_usable


def test_the_offset_ceiling_scales_with_the_shorter_track() -> None:
    """Two ten-minute clips cannot legitimately sit five minutes apart."""
    assessed = AudioAnalyzer().assess_match(
        result(delay_ms=200_000.0),
        src_duration_sec=600.0,
        sync_duration_sec=600.0,
    )
    assert assessed.verdict is MatchVerdict.NO_MATCH
    assert "reason_offset_implausible" in assessed.verdict_reasons


def test_a_peak_at_the_noise_floor_is_no_match() -> None:
    assessed = verdict_for(confidence=1.5, phat_probes=0, phat_sharpness=0.0)
    assert assessed.verdict is MatchVerdict.NO_MATCH
    assert "reason_confidence_floor" in assessed.verdict_reasons


def test_sample_accurate_agreement_outranks_a_modest_envelope_score() -> None:
    """A dub mixed differently correlates weakly and is still the same film.

    Measured on a real cross-language pair: the envelope score was 3.1 while
    eleven independent phase-transform probes agreed to within a millisecond.
    Flagging that as doubtful teaches the user to click through the warning
    that actually matters.
    """
    assessed = verdict_for(confidence=3.1, phat_probes=11, phat_sharpness=15.4)
    assert assessed.verdict is MatchVerdict.RELIABLE


def test_a_weak_score_with_no_confirmation_stays_doubtful() -> None:
    assessed = verdict_for(confidence=3.1, phat_probes=0, phat_sharpness=0.0)
    assert assessed.verdict is MatchVerdict.UNCERTAIN
    assert "reason_confidence_low" in assessed.verdict_reasons


def test_scattered_windows_make_the_result_doubtful() -> None:
    assessed = verdict_for(
        lag_spread_ms=SYNC_CONFIG.window_disagreement_warn_ms + 50.0,
    )
    assert assessed.verdict is MatchVerdict.UNCERTAIN
    assert "reason_windows_scattered" in assessed.verdict_reasons


def test_regions_explain_their_own_scatter() -> None:
    """A spliced file is measured against its regions, so it reads as tight."""
    regions = (
        OffsetRegion(0.0, 2838.0, 1496.8, 6, 4.4, 126.0, 1052.8),
        OffsetRegion(2838.0, 4999.0, 1828.7, 9, 3.5, 3042.3, 4906.4),
        OffsetRegion(4999.0, float("inf"), 2165.1, 26, 4.3, 5030.0, 6447.4),
    )
    assessed = verdict_for(delay_ms=1828.9, offset_regions=regions, lag_spread_ms=1.3)
    assert assessed.verdict is MatchVerdict.RELIABLE


# ── The measured spread has to describe the offset that will be applied ──────

FINE_RATE = 50.0


def window(center_sec: float, lag_ms: float, predicted_ms: float | None = None,
           score: float = 6.0) -> dict[str, float]:
    lag = lag_ms / 1000.0 * FINE_RATE
    predicted = (predicted_ms if predicted_ms is not None else lag_ms) / 1000.0 * FINE_RATE
    return {
        "center_sec": center_sec,
        "lag": lag,
        "predicted_lag": predicted,
        "residual_lag": lag - predicted,
        "score": score,
    }


def test_windows_fitted_to_their_own_anchors_still_report_the_real_spread() -> None:
    """An anchored candidate used to report 0.0 ms on a 660 ms staircase.

    ``residual_lag`` is the distance from whatever the candidate predicted, and
    an anchored candidate predicts the anchors it was built from, so its
    residuals collapse to nothing on exactly the files a single delay cannot
    describe.  The user was told the windows agreed perfectly.
    """
    rows = [window(300.0 + i * 300.0, 1500.0 + i * 220.0, predicted_ms=1500.0 + i * 220.0)
            for i in range(12)]
    computed = AudioAnalyzer()._compute_final_result(
        rows, 0, 0.0, 5.0, FINE_RATE, len(rows), False, 3.5,
    )
    assert computed.residual_mad_ms == pytest.approx(0.0, abs=1e-6)
    assert computed.windows_disagree_ms > 300.0


def test_a_stepped_file_claims_no_drift() -> None:
    """A line through a staircase has a slope and it means nothing.

    The three-region pair below fitted at 7.1 ms/min with an R² of 0.96, which
    reads as a confident drift measurement and would have retimed the whole
    track had the step path not happened to take precedence.
    """
    rows = (
        [window(200.0 + i * 120.0, 1497.0, score=8.0) for i in range(10)]
        + [window(3000.0 + i * 120.0, 1829.0, score=8.0) for i in range(10)]
        + [window(5100.0 + i * 120.0, 2165.0, score=8.0) for i in range(10)]
    )
    computed = AudioAnalyzer()._compute_final_result(
        rows, 0, 0.0, 5.0, FINE_RATE, len(rows), False, 3.5,
    )
    assert len(computed.offset_regions) == 3
    assert computed.drift_ms_per_min is None
    assert computed.drift_r2 is None


# ── Anchors must not invent a ramp across an edit ────────────────────────────


def _anchor(center_sec: float, lag_ms: float):
    from audio_sync.core.analyzer import _LagAnchor

    return _LagAnchor(
        center_frame=center_sec * FINE_RATE,
        lag_frame=lag_ms / 1000.0 * FINE_RATE,
        weight=100.0,
    )


def test_nearby_anchors_are_still_interpolated() -> None:
    """Two anchors a minute apart really can be a clock sliding."""
    anchors = (_anchor(100.0, 1000.0), _anchor(160.0, 1060.0))
    predicted = AudioAnalyzer()._predict_lag_from_anchors(
        130.0 * FINE_RATE, anchors, 0.0, FINE_RATE,
    )
    assert predicted / FINE_RATE * 1000.0 == pytest.approx(1030.0, abs=1.0)


def test_a_wide_gap_with_a_large_jump_holds_the_nearer_anchor() -> None:
    """An hour apart and 670 ms adrift is an edit, not a slide.

    Interpolating handed every window in the gap an offset that was true
    nowhere in the film, and the resulting straight-line fit turned a genuine
    three-region staircase into a smooth 7 ms/min drift.
    """
    anchors = (_anchor(1052.0, 1501.0), _anchor(5030.0, 2171.0))
    early = AudioAnalyzer()._predict_lag_from_anchors(
        1500.0 * FINE_RATE, anchors, 0.0, FINE_RATE,
    )
    late = AudioAnalyzer()._predict_lag_from_anchors(
        4500.0 * FINE_RATE, anchors, 0.0, FINE_RATE,
    )
    assert early / FINE_RATE * 1000.0 == pytest.approx(1501.0, abs=1.0)
    assert late / FINE_RATE * 1000.0 == pytest.approx(2171.0, abs=1.0)


# ── Sample-accurate refinement ───────────────────────────────────────────────


def test_phat_refinement_beats_the_feature_grid(tmp_path) -> None:
    """The feature grid quantises to 20 ms; the audio knows better.

    On a real pair the tool reported -10560 ms where the audio says -10527 ms —
    three quarters of a frame, audible on dialogue.  This builds a pair with a
    known offset that deliberately falls between feature frames.
    """
    rate = 16000
    rng = np.random.default_rng(7)
    duration = 90
    signal = rng.normal(0.0, 0.2, size=rate * duration)
    # Bursts of energy give the correlation something to lock onto, the way
    # dialogue and effects do.
    for start in range(0, signal.size - rate, rate * 3):
        signal[start:start + rate // 2] *= 6.0

    # Dropping the first 1234 samples of the reference puts the same content
    # 1234 samples *later* in the target, which is a lag of -77.125 ms — and
    # 77.125 ms is deliberately not a multiple of the 20 ms feature grid.
    true_lag_samples = 1234
    true_lag_ms = -true_lag_samples / rate * 1000.0
    src = signal[true_lag_samples:]
    sync = signal[: signal.size - true_lag_samples]

    def write(path, data):
        scaled = np.clip(data, -1.0, 1.0) * 30000.0
        path.write_bytes(scaled.astype("<i2").tobytes())
        return str(path)

    src_path = write(tmp_path / "src.s16le", src)
    sync_path = write(tmp_path / "sync.s16le", sync)

    analyzer = AudioAnalyzer()
    refined = analyzer._refine_lag_with_phat(
        rate,
        src_path,
        sync_path,
        lag_ms=-60.0,  # 17 ms off, as a feature-grid answer would be
        start_sec=0.0,
        end_sec=src.size / rate,
        src_samples=src.size,
        sync_samples=sync.size,
    )
    assert refined is not None
    lag_ms, sharpness, probes = refined
    assert lag_ms == pytest.approx(true_lag_ms, abs=1.0)
    assert probes >= SYNC_CONFIG.phat_refine_min_agreeing
    assert sharpness >= SYNC_CONFIG.phat_refine_min_sharpness


def test_phat_refinement_declines_on_unrelated_audio(tmp_path) -> None:
    """Corroboration is only worth something if it can fail."""
    rate = 16000
    rng = np.random.default_rng(11)
    a = rng.normal(0.0, 0.2, size=rate * 90)
    b = rng.normal(0.0, 0.2, size=rate * 90)

    def write(path, data):
        path.write_bytes((np.clip(data, -1, 1) * 30000.0).astype("<i2").tobytes())
        return str(path)

    refined = AudioAnalyzer()._refine_lag_with_phat(
        rate,
        write(tmp_path / "a.s16le", a),
        write(tmp_path / "b.s16le", b),
        lag_ms=0.0,
        start_sec=0.0,
        end_sec=90.0,
        src_samples=a.size,
        sync_samples=b.size,
    )
    assert refined is None
