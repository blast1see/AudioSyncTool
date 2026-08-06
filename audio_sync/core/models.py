"""Veri modelleri — iş mantığı boyunca kullanılan yapılar."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from audio_sync.config import PcmCodec

# ── Ses Bilgisi ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AudioInfo:
    """FFprobe ile okunan ses dosyası meta verisi.

    Attributes:
        channels: Kanal sayısı (mono=1, stereo=2, …).
        codec: PCM codec türü.
        bits: Bit derinliği (16, 24, 32).
        sample_rate: Örnekleme oranı (Hz).
    """

    channels: int
    codec: PcmCodec
    bits: int
    sample_rate: int

    @classmethod
    def default(cls) -> AudioInfo:
        """Return explicit fallback metadata for callers that opt into it."""
        return cls(channels=2, codec=PcmCodec.S32LE, bits=32, sample_rate=48000)


# ── Çıktı Örnekleme Oranı ───────────────────────────────────────────────────


@dataclass(frozen=True)
class OutputSampleRate:
    """Çıktı örnekleme oranı kararı.

    Attributes:
        rate: Hedef örnekleme oranı (Hz).  ``None`` ise kaynak korunur.
        label: Kullanıcıya gösterilecek açıklama.
    """

    rate: int | None
    label: str

    @property
    def needs_resample(self) -> bool:
        """Yeniden örnekleme gerekip gerekmediğini döndürür."""
        return self.rate is not None

    @classmethod
    def decide(cls, src_sr: int, sync_sr: int, force_48k: bool) -> OutputSampleRate:
        """Kaynak ve senkron örnekleme oranlarına göre çıktı kararı verir.

        Args:
            src_sr: Kaynak dosya örnekleme oranı (Hz).
            sync_sr: Senkronize edilecek dosya örnekleme oranı (Hz).
            force_48k: Kullanıcı 48 kHz'i zorladı mı?

        Returns:
            Uygun ``OutputSampleRate`` örneği.
        """
        # ``src_sr`` is retained in the public signature for compatibility.
        # Only the synchronized track is written, so the reference track's
        # sample rate must not force an unnecessary conversion.
        _ = src_sr
        if force_48k:
            return cls(rate=48000, label="48000 Hz")
        return cls(rate=None, label=f"keep source ({sync_sr} Hz)")


# ── Ofset Bölgesi ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class OffsetRegion:
    """Referans zaman çizgisinde tek bir sabit ofsetin geçerli olduğu aralık.

    Yayın dublajları çoğu zaman tek bir gecikmeyle hizalanmaz: reklam arası
    kesmeleri, makara değişimleri veya farklı kurgular filmin ortasında ani bir
    basamak yaratır.  Ne sabit ofset ne de doğrusal drift bunu karşılar; bu
    yüzden ofset zaman içinde parça parça tanımlanır.

    Attributes:
        start_sec: Bölgenin referans zaman çizgisindeki başlangıcı (sn).
        end_sec: Bölgenin bitişi (sn).  Son bölge için ``math.inf``.
        lag_ms: Bu bölgede geçerli olan gecikme (ms), ``delay_ms`` ile aynı
            işaret kuralını kullanır.
        window_count: Bölgeyi destekleyen doğrulanmış pencere sayısı.
        confidence: Bölgeyi destekleyen pencerelerin medyan skoru.
    """

    start_sec: float
    end_sec: float
    lag_ms: float
    window_count: int
    confidence: float
    evidence_start_sec: float = 0.0
    evidence_end_sec: float = 0.0

    @property
    def duration_sec(self) -> float:
        """Bölge süresi; son bölge için ``math.inf``."""
        return self.end_sec - self.start_sec

    def bounds_in_minutes(self, open_ended: str = "end") -> tuple[float, str]:
        """Bölge sınırlarını dakikaya çevirir.

        Son bölgenin bitişi ``math.inf`` olduğu için her gösterim yerinde ayrı
        ayrı özel duruma sokuluyordu — pipeline logunda, arayüz logunda ve
        FFmpeg özetinde, üçü de farklı hassasiyetle.  Dönüşüm burada bir kez
        yapılır, biçimlendirme çağırana kalır.
        """
        end = open_ended if math.isinf(self.end_sec) else f"{self.end_sec / 60:.1f}"
        return self.start_sec / 60.0, end


# ── Eşleşme Kararı ───────────────────────────────────────────────────────────


class MatchVerdict(Enum):
    """Ölçülen gecikmenin ne kadar ciddiye alınabileceği.

    Korelasyon her zaman bir tepe bulur.  Bambaşka iki filmin sesi verildiğinde
    de bulur — ölçülen bir örnekte araç, alakasız bir çift için ``-1820320 ms``
    gibi bir sonucu tam ekran gösterip senkron düğmesini açık bıraktı.  Bu
    yüzden "gecikme kaç" sorusunun yanında "bu iki parça gerçekten aynı içerik
    mi" sorusunun da bir cevabı olmalı.

    Attributes:
        RELIABLE: Ölçüm tutarlı; sonuç doğrudan kullanılabilir.
        UNCERTAIN: Eşleşme var ama tek bir gecikme dosyanın tamamını
            tutmayabilir — kurgu farkı, drift ya da zayıf korelasyon.
        NO_MATCH: İki parça aynı içerik değil.  Üretilen sayı anlamsızdır.
    """

    RELIABLE = "reliable"
    UNCERTAIN = "uncertain"
    NO_MATCH = "no_match"


# ── Analiz Sonucu ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AnalysisResult:
    """Senkronizasyon analiz sonucu.

    Attributes:
        delay_ms: Nihai hesaplanan gecikme (ms).
        coarse_ms: Kaba analiz sonucu (ms).
        confidence: Güven skoru (yüksek = daha güvenilir).
        total_segments: Toplam segment sayısı.
        used_segments: Kullanılan (doğrulanan) segment sayısı.
        drift_ms_per_min: Tahmini drift (ms/dk).  ``None`` ise hesaplanamadı.
        skip_fallback: Atlama süresi çok uzun olduğu için tam dosya kullanıldı mı?
        drift_intercept_ms: Drift doğrusunun ``t=0`` anındaki gecikmesi (ms).
            Drift düzeltmesi uygulanırken sabit ofset bu değerden türetilir;
            ``delay_ms`` segmentlerin ağırlıklı medyanı olduğu için içeriğin
            ortasındaki gecikmeyi temsil eder ve tempo düzeltmesiyle birlikte
            kullanılamaz.
        drift_r2: Drift doğrusal uyumunun açıkladığı varyans oranı (0–1).
            Düşük değer, ölçülen eğimin gürültü olduğunu gösterir.
        drift_span_sec: Drift uyumunu besleyen segmentlerin zaman aralığı (sn).
    """

    delay_ms: float
    coarse_ms: float
    confidence: float
    total_segments: int
    used_segments: int
    drift_ms_per_min: float | None
    skip_fallback: bool
    drift_intercept_ms: float | None = None
    drift_r2: float | None = None
    drift_span_sec: float = 0.0
    offset_regions: tuple[OffsetRegion, ...] = ()
    residual_mad_ms: float = 0.0
    # Spread of the validated windows about ``delay_ms`` itself, in ms.  This
    # is deliberately *not* ``residual_mad_ms``: the latter measures the fit to
    # whichever model the winning candidate proposed, and an anchored candidate
    # is fitted to its own anchors, so it reads ~0 on precisely the files that
    # a single delay cannot describe.  A three-region staircase measured 0.0 ms
    # of "disagreement" while its regions sat 660 ms apart.
    lag_spread_ms: float = 0.0
    # Name of the frame-rate conversion that explains the pair better than no
    # conversion, when one does.  Stored as the enum member name so this module
    # does not have to import the config layer.
    suspected_fps_conversion: str | None = None
    verdict: MatchVerdict = MatchVerdict.RELIABLE
    # i18n keys naming what pushed the verdict down, in the order found.
    verdict_reasons: tuple[str, ...] = ()
    # Sample-accurate cross-check of ``delay_ms`` on the raw PCM, when one was
    # possible: ``(refined_ms, sharpness, agreeing_probes)``.
    phat_refined_ms: float | None = None
    phat_sharpness: float = 0.0
    phat_probes: int = 0
    src_duration_sec: float = 0.0
    sync_duration_sec: float = 0.0

    @property
    def windows_disagree_ms(self) -> float:
        """Spread of the validated windows about the delay actually reported.

        This is the honest measure of how far the single reported delay can be
        trusted across the file.  A clean pair settles around 15 ms; a pair
        whose sources are structurally different — a different cut, or a clock
        difference too large for the search window to follow — leaves hundreds
        of milliseconds of disagreement, and the headline delay is then only
        right for whichever stretch of the film dominated the vote.
        """
        return self.lag_spread_ms or self.residual_mad_ms

    @property
    def is_usable(self) -> bool:
        """Whether the measurement is worth acting on at all."""
        return self.verdict is not MatchVerdict.NO_MATCH

    @property
    def has_step_discontinuity(self) -> bool:
        """Ofsetin dosya boyunca en az bir kez sıçrayıp sıçramadığı."""
        return len(self.offset_regions) > 1

    @property
    def step_span_ms(self) -> float:
        """En büyük ve en küçük bölge ofseti arasındaki fark (ms)."""
        if not self.offset_regions:
            return 0.0
        lags = [region.lag_ms for region in self.offset_regions]
        return max(lags) - min(lags)

    @property
    def has_drift_measurement(self) -> bool:
        """Whether a usable slope and intercept came out of the fit.

        This reports only what was measured.  Whether the measurement is worth
        acting on is a policy question with configurable thresholds, and it is
        answered by :meth:`SyncPipeline.resolve_drift_correction` — a result
        object should not be deciding what the pipeline does with it.
        """
        return (
            self.drift_ms_per_min is not None
            and self.drift_intercept_ms is not None
            and self.drift_r2 is not None
        )


class OperationCancelledError(RuntimeError):
    """Raised when a long-running background operation is cancelled by the user."""


class AudioProbeError(RuntimeError):
    """Raised when FFprobe cannot produce trustworthy audio metadata."""


class UnsafeOutputPathError(ValueError):
    """Raised when an output path would overwrite one of the input files."""


class NoMatchError(RuntimeError):
    """Raised when the two tracks are not the same content.

    Writing a file from such a measurement is worse than writing nothing: the
    result is silently and hugely out of sync, and nothing in it points back at
    the mistake that produced it.
    """


class EncodingError(RuntimeError):
    """Raised when final encoding fails after synchronization completed."""

    def __init__(self, message: str, fallback_path: str | None = None) -> None:
        super().__init__(message)
        self.fallback_path = fallback_path


# ── İlerleme Callback Protokolü ─────────────────────────────────────────────


class ProgressCallback(Protocol):
    """İş mantığından UI'a ilerleme bildirimi için protokol.

    Bu protokolü uygulayan herhangi bir nesne callback olarak kullanılabilir.
    Test'te mock, UI'da gerçek implementasyon sağlanır.
    """

    def on_log(self, message: str) -> None:
        """Log mesajı gönderir."""
        ...

    def on_progress(self, percent: int) -> None:
        """İlerleme yüzdesini günceller (0-100)."""
        ...

    def on_info_update(self, key: str, value: str, color: str | None = None) -> None:
        """Bilgi panelindeki bir değeri günceller."""
        ...

    def on_complete(self, out_path: str) -> None:
        """İşlem başarıyla tamamlandığında çağrılır."""
        ...

    def on_error(self, error: str) -> None:
        """Hata oluştuğunda çağrılır."""
        ...
