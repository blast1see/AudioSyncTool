"""Uygulama yapılandırması — tema, fontlar, algoritmik parametreler ve sabitler."""

from __future__ import annotations

import dataclasses
import enum
import json
import os
import sys
import tempfile
import threading
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

# ── Tool Path Resolution ─────────────────────────────────────────────
_TOOL_PATHS_DIR = Path.home() / ".audio_sync_tool"
_TOOL_PATHS_FILE = _TOOL_PATHS_DIR / "tool_paths.json"
_PROBE_CACHE_DIR = _TOOL_PATHS_DIR / "probe"

# qaac binary candidates — 64-bit build is preferred
_QAAC_CANDIDATES = ("qaac64", "qaac")

# Fallback used when PATHEXT is missing; mirrors the Windows default order so
# that a planted ``ffmpeg.bat`` can never win over a real ``ffmpeg.exe``.
_DEFAULT_PATHEXT = ".COM;.EXE;.BAT;.CMD"

_resolve_lock = threading.Lock()
_resolve_cache: dict[str, str] = {}


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
    temp_path: Path | None = None
    try:
        _TOOL_PATHS_DIR.mkdir(parents=True, exist_ok=True)
        data = {"version": 1, "tool_paths": paths.to_dict()}
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=_TOOL_PATHS_DIR,
            prefix=f".{_TOOL_PATHS_FILE.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temp_path, _TOOL_PATHS_FILE)
        global TOOL_PATHS
        TOOL_PATHS = paths
        invalidate_tool_cache()
        return True
    except Exception:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
        return False


def probe_cache_dir() -> Path:
    """Return a per-user scratch directory for external-tool runtime probes.

    Probing must never write inside the installation tree: that directory is
    read-only for system-wide installs and ephemeral inside a PyInstaller
    bundle.
    """
    _PROBE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _PROBE_CACHE_DIR


def _executable_candidates(name: str) -> tuple[str, ...]:
    """Return the filenames to try for ``name`` on the current platform."""
    if sys.platform != "win32":
        return (name,)

    if os.path.splitext(name)[1]:
        return (name,)

    extensions = [
        ext
        for ext in (os.environ.get("PATHEXT") or _DEFAULT_PATHEXT).split(os.pathsep)
        if ext.startswith(".")
    ]
    return tuple(name + ext for ext in extensions) or (name + ".EXE",)


def _is_executable_file(path: str) -> bool:
    return os.path.isfile(path) and os.access(path, os.X_OK)


def which_on_path(name: str) -> str | None:
    """Locate ``name`` in PATH, deliberately ignoring the working directory.

    ``shutil.which`` searches the current directory first on Windows, so
    launching the app from a folder that happens to contain ``ffmpeg.exe``
    would run that binary instead of the installed one. Only absolute PATH
    entries are searched here, which also rules out relative PATH entries.
    """
    if os.path.dirname(name):
        return name if _is_executable_file(name) else None

    candidates = _executable_candidates(name)
    for entry in (os.environ.get("PATH") or os.defpath).split(os.pathsep):
        entry = entry.strip().strip('"')
        if not entry or not os.path.isabs(entry):
            continue
        for candidate in candidates:
            full_path = os.path.join(entry, candidate)
            if _is_executable_file(full_path):
                return full_path
    return None


def invalidate_tool_cache() -> None:
    """Drop memoized tool locations after the configured paths change."""
    with _resolve_lock:
        _resolve_cache.clear()


def resolve_tool(name: str) -> str:
    """Resolve an external tool to its executable path.

    Resolution order:
    1. User-configured custom path in TOOL_PATHS (if set and the file exists)
    2. PATH lookup via :func:`which_on_path`, which skips the working directory
    3. For qaac: tries qaac64 first, then qaac

    Results are memoized because a single synchronization run resolves the same
    tools a dozen times, and each miss walks every PATH directory.

    Args:
        name: Tool name — one of "ffmpeg", "ffprobe", "qaac", "deew"

    Returns:
        Absolute path to the resolved executable.

    Raises:
        OSError: If the tool cannot be found
    """
    # Check user-configured custom path — this wins over PATH by design.
    custom = getattr(TOOL_PATHS, name, None)
    if custom and os.path.isfile(custom):
        return os.path.abspath(custom)

    with _resolve_lock:
        cached = _resolve_cache.get(name)
    if cached is not None and _is_executable_file(cached):
        return cached

    # Special handling for qaac — try qaac64 first
    candidates = _QAAC_CANDIDATES if name == "qaac" else (name,)
    for candidate in candidates:
        found = which_on_path(candidate)
        if found:
            resolved = os.path.abspath(found)
            with _resolve_lock:
                _resolve_cache[name] = resolved
            return resolved

    if name == "qaac":
        raise OSError(
            "qaac not found. Please install qaac and add it to PATH "
            "(expected at C:\\qaac). The binary may be named qaac64.exe."
        )
    raise OSError(f"{name} not found in PATH. Please install {name} or set a custom path.")


# ── Senkronizasyon Modu ──────────────────────────────────────────────────────


class SyncMode(Enum):
    """FFmpeg ses senkronizasyon filtre stratejileri.

    Sürüm 2.4 öncesinde altı mod tanımlıydı ancak beşi bayt bayt aynı çıktıyı
    üretiyordu: ``adelay``/``atrim`` dışındaki filtreler ya hiç eklenmiyor ya da
    (``rubberband=tempo=1.0`` gibi) hiçbir şey yapmayan bir geçiş aşamasıydı.
    Bu yüzden mod listesi gerçekten farklı davranan üç seçeneğe indirildi;
    kaldırılan adlar :data:`LEGACY_SYNC_MODE_ALIASES` ile eşlenerek eski
    ayarların bozulması önlenir.

    Attributes:
        filter_name: FFmpeg filtre adı.
        display_name: Kullanıcıya gösterilecek açıklama.
        description_tr: Türkçe açıklama.
        description_en: İngilizce açıklama.
        is_default: Öntanımlı seçim mi?
    """

    ADELAY_AMIX = ("precise",
                   "Precise offset (Default)", "Kesin ofset (Varsayılan)",
                   "Örnek hassasiyetinde gecikme/kırpma — neredeyse her durumda doğru seçim",
                   "Sample-accurate delay/trim — the right choice in almost every case",
                   True)
    ARESAMPLE = ("aresample",
                 "Repair timestamps", "Zaman damgası onarımı",
                 "Ofsetten sonra aresample=async=1 ekler; zaman damgası bozuk "
                 "yayın/VFR kayıtları için",
                 "Adds aresample=async=1 after the offset; for stream or VFR "
                 "captures with broken timestamps",
                 False)
    RUBBERBAND = ("rubberband",
                  "Rubber Band stretch", "Rubber Band germe",
                  "Drift düzeltmesini librubberband ile uygular; yalnızca drift "
                  "varsa devreye girer (librubberband gerektirir)",
                  "Performs drift correction with librubberband; only engages "
                  "when drift is present (requires librubberband)",
                  False)

    def __init__(
        self, filter_name: str, display_name: str, display_name_tr: str,
        description_tr: str, description_en: str,
        is_default: bool = False,
    ) -> None:
        self.filter_name = filter_name
        self.display_name = display_name
        self.display_name_tr = display_name_tr
        self.description_tr = description_tr
        self.description_en = description_en
        self.is_default = is_default

    def label(self, turkish: bool) -> str:
        """Return the menu label for the active language."""
        return self.display_name_tr if turkish else self.display_name


# Retired members map onto whichever surviving mode reproduces the behaviour
# they actually had, so a saved preference or an older script keeps working.
LEGACY_SYNC_MODE_ALIASES: dict[str, SyncMode] = {
    "ATEMPO": SyncMode.ADELAY_AMIX,
    "APAD": SyncMode.ADELAY_AMIX,
    "ASYNCTS": SyncMode.ARESAMPLE,
}


def sync_mode_from_name(name: str) -> SyncMode:
    """Resolve a mode by member name, tolerating the retired v2.3 names."""
    try:
        return SyncMode[name]
    except KeyError:
        return LEGACY_SYNC_MODE_ALIASES.get(name, SyncMode.ADELAY_AMIX)


# ── Tema Renkleri ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Theme:
    """Uygulama renk paleti.  ``frozen=True`` ile değiştirilemez.

    Renkler dekoratif değil anlamlıdır: ``accent`` her yerde *kaynak/referans*
    parçayı, ``accent2`` ise *senkronize edilen* parçayı temsil eder.  Böylece
    kullanıcı hangi kartın hangi dosyaya ait olduğunu okumadan görebilir.
    """

    bg: str = "#0d0e12"
    card: str = "#16181f"
    raised: str = "#1d202a"
    accent: str = "#6c63ff"
    accent2: str = "#ff6584"
    text: str = "#e6e8ef"
    muted: str = "#7c8296"
    border: str = "#262a36"
    input_bg: str = "#0b0c10"

    # Durum renkleri — ölçüm güvenilirliği ve uyarılar için.
    ok: str = "#3ddc97"
    warn: str = "#ffb454"
    err: str = "#ff5c5c"


# ── Fontlar ──────────────────────────────────────────────────────────────────


def _ui_family() -> str:
    """Pick the native interface face for the current platform."""
    if sys.platform == "win32":
        return "Segoe UI"
    if sys.platform == "darwin":
        return "SF Pro Text"
    return "DejaVu Sans"


def _mono_family() -> str:
    """Pick the face used for measurements, paths and the log."""
    if sys.platform == "win32":
        return "Consolas"
    if sys.platform == "darwin":
        return "SF Mono"
    return "DejaVu Sans Mono"


@dataclass(frozen=True)
class Fonts:
    """Uygulama font tanımları.

    İki ses vardır: arayüz metni için sistemin yerel arayüz fontu, ölçüm
    değerleri ve log için eşaralıklı font.  v2.3'te her şey ``Courier New``
    ile yazılıyordu; bu hem okunabilirliği düşürüyor hem de rakamların
    hizalanmasından gelen "ölçüm aleti" hissini bir üslup değil varsayılan
    haline getiriyordu.
    """

    label: tuple[str, int] = (_ui_family(), 9)
    small: tuple[str, int] = (_ui_family(), 9)
    tiny: tuple[str, int] = (_ui_family(), 8)
    section: tuple[str, int, str] = (_ui_family(), 8, "bold")
    mono: tuple[str, int] = (_mono_family(), 9)
    button: tuple[str, int, str] = (_ui_family(), 10, "bold")
    header: tuple[str, int, str] = (_ui_family(), 19, "bold")
    dot: tuple[str, int] = (_ui_family(), 11)
    info_value: tuple[str, int, str] = (_mono_family(), 10, "bold")

    # Ölçüm ekranı — aracın tek asıl çıktısı olan gecikme değeri için.
    readout: tuple[str, int, str] = (_mono_family(), 30, "bold")
    readout_unit: tuple[str, int] = (_mono_family(), 12)


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
            Kaynak/hedef FPS oranı. Nihai ``atempo`` değeri bunun tersidir.
        """
        return self.source_fps / self.target_fps

    @property
    def corrects_drift_ms_per_min(self) -> float:
        """Bu dönüşümün gideridiği drift (ms/dk).

        Bir kare hızı uyuşmazlığı sabit oranlı bir hız hatasıdır; ölçülen drift
        de öyle.  İkisini aynı birimde ifade etmek, ölçümü tabloyla
        karşılaştırıp "bu aslında bir FPS sorunu" diyebilmeyi sağlar.
        """
        return (1.0 - (self.target_fps / self.source_fps)) * 60_000.0


def match_drift_to_fps(
    drift_ms_per_min: float,
    tolerance_ms_per_min: float = 4.0,
) -> FpsConversion | None:
    """Identify a measured drift as a standard frame-rate mismatch.

    A dub mastered at the wrong rate drifts by a very specific amount — about
    60 ms/min for a 24 vs 23.976 mismatch, about 2.5 s/min for PAL — so a
    measured slope near one of those numbers is not a coincidence.  Saying which
    conversion it is turns "your audio drifts" into "your audio is the wrong
    frame rate, here is the one to pick", and the FPS path corrects it *before*
    analysis rather than fighting the search window afterwards.
    """
    best: FpsConversion | None = None
    best_error = tolerance_ms_per_min
    for conversion in FpsConversion:
        error = abs(conversion.corrects_drift_ms_per_min - drift_ms_per_min)
        if error < best_error:
            best_error = error
            best = conversion
    return best


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
    analysis_chunk_sec: int = 30
    fingerprint_enabled: bool = True
    fingerprint_frame_size: int = 2048
    fingerprint_hop_size: int = 512
    fingerprint_frame_stride: int = 2
    fingerprint_peaks_per_frame: int = 3
    fingerprint_peak_min_distance_bins: int = 6
    fingerprint_target_zone_frames: int = 20
    fingerprint_fanout: int = 4
    fingerprint_hash_bin_size: int = 2
    fingerprint_max_hash_occurrences: int = 24
    fingerprint_min_votes: int = 8
    fingerprint_cluster_radius_frames: int = 2
    fingerprint_top_clusters: int = 3
    fingerprint_anchor_bucket_sec: float = 18.0
    fingerprint_anchor_min_spacing_sec: float = 8.0
    fingerprint_max_anchors: int = 18

    # Yerel offset haritasi / drift takibi
    anchor_local_search_sec: float = 2.0
    offset_map_local_search_sec: float = 1.0
    offset_map_bucket_sec: float = 18.0
    offset_map_min_spacing_sec: float = 8.0
    offset_map_min_points: int = 3
    validation_refine_multiplier: int = 2

    # Kaba drift kancası — dosyanın başı ve sonu ``local_search_sec``'ten fazla
    # ayrışıyorsa segment doğrulaması tek bir ofsetin etrafında arayarak
    # dosyanın çoğunu ıskalar.  Bu eşikler ne zaman iki noktalı bir doğruyla
    # yönlendirileceğini belirler.
    coarse_drift_min_spread_sec: float = 1.0
    coarse_drift_max_spread_sec: float = 120.0
    coarse_drift_min_score: float = 2.0

    # Doğrulanan pencerelerin birbirinden bu kadar ayrıştığı bir ölçüm, tek bir
    # gecikmeyle tüm dosyayı hizalayamaz; kullanıcı bunu sessizce öğrenmemeli.
    # Temiz bir çift ~15 ms'de oturur, 100 ms yapısal bir uyuşmazlığa işaret eder.
    window_disagreement_warn_ms: float = 100.0

    # ── Eşleşme güvenilirliği ────────────────────────────────────────────
    # Analiz her zaman bir sayı üretir; o sayının *anlamlı* olup olmadığı ayrı
    # bir sorudur.  Yanlış dosya çifti verildiğinde (ör. başka bir filmin sesi)
    # korelasyon yine bir tepe bulur ve araç bunu kocaman bir rakam olarak
    # gösterir.  Aşağıdaki eşikler "bu iki parça aslında eşleşmiyor" demeyi
    # mümkün kılar.
    #
    # ``confidence`` korelasyon tepesinin kendi gürültü tabanına oranıdır:
    # 1.0 saf gürültü, gerçek bir eşleşme 4'ün üzerine çıkar.  Ölçülen bir
    # uyuşmazlık örneğinde (Children of Men sesi + L.A. Confidential dublajı)
    # skor 1.87'de kalmıştı.
    match_min_confidence: float = 2.5
    match_uncertain_confidence: float = 4.0
    # Bir dublajın gecikmesi saniyeler, en kötü ihtimalle bir iki dakikadır.
    # Bunun ötesi ölçüm değil, yanlış eşleşmedir.
    match_max_offset_sec: float = 600.0
    match_max_offset_fraction: float = 0.25
    # Basamak modeliyle açıklanamayan bu kadarlık bir saçılma, iki parçanın
    # aynı içerik olmadığını gösterir.
    match_no_match_spread_ms: float = 400.0
    # Kaç bağımsız GCC-PHAT noktası aynı yerde buluşursa envelope skorunun
    # düşüklüğü affedilir.  Farklı miksajlı bir dublaj envelope korelasyonunda
    # 3 civarında kalırken faz dönüşümü aynı gecikmeyi 11 ayrı noktada teyit
    # edebiliyor; bu durumda uyarı vermek gerçek uyarıları değersizleştirir.
    match_phat_corroboration_probes: int = 6

    # ── Örnek hassasiyetinde son rötuş (GCC-PHAT) ────────────────────────
    # Segment doğrulaması ince öznitelik ızgarasında çalışır: 20 ms'lik adımlar,
    # yani en iyi ihtimalle ±10 ms'lik bir yuvarlama.  Ölçülen bir çiftte kaba
    # ızgara -10560 ms derken gerçek değer -10527 ms'ydi — bir karenin dörtte
    # üçü kadar hata.  Ham PCM üzerinde faz dönüşümlü korelasyon (GCC-PHAT)
    # bunu 0.0625 ms çözünürlüğe indirir ve aynı zamanda bağımsız bir ikinci
    # ölçüm olduğu için sonucu doğrulamak için de kullanılır.
    phat_refine_enabled: bool = True
    phat_refine_probe_sec: float = 20.0
    phat_refine_probes: int = 24
    phat_refine_search_sec: float = 0.75
    phat_refine_min_sharpness: float = 8.0
    phat_refine_min_agreeing: int = 3
    phat_refine_agree_ms: float = 40.0
    phat_refine_band_low_hz: float = 100.0
    phat_refine_band_high_hz: float = 4000.0

    # ── Çıktı doğrulama ──────────────────────────────────────────────────
    # Bir senkron aracının en çok eksik olan şeyi: "oldu mu?" sorusunun cevabı.
    # Yazılan dosyadan ve referanstan aynı anlara denk gelen birkaç kısa parça
    # okunup aralarındaki kalan fark ölçülür.  Tüm filmi yeniden çözmek yerine
    # birkaç saniyelik sondalar kullanıldığı için maliyeti saniyeler mertebesinde.
    verify_output_enabled: bool = True
    verify_probe_count: int = 6
    verify_probe_sec: float = 15.0
    verify_search_sec: float = 2.0
    verify_min_sharpness: float = 6.0
    # Bir karenin (23.976 fps'de ~42 ms) altındaki kalıntı duyulmaz; bunun
    # üzerinde kullanıcı bilmelidir.
    verify_warn_ms: float = 40.0

    # Zaman içinde birbirinden bu kadar uzak iki çıpa arasında doğrusal
    # interpolasyon yapmak, aradaki her pencereye var olmayan bir rampa
    # dayatır.  Dublajlarda asıl yaygın olan sürekli kayma değil, kurgudan
    # gelen ani basamaktır; boşluk büyükse en yakın çıpanın değeri tutulur.
    anchor_interpolation_max_gap_sec: float = 300.0
    anchor_interpolation_max_jump_ms: float = 250.0

    # Kare hızı uyuşmazlığını doğrudan sınama: hedefin öznitelik akışı standart
    # oranlarla yeniden örneklenip skorlanır.  Kazanan oranın, dönüşümsüz
    # duruma göre skoru bu kat kadar iyileştirmesi gerekir.
    rate_mismatch_detection: bool = True
    rate_mismatch_min_gain: float = 1.25

    # FFmpeg
    ffmpeg_timeout_sec: int = 300
    ffmpeg_timeout_per_gib_sec: int = 120
    ffmpeg_complex_format_bonus_sec: int = 300
    ffmpeg_max_timeout_sec: int = 3600
    ffprobe_timeout_sec: int = 30

    # Drift uyarı eşiği (ms/dk)
    drift_warning_threshold: float = 20.0

    # Drift düzeltmesi için gereken en küçük eğim (ms/dk).  1 ms/dk, iki
    # saatlik bir filmde 120 ms birikir — duyulur bir kayma.  Bunun altındaki
    # değerler ölçüm gürültüsünden ayırt edilemez ve tüm parçayı boş yere
    # yeniden zamanlamaya değmez.
    drift_correction_min_ms_per_min: float = 1.0
    # Drift düzeltmesinin diğer üç koşulu.  Bunlar bir zamanlar
    # ``AnalysisResult`` içine gömülüydü; yarısı buradan ayarlanıp yarısı
    # ayarlanamayınca ``drift_correction_min_ms_per_min``'i düşüren bir kullanıcı
    # hiçbir etki göremiyordu.  Karar tek yerde verilsin.
    drift_correction_min_r2: float = 0.80
    drift_correction_min_segments: int = 6
    drift_correction_min_span_sec: float = 60.0

    # Basamak (step) tespiti — kurgu farkından doğan ani ofset sıçramaları.
    step_detection_enabled: bool = True
    # 40 ms altındaki fark, sesi kesip eklemenin getireceği riske değmez;
    # dudak senkronu bu büyüklükte zaten kusursuz sayılır.
    step_min_ms: float = 40.0
    # Her iki tarafın da bağımsız kanıtı olmalı; tek pencere basamak yaratamaz.
    step_min_windows: int = 4
    # İki dakikadan kısa bir "bölge" büyük olasılıkla ölçüm gürültüsüdür.
    step_min_region_sec: float = 120.0
    step_max_regions: int = 8
    # Bölünmenin maliyeti, sıçrama büyüklüğünün bu katı kadar düşürmesi gerekir.
    step_min_cost_gain: float = 2.0
    # Zayıf korele olmuş pencereler basamak sınırı çizemez.
    step_min_window_score: float = 2.5
    # Sıçrama, pencerelerin kendi saçılmasının en az bu katı olmalı; aksi hâlde
    # sınır gürültünün içine çizilmiş olur.
    step_min_snr: float = 4.0
    # Basamak modeli, doğru modeline göre maliyeti en fazla bu orana
    # düşürebiliyorsa kesmeye değmez — düzgün artan bir ofset drifttir.
    step_vs_line_margin: float = 0.55
    # Aykırı pencere elemesi: her pencere önündeki ve arkasındaki bu kadar
    # komşunun medyanıyla ayrı ayrı karşılaştırılır, iyi olan taraf sayılır.
    step_outlier_neighbours: int = 3
    step_outlier_tolerance: float = 6.0
    # Elemenin yiyebileceği en büyük pencere oranı — kaskad koruması.
    step_outlier_max_fraction: float = 0.35
    # Sınır konumlarının yinelemeli iyileştirmesi; birkaç geçişte oturur.
    step_boundary_refine_passes: int = 4
    # Sınırı sesin kendisinde ikili arama ile daraltma.  Pencereler seyrek
    # olduğunda ortalama tahmini onlarca dakika şaşabiliyor.
    step_boundary_audio_search: bool = True
    step_boundary_probe_sec: float = 24.0
    # Sınır ne kadar şaşarsa, aradaki süre boyunca hata tam basamak kadar olur;
    # bu yüzden aramayı saniyeler mertebesine kadar sürdürmeye değer.
    step_boundary_search_iterations: int = 16
    step_boundary_search_precision_sec: float = 4.0
    step_boundary_search_min_gap_sec: float = 60.0
    step_boundary_min_margin: float = 0.02
    # Ek yerlerine uygulanan kısa sönümleme — tıklama sesini engeller.
    step_splice_fade_sec: float = 0.008


# ── Deew Encoder Yapılandırması ──────────────────────────────────────────────


class DeewFormat(Enum):
    """Deew çıktı format seçenekleri."""

    DD = ("dd", "AC3", ".ac3", ())
    DDP = ("ddp", "EAC3", ".eac3", (".ec3",))

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
    timeout_sec: int = 600


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
    """Deew pipeline için kullanılacak araç seçimi."""

    DEEW = ("deew", "Deew")
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
    DEEW = "deew"
    FFMPEG = "ffmpeg"
    QAAC = "qaac"
    # NATIVE removed — FLAC/Opus now handled by FFmpeg


class FFmpegOutputFormat(enum.Enum):
    """FFmpeg output format options."""
    AAC = ("aac", ".m4a", "AAC (FFmpeg)")
    FLAC = ("flac", ".flac", "FLAC (FFmpeg)")
    OPUS = ("libopus", ".opus", "Opus (FFmpeg)")
    AC3 = ("ac3", ".ac3", "AC3 (FFmpeg)")
    EAC3 = ("eac3", ".eac3", "E-AC3 (FFmpeg)")

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
    ac3_bitrate: int = FFMPEG_AC3_DEFAULT_BITRATE
    eac3_bitrate: int = FFMPEG_EAC3_DEFAULT_BITRATE


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
    timeout_sec: int = 600
    timeout_per_gib_sec: int = 900  # grow the budget with the input size
    max_timeout_sec: int = 3600


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
    ".ac3", ".eac3", ".ec3", ".dts", ".dtshd", ".thd", ".mka", ".opus", ".wma",
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
    "dts": ".dts", "dtshd": ".dtshd", "flac": ".flac", "opus": ".opus",
    "mp3": ".mp3", "vorbis": ".ogg", "pcm_s16le": ".wav",
    "pcm_s24le": ".wav", "pcm_s32le": ".wav",
    "truehd": ".thd",
}
