"""Veri modelleri — iş mantığı boyunca kullanılan yapılar."""

from __future__ import annotations

from dataclasses import dataclass
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
        """FFprobe başarısız olduğunda kullanılacak varsayılan değerler."""
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
        if force_48k or src_sr != 48000 or sync_sr != 48000:
            return cls(rate=48000, label="48000 Hz")
        return cls(rate=None, label="kaynağı koru (zaten 48 kHz)")


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
    """

    delay_ms: float
    coarse_ms: float
    confidence: float
    total_segments: int
    used_segments: int
    drift_ms_per_min: float | None
    skip_fallback: bool


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
