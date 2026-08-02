"""Audio delay analysis engine."""

from __future__ import annotations

import math
import os
import warnings
from dataclasses import dataclass, field, replace
from typing import Iterator

import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, correlate, fftconvolve, sosfilt, sosfiltfilt

from audio_sync.config import SYNC_CONFIG, SyncConfig
from audio_sync.core.models import AnalysisResult

ANALYSIS_DTYPE = np.float32
_INT16_INFO = np.iinfo(np.int16)
_INT16_SCALE = ANALYSIS_DTYPE(1.0 / max(abs(_INT16_INFO.min), _INT16_INFO.max))


@dataclass(frozen=True)
class _FeatureBundle:
    coarse: np.ndarray
    fine: np.ndarray


@dataclass(frozen=True)
class _FingerprintEstimate:
    delay_ms: float
    votes: int
    score: float
    anchors: tuple["_FingerprintAnchor", ...] = ()
    drift_ms_per_min: float | None = None


@dataclass(frozen=True)
class _FingerprintAnchor:
    center_sec: float
    lag_ms: float
    weight: float


@dataclass(frozen=True)
class _LagAnchor:
    center_frame: float
    lag_frame: float
    weight: float


@dataclass(frozen=True)
class _CandidateSpec:
    coarse_lag_fine: int
    coarse_ms: float
    score: float
    anchors: tuple[_LagAnchor, ...] = ()
    local_search_sec: float | None = None


@dataclass
class _StreamingFeatureBuilder:
    """Build one feature stream incrementally from normalized PCM chunks."""

    rate: int
    hop_ms: int
    smooth_ms: int
    config: SyncConfig
    apply_bandpass: bool = True
    feature_parts: list[np.ndarray] = field(default_factory=list)
    prev_filtered_sample: float = 0.0
    smooth_pending: np.ndarray = field(
        default_factory=lambda: np.empty(0, dtype=ANALYSIS_DTYPE),
    )
    pending_start: int = 0
    emitted_until: int = 0

    def __post_init__(self) -> None:
        self._hop = max(1, int(self.rate * self.hop_ms / 1000.0))
        self._smooth = max(8, int(self.rate * self.smooth_ms / 1000.0))
        self._left = (self._smooth - 1) // 2
        self._right = self._smooth - 1 - self._left
        self._feature_rate = self.rate / self._hop
        self._kernel = np.full(
            self._smooth,
            ANALYSIS_DTYPE(1.0 / self._smooth),
            dtype=ANALYSIS_DTYPE,
        )

        self._sos: np.ndarray | None = None
        self._zi: np.ndarray | None = None

        if self.apply_bandpass and self.rate >= 1000:
            low = self.config.bandpass_low_hz
            high = min(self.config.bandpass_high_hz, self.rate * 0.45)
            if high > low * 1.2:
                self._sos = butter(
                    self.config.bandpass_order,
                    [low, high],
                    btype="bandpass",
                    fs=self.rate,
                    output="sos",
                )
                self._zi = np.zeros((self._sos.shape[0], 2), dtype=ANALYSIS_DTYPE)

    def process(self, chunk: np.ndarray) -> None:
        """Consume one normalized chunk."""
        if chunk.size == 0:
            return

        filtered = self._filter(chunk)
        prev = ANALYSIS_DTYPE(self.prev_filtered_sample)
        dx = np.diff(filtered, prepend=prev)
        self.prev_filtered_sample = float(filtered[-1])

        emphasis = (
            self.config.emphasis_signal_weight * np.abs(filtered)
            + self.config.emphasis_diff_weight * np.abs(dx)
        )
        self._append_smoothed(emphasis)

    def finalize(self) -> tuple[np.ndarray, float]:
        """Return the final feature vector and its sample rate."""
        if self.smooth_pending.size:
            conv = np.convolve(self.smooth_pending, self._kernel, mode="same")
            emit_local_start = max(0, self.emitted_until - self.pending_start)
            if conv.size > emit_local_start:
                env_chunk = np.asarray(
                    np.log1p(conv[emit_local_start:] * self.config.envelope_gain),
                    dtype=ANALYSIS_DTYPE,
                )
                self._append_feature_samples(env_chunk, self.emitted_until)
                self.emitted_until = self.pending_start + conv.size

        if self.feature_parts:
            feat = np.concatenate(self.feature_parts)
        else:
            feat = np.empty(0, dtype=ANALYSIS_DTYPE)

        if feat.size < self.config.min_feature_length:
            raise RuntimeError("Analiz icin yeterli ornek olusmadi.")

        feat = np.asarray(np.diff(feat, prepend=feat[0]), dtype=ANALYSIS_DTYPE)
        np.maximum(feat, 0.0, out=feat)
        feat -= ANALYSIS_DTYPE(np.median(feat))

        std = float(np.std(feat))
        if std > 1e-9:
            feat /= ANALYSIS_DTYPE(std)
        else:
            feat.fill(0.0)

        self.feature_parts.clear()
        self.smooth_pending = np.empty(0, dtype=ANALYSIS_DTYPE)
        self.pending_start = 0
        self.emitted_until = 0

        return feat, self._feature_rate

    def _filter(self, chunk: np.ndarray) -> np.ndarray:
        if self._sos is None or self._zi is None:
            return np.asarray(chunk, dtype=ANALYSIS_DTYPE)

        filtered, self._zi = sosfilt(self._sos, chunk, zi=self._zi)
        return np.asarray(filtered, dtype=ANALYSIS_DTYPE)

    def _append_smoothed(self, emphasis: np.ndarray) -> None:
        if emphasis.size == 0:
            return

        if self.smooth_pending.size:
            self.smooth_pending = np.concatenate((self.smooth_pending, emphasis))
        else:
            self.smooth_pending = np.asarray(emphasis, dtype=ANALYSIS_DTYPE)

        conv = np.convolve(self.smooth_pending, self._kernel, mode="same")
        stable_local_end = max(0, self.smooth_pending.size - self._right)
        emit_local_start = max(0, self.emitted_until - self.pending_start)

        if stable_local_end > emit_local_start:
            env_chunk = np.asarray(
                np.log1p(conv[emit_local_start:stable_local_end] * self.config.envelope_gain),
                dtype=ANALYSIS_DTYPE,
            )
            self._append_feature_samples(env_chunk, self.emitted_until)
            self.emitted_until = self.pending_start + stable_local_end

        retain_from = max(0, stable_local_end - self._left)
        if retain_from > 0:
            self.smooth_pending = self.smooth_pending[retain_from:]
            self.pending_start += retain_from

    def _append_feature_samples(self, env_chunk: np.ndarray, env_start: int) -> None:
        if env_chunk.size == 0:
            return

        first = (-env_start) % self._hop
        feat_chunk = env_chunk[first::self._hop]
        if feat_chunk.size:
            self.feature_parts.append(np.asarray(feat_chunk, dtype=ANALYSIS_DTYPE))


class AudioAnalyzer:
    """Robust two-stage delay analysis for mono PCM inputs."""

    def __init__(self, config: SyncConfig = SYNC_CONFIG) -> None:
        self._config = config

    def calculate_delay(
        self,
        src_wav: str,
        sync_wav: str,
        skip_intro_sec: float = 120.0,
        total_segments: int = 12,
    ) -> AnalysisResult:
        """Calculate delay from two mono WAV files."""
        rate1, data1 = wavfile.read(src_wav)
        rate2, data2 = wavfile.read(sync_wav)
        return self.calculate_delay_from_arrays(
            rate1,
            data1,
            data2,
            sync_rate=rate2,
            skip_intro_sec=skip_intro_sec,
            total_segments=total_segments,
        )

    def calculate_delay_from_arrays(
        self,
        rate: int,
        src_audio: np.ndarray,
        sync_audio: np.ndarray,
        *,
        sync_rate: int | None = None,
        skip_intro_sec: float = 120.0,
        total_segments: int = 12,
    ) -> AnalysisResult:
        """Calculate delay from two in-memory mono PCM arrays."""
        rate, d1, d2 = self._prepare_arrays(
            rate,
            src_audio,
            sync_audio,
            sync_rate=sync_rate,
        )
        return self._calculate_delay_from_normalized(
            rate,
            d1,
            d2,
            skip_intro_sec=skip_intro_sec,
            total_segments=total_segments,
        )

    def calculate_delay_from_pcm_files(
        self,
        rate: int,
        src_pcm_path: str,
        sync_pcm_path: str,
        *,
        sync_rate: int | None = None,
        skip_intro_sec: float = 120.0,
        total_segments: int = 12,
    ) -> AnalysisResult:
        """Calculate delay from raw mono s16le PCM files on disk."""
        effective_sync_rate = rate if sync_rate is None else sync_rate
        if rate != effective_sync_rate:
            raise RuntimeError("Analiz ornekleme oranlari eslesmiyor.")

        src_samples = self._raw_pcm_sample_count(src_pcm_path)
        sync_samples = self._raw_pcm_sample_count(sync_pcm_path)
        min_samples = int(rate * self._config.min_audio_duration_sec)
        if src_samples < min_samples or sync_samples < min_samples:
            raise RuntimeError(
                f"Senkron analizi icin dosyalar cok kisa "
                f"(en az ~{self._config.min_audio_duration_sec} sn gerekli)."
            )

        requested_skip = int(max(0.0, skip_intro_sec) * rate)
        skip_samples, skip_fallback = self._resolve_skip_samples(
            src_samples,
            sync_samples,
            requested_skip,
            min_samples,
        )

        src_mean, src_peak = self._measure_pcm_normalization(src_pcm_path)
        sync_mean, sync_peak = self._measure_pcm_normalization(sync_pcm_path)

        fingerprint_estimate = self._estimate_fingerprint_delay_from_pcm_files(
            rate,
            src_pcm_path,
            sync_pcm_path,
            skip_samples=skip_samples,
            src_mean=src_mean,
            src_peak=src_peak,
            sync_mean=sync_mean,
            sync_peak=sync_peak,
        )

        src_features = self._build_features_from_pcm_file(
            src_pcm_path,
            rate,
            skip_samples,
            mean=src_mean,
            peak=src_peak,
        )
        sync_features = self._build_features_from_pcm_file(
            sync_pcm_path,
            rate,
            skip_samples,
            mean=sync_mean,
            peak=sync_peak,
        )

        return self._calculate_delay_from_features(
            rate,
            src_features,
            sync_features,
            skip_samples=skip_samples,
            total_segments=total_segments,
            skip_fallback=skip_fallback,
            fingerprint_estimate=fingerprint_estimate,
        )

    @staticmethod
    def normalize_audio(data: np.ndarray) -> np.ndarray:
        """Normalize raw PCM/WAV data into [-1, 1] float32."""
        x = data.astype(ANALYSIS_DTYPE, copy=True)

        if np.issubdtype(data.dtype, np.integer):
            info = np.iinfo(data.dtype)
            x *= ANALYSIS_DTYPE(1.0 / max(abs(info.min), info.max))

        np.nan_to_num(x, copy=False, nan=0.0, posinf=0.0, neginf=0.0)
        x -= np.mean(x, dtype=np.float64)

        peak = np.max(np.abs(x)) if x.size > 0 else 0.0
        if peak > 1e-9:
            x *= ANALYSIS_DTYPE(1.0 / peak)

        return x

    def bandpass_for_sync(self, x: np.ndarray, rate: int) -> np.ndarray:
        """Apply the legacy zero-phase bandpass used by the array path."""
        cfg = self._config
        if rate < 1000 or len(x) < rate:
            return x

        low = cfg.bandpass_low_hz
        high = min(cfg.bandpass_high_hz, rate * 0.45)
        if high <= low * 1.2:
            return x

        try:
            sos = butter(
                cfg.bandpass_order,
                [low, high],
                btype="bandpass",
                fs=rate,
                output="sos",
            )
            return np.asarray(sosfiltfilt(sos, x), dtype=ANALYSIS_DTYPE)
        except Exception as exc:
            warnings.warn(
                f"Bandpass filtre uygulanamadi, filtresiz sinyal kullaniliyor: {exc}",
                RuntimeWarning,
                stacklevel=2,
            )
            return x

    @staticmethod
    def best_lag(feat1: np.ndarray, feat2: np.ndarray) -> tuple[int, float]:
        """Find the strongest lag between two feature vectors."""
        corr = correlate(feat1, feat2, mode="full", method="fft")
        lags = np.arange(-len(feat2) + 1, len(feat1))
        idx = int(np.argmax(corr))
        peak = float(corr[idx])
        floor = float(np.median(np.abs(corr)) + 1e-9)
        score = peak / floor
        return int(lags[idx]), score

    @staticmethod
    def describe_offset(delay_ms: float) -> str:
        if delay_ms >= 0:
            return "sync ses ileride"
        return "sync ses geride"

    def _prepare_arrays(
        self,
        rate: int,
        src_audio: np.ndarray,
        sync_audio: np.ndarray,
        *,
        sync_rate: int | None = None,
    ) -> tuple[int, np.ndarray, np.ndarray]:
        effective_sync_rate = rate if sync_rate is None else sync_rate
        if rate != effective_sync_rate:
            raise RuntimeError("Analiz ornekleme oranlari eslesmiyor.")

        d1 = self.normalize_audio(src_audio)
        d2 = self.normalize_audio(sync_audio)

        min_samples = int(rate * self._config.min_audio_duration_sec)
        if len(d1) < min_samples or len(d2) < min_samples:
            raise RuntimeError(
                f"Senkron analizi icin dosyalar cok kisa "
                f"(en az ~{self._config.min_audio_duration_sec} sn gerekli)."
            )

        return rate, d1, d2

    def _calculate_delay_from_normalized(
        self,
        rate: int,
        d1: np.ndarray,
        d2: np.ndarray,
        *,
        skip_intro_sec: float,
        total_segments: int,
    ) -> AnalysisResult:
        requested_skip = int(max(0.0, skip_intro_sec) * rate)
        min_samples = int(rate * self._config.min_audio_duration_sec)
        d1_for_coarse, d2_for_coarse, skip_samples, skip_fallback = self._apply_skip(
            d1,
            d2,
            requested_skip,
            min_samples,
        )

        d1_full_filtered = self.bandpass_for_sync(d1, rate)
        d2_full_filtered = self.bandpass_for_sync(d2, rate)

        if skip_samples == 0:
            d1_coarse_filtered = d1_full_filtered
            d2_coarse_filtered = d2_full_filtered
        else:
            d1_coarse_filtered = self.bandpass_for_sync(d1_for_coarse, rate)
            d2_coarse_filtered = self.bandpass_for_sync(d2_for_coarse, rate)

        coarse_feat1, _ = self._build_feature_from_filtered(
            d1_coarse_filtered,
            rate,
            hop_ms=self._config.coarse_hop_ms,
            smooth_ms=self._config.coarse_smooth_ms,
        )
        coarse_feat2, _ = self._build_feature_from_filtered(
            d2_coarse_filtered,
            rate,
            hop_ms=self._config.coarse_hop_ms,
            smooth_ms=self._config.coarse_smooth_ms,
        )
        fine_feat1, _ = self._build_feature_from_filtered(
            d1_full_filtered,
            rate,
            hop_ms=self._config.fine_hop_ms,
            smooth_ms=self._config.fine_smooth_ms,
        )
        fine_feat2, _ = self._build_feature_from_filtered(
            d2_full_filtered,
            rate,
            hop_ms=self._config.fine_hop_ms,
            smooth_ms=self._config.fine_smooth_ms,
        )

        return self._calculate_delay_from_features(
            rate,
            _FeatureBundle(coarse=coarse_feat1, fine=fine_feat1),
            _FeatureBundle(coarse=coarse_feat2, fine=fine_feat2),
            skip_samples=skip_samples,
            total_segments=total_segments,
            skip_fallback=skip_fallback,
            fingerprint_estimate=None,
        )

    def _calculate_delay_from_features(
        self,
        rate: int,
        src_features: _FeatureBundle,
        sync_features: _FeatureBundle,
        *,
        skip_samples: int,
        total_segments: int,
        skip_fallback: bool,
        fingerprint_estimate: _FingerprintEstimate | None = None,
    ) -> AnalysisResult:
        coarse_rate = rate / max(1, int(rate * self._config.coarse_hop_ms / 1000.0))
        fine_rate = rate / max(1, int(rate * self._config.fine_hop_ms / 1000.0))

        coarse_lag, coarse_score = self.best_lag(src_features.coarse, sync_features.coarse)
        coarse_ms = coarse_lag / coarse_rate * 1000.0
        coarse_lag_fine = int(round(coarse_lag * (fine_rate / coarse_rate)))

        candidates: list[_CandidateSpec] = [
            _CandidateSpec(
                coarse_lag_fine=coarse_lag_fine,
                coarse_ms=float(coarse_ms),
                score=float(coarse_score),
                anchors=(),
                local_search_sec=self._config.local_search_sec,
            ),
        ]

        if fingerprint_estimate is not None:
            fingerprint_anchors = self._convert_fingerprint_anchors(
                fingerprint_estimate.anchors,
                fine_rate,
            )
            hint_ms = float(fingerprint_estimate.delay_ms)
            hint_lag_fine = int(round(hint_ms / 1000.0 * fine_rate))
            if fingerprint_anchors or abs(hint_lag_fine - coarse_lag_fine) > 2:
                candidates.append(
                    _CandidateSpec(
                        coarse_lag_fine=hint_lag_fine,
                        coarse_ms=hint_ms,
                        score=float(fingerprint_estimate.score),
                        anchors=fingerprint_anchors,
                        local_search_sec=(
                            self._config.anchor_local_search_sec
                            if fingerprint_anchors
                            else self._config.local_search_sec
                        ),
                    ),
                )

        best_result: AnalysisResult | None = None
        best_key: tuple[float, float, float, float, float] | None = None
        for candidate in candidates:
            segment_results = self._segment_validation(
                src_features.fine,
                sync_features.fine,
                fine_rate,
                candidate.coarse_lag_fine,
                skip_samples,
                rate,
                total_segments,
                lag_anchors=candidate.anchors,
                local_search_sec=candidate.local_search_sec,
            )
            segment_results = self._refine_segment_validation(
                src_features.fine,
                sync_features.fine,
                fine_rate,
                segment_results,
                candidate,
                skip_samples=skip_samples,
                rate=rate,
                total_segments=total_segments,
            )

            result = self._compute_final_result(
                segment_results,
                candidate.coarse_lag_fine,
                candidate.coarse_ms,
                candidate.score,
                fine_rate,
                total_segments,
                skip_fallback,
                self._config.local_search_sec,
            )
            if (
                result.drift_ms_per_min is None
                and fingerprint_estimate is not None
                and candidate.anchors
                and fingerprint_estimate.drift_ms_per_min is not None
            ):
                result = replace(
                    result,
                    drift_ms_per_min=float(fingerprint_estimate.drift_ms_per_min),
                )
            key = (
                float(result.used_segments > 0),
                float(result.used_segments),
                float(result.confidence),
                float(len(candidate.anchors)),
                float(candidate.score),
            )
            if best_key is None or key > best_key:
                best_key = key
                best_result = result

        if best_result is None:
            raise RuntimeError("Analiz sonucu olusturulamadi.")
        return best_result

    def _convert_fingerprint_anchors(
        self,
        anchors: tuple[_FingerprintAnchor, ...],
        fine_rate: float,
    ) -> tuple[_LagAnchor, ...]:
        if not anchors:
            return ()

        fine_anchors = tuple(
            _LagAnchor(
                center_frame=anchor.center_sec * fine_rate,
                lag_frame=anchor.lag_ms / 1000.0 * fine_rate,
                weight=max(1.0, float(anchor.weight)),
            )
            for anchor in anchors
        )
        return self._normalize_lag_anchors(
            fine_anchors,
            min_spacing_frames=max(
                1.0,
                self._config.fingerprint_anchor_min_spacing_sec * fine_rate,
            ),
        )

    def _normalize_lag_anchors(
        self,
        anchors: tuple[_LagAnchor, ...],
        *,
        min_spacing_frames: float,
    ) -> tuple[_LagAnchor, ...]:
        if not anchors:
            return ()

        ordered = sorted(anchors, key=lambda anchor: anchor.center_frame)
        merged: list[_LagAnchor] = []
        for anchor in ordered:
            if anchor.weight <= 0:
                continue
            if not merged:
                merged.append(anchor)
                continue

            prev = merged[-1]
            if abs(anchor.center_frame - prev.center_frame) < min_spacing_frames:
                total_weight = prev.weight + anchor.weight
                merged[-1] = _LagAnchor(
                    center_frame=(
                        (prev.center_frame * prev.weight)
                        + (anchor.center_frame * anchor.weight)
                    ) / total_weight,
                    lag_frame=(
                        (prev.lag_frame * prev.weight)
                        + (anchor.lag_frame * anchor.weight)
                    ) / total_weight,
                    weight=total_weight,
                )
            else:
                merged.append(anchor)

        return tuple(merged)

    def _merge_lag_anchors(
        self,
        base_anchors: tuple[_LagAnchor, ...],
        extra_anchors: tuple[_LagAnchor, ...],
        fine_rate: float,
    ) -> tuple[_LagAnchor, ...]:
        return self._normalize_lag_anchors(
            tuple((*base_anchors, *extra_anchors)),
            min_spacing_frames=max(
                1.0,
                self._config.offset_map_min_spacing_sec * fine_rate,
            ),
        )

    def _refine_segment_validation(
        self,
        fine_feat1: np.ndarray,
        fine_feat2: np.ndarray,
        fine_rate: float,
        segment_results: list[dict[str, float]],
        candidate: _CandidateSpec,
        *,
        skip_samples: int,
        rate: int,
        total_segments: int,
    ) -> list[dict[str, float]]:
        lag_map = self._build_offset_map_from_segments(
            segment_results,
            fine_rate,
        )
        if not lag_map:
            return segment_results

        merged_anchors = self._merge_lag_anchors(candidate.anchors, lag_map, fine_rate)
        refined_total_segments = max(
            total_segments * self._config.validation_refine_multiplier,
            total_segments + len(merged_anchors) * 2,
        )
        refined_results = self._segment_validation(
            fine_feat1,
            fine_feat2,
            fine_rate,
            candidate.coarse_lag_fine,
            skip_samples,
            rate,
            refined_total_segments,
            lag_anchors=merged_anchors,
            local_search_sec=self._config.offset_map_local_search_sec,
        )
        return self._merge_segment_results(segment_results, refined_results)

    def _build_offset_map_from_segments(
        self,
        segment_results: list[dict[str, float]],
        fine_rate: float,
    ) -> tuple[_LagAnchor, ...]:
        kept = self._filter_segment_results(
            segment_results,
            fine_rate,
            self._config.local_search_sec,
        )
        if len(kept) < self._config.offset_map_min_points:
            return ()

        bucket_sec = max(
            self._config.offset_map_bucket_sec,
            self._config.segment_duration_sec * 0.5,
        )
        bucket_map: dict[int, list[dict[str, float]]] = {}
        for row in kept:
            bucket_key = int(row["center_sec"] // bucket_sec)
            bucket_map.setdefault(bucket_key, []).append(row)

        anchors: list[_LagAnchor] = []
        for bucket in sorted(bucket_map):
            rows = bucket_map[bucket]
            weights = np.array(
                [max(1.0, row["score"]) for row in rows],
                dtype=np.float64,
            )
            centers = np.array([row["center_sec"] for row in rows], dtype=np.float64)
            lags = np.array([row["lag"] for row in rows], dtype=np.float64)
            anchors.append(
                _LagAnchor(
                    center_frame=float(np.average(centers, weights=weights) * fine_rate),
                    lag_frame=float(np.average(lags, weights=weights)),
                    weight=float(np.sum(weights)),
                ),
            )

        return self._normalize_lag_anchors(
            tuple(anchors),
            min_spacing_frames=max(
                1.0,
                self._config.offset_map_min_spacing_sec * fine_rate,
            ),
        )

    @staticmethod
    def _merge_segment_results(
        base_results: list[dict[str, float]],
        extra_results: list[dict[str, float]],
    ) -> list[dict[str, float]]:
        if not extra_results:
            return base_results

        merged = list(base_results)
        for candidate in extra_results:
            replaced = False
            for index, current in enumerate(merged):
                if abs(current["center_sec"] - candidate["center_sec"]) <= 0.75:
                    if candidate["score"] > current["score"]:
                        merged[index] = candidate
                    replaced = True
                    break
            if not replaced:
                merged.append(candidate)

        merged.sort(key=lambda row: row["center_sec"])
        return merged

    @staticmethod
    def _apply_skip(
        d1: np.ndarray,
        d2: np.ndarray,
        skip_samples: int,
        min_samples: int,
    ) -> tuple[np.ndarray, np.ndarray, int, bool]:
        skip_fallback = False

        d1_coarse = d1[skip_samples:] if skip_samples < len(d1) else np.array([], dtype=ANALYSIS_DTYPE)
        d2_coarse = d2[skip_samples:] if skip_samples < len(d2) else np.array([], dtype=ANALYSIS_DTYPE)

        if len(d1_coarse) < min_samples or len(d2_coarse) < min_samples:
            d1_coarse = d1
            d2_coarse = d2
            skip_samples = 0
            skip_fallback = True

        return d1_coarse, d2_coarse, skip_samples, skip_fallback

    def _build_feature_from_filtered(
        self,
        x_filtered: np.ndarray,
        rate: int,
        hop_ms: int = 40,
        smooth_ms: int = 120,
    ) -> tuple[np.ndarray, float]:
        cfg = self._config

        dx = np.diff(x_filtered, prepend=x_filtered[0])
        emphasis = (
            cfg.emphasis_signal_weight * np.abs(x_filtered)
            + cfg.emphasis_diff_weight * np.abs(dx)
        )

        smooth = max(8, int(rate * smooth_ms / 1000.0))
        kernel = np.full(smooth, ANALYSIS_DTYPE(1.0 / smooth), dtype=ANALYSIS_DTYPE)

        env = np.asarray(fftconvolve(emphasis, kernel, mode="same"), dtype=ANALYSIS_DTYPE)
        env = np.log1p(env * cfg.envelope_gain)

        hop = max(1, int(rate * hop_ms / 1000.0))
        feat = env[::hop]
        if len(feat) < cfg.min_feature_length:
            raise RuntimeError("Analiz icin yeterli ornek olusmadi.")

        feat = np.diff(feat, prepend=feat[0])
        feat = np.maximum(feat, 0.0)
        feat = feat - np.median(feat)
        std = np.std(feat)
        if std > 1e-9:
            feat = feat / std
        else:
            feat = feat * ANALYSIS_DTYPE(0.0)

        return feat.astype(ANALYSIS_DTYPE, copy=False), rate / hop

    def _build_features_from_pcm_file(
        self,
        pcm_path: str,
        rate: int,
        skip_samples: int,
        *,
        mean: float | None = None,
        peak: float | None = None,
    ) -> _FeatureBundle:
        if mean is None or peak is None:
            mean, peak = self._measure_pcm_normalization(pcm_path)
        coarse_feat, fine_feat = self._stream_pcm_features(
            pcm_path,
            rate,
            skip_samples,
            mean,
            peak,
        )
        return _FeatureBundle(coarse=coarse_feat, fine=fine_feat)

    def _estimate_fingerprint_delay_from_pcm_files(
        self,
        rate: int,
        src_pcm_path: str,
        sync_pcm_path: str,
        *,
        skip_samples: int,
        src_mean: float,
        src_peak: float,
        sync_mean: float,
        sync_peak: float,
    ) -> _FingerprintEstimate | None:
        cfg = self._config
        if not cfg.fingerprint_enabled:
            return None

        src_peak_frames = self._extract_fingerprint_peak_frames(
            src_pcm_path,
            rate,
            skip_samples=skip_samples,
            mean=src_mean,
            peak=src_peak,
        )
        sync_peak_frames = self._extract_fingerprint_peak_frames(
            sync_pcm_path,
            rate,
            skip_samples=skip_samples,
            mean=sync_mean,
            peak=sync_peak,
        )

        if not src_peak_frames or not sync_peak_frames:
            return None

        return self._match_fingerprint_peak_frames(
            src_peak_frames,
            sync_peak_frames,
            rate,
        )

    def _extract_fingerprint_peak_frames(
        self,
        pcm_path: str,
        rate: int,
        *,
        skip_samples: int,
        mean: float,
        peak: float,
    ) -> list[tuple[int, tuple[int, ...]]]:
        cfg = self._config
        frame_size = cfg.fingerprint_frame_size
        hop = cfg.fingerprint_hop_size
        frame_stride = max(1, cfg.fingerprint_frame_stride)

        if rate <= 0 or frame_size <= 0 or hop <= 0 or frame_size <= hop:
            return []

        freq_resolution = rate / frame_size
        min_bin = max(1, int(120.0 / freq_resolution))
        max_bin = min(frame_size // 2, int(min(rate * 0.45, 5000.0) / freq_resolution))
        if max_bin <= min_bin:
            return []

        chunk_size = max(self._chunk_size_samples(), frame_size * 8)
        peak_frames: list[tuple[int, tuple[int, ...]]] = []
        total_samples = self._raw_pcm_sample_count(pcm_path)
        overlap = frame_size - hop
        mean_value = ANALYSIS_DTYPE(mean)
        inv_peak = ANALYSIS_DTYPE(1.0 / peak)
        window = np.hanning(frame_size).astype(ANALYSIS_DTYPE)

        for core_start in range(skip_samples, total_samples, chunk_size):
            core_end = min(total_samples, core_start + chunk_size)
            read_start = max(skip_samples, core_start - overlap)
            read_end = min(total_samples, core_end + overlap)
            raw = self._read_pcm_range(pcm_path, read_start, read_end)
            chunk = raw.astype(ANALYSIS_DTYPE)
            chunk *= _INT16_SCALE
            chunk -= mean_value
            chunk *= inv_peak
            if chunk.size < frame_size:
                continue

            frame_starts = np.arange(0, chunk.size - frame_size + 1, hop, dtype=np.int64)
            if frame_starts.size == 0:
                continue

            absolute_frame_starts = read_start + frame_starts
            core_mask = (
                (absolute_frame_starts >= core_start)
                & (absolute_frame_starts < core_end)
            )
            frame_starts = frame_starts[core_mask]
            absolute_frame_starts = absolute_frame_starts[core_mask]
            if frame_starts.size == 0:
                continue

            frames = np.lib.stride_tricks.sliding_window_view(chunk, frame_size)[::hop]
            frames = frames[core_mask]
            frame_energy = np.sqrt(np.mean(frames * frames, axis=1, dtype=np.float64))
            energy_floor = 0.01
            if frame_energy.size:
                energy_floor = max(
                    energy_floor,
                    float(np.percentile(frame_energy, 35)) * 0.5,
                )
            active_mask = frame_energy > energy_floor
            if not np.any(active_mask):
                continue

            frames = frames[active_mask]
            absolute_frame_starts = absolute_frame_starts[active_mask]
            spectra = np.abs(np.fft.rfft(frames * window, axis=1))
            spectra = np.asarray(np.log1p(spectra), dtype=ANALYSIS_DTYPE)
            spectra = spectra[:, min_bin:max_bin]

            for row_index in range(0, spectra.shape[0], frame_stride):
                peak_bins = self._pick_fingerprint_peak_bins(
                    spectra[row_index],
                    min_bin=min_bin,
                    peaks_per_frame=cfg.fingerprint_peaks_per_frame,
                    min_distance=cfg.fingerprint_peak_min_distance_bins,
                )
                if peak_bins:
                    peak_frames.append(
                        (int(absolute_frame_starts[row_index] // hop), peak_bins),
                    )

        return peak_frames

    def _pick_fingerprint_peak_bins(
        self,
        spectrum_slice: np.ndarray,
        *,
        min_bin: int,
        peaks_per_frame: int,
        min_distance: int,
    ) -> tuple[int, ...]:
        if spectrum_slice.size == 0:
            return ()

        median = float(np.median(spectrum_slice))
        std = float(np.std(spectrum_slice))
        threshold = median + std * 0.75
        candidates = np.flatnonzero(spectrum_slice >= threshold)
        if candidates.size == 0:
            candidates = np.array([int(np.argmax(spectrum_slice))], dtype=np.int64)

        order = candidates[np.argsort(spectrum_slice[candidates])[::-1]]
        selected: list[int] = []
        for idx in order:
            if all(abs(int(idx) - prev) >= min_distance for prev in selected):
                selected.append(int(idx))
                if len(selected) >= peaks_per_frame:
                    break

        return tuple(min_bin + idx for idx in selected)

    def _match_fingerprint_peak_frames(
        self,
        src_peak_frames: list[tuple[int, tuple[int, ...]]],
        sync_peak_frames: list[tuple[int, tuple[int, ...]]],
        rate: int,
    ) -> _FingerprintEstimate | None:
        cfg = self._config
        source_hashes = self._build_fingerprint_hash_map(src_peak_frames)
        if not source_hashes:
            return None

        votes: dict[int, int] = {}
        for sync_hash, sync_anchor_frame in self._iter_fingerprint_hashes(sync_peak_frames):
            source_frames = source_hashes.get(sync_hash)
            if not source_frames:
                continue
            for src_anchor_frame in source_frames:
                offset = src_anchor_frame - sync_anchor_frame
                votes[offset] = votes.get(offset, 0) + 1

        if not votes:
            return None

        scored_offsets = self._rank_fingerprint_offsets(votes)
        best_offset, best_score, best_votes = scored_offsets[0]
        if best_votes < cfg.fingerprint_min_votes:
            return None

        anchors = self._build_fingerprint_anchors(
            source_hashes,
            sync_peak_frames,
            scored_offsets,
            rate,
        )

        second_score = scored_offsets[1][1] if len(scored_offsets) > 1 else 1.0
        score = best_score / max(1.0, second_score)
        score *= max(1.0, np.log1p(best_votes))

        delay_ms = best_offset * cfg.fingerprint_hop_size / rate * 1000.0
        drift_ms_per_min: float | None = None
        if len(anchors) >= 2:
            t = np.array([anchor.center_sec for anchor in anchors], dtype=np.float64)
            y = np.array([anchor.lag_ms for anchor in anchors], dtype=np.float64)
            w = np.array([max(1.0, anchor.weight) for anchor in anchors], dtype=np.float64)
            slope_ms_per_sec = float(np.polyfit(t, y, 1, w=w)[0])
            drift_ms_per_min = slope_ms_per_sec * 60.0

        return _FingerprintEstimate(
            delay_ms=float(delay_ms),
            votes=int(best_votes),
            score=float(score),
            anchors=anchors,
            drift_ms_per_min=drift_ms_per_min,
        )

    def _rank_fingerprint_offsets(
        self,
        votes: dict[int, int],
    ) -> list[tuple[int, float, int]]:
        radius = max(1, self._config.fingerprint_cluster_radius_frames)
        ranked: list[tuple[int, float, int]] = []
        for offset, count in votes.items():
            score = float(count)
            for step in range(1, radius + 1):
                weight = 1.0 - (step / (radius + 1.0))
                score += weight * votes.get(offset - step, 0)
                score += weight * votes.get(offset + step, 0)
            ranked.append((offset, score, count))

        ranked.sort(key=lambda item: item[1], reverse=True)
        selected: list[tuple[int, float, int]] = []
        for offset, score, count in ranked:
            if any(
                abs(offset - existing_offset) <= radius * 2
                for existing_offset, _existing_score, _existing_count in selected
            ):
                continue
            selected.append((offset, score, count))
            if len(selected) >= max(1, self._config.fingerprint_top_clusters):
                break
        return selected or ranked[:1]

    def _build_fingerprint_anchors(
        self,
        source_hashes: dict[int, list[int]],
        sync_peak_frames: list[tuple[int, tuple[int, ...]]],
        ranked_offsets: list[tuple[int, float, int]],
        rate: int,
    ) -> tuple[_FingerprintAnchor, ...]:
        if not ranked_offsets:
            return ()

        cfg = self._config
        radius = max(1, cfg.fingerprint_cluster_radius_frames)
        bucket_frames = max(
            1,
            int(cfg.fingerprint_anchor_bucket_sec * rate / cfg.fingerprint_hop_size),
        )
        cluster_weights = {
            offset: max(1.0, np.log1p(score))
            for offset, score, _count in ranked_offsets
        }
        bucket_stats: dict[int, dict[int, list[float]]] = {}

        for sync_hash, sync_anchor_frame in self._iter_fingerprint_hashes(sync_peak_frames):
            source_frames = source_hashes.get(sync_hash)
            if not source_frames:
                continue

            for src_anchor_frame in source_frames:
                offset = src_anchor_frame - sync_anchor_frame
                nearest_offset = min(
                    cluster_weights,
                    key=lambda candidate: abs(offset - candidate),
                )
                distance = abs(offset - nearest_offset)
                if distance > radius:
                    continue

                bucket_key = max(0, src_anchor_frame // bucket_frames)
                offset_map = bucket_stats.setdefault(bucket_key, {})
                stats = offset_map.setdefault(offset, [0.0, 0.0])
                distance_weight = 1.0 - (distance / (radius + 1.0))
                weight = cluster_weights[nearest_offset] * max(0.25, distance_weight)
                stats[0] += weight
                stats[1] += weight * src_anchor_frame

        anchors: list[_FingerprintAnchor] = []
        for bucket_key in sorted(bucket_stats):
            offset_map = bucket_stats[bucket_key]
            best_offset: int | None = None
            best_score = 0.0

            for offset, stats in offset_map.items():
                score = stats[0]
                for step in range(1, radius + 1):
                    weight = 1.0 - (step / (radius + 1.0))
                    if offset - step in offset_map:
                        score += weight * offset_map[offset - step][0]
                    if offset + step in offset_map:
                        score += weight * offset_map[offset + step][0]
                if score > best_score:
                    best_offset = offset
                    best_score = score

            if best_offset is None or best_score < 2.0:
                continue

            cluster_rows = [
                (offset, stats)
                for offset, stats in offset_map.items()
                if abs(offset - best_offset) <= radius
            ]
            weights = np.array(
                [
                    stats[0] * max(0.25, 1.0 - (abs(offset - best_offset) / (radius + 1.0)))
                    for offset, stats in cluster_rows
                ],
                dtype=np.float64,
            )
            offsets = np.array([offset for offset, _stats in cluster_rows], dtype=np.float64)
            centers = np.array(
                [stats[1] / max(stats[0], 1e-9) for _offset, stats in cluster_rows],
                dtype=np.float64,
            )

            anchor_center_frame = float(np.average(centers, weights=weights))
            anchor_offset = float(np.average(offsets, weights=weights))
            anchors.append(
                _FingerprintAnchor(
                    center_sec=anchor_center_frame * cfg.fingerprint_hop_size / rate,
                    lag_ms=anchor_offset * cfg.fingerprint_hop_size / rate * 1000.0,
                    weight=float(np.sum(weights)),
                ),
            )

        return self._prune_fingerprint_anchors(anchors)

    def _prune_fingerprint_anchors(
        self,
        anchors: list[_FingerprintAnchor],
    ) -> tuple[_FingerprintAnchor, ...]:
        if not anchors:
            return ()

        min_spacing = max(0.5, self._config.fingerprint_anchor_min_spacing_sec)
        merged: list[_FingerprintAnchor] = []
        for anchor in sorted(anchors, key=lambda item: item.center_sec):
            if not merged:
                merged.append(anchor)
                continue

            prev = merged[-1]
            if abs(anchor.center_sec - prev.center_sec) < min_spacing:
                total_weight = prev.weight + anchor.weight
                merged[-1] = _FingerprintAnchor(
                    center_sec=(
                        (prev.center_sec * prev.weight)
                        + (anchor.center_sec * anchor.weight)
                    ) / total_weight,
                    lag_ms=(
                        (prev.lag_ms * prev.weight)
                        + (anchor.lag_ms * anchor.weight)
                    ) / total_weight,
                    weight=total_weight,
                )
            else:
                merged.append(anchor)

        if len(merged) <= self._config.fingerprint_max_anchors:
            return tuple(merged)

        selected = sorted(
            merged,
            key=lambda item: item.weight,
            reverse=True,
        )[:self._config.fingerprint_max_anchors]
        return tuple(sorted(selected, key=lambda item: item.center_sec))

    def _build_fingerprint_hash_map(
        self,
        peak_frames: list[tuple[int, tuple[int, ...]]],
    ) -> dict[int, list[int]]:
        source_hashes: dict[int, list[int]] = {}
        for hash_value, anchor_frame in self._iter_fingerprint_hashes(peak_frames):
            source_hashes.setdefault(hash_value, []).append(anchor_frame)

        max_occurrences = self._config.fingerprint_max_hash_occurrences
        return {
            hash_value: frames
            for hash_value, frames in source_hashes.items()
            if 0 < len(frames) <= max_occurrences
        }

    def _iter_fingerprint_hashes(
        self,
        peak_frames: list[tuple[int, tuple[int, ...]]],
    ) -> Iterator[tuple[int, int]]:
        cfg = self._config
        max_dt = max(2, cfg.fingerprint_target_zone_frames)
        fanout = max(1, cfg.fingerprint_fanout)
        bin_size = max(1, cfg.fingerprint_hash_bin_size)

        for anchor_index, (anchor_frame, anchor_bins) in enumerate(peak_frames):
            emitted = 0
            for target_frame, target_bins in peak_frames[anchor_index + 1:]:
                delta = target_frame - anchor_frame
                if delta <= 0:
                    continue
                if delta > max_dt:
                    break

                for anchor_bin in anchor_bins:
                    for target_bin in target_bins:
                        hash_value = (
                            ((anchor_bin // bin_size) & 0x3FF) << 16
                            | ((target_bin // bin_size) & 0x3FF) << 6
                            | (delta & 0x3F)
                        )
                        yield hash_value, anchor_frame
                        emitted += 1
                        if emitted >= fanout:
                            break
                    if emitted >= fanout:
                        break
                if emitted >= fanout:
                    break

    def _measure_pcm_normalization(self, pcm_path: str) -> tuple[float, float]:
        """Return the DC offset and the peak of the centred signal.

        ``max|x - mean|`` is always attained at one of the two extremes of
        ``x``, so tracking a running min/max lets this read the decoded PCM
        once instead of twice — the file is roughly 2 MB per audio minute and
        both channels are measured, so the second pass was the single largest
        chunk of avoidable I/O in the analysis stage.
        """
        total_sum = 0.0
        total_count = 0
        minimum = math.inf
        maximum = -math.inf

        for chunk in self._iter_pcm_file_chunks(pcm_path, self._chunk_size_samples()):
            scaled = chunk.astype(ANALYSIS_DTYPE)
            scaled *= _INT16_SCALE
            total_sum += float(np.sum(scaled, dtype=np.float64))
            total_count += scaled.size
            minimum = min(minimum, float(np.min(scaled)))
            maximum = max(maximum, float(np.max(scaled)))

        if total_count == 0:
            raise RuntimeError("Mono decode returned an empty PCM buffer.")

        mean = total_sum / total_count
        # Reproduce the float32 subtraction the streaming stage performs so the
        # peak stays bit-identical to a per-sample scan.
        centred_mean = ANALYSIS_DTYPE(mean)
        peak = float(
            max(
                abs(ANALYSIS_DTYPE(maximum) - centred_mean),
                abs(ANALYSIS_DTYPE(minimum) - centred_mean),
            )
        )

        return mean, peak if peak > 1e-9 else 1.0

    def _stream_pcm_features(
        self,
        pcm_path: str,
        rate: int,
        skip_samples: int,
        mean: float,
        peak: float,
    ) -> tuple[np.ndarray, np.ndarray]:
        chunk_size = self._chunk_size_samples()
        fine_builder = _StreamingFeatureBuilder(
            rate,
            self._config.fine_hop_ms,
            self._config.fine_smooth_ms,
            self._config,
            apply_bandpass=False,
        )
        coarse_builder = _StreamingFeatureBuilder(
            rate,
            self._config.coarse_hop_ms,
            self._config.coarse_smooth_ms,
            self._config,
            apply_bandpass=False,
        )

        start = 0
        for start, chunk in self._iter_filtered_pcm_chunks(
            pcm_path,
            rate,
            mean,
            peak,
            chunk_size,
        ):

            fine_builder.process(chunk)

            if skip_samples == 0:
                coarse_builder.process(chunk)
                continue

            coarse_offset = skip_samples - start
            if coarse_offset <= 0:
                coarse_builder.process(chunk)
            elif coarse_offset < chunk.size:
                coarse_builder.process(chunk[coarse_offset:])

        fine_feat, _ = fine_builder.finalize()
        coarse_feat, _ = coarse_builder.finalize()
        return coarse_feat, fine_feat

    def _chunk_size_samples(self) -> int:
        return max(
            int(self._config.analysis_sample_rate * self._config.analysis_chunk_sec),
            65536,
        )

    @staticmethod
    def _iter_pcm_file_chunks(pcm_path: str, chunk_size: int) -> np.ndarray:
        bytes_per_chunk = chunk_size * np.dtype(np.int16).itemsize
        with open(pcm_path, "rb") as handle:
            while True:
                pcm_bytes = handle.read(bytes_per_chunk)
                if not pcm_bytes:
                    break
                if len(pcm_bytes) % np.dtype(np.int16).itemsize != 0:
                    pcm_bytes = pcm_bytes[:-(len(pcm_bytes) % np.dtype(np.int16).itemsize)]
                    if not pcm_bytes:
                        break
                yield np.frombuffer(pcm_bytes, dtype=np.int16)

    def _iter_filtered_pcm_chunks(
        self,
        pcm_path: str,
        rate: int,
        mean: float,
        peak: float,
        chunk_size: int,
    ) -> Iterator[tuple[int, np.ndarray]]:
        total_samples = self._raw_pcm_sample_count(pcm_path)
        overlap = max(rate * 2, chunk_size // 8)
        mean_value = ANALYSIS_DTYPE(mean)
        inv_peak = ANALYSIS_DTYPE(1.0 / peak)

        for start in range(0, total_samples, chunk_size):
            end = min(total_samples, start + chunk_size)
            read_start = max(0, start - overlap)
            read_end = min(total_samples, end + overlap)
            raw = self._read_pcm_range(pcm_path, read_start, read_end)
            chunk = raw.astype(ANALYSIS_DTYPE)
            chunk *= _INT16_SCALE
            chunk -= mean_value
            chunk *= inv_peak

            filtered = self.bandpass_for_sync(chunk, rate)
            core_start = start - read_start
            core_end = core_start + (end - start)
            yield start, np.asarray(filtered[core_start:core_end], dtype=ANALYSIS_DTYPE)

    @staticmethod
    def _raw_pcm_sample_count(pcm_path: str) -> int:
        byte_count = os.path.getsize(pcm_path)
        sample_width = np.dtype(np.int16).itemsize
        if byte_count % sample_width != 0:
            byte_count -= byte_count % sample_width
        return byte_count // sample_width

    @staticmethod
    def _resolve_skip_samples(
        src_samples: int,
        sync_samples: int,
        skip_samples: int,
        min_samples: int,
    ) -> tuple[int, bool]:
        remaining_src = max(0, src_samples - skip_samples)
        remaining_sync = max(0, sync_samples - skip_samples)
        if remaining_src < min_samples or remaining_sync < min_samples:
            return 0, True
        return skip_samples, False

    @staticmethod
    def _read_pcm_range(pcm_path: str, start_sample: int, end_sample: int) -> np.ndarray:
        sample_width = np.dtype(np.int16).itemsize
        with open(pcm_path, "rb") as handle:
            handle.seek(start_sample * sample_width)
            pcm_bytes = handle.read((end_sample - start_sample) * sample_width)
        return np.frombuffer(pcm_bytes, dtype=np.int16)

    def _segment_validation(
        self,
        fine_feat1: np.ndarray,
        fine_feat2: np.ndarray,
        fine_rate: float,
        coarse_lag: int,
        skip_samples: int,
        rate: int,
        total_segments: int,
        *,
        lag_anchors: tuple[_LagAnchor, ...] = (),
        local_search_sec: float | None = None,
    ) -> list[dict[str, float]]:
        cfg = self._config
        seg_len = max(1, int(cfg.segment_duration_sec * fine_rate))
        local_steps = max(
            1,
            int((cfg.local_search_sec if local_search_sec is None else local_search_sec) * fine_rate),
        )
        fine_skip = int(skip_samples / rate * fine_rate)

        lag_values = [int(round(anchor.lag_frame)) for anchor in lag_anchors] or [coarse_lag]
        max_lag = max(0, *lag_values)
        min_lag = min(0, *lag_values)

        overlap_start_ref = max(0, max_lag, fine_skip)
        overlap_end_ref = min(len(fine_feat1), len(fine_feat2) + min_lag)
        start_positions = self._build_validation_positions(
            overlap_start_ref,
            overlap_end_ref,
            seg_len,
            total_segments,
            lag_anchors,
        )

        segment_results: list[dict[str, float]] = []

        for ref_start in start_positions:
            center_frame = ref_start + seg_len / 2
            predicted_lag = self._predict_lag_from_anchors(
                center_frame,
                lag_anchors,
                float(coarse_lag),
            )
            sync_start_guess = int(round(ref_start - predicted_lag))
            win2_start = sync_start_guess - local_steps
            win2_end = sync_start_guess + seg_len + local_steps

            if win2_start < 0 or win2_end > len(fine_feat2):
                continue

            seg1 = fine_feat1[ref_start: ref_start + seg_len]
            win2 = fine_feat2[win2_start: win2_end]

            if np.std(seg1) < cfg.min_std_threshold or np.std(win2) < cfg.min_std_threshold:
                continue

            corr = correlate(win2, seg1, mode="valid", method="fft")
            best_idx = int(np.argmax(corr))
            peak = float(corr[best_idx])
            floor = float(np.median(np.abs(corr)) + 1e-9)
            score = peak / floor
            refined_lag = predicted_lag + local_steps - best_idx

            segment_results.append(
                {
                    "center_sec": center_frame / fine_rate,
                    "lag": float(refined_lag),
                    "predicted_lag": float(predicted_lag),
                    "residual_lag": float(refined_lag - predicted_lag),
                    "score": score,
                },
            )

        return segment_results

    def _build_validation_positions(
        self,
        overlap_start_ref: int,
        overlap_end_ref: int,
        seg_len: int,
        total_segments: int,
        lag_anchors: tuple[_LagAnchor, ...],
    ) -> np.ndarray:
        usable = overlap_end_ref - overlap_start_ref - seg_len
        positions: list[int] = []

        if usable > seg_len:
            positions.extend(
                int(value)
                for value in np.linspace(
                    overlap_start_ref,
                    overlap_end_ref - seg_len,
                    total_segments,
                    dtype=int,
                )
            )
        elif overlap_end_ref - overlap_start_ref > seg_len:
            positions.append(int(overlap_start_ref))

        if lag_anchors:
            half_seg = seg_len / 2.0
            for anchor in lag_anchors:
                start = int(round(anchor.center_frame - half_seg))
                if start < overlap_start_ref or start + seg_len > overlap_end_ref:
                    continue
                positions.append(start)

        if not positions:
            return np.array([], dtype=int)

        return np.array(sorted(set(positions)), dtype=int)

    @staticmethod
    def _predict_lag_from_anchors(
        center_frame: float,
        lag_anchors: tuple[_LagAnchor, ...],
        fallback_lag: float,
    ) -> float:
        if not lag_anchors:
            return fallback_lag

        if len(lag_anchors) == 1:
            return float(lag_anchors[0].lag_frame)

        if center_frame <= lag_anchors[0].center_frame:
            return float(lag_anchors[0].lag_frame)
        if center_frame >= lag_anchors[-1].center_frame:
            return float(lag_anchors[-1].lag_frame)

        for left, right in zip(lag_anchors, lag_anchors[1:]):
            if left.center_frame <= center_frame <= right.center_frame:
                span = right.center_frame - left.center_frame
                if span <= 1e-9:
                    return float(left.lag_frame)
                ratio = (center_frame - left.center_frame) / span
                return float(left.lag_frame + ((right.lag_frame - left.lag_frame) * ratio))

        return fallback_lag

    def _filter_segment_results(
        self,
        segment_results: list[dict[str, float]],
        fine_rate: float,
        local_search_sec: float = 3.5,
    ) -> list[dict[str, float]]:
        if not segment_results:
            return []

        residual_values = np.array(
            [
                r.get("residual_lag", r["lag"])
                for r in segment_results
            ],
            dtype=np.float64,
        )
        weights = np.array(
            [max(1.0, r["score"]) for r in segment_results],
            dtype=np.float64,
        )
        dominant_center = self._find_dominant_cluster_center(
            residual_values,
            weights,
            fine_rate,
        )
        mad = float(np.median(np.abs(residual_values - dominant_center)))
        local_steps_approx = int(local_search_sec * fine_rate)
        tolerance = min(
            max(fine_rate * 0.05, 2.5 * mad, 1.5),
            max(fine_rate * 0.16, local_steps_approx * 0.18),
        )
        kept = [
            row
            for row in segment_results
            if abs(row.get("residual_lag", row["lag"]) - dominant_center) <= tolerance
        ]

        if not kept:
            kept = sorted(segment_results, key=lambda r: r["score"], reverse=True)[:3]

        kept.sort(key=lambda row: row["center_sec"])
        return kept

    @staticmethod
    def _find_dominant_cluster_center(
        values: np.ndarray,
        weights: np.ndarray,
        fine_rate: float,
    ) -> float:
        if values.size == 0:
            return 0.0
        if values.size == 1:
            return float(values[0])

        radius = max(2.0, fine_rate * 0.12)
        best_index = 0
        best_score = -1.0
        for index, center in enumerate(values):
            distance = np.abs(values - center)
            shape = np.clip(1.0 - (distance / radius), 0.0, None)
            score = float(np.sum(weights * shape))
            if score > best_score:
                best_score = score
                best_index = index

        center = float(values[best_index])
        distance = np.abs(values - center)
        in_cluster = distance <= radius
        if not np.any(in_cluster):
            return center

        return float(np.average(values[in_cluster], weights=weights[in_cluster]))

    def _compute_final_result(
        self,
        segment_results: list[dict[str, float]],
        coarse_lag_fine: int,
        coarse_ms: float,
        coarse_score: float,
        fine_rate: float,
        total_segments: int,
        skip_fallback: bool,
        local_search_sec: float = 3.5,
    ) -> AnalysisResult:
        kept = self._filter_segment_results(
            segment_results,
            fine_rate,
            local_search_sec,
        )

        if kept:
            kept_lags = np.array([r["lag"] for r in kept], dtype=np.float64)
            kept_scores = np.array([max(1.0, r["score"]) for r in kept], dtype=np.float64)
            final_lag = self._weighted_median(kept_lags, kept_scores)

            drift_ms_per_min: float | None = None
            if len(kept) >= 4:
                t = np.array([r["center_sec"] for r in kept], dtype=np.float64)
                y = np.array([r["lag"] / fine_rate * 1000.0 for r in kept], dtype=np.float64)
                slope_ms_per_sec = float(np.polyfit(t, y, 1)[0])
                drift_ms_per_min = slope_ms_per_sec * 60.0

            confidence = float(np.median([r["score"] for r in kept]))
            used_segments = len(kept)
        else:
            final_lag = coarse_lag_fine
            used_segments = 0
            confidence = coarse_score
            drift_ms_per_min = None

        final_ms = final_lag / fine_rate * 1000.0

        return AnalysisResult(
            delay_ms=float(final_ms),
            coarse_ms=float(coarse_ms),
            confidence=float(confidence),
            total_segments=int(total_segments),
            used_segments=int(used_segments),
            drift_ms_per_min=drift_ms_per_min,
            skip_fallback=bool(skip_fallback),
        )

    @staticmethod
    def _weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
        if values.size == 0:
            return 0.0
        if values.size == 1:
            return float(values[0])

        order = np.argsort(values)
        sorted_values = values[order]
        sorted_weights = weights[order]
        cumulative = np.cumsum(sorted_weights, dtype=np.float64)
        cutoff = float(sorted_weights.sum()) * 0.5
        index = int(np.searchsorted(cumulative, cutoff, side="left"))
        index = min(max(index, 0), sorted_values.size - 1)
        return float(sorted_values[index])
