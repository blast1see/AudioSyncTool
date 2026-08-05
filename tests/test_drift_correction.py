"""Drift correction: the maths, the gating, and the resulting filter chain."""

from __future__ import annotations

import numpy as np
import pytest

from audio_sync.config import (
    LEGACY_SYNC_MODE_ALIASES,
    SYNC_CONFIG,
    PcmCodec,
    SyncMode,
    sync_mode_from_name,
)
from audio_sync.core.analyzer import AudioAnalyzer
from audio_sync.core.ffmpeg_wrapper import FFmpegWrapper
from audio_sync.core.models import AnalysisResult, AudioInfo, OutputSampleRate
from audio_sync.core.pipeline import SyncPipeline

INFO = AudioInfo(2, PcmCodec.S16LE, 16, 48_000)
KEEP_RATE = OutputSampleRate.decide(48_000, 48_000, False)


def analysis(**overrides) -> AnalysisResult:
    base = dict(
        delay_ms=150.0,
        coarse_ms=150.0,
        confidence=5.0,
        total_segments=20,
        used_segments=20,
        drift_ms_per_min=60.0,
        skip_fallback=False,
        drift_intercept_ms=0.0,
        drift_r2=0.99,
        drift_span_sec=280.0,
    )
    base.update(overrides)
    return AnalysisResult(**base)


# ── the maths ────────────────────────────────────────────────────────────────


def test_tempo_factor_cancels_the_measured_slope() -> None:
    """A track running 0.1 % fast reads as ~60 ms/min and needs ~0.999x."""
    # ffmpeg atempo=1.001 makes sync[u] == ref[1.001*u], so lag(t) grows by
    # (1 - 1/1.001) sec per second == 59.94 ms/min.
    drift = (1.0 - 1.0 / 1.001) * 60_000.0
    factor = FFmpegWrapper.drift_tempo_factor(drift)
    assert factor == pytest.approx(1.0 / 1.001, rel=1e-9)


def test_zero_drift_is_a_no_op_factor() -> None:
    assert FFmpegWrapper.drift_tempo_factor(0.0) == 1.0


# ── the fit ──────────────────────────────────────────────────────────────────


def test_drift_fit_recovers_slope_and_intercept() -> None:
    t = np.linspace(0.0, 300.0, 25)
    y = 40.0 + 1.5 * t  # 40 ms at t=0, 90 ms/min
    slope, intercept, r2 = AudioAnalyzer._fit_drift_line(t, y, np.ones_like(t))
    assert slope == pytest.approx(1.5, rel=1e-6)
    assert intercept == pytest.approx(40.0, rel=1e-6)
    assert r2 == pytest.approx(1.0, abs=1e-9)


def test_drift_fit_reports_low_r2_for_scatter() -> None:
    rng = np.random.default_rng(1234)
    t = np.linspace(0.0, 300.0, 25)
    y = rng.normal(0.0, 50.0, t.size)
    _slope, _intercept, r2 = AudioAnalyzer._fit_drift_line(t, y, np.ones_like(t))
    assert r2 < 0.5


def test_drift_fit_rejects_degenerate_input() -> None:
    t = np.full(8, 12.0)
    assert AudioAnalyzer._fit_drift_line(t, t, np.ones_like(t)) is None


# ── the gate ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"drift_r2": 0.4}, "fit explains too little"),
        ({"used_segments": 3}, "too few segments"),
        ({"drift_span_sec": 10.0}, "measured over too short a span"),
        ({"drift_ms_per_min": 0.2}, "slope below the action threshold"),
        ({"drift_intercept_ms": None}, "no intercept to anchor on"),
    ],
)
def test_unreliable_drift_is_not_applied(overrides, reason) -> None:
    drift, delay = SyncPipeline.resolve_drift_correction(
        analysis(**overrides), enabled=True, config=SYNC_CONFIG
    )
    assert drift is None, reason
    assert delay == 150.0, "must fall back to the median offset"


def test_reliable_drift_is_applied_with_the_intercept() -> None:
    drift, delay = SyncPipeline.resolve_drift_correction(
        analysis(drift_intercept_ms=12.0), enabled=True, config=SYNC_CONFIG
    )
    assert drift == 60.0
    # The intercept, not the 150 ms median — that is the whole point.
    assert delay == 12.0


def test_drift_correction_can_be_switched_off() -> None:
    drift, delay = SyncPipeline.resolve_drift_correction(
        analysis(), enabled=False, config=SYNC_CONFIG
    )
    assert drift is None
    assert delay == 150.0


# ── the filter chain ─────────────────────────────────────────────────────────


def build(monkeypatch, **kwargs) -> str:
    monkeypatch.setattr("audio_sync.core.ffmpeg_wrapper.resolve_tool", lambda name: name)
    cmd, _summary = FFmpegWrapper().build_sync_command(
        "sync.wav", kwargs.pop("delay_ms", 0.0), INFO, KEEP_RATE, "out.wav", **kwargs
    )
    return cmd[cmd.index("-filter_complex") + 1]


def test_no_drift_means_no_tempo_stage(monkeypatch) -> None:
    chain = build(monkeypatch, delay_ms=250.0)
    assert "atempo" not in chain
    assert "rubberband" not in chain
    assert "adelay=250.000|250.000:all=1" in chain


def test_drift_stage_precedes_the_offset(monkeypatch) -> None:
    """Order matters: a tempo change downstream would rescale the offset."""
    chain = build(monkeypatch, delay_ms=250.0, drift_ms_per_min=60.0)
    assert chain.index("atempo") < chain.index("adelay")


def test_offset_is_rescaled_by_the_tempo_factor(monkeypatch) -> None:
    chain = build(monkeypatch, delay_ms=250.0, drift_ms_per_min=60.0)
    factor = FFmpegWrapper.drift_tempo_factor(60.0)
    assert f"adelay={250.0 / factor:.3f}" in chain


def test_negative_offset_trims_the_head(monkeypatch) -> None:
    chain = build(monkeypatch, delay_ms=-250.0)
    assert "atrim=start=0.250000" in chain
    assert "asetpts=PTS-STARTPTS" in chain


def test_zero_offset_emits_no_offset_stage(monkeypatch) -> None:
    chain = build(monkeypatch, delay_ms=0.0)
    assert "adelay" not in chain
    assert "atrim" not in chain
    assert "acopy" in chain


def test_rubberband_only_engages_when_there_is_drift(monkeypatch) -> None:
    """v2.3 inserted rubberband=tempo=1.0 unconditionally — a lossy no-op."""
    idle = build(monkeypatch, delay_ms=250.0, sync_mode=SyncMode.RUBBERBAND)
    assert "rubberband" not in idle

    working = build(
        monkeypatch, delay_ms=250.0, sync_mode=SyncMode.RUBBERBAND, drift_ms_per_min=60.0
    )
    assert "rubberband=tempo=" in working
    assert "atempo" not in working


def test_aresample_mode_appends_the_async_stage(monkeypatch) -> None:
    chain = build(monkeypatch, delay_ms=250.0, sync_mode=SyncMode.ARESAMPLE)
    assert chain.index("adelay") < chain.index("aresample=async=1")


# ── retired modes ────────────────────────────────────────────────────────────


def test_every_surviving_mode_is_behaviourally_distinct(monkeypatch) -> None:
    chains = {
        mode: build(monkeypatch, delay_ms=250.0, drift_ms_per_min=60.0, sync_mode=mode)
        for mode in SyncMode
    }
    assert len(set(chains.values())) == len(SyncMode), chains


@pytest.mark.parametrize("legacy", sorted(LEGACY_SYNC_MODE_ALIASES))
def test_legacy_mode_names_still_resolve(legacy: str) -> None:
    assert sync_mode_from_name(legacy) is LEGACY_SYNC_MODE_ALIASES[legacy]


def test_unknown_mode_name_falls_back_to_default() -> None:
    assert sync_mode_from_name("NOPE").is_default
