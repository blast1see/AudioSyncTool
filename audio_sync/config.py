"""Uygulama yapılandırması — tema, fontlar, algoritmik parametreler ve sabitler."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


# ── Senkronizasyon Modu ──────────────────────────────────────────────────────


class SyncMode(Enum):
    """FFmpeg ses senkronizasyon filtre modları.

    Her mod farklı bir FFmpeg filtre stratejisi kullanır:
        - ADELAY_AMIX: Varsayılan — adelay + amix ile gecikme uygulama ve karıştırma.
        - ARESAMPLE: aresample filtresi ile örnekleme oranı tabanlı senkronizasyon.
        - ATEMPO: atempo filtresi ile tempo tabanlı ince ayar senkronizasyonu.
        - RUBBERBAND: librubberband tabanlı yüksek kaliteli zaman uzatma/sıkıştırma.
        - APAD: apad + atrim ile sessizlik ekleme/kırpma tabanlı senkronizasyon.
        - ASYNCTS: asyncts (eski) filtresi ile otomatik ses senkronizasyonu.

    Attributes:
        filter_name: FFmpeg filtre adı.
        display_name: Kullanıcıya gösterilecek açıklama.
        description_tr: Türkçe açıklama.
        description_en: İngilizce açıklama.
    """

    ADELAY_AMIX = ("adelay+amix", "adelay + amix (Varsayılan)",
                   "Gecikme uygulama ve karıştırma — en güvenilir yöntem",
                   "Delay application and mixing — most reliable method")
    ARESAMPLE = ("aresample", "aresample",
                 "Örnekleme oranı tabanlı senkronizasyon",
                 "Sample rate based synchronization")
    ATEMPO = ("atempo", "atempo (kırpma + ince ayar)",
              "Kırpma tabanlı senkronizasyon — sessizlik boşluğu oluşturmaz",
              "Trim-based synchronization — no silence gaps")
    RUBBERBAND = ("rubberband", "rubberband (yüksek kalite)",
                  "Kırpma + rubberband kalite iyileştirme (librubberband gerektirir)",
                  "Trim + rubberband quality enhancement (requires librubberband)")
    APAD = ("apad+atrim", "apad + atrim",
            "Sessizlik ekleme/kırpma tabanlı senkronizasyon",
            "Silence padding/trimming based synchronization")
    ASYNCTS = ("asyncts", "asyncts (eski)",
               "Otomatik ses senkronizasyonu (eski FFmpeg filtresi)",
               "Automatic audio sync (legacy FFmpeg filter)")

    def __init__(
        self, filter_name: str, display_name: str,
        description_tr: str, description_en: str,
    ) -> None:
        self.filter_name = filter_name
        self.display_name = display_name
        self.description_tr = description_tr
        self.description_en = description_en


# ── Tema Renkleri ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Theme:
    """Uygulama renk paleti.  ``frozen=True`` ile değiştirilemez."""

    bg: str = "#0f0f13"
    card: str = "#1a1a22"
    accent: str = "#6c63ff"
    accent2: str = "#ff6584"
    text: str = "#e8e8f0"
    muted: str = "#6b6b82"
    border: str = "#2a2a3a"
    input_bg: str = "#11111a"


# ── Fontlar ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Fonts:
    """Uygulama font tanımları."""

    label: tuple[str, int] = ("Courier New", 10)
    small: tuple[str, int] = ("Courier New", 9)
    mono: tuple[str, int] = ("Courier New", 10)
    button: tuple[str, int, str] = ("Courier New", 10, "bold")
    header: tuple[str, int, str] = ("Courier New", 28, "bold")
    dot: tuple[str, int] = ("Courier New", 14)
    info_value: tuple[str, int, str] = ("Courier New", 10, "bold")


# ── PCM Codec Enum ──────────────────────────────────────────────────────────


class FpsConversion(Enum):
    """FPS dönüşüm senaryoları — kaynak ve hedef frame rate çiftleri.

    Her senaryo için matematiksel oran ``source_fps / target_fps`` olarak
    hesaplanır.  Bu oran FFmpeg ``atempo`` filtresine geçirilerek ses hızı
    ayarlanır.

    Attributes:
        source_fps: Kaynak frame rate.
        target_fps: Hedef frame rate.
        display_name: Kullanıcıya gösterilecek açıklama.
    """

    FPS_25_TO_23976 = (25.0, 23.976, "25 → 23.976 FPS")
    FPS_24_TO_23976 = (24.0, 23.976, "24 → 23.976 FPS")
    FPS_25_TO_24 = (25.0, 24.0, "25 → 24 FPS")
    FPS_24_TO_25 = (24.0, 25.0, "24 → 25 FPS")
    FPS_23976_TO_24 = (23.976, 24.0, "23.976 → 24 FPS")
    FPS_23976_TO_25 = (23.976, 25.0, "23.976 → 25 FPS")

    def __init__(self, source_fps: float, target_fps: float, display_name: str) -> None:
        self.source_fps = source_fps
        self.target_fps = target_fps
        self.display_name = display_name

    @property
    def tempo_ratio(self) -> float:
        """FFmpeg ``atempo`` filtresi için hız oranını hesaplar.

        Returns:
            Hız oranı.  >1.0 → yavaşlatma, <1.0 → hızlandırma.
        """
        return self.source_fps / self.target_fps


@dataclass(frozen=True)
class FpsConfig:
    """FPS dönüşüm yapılandırması.

    Attributes:
        enabled: FPS dönüşümü etkin mi?
        conversion: Seçili dönüşüm senaryosu.
    """

    enabled: bool = False
    conversion: FpsConversion = FpsConversion.FPS_25_TO_23976


class PcmCodec(Enum):
    """FFmpeg PCM codec seçenekleri — bit derinliğine göre."""

    S16LE = ("pcm_s16le", 16)
    S24LE = ("pcm_s24le", 24)
    S32LE = ("pcm_s32le", 32)

    def __init__(self, codec_name: str, max_bits: int) -> None:
        self.codec_name = codec_name
        self.max_bits = max_bits

    @classmethod
    def from_bits(cls, bits: int) -> PcmCodec:
        """Bit derinliğine göre uygun codec'i seçer.

        Args:
            bits: Ses dosyasının bit derinliği.

        Returns:
            Uygun ``PcmCodec`` enum üyesi.
        """
        if bits <= 16:
            return cls.S16LE
        if bits <= 24:
            return cls.S24LE
        return cls.S32LE


# ── Senkronizasyon Algoritma Parametreleri ───────────────────────────────────


@dataclass(frozen=True)
class SyncConfig:
    """Senkronizasyon algoritması yapılandırması.

    Tüm sihirli sayılar burada merkezi olarak tanımlanır.
    """

    # Kaba analiz
    coarse_hop_ms: int = 80
    coarse_smooth_ms: int = 180

    # İnce analiz
    fine_hop_ms: int = 20
    fine_smooth_ms: int = 80

    # Segment parametreleri
    segment_duration_sec: float = 12.0
    local_search_sec: float = 3.5
    min_std_threshold: float = 0.30

    # Sinyal işleme
    envelope_gain: float = 12.0
    emphasis_signal_weight: float = 0.70
    emphasis_diff_weight: float = 0.30
    bandpass_low_hz: float = 90.0
    bandpass_high_hz: float = 3800.0
    bandpass_order: int = 4
    min_feature_length: int = 16

    # Genel
    min_audio_duration_sec: int = 8
    analysis_sample_rate: int = 16000

    # FFmpeg
    ffmpeg_timeout_sec: int = 300
    ffprobe_timeout_sec: int = 30

    # Drift uyarı eşiği (ms/dk)
    drift_warning_threshold: float = 20.0


# ── Deew Encoder Yapılandırması ──────────────────────────────────────────────


class DeewFormat(Enum):
    """Deew çıktı format seçenekleri."""

    DD = ("dd", "AC3 (Dolby Digital)", ".ac3")
    DDP = ("ddp", "EAC3 (Dolby Digital Plus)", ".eac3")

    def __init__(self, cli_value: str, display_name: str, extension: str) -> None:
        self.cli_value = cli_value
        self.display_name = display_name
        self.extension = extension


class DeewDownmix(Enum):
    """Deew downmix (kanal düzeni) seçenekleri."""

    MONO = (1, "Mono (1.0)")
    STEREO = (2, "Stereo (2.0)")
    SURROUND = (6, "5.1 Surround")
    SURROUND_71 = (8, "7.1 Surround")

    def __init__(self, channels: int, display_name: str) -> None:
        self.channels = channels
        self.display_name = display_name


class DeewDRC(Enum):
    """Deew DRC (Dynamic Range Compression) profilleri."""

    FILM_LIGHT = ("film_light", "Film Light")
    FILM_STANDARD = ("film_standard", "Film Standard")
    MUSIC_LIGHT = ("music_light", "Music Light (varsayılan)")
    MUSIC_STANDARD = ("music_standard", "Music Standard")
    SPEECH = ("speech", "Speech")

    def __init__(self, cli_value: str, display_name: str) -> None:
        self.cli_value = cli_value
        self.display_name = display_name


@dataclass(frozen=True)
class DeewConfig:
    """Deew encoder yapılandırması.

    Attributes:
        enabled: Deew dönüştürme etkin mi?
        format: Çıktı formatı (DD veya DDP).
        bitrate: Bitrate (kbps).  ``None`` ise deew varsayılanı kullanılır.
        downmix: Kanal düzeni.  ``None`` ise kaynak korunur.
        drc: DRC profili.
        dialnorm: Dialnorm değeri (-31 ile 0 arası, 0 = otomatik).
        delete_intermediate_wav: Ara WAV dosyasını sil mi?
    """

    enabled: bool = False
    format: DeewFormat = DeewFormat.DDP
    bitrate: int | None = None
    downmix: DeewDownmix | None = None
    drc: DeewDRC = DeewDRC.MUSIC_LIGHT
    dialnorm: int = 0
    delete_intermediate_wav: bool = True


# ── Deew Bitrate Tabloları ───────────────────────────────────────────────────

# Deew'in desteklediği bitrate değerleri (format_kanal bazında)
DEEW_BITRATES: dict[str, list[int]] = {
    # DD (AC3)
    "dd_mono":    [96, 112, 128, 160, 192, 224, 256, 320, 384, 448, 512, 576, 640],
    "dd_stereo":  [96, 112, 128, 160, 192, 224, 256, 320, 384, 448, 512, 576, 640],
    "dd_51":      [224, 256, 320, 384, 448, 512, 576, 640],
    # DDP (EAC3)
    "ddp_mono":   [32, 40, 48, 56, 64, 72, 80, 88, 96, 104, 112, 120, 128, 144,
                   160, 176, 192, 200, 208, 216, 224, 232, 240, 248, 256, 272,
                   288, 304, 320, 336, 352, 368, 384, 400, 448, 512, 576, 640,
                   704, 768, 832, 896, 960, 1008, 1024],
    "ddp_stereo": [96, 104, 112, 120, 128, 144, 160, 176, 192, 200, 208, 216,
                   224, 232, 240, 248, 256, 272, 288, 304, 320, 336, 352, 368,
                   384, 400, 448, 512, 576, 640, 704, 768, 832, 896, 960, 1008,
                   1024],
    "ddp_51":     [192, 200, 208, 216, 224, 232, 240, 248, 256, 272, 288, 304,
                   320, 336, 352, 368, 384, 400, 448, 512, 576, 640, 704, 768,
                   832, 896, 960, 1008, 1024],
    "ddp_71":     [192, 200, 208, 216, 224, 232, 240, 248, 256, 272, 288, 304,
                   320, 336, 352, 368, 384, 400, 448, 512, 576, 640, 704, 768,
                   832, 896, 960, 1008, 1024, 1536],
}

# UI'da gösterilecek yaygın bitrate değerleri (kısa liste)
DEEW_COMMON_BITRATES: dict[str, list[int]] = {
    "dd_mono":    [128, 192, 224, 256, 384, 448, 640],
    "dd_stereo":  [128, 192, 224, 256, 384, 448, 640],
    "dd_51":      [224, 256, 384, 448, 640],
    "ddp_mono":   [64, 96, 128, 192, 224, 256, 384, 448, 640, 768, 1024],
    "ddp_stereo": [128, 192, 224, 256, 384, 448, 640, 768, 1024],
    "ddp_51":     [192, 224, 256, 384, 448, 640, 768, 1024],
    "ddp_71":     [224, 256, 384, 448, 640, 768, 896, 1024, 1536],
}

# Varsayılan bitrate değerleri (format_kanal bazında)
DEEW_DEFAULT_BITRATES: dict[str, int] = {
    "dd_mono":    192,
    "dd_stereo":  256,
    "dd_51":      448,
    "ddp_mono":   256,
    "ddp_stereo": 384,
    "ddp_51":     640,
    "ddp_71":     768,
}


def get_deew_bitrate_key(fmt: DeewFormat, downmix: DeewDownmix | None) -> str:
    """Format ve kanal düzenine göre bitrate tablo anahtarını döndürür.

    Args:
        fmt: Deew çıktı formatı.
        downmix: Kanal düzeni.  ``None`` ise stereo varsayılır.

    Returns:
        Bitrate tablosu anahtarı (ör. ``"ddp_stereo"``).
    """
    prefix = fmt.cli_value  # "dd" veya "ddp"
    if downmix is None or downmix == DeewDownmix.STEREO:
        suffix = "stereo"
    elif downmix == DeewDownmix.MONO:
        suffix = "mono"
    elif downmix == DeewDownmix.SURROUND_71:
        suffix = "71"
    else:
        suffix = "51"
    return f"{prefix}_{suffix}"


# ── Encoder Seçimi ───────────────────────────────────────────────────────────


class EncoderType(Enum):
    """Dolby encoding için kullanılacak araç seçimi."""

    DEE = ("dee", "DEE (Dolby Encoding Engine)")
    FFMPEG = ("ffmpeg", "FFmpeg")

    def __init__(self, cli_value: str, display_name: str) -> None:
        self.cli_value = cli_value
        self.display_name = display_name


# FFmpeg AC3/EAC3 bitrate tabloları
FFMPEG_AC3_BITRATES: list[int] = [96, 128, 160, 192, 224, 256, 320, 384, 448, 512, 576, 640]
FFMPEG_EAC3_BITRATES: list[int] = [
    64, 96, 128, 160, 192, 224, 256, 320, 384, 448, 512, 640, 768, 896, 1024,
]

FFMPEG_AC3_DEFAULT_BITRATE: int = 448
FFMPEG_EAC3_DEFAULT_BITRATE: int = 640


# ── Varsayılan Örnekler ─────────────────────────────────────────────────────

THEME = Theme()
FONTS = Fonts()
SYNC_CONFIG = SyncConfig()
DEEW_CONFIG = DeewConfig()
FPS_CONFIG = FpsConfig()

# Desteklenen ses dosyası uzantıları
SUPPORTED_AUDIO_EXTENSIONS_LIST: tuple[str, ...] = (
    ".wav", ".mp3", ".flac", ".aac", ".ogg", ".m4a",
    ".ac3", ".eac3", ".dts", ".mka", ".opus", ".wma",
)
SUPPORTED_AUDIO_EXTENSIONS: str = " ".join(f"*{ext}" for ext in SUPPORTED_AUDIO_EXTENSIONS_LIST)
