"""Ses analizi ve gecikme hesaplama motoru.

Bu modül Tkinter'a bağımlı **değildir** ve bağımsız olarak test edilebilir.
Tüm DSP işlemleri burada merkezi olarak yapılır.
"""

from __future__ import annotations

import warnings

import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, correlate, fftconvolve, sosfiltfilt

from audio_sync.config import SyncConfig, SYNC_CONFIG
from audio_sync.core.models import AnalysisResult


class AudioAnalyzer:
    """Ses analizi ve gecikme hesaplama motoru.

    Args:
        config: Senkronizasyon algoritma parametreleri.

    Example::

        analyzer = AudioAnalyzer()
        result = analyzer.calculate_delay("src.wav", "sync.wav", skip_intro_sec=120)
        print(f"Gecikme: {result.delay_ms:.1f} ms")
    """

    def __init__(self, config: SyncConfig = SYNC_CONFIG) -> None:
        self._config = config

    # ── Ana API ──────────────────────────────────────────────────────────

    def calculate_delay(
        self,
        src_wav: str,
        sync_wav: str,
        skip_intro_sec: float = 120.0,
        total_segments: int = 12,
    ) -> AnalysisResult:
        """İki aşamalı sağlam kayma hesabı.

        Algoritma:
            1. Başlangıçtaki farklı bölümü atlayarak kaba offset hesaplar.
            2. Çoklu segmentle yüksek çözünürlüklü doğrulama yapar.
            3. Outlier filtreleme ve ağırlıklı ortalama ile nihai sonuç üretir.

        Args:
            src_wav: Kaynak (referans) mono WAV dosyası yolu.
            sync_wav: Senkronize edilecek mono WAV dosyası yolu.
            skip_intro_sec: Başlangıçta atlanacak süre (saniye).
            total_segments: Doğrulama için kullanılacak segment sayısı.

        Returns:
            ``AnalysisResult`` nesnesi.

        Raises:
            RuntimeError: Örnekleme oranları eşleşmiyorsa veya dosyalar çok kısaysa.

        Note:
            Pozitif delay_ms → sync ses ileride (erken başlıyor).
            Negatif delay_ms → sync ses geride (geç başlıyor).
        """
        rate, d1, d2 = self._load_and_validate(src_wav, sync_wav)
        cfg = self._config

        # Atlama hesabı
        skip_samples = int(max(0.0, skip_intro_sec) * rate)
        skip_fallback = False

        d1_for_coarse, d2_for_coarse, skip_samples, skip_fallback = self._apply_skip(
            d1, d2, skip_samples, int(rate * cfg.min_audio_duration_sec),
        )

        # Bandpass filtreyi bir kez uygula (performans optimizasyonu)
        d1_coarse_filtered = self.bandpass_for_sync(d1_for_coarse, rate)
        d2_coarse_filtered = self.bandpass_for_sync(d2_for_coarse, rate)
        d1_full_filtered = self.bandpass_for_sync(d1, rate)
        d2_full_filtered = self.bandpass_for_sync(d2, rate)

        # Kaba analiz
        coarse_feat1, coarse_rate = self._build_feature_from_filtered(
            d1_coarse_filtered, rate, hop_ms=cfg.coarse_hop_ms, smooth_ms=cfg.coarse_smooth_ms,
        )
        coarse_feat2, _ = self._build_feature_from_filtered(
            d2_coarse_filtered, rate, hop_ms=cfg.coarse_hop_ms, smooth_ms=cfg.coarse_smooth_ms,
        )
        coarse_lag, coarse_score = self.best_lag(coarse_feat1, coarse_feat2)
        coarse_ms = coarse_lag / coarse_rate * 1000.0

        # İnce analiz
        fine_feat1, fine_rate = self._build_feature_from_filtered(
            d1_full_filtered, rate, hop_ms=cfg.fine_hop_ms, smooth_ms=cfg.fine_smooth_ms,
        )
        fine_feat2, _ = self._build_feature_from_filtered(
            d2_full_filtered, rate, hop_ms=cfg.fine_hop_ms, smooth_ms=cfg.fine_smooth_ms,
        )

        # Segment doğrulama
        segment_results = self._segment_validation(
            fine_feat1, fine_feat2, fine_rate, coarse_lag,
            skip_samples, rate, total_segments,
        )

        # Sonuç hesaplama
        return self._compute_final_result(
            segment_results, coarse_lag, coarse_ms, coarse_score, coarse_rate,
            fine_rate, total_segments, skip_fallback, cfg.local_search_sec,
        )

    # ── Sinyal İşleme (Statik — Test Edilebilir) ────────────────────────

    @staticmethod
    def normalize_audio(data: np.ndarray) -> np.ndarray:
        """Ham ses verisini [-1, 1] aralığına normalize eder.

        İşlem adımları:
            1. float64'e dönüştürme
            2. Tamsayı ölçekleme (int16/int32 → [-1, 1])
            3. NaN/Inf temizleme
            4. DC offset kaldırma (ortalama çıkarma)
            5. Tepe normalizasyonu

        Args:
            data: ``wavfile.read()`` çıktısı (int16/int32/float32/float64).

        Returns:
            Normalize edilmiş float64 dizisi, tepe değeri 1.0.
        """
        x = data.astype(np.float64, copy=True)

        if np.issubdtype(data.dtype, np.integer):
            info = np.iinfo(data.dtype)
            x *= 1.0 / max(abs(info.min), info.max)

        # NaN/Inf temizle (in-place)
        np.nan_to_num(x, copy=False, nan=0.0, posinf=0.0, neginf=0.0)

        # DC offset kaldır (in-place)
        x -= np.mean(x)

        # Tepe normalizasyonu (in-place)
        peak = np.max(np.abs(x)) if x.size > 0 else 0.0
        if peak > 1e-9:
            x *= 1.0 / peak

        return x

    def bandpass_for_sync(self, x: np.ndarray, rate: int) -> np.ndarray:
        """Senkronizasyon için bandpass filtre uygular.

        Args:
            x: Giriş sinyali.
            rate: Örnekleme oranı (Hz).

        Returns:
            Filtrelenmiş sinyal.  Filtre uygulanamıyorsa orijinal sinyal döner.
        """
        cfg = self._config
        if rate < 1000 or len(x) < rate:
            return x

        low = cfg.bandpass_low_hz
        high = min(cfg.bandpass_high_hz, rate * 0.45)
        if high <= low * 1.2:
            return x

        try:
            sos = butter(
                cfg.bandpass_order, [low, high],
                btype="bandpass", fs=rate, output="sos",
            )
            return sosfiltfilt(sos, x)
        except Exception as exc:
            warnings.warn(
                f"Bandpass filtre uygulanamadı, filtresiz sinyal kullanılıyor: {exc}",
                RuntimeWarning,
                stacklevel=2,
            )
            return x

    @staticmethod
    def best_lag(feat1: np.ndarray, feat2: np.ndarray) -> tuple[int, float]:
        """İki özellik vektörü arasındaki en iyi gecikmeyi bulur.

        Çapraz korelasyon kullanarak en yüksek benzerlik noktasını tespit eder.

        Args:
            feat1: Birinci özellik vektörü (referans).
            feat2: İkinci özellik vektörü.

        Returns:
            ``(lag, score)`` çifti.
            ``lag``: Örnek cinsinden gecikme.
            ``score``: Tepe/taban oranı (güven göstergesi).
        """
        corr = correlate(feat1, feat2, mode="full", method="fft")
        lags = np.arange(-len(feat2) + 1, len(feat1))
        idx = int(np.argmax(corr))
        peak = float(corr[idx])
        floor = float(np.median(np.abs(corr)) + 1e-9)
        score = peak / floor
        return int(lags[idx]), score

    @staticmethod
    def describe_offset(delay_ms: float) -> str:
        """Gecikme değerini insan okunabilir açıklamaya çevirir.

        Args:
            delay_ms: Gecikme (milisaniye).

        Returns:
            Türkçe açıklama metni.
        """
        if delay_ms >= 0:
            return "sync ses ileride"
        return "sync ses geride"

    # ── Dahili Yardımcılar ───────────────────────────────────────────────

    def _load_and_validate(
        self, src_wav: str, sync_wav: str,
    ) -> tuple[int, np.ndarray, np.ndarray]:
        """WAV dosyalarını yükler, doğrular ve normalize eder.

        Returns:
            ``(rate, d1_normalized, d2_normalized)`` üçlüsü.

        Raises:
            RuntimeError: Örnekleme oranları eşleşmiyorsa veya dosyalar çok kısaysa.
        """
        rate1, data1 = wavfile.read(src_wav)
        rate2, data2 = wavfile.read(sync_wav)

        if rate1 != rate2:
            raise RuntimeError("Analiz örnekleme oranları eşleşmiyor.")

        rate = rate1
        d1 = self.normalize_audio(data1)
        d2 = self.normalize_audio(data2)

        min_samples = int(rate * self._config.min_audio_duration_sec)
        if len(d1) < min_samples or len(d2) < min_samples:
            raise RuntimeError(
                f"Senkron analizi için dosyalar çok kısa "
                f"(en az ~{self._config.min_audio_duration_sec} sn gerekli)."
            )

        return rate, d1, d2

    @staticmethod
    def _apply_skip(
        d1: np.ndarray,
        d2: np.ndarray,
        skip_samples: int,
        min_samples: int,
    ) -> tuple[np.ndarray, np.ndarray, int, bool]:
        """Başlangıç atlamasını uygular, gerekirse fallback yapar.

        Returns:
            ``(d1_coarse, d2_coarse, effective_skip_samples, skip_fallback)``
        """
        skip_fallback = False

        d1_coarse = d1[skip_samples:] if skip_samples < len(d1) else np.array([], dtype=np.float64)
        d2_coarse = d2[skip_samples:] if skip_samples < len(d2) else np.array([], dtype=np.float64)

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
        """Önceden filtrelenmiş sinyalden özellik vektörü oluşturur.

        Bandpass filtre zaten uygulanmış olmalıdır (performans optimizasyonu).

        Args:
            x_filtered: Bandpass filtrelenmiş sinyal.
            rate: Örnekleme oranı (Hz).
            hop_ms: Atlama boyutu (ms).
            smooth_ms: Yumuşatma penceresi (ms).

        Returns:
            ``(feature_vector, feature_rate)`` çifti.

        Raises:
            RuntimeError: Yeterli örnek oluşmazsa.
        """
        cfg = self._config

        dx = np.diff(x_filtered, prepend=x_filtered[0])
        emphasis = cfg.emphasis_signal_weight * np.abs(x_filtered) + cfg.emphasis_diff_weight * np.abs(dx)

        smooth = max(8, int(rate * smooth_ms / 1000.0))
        kernel = np.ones(smooth, dtype=np.float64) / smooth

        # FFT tabanlı konvolüsyon — büyük dizilerde ~O(n log n)
        env = fftconvolve(emphasis, kernel, mode="same")
        env = np.log1p(env * cfg.envelope_gain)

        hop = max(1, int(rate * hop_ms / 1000.0))
        feat = env[::hop]
        if len(feat) < cfg.min_feature_length:
            raise RuntimeError("Analiz için yeterli örnek oluşmadı.")

        feat = np.diff(feat, prepend=feat[0])
        feat = np.maximum(feat, 0.0)
        feat = feat - np.median(feat)
        std = np.std(feat)
        if std > 1e-9:
            feat = feat / std
        else:
            feat = feat * 0.0

        return feat.astype(np.float64), rate / hop

    def _segment_validation(
        self,
        fine_feat1: np.ndarray,
        fine_feat2: np.ndarray,
        fine_rate: float,
        coarse_lag: int,
        skip_samples: int,
        rate: int,
        total_segments: int,
    ) -> list[dict[str, float]]:
        """Çoklu segment doğrulaması yapar.

        Args:
            fine_feat1: Referans ince özellik vektörü.
            fine_feat2: Senkron ince özellik vektörü.
            fine_rate: İnce özellik örnekleme oranı.
            coarse_lag: Kaba analiz sonucu (örnek cinsinden).
            skip_samples: Atlanan örnek sayısı.
            rate: Orijinal örnekleme oranı.
            total_segments: Toplam segment sayısı.

        Returns:
            Segment sonuçları listesi.
        """
        cfg = self._config
        seg_len = max(1, int(cfg.segment_duration_sec * fine_rate))
        local_steps = max(1, int(cfg.local_search_sec * fine_rate))
        fine_skip = int(skip_samples / rate * fine_rate)

        overlap_start_ref = max(0, coarse_lag, fine_skip)
        overlap_end_ref = min(len(fine_feat1), len(fine_feat2) + coarse_lag)
        usable = overlap_end_ref - overlap_start_ref - seg_len

        if usable > seg_len:
            start_positions = np.linspace(
                overlap_start_ref,
                overlap_end_ref - seg_len,
                total_segments,
                dtype=int,
            )
        elif overlap_end_ref - overlap_start_ref > seg_len:
            start_positions = np.array([overlap_start_ref], dtype=int)
        else:
            start_positions = np.array([], dtype=int)

        segment_results: list[dict[str, float]] = []

        for ref_start in start_positions:
            sync_start_guess = ref_start - coarse_lag
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
            refined_lag = coarse_lag + local_steps - best_idx

            segment_results.append({
                "center_sec": (ref_start + seg_len / 2) / fine_rate,
                "lag": float(refined_lag),
                "score": score,
            })

        return segment_results

    @staticmethod
    def _compute_final_result(
        segment_results: list[dict[str, float]],
        coarse_lag: int,
        coarse_ms: float,
        coarse_score: float,
        coarse_rate: float,
        fine_rate: float,
        total_segments: int,
        skip_fallback: bool,
        local_search_sec: float = 3.5,
    ) -> AnalysisResult:
        """Segment sonuçlarından nihai gecikme ve analiz sonucu hesaplar.

        Returns:
            ``AnalysisResult`` nesnesi.
        """
        if segment_results:
            lag_values = np.array([r["lag"] for r in segment_results], dtype=np.float64)
            median_lag = float(np.median(lag_values))
            mad = float(np.median(np.abs(lag_values - median_lag)))

            local_steps_approx = int(local_search_sec * fine_rate)
            tolerance = max(local_steps_approx * 0.60, 3.0 * mad, fine_rate * 0.18)
            kept = [r for r in segment_results if abs(r["lag"] - median_lag) <= tolerance]

            if not kept:
                kept = sorted(segment_results, key=lambda r: r["score"], reverse=True)[:3]

            kept_lags = np.array([r["lag"] for r in kept], dtype=np.float64)
            kept_scores = np.array([max(1.0, r["score"]) for r in kept], dtype=np.float64)
            final_lag = float(np.average(kept_lags, weights=kept_scores))

            drift_ms_per_min: float | None = None
            if len(kept) >= 4:
                t = np.array([r["center_sec"] for r in kept], dtype=np.float64)
                y = np.array([r["lag"] / fine_rate * 1000.0 for r in kept], dtype=np.float64)
                slope_ms_per_sec = float(np.polyfit(t, y, 1)[0])
                drift_ms_per_min = slope_ms_per_sec * 60.0

            confidence = float(np.median([r["score"] for r in kept]))
            used_segments = len(kept)
        else:
            final_lag = coarse_lag * (fine_rate / coarse_rate)
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
