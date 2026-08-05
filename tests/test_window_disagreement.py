"""Reporting when the validated windows do not agree with each other.

A high correlation score says each window matched something well; it says
nothing about whether the windows agree with *each other*.  Two sources that
are different cuts, or that drift further apart than the search window can
follow, produce confident windows scattered over hundreds of milliseconds — and
the single reported delay is then only right for whichever stretch of the film
dominated the vote.  Measured on a 132-minute cross-language pair, the windows
disagreed by 200 ms and the produced file was seconds out at the ends.
"""

from __future__ import annotations

import numpy as np
import pytest

from audio_sync.config import SYNC_CONFIG
from audio_sync.core.analyzer import AudioAnalyzer
from audio_sync.core.models import AnalysisResult

FINE_RATE = 50.0


def window(center_sec: float, lag_ms: float, score: float = 6.0) -> dict[str, float]:
    lag = lag_ms / 1000.0 * FINE_RATE
    return {
        "center_sec": center_sec,
        "lag": lag,
        "predicted_lag": lag,
        "residual_lag": lag,
        "score": score,
    }


def result_for(rows: list[dict[str, float]]) -> AnalysisResult:
    return AudioAnalyzer()._compute_final_result(
        rows, 0, 0.0, 5.0, FINE_RATE, len(rows), False, 3.5
    )


def test_agreeing_windows_report_a_small_spread() -> None:
    rng = np.random.default_rng(11)
    rows = [
        window(120.0 + i * 60.0, -1200.0 + float(rng.normal(0, 8.0)))
        for i in range(30)
    ]
    assert result_for(rows).windows_disagree_ms < 30.0


def test_scattered_windows_report_a_large_spread() -> None:
    rng = np.random.default_rng(11)
    rows = [
        window(120.0 + i * 60.0, -1200.0 + float(rng.normal(0, 250.0)))
        for i in range(30)
    ]
    spread = result_for(rows).windows_disagree_ms
    assert spread >= SYNC_CONFIG.window_disagreement_warn_ms, spread


def test_spread_is_zero_when_nothing_validated() -> None:
    assert result_for([]).windows_disagree_ms == 0.0


@pytest.mark.gui
def test_scatter_downgrades_the_readout_even_at_a_good_score() -> None:
    """A confident-looking score must not present a result that cannot hold."""
    from audio_sync.i18n import t
    from audio_sync.ui.app import AudioSyncApp

    try:
        app = AudioSyncApp()
    except Exception as exc:  # pragma: no cover - environment problem
        pytest.skip(f"GUI unavailable: {exc}")

    try:
        app.withdraw()
        scattered = AnalysisResult(
            delay_ms=32873.0, coarse_ms=32672.0, confidence=4.5,
            total_segments=56, used_segments=31, drift_ms_per_min=-2.0,
            skip_fallback=False, residual_mad_ms=200.0,
        )
        app._display_analysis_result(scattered)
        app.update()

        detail = app._readout_detail.cget("text")
        assert t("confidence_weak") in detail
        assert t("confidence_strong") not in detail
        assert "200" in detail
    finally:
        app.destroy()
