"""Uygulama yapılandırması — tema, fontlar, algoritmik parametreler ve sabitler."""

from __future__ import annotations

import dataclasses
import enum
import json
import os
import shutil
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


# ── Tool Path Resolution ─────────────────────────────────────────────
_TOOL_PATHS_DIR = Path.home() / ".audio_sync_tool"
_TOOL_PATHS_FILE = _TOOL_PATHS_DIR / "tool_paths.json"

# qaac binary candidates — 64-bit build is preferred
_QAAC_CANDIDATES = ("qaac64", "qaac")


@dataclasses.dataclass
class ToolPaths:
    """User-configurable paths for external tools.
    
    When a path is None, the tool is resolved via system PATH.
    When a path is set, that exact path is used instead.
    """
    ffmpeg: str | None = None
    ffprobe: str | None = None
    qaac: str | None = None
    deew: str | None = None

    def to_dict(self) -> dict:
        return {k: v for k, v in dataclasses.asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict) -> "ToolPaths":
        fields = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in fields})


def _load_tool_paths() -> ToolPaths:
    """Load tool paths from persistent JSON config."""
    try:
        if _TOOL_PATHS_FILE.is_file():
            data = json.loads(_TOOL_PATHS_FILE.read_text(encoding="utf-8"))
            return ToolPaths.from_dict(data.get("tool_paths", {}))
    except Exception:
        pass
    return ToolPaths()


def save_tool_paths(paths: ToolPaths) -> bool:
    """Save tool paths to persistent JSON config.

    Returns:
        True if saved successfully, False on I/O error.
    """
    global TOOL_PATHS
    TOOL_PATHS = paths
    try:
        _TOOL_PATHS_DIR.mkdir(parents=True, exist_ok=True)
        data = {"version": 1, "tool_paths": paths.to_dict()}
        _TOOL_PATHS_FILE.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return True
    except Exception:
        return False


def resolve_tool(name: str) -> str:
    """Resolve an external tool to its executable path.
    
    Resolution order:
    1. User-configured custom path in TOOL_PATHS (if set and file exists)
    2. System PATH lookup via shutil.which()
    3. For qaac: tries qaac64 first, then qaac
    
    Args:
        name: Tool name — one of "ffmpeg", "ffprobe", "qaac", "deew"
        
    Returns:
        Resolved executable path or name (for PATH-based lookup)
        
    Raises:
        OSError: If the tool cannot be found
    """
    # Check user-configured custom path
    custom = getattr(TOOL_PATHS, name, None)
    if custom and os.path.isfile(custom):
        return custom
    
    # Special handling for qaac — try qaac64 first
    if name == "qaac":
        for candidate in _QAAC_CANDIDATES:
            found = shutil.which(candidate)
            if found:
                return found
        raise OSError(
            f"qaac not found. Please install qaac and add it to PATH "
            f"(expected at C:\\qaac). The binary may be named qaac64.exe."
        )
    
    # Standard PATH lookup
    found = shutil.which(name)
    if found:
        return found
    
    raise OSError(f"{name} not found in PATH. Please install {name} or set a custom path.")


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

    ADELAY_AMIX = ("adelay+amix", "adelay + amix (Default)",
                   "Gecikme uygulama ve karıştırma — en güvenilir yöntem",
                   "Delay application and mixing — most reliable method")
    ARESAMPLE = ("aresample", "aresample",
                 "Örnekleme oranı tabanlı senkronizasyon",
                 "Sample rate based synchronization")
    ATEMPO = ("atempo", "atempo (trim + fine-tune)",
              "Kırpma tabanlı senkronizasyon — sessizlik boşluğu oluşturmaz",
              "Trim-based synchronization — no silence gaps")
    RUBBERBAND = ("rubberband", "rubberband (high quality)",
                  "Kırpma + rubberband kalite iyileştirme (librubberband gerektirir)",
                  "Trim + rubberband quality enhancement (requires librubberband)")
    APAD = ("apad+atrim", "apad + atrim",
            "Sessizlik ekleme/kırpma tabanlı senkronizasyon",
            "Silence padding/trimming based synchronization")
    ASYNCTS = ("asyncts", "asyncts (legacy)",
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

    DD = ("dd", "AC3 (Dolby Digital)", ".ac3", ())
    DDP = ("ddp", "EAC3 (Dolby Digital Plus)", ".eac3", (".ec3",))

    def __init__(
        self, cli_value: str, display_name: str, extension: str,
        alt_extensions: tuple[str, ...] = (),
    ) -> None:
        self.cli_value = cli_value
        self.display_name = display_name
        self.extension = extension
        self.alt_extensions = alt_extensions

    @property
    def all_extensions(self) -> tuple[str, ...]:
        """Birincil ve alternatif uzantıların tümünü döndürür."""
        return (self.extension, *self.alt_extensions)


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
    MUSIC_LIGHT = ("music_light", "Music Light (default)")
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


# ── Encoding Pipeline ─────────────────────────────────────────────
class EncodingPipeline(enum.Enum):
    """Top-level encoding pipeline selector."""
    NONE = "none"
    DOLBY = "dolby"
    FFMPEG = "ffmpeg"
    QAAC = "qaac"
    # NATIVE removed — FLAC/Opus now handled by FFmpeg


class FFmpegOutputFormat(enum.Enum):
    """FFmpeg output format options."""
    AAC = ("aac", ".m4a", "AAC (FFmpeg)")
    FLAC = ("flac", ".flac", "FLAC (FFmpeg)")
    OPUS = ("libopus", ".opus", "Opus (FFmpeg)")

    def __init__(self, codec: str, ext: str, label: str) -> None:
        self.codec = codec
        self.ext = ext
        self.label = label


@dataclasses.dataclass(frozen=True)
class FFmpegEncodeConfig:
    """FFmpeg encoding configuration."""
    format: FFmpegOutputFormat = FFmpegOutputFormat.AAC
    aac_bitrate: int = 256          # kbps for AAC
    flac_compression: int = 5       # 0-12 for FLAC
    flac_bit_depth: int = 24        # 16 or 24
    opus_bitrate: int = 128         # kbps for Opus


class QaacMode(enum.Enum):
    """qaac encoding mode."""
    TVBR = ("--tvbr", "True VBR (TVBR)")
    CVBR = ("--cvbr", "Constrained VBR (CVBR)")
    ABR = ("--abr", "ABR")
    CBR = ("--cbr", "CBR")

    def __init__(self, flag: str, label: str) -> None:
        self.flag = flag
        self.label = label


@dataclasses.dataclass(frozen=True)
class QaacConfig:
    """qaac encoder configuration."""
    mode: QaacMode = QaacMode.TVBR
    tvbr_quality: int = 91          # 0-127 for TVBR
    cvbr_bitrate: int = 256         # kbps for CVBR
    abr_bitrate: int = 256          # kbps for ABR
    cbr_bitrate: int = 256          # kbps for CBR
    he_aac: bool = False            # Use HE-AAC profile
    no_delay: bool = True           # --no-delay flag


# ── Varsayılan Örnekler ─────────────────────────────────────────────────────

THEME = Theme()
FONTS = Fonts()
SYNC_CONFIG = SyncConfig()
DEEW_CONFIG = DeewConfig()
FPS_CONFIG = FpsConfig()
FFMPEG_ENCODE_CONFIG = FFmpegEncodeConfig()
QAAC_CONFIG = QaacConfig()
TOOL_PATHS = _load_tool_paths()

# Supported audio file extensions
SUPPORTED_AUDIO_EXTENSIONS_LIST: tuple[str, ...] = (
    ".wav", ".mp3", ".flac", ".aac", ".ogg", ".m4a",
    ".ac3", ".eac3", ".ec3", ".dts", ".mka", ".opus", ".wma",
)

# Container formats that may contain multiple audio streams
CONTAINER_EXTENSIONS: tuple[str, ...] = (
    ".mkv", ".mp4", ".m4v", ".webm", ".ts", ".mts",
)

# All supported extensions (audio + containers)
ALL_SUPPORTED_EXTENSIONS_LIST: tuple[str, ...] = (
    *SUPPORTED_AUDIO_EXTENSIONS_LIST, *CONTAINER_EXTENSIONS,
)
SUPPORTED_AUDIO_EXTENSIONS: str = " ".join(
    f"*{ext}" for ext in ALL_SUPPORTED_EXTENSIONS_LIST
)

# Codec name → file extension mapping (used for container stream extraction)
CODEC_EXTENSION_MAP: dict[str, str] = {
    "aac": ".aac", "ac3": ".ac3", "eac3": ".eac3",
    "dts": ".dts", "flac": ".flac", "opus": ".opus",
    "mp3": ".mp3", "vorbis": ".ogg", "pcm_s16le": ".wav",
    "pcm_s24le": ".wav", "pcm_s32le": ".wav",
    "truehd": ".thd",
}
