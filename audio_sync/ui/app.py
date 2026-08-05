"""Main application window — UI coordination only.

Business logic resides in ``core.pipeline``, ``core.analyzer``, and
``core.ffmpeg_wrapper``; utility functions live in ``utils``.
"""

from __future__ import annotations

import os
import tempfile as _tempfile_mod
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from tkinter import filedialog, messagebox
from typing import TYPE_CHECKING, Callable

from audio_sync.config import (
    CODEC_EXTENSION_MAP,
    CONTAINER_EXTENSIONS,
    DEEW_COMMON_BITRATES,
    DEEW_DEFAULT_BITRATES,
    FFMPEG_AC3_BITRATES,
    FFMPEG_AC3_DEFAULT_BITRATE,
    FFMPEG_EAC3_BITRATES,
    FFMPEG_EAC3_DEFAULT_BITRATE,
    FONTS,
    SYNC_CONFIG,
    THEME,
    TOOL_PATHS,
    DeewConfig,
    DeewDownmix,
    DeewDRC,
    DeewFormat,
    EncodingPipeline,
    FFmpegEncodeConfig,
    FFmpegOutputFormat,
    FpsConversion,
    QaacConfig,
    QaacMode,
    SyncConfig,
    SyncMode,
    ToolPaths,
    get_deew_bitrate_key,
    resolve_tool,
    save_tool_paths,
)
from audio_sync.core.deew_encoder import (
    get_deew_runtime_status,
    reset_deew_probe_cache,
    resolve_deew_backend,
)
from audio_sync.core.encoder import QaacEncoder
from audio_sync.core.ffmpeg_wrapper import FFmpegWrapper
from audio_sync.core.models import (
    AnalysisResult,
    AudioInfo,
    EncodingError,
    OperationCancelledError,
    OutputSampleRate,
)
from audio_sync.core.pipeline import EncodingRequest, SyncPipeline, SyncRequest
from audio_sync.i18n import Language, get_i18n, t
from audio_sync.ui.drop_zone import DropZone
from audio_sync.ui.stream_dialog import ask_stream_selection
from audio_sync.utils import parse_float, parse_int, validate_file

if TYPE_CHECKING:
    from audio_sync.core.analyzer import AudioAnalyzer

# Try to use tkinterdnd2 for drag & drop support
_TkBase: type = tk.Tk
try:
    from tkinterdnd2 import TkinterDnD
    _TkBase = TkinterDnD.Tk  # type: ignore[assignment]
except ImportError:
    pass


@dataclass(frozen=True)
class _PreparedAnalysis:
    """Shared analysis artifacts reused by analyze-only and full sync flows."""

    src_info: AudioInfo
    sync_info: AudioInfo
    output_sr: OutputSampleRate
    effective_sync_path: str
    fps_tmp_path: str | None
    src_rate: int
    sync_rate: int
    src_pcm_path: str
    sync_pcm_path: str
    src_samples: int
    sync_samples: int


class AudioSyncApp(_TkBase):  # type: ignore[misc]
    """Audio Sync Tool main window.

    Uses tkinterdnd2.TkinterDnD.Tk as base when available for drag & drop,
    otherwise falls back to standard tk.Tk.
    """

    def __init__(
        self,
        config: SyncConfig = SYNC_CONFIG,
        ffmpeg: FFmpegWrapper | None = None,
        analyzer: "AudioAnalyzer | None" = None,
    ) -> None:
        super().__init__()
        self.title("Audio Sync Tool")
        self.resizable(True, True)
        self.minsize(900, 560)
        self.configure(bg=THEME.bg)

        # i18n
        self._i18n = get_i18n()

        # Bağımlılıklar (Dependency Injection)
        self._config = config
        self._ffmpeg = ffmpeg or FFmpegWrapper(config=config)
        self._analyzer = analyzer
        self._pipeline = SyncPipeline(config=config, ffmpeg=self._ffmpeg, analyzer=analyzer)

        # Durum
        self._src_path: str = ""
        self._sync_path: str = ""
        self._delay_ms: float | None = None
        self._processing: bool = False
        self._processing_lock = threading.Lock()
        self._cancel_event = threading.Event()

        # Deew availability is probed off the UI thread; ``None`` = not yet known.
        self._deew_available: bool | None = None
        self._deew_probe_running: bool = False

        # Set once teardown starts so worker threads stop scheduling callbacks
        # into an interpreter that is going away.
        self._closing: bool = False
        self._pending_after_ids: set[str] = set()

        # Kullanıcı ayarları
        self.skip_intro_var = tk.StringVar(value="120")
        self.segment_count_var = tk.StringVar(value="12")
        self.force_48k_var = tk.BooleanVar(value=False)
        self.correct_drift_var = tk.BooleanVar(value=True)
        self.correct_steps_var = tk.BooleanVar(value=True)

        # Senkronizasyon modu
        self.sync_mode_var = tk.StringVar(value=SyncMode.ADELAY_AMIX.display_name)

        # FPS dönüşüm ayarları
        self.fps_enabled_var = tk.BooleanVar(value=False)
        self.fps_auto_var = tk.BooleanVar(value=True)
        self.fps_conversion_var = tk.StringVar(value=FpsConversion.FPS_25_TO_23976.display_name)

        # Deew encoding ayarları
        self.deew_format_var = tk.StringVar(value=DeewFormat.DDP.cli_value)
        self.deew_bitrate_var = tk.StringVar(value="")
        self.deew_downmix_var = tk.StringVar(value="auto")
        self.deew_drc_var = tk.StringVar(value=DeewDRC.MUSIC_LIGHT.cli_value)
        self.deew_dialnorm_var = tk.StringVar(value="0")
        self.deew_delete_wav_var = tk.BooleanVar(value=True)

        # Encoding pipeline
        self._encoding_pipeline_var = tk.StringVar(value=EncodingPipeline.NONE.value)

        # FFmpeg encoding
        self._ffmpeg_format_var = tk.StringVar(value=FFmpegOutputFormat.AAC.codec)
        self._ffmpeg_aac_bitrate_var = tk.StringVar(value="256")
        self._ffmpeg_flac_compression_var = tk.StringVar(value="5")
        self._ffmpeg_flac_bit_depth_var = tk.StringVar(value="24")
        self._ffmpeg_opus_bitrate_var = tk.StringVar(value="128")
        self._ffmpeg_ac3eac3_bitrate_var = tk.StringVar(value=str(FFMPEG_AC3_DEFAULT_BITRATE))
        self._ffmpeg_downmix_var = tk.StringVar(value="auto")

        # qaac encoding
        self._qaac_mode_var = tk.StringVar(value=QaacMode.TVBR.flag)
        self._qaac_tvbr_quality_var = tk.StringVar(value="91")
        self._qaac_cvbr_bitrate_var = tk.StringVar(value="256")
        self._qaac_abr_bitrate_var = tk.StringVar(value="256")
        self._qaac_cbr_bitrate_var = tk.StringVar(value="256")
        self._qaac_he_aac_var = tk.BooleanVar(value=False)
        self._qaac_no_delay_var = tk.BooleanVar(value=True)

        # Dil seçimi
        self.language_var = tk.StringVar(value=self._i18n.language.display_name)

        # UI oluştur
        self._build_ui()

    # ── UI Oluşturma ─────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        """Ana arayüzü oluşturur — alt metotlara delege eder.

        Paneller tek bir sütun yerine iki sütuna yerleştirilir.  v2.3'te
        yığılmış düzen 1262 piksel yüksekliğe ulaşıyordu; 1080p bir ekranda
        pencere hiçbir zaman tamamını gösteremiyor, kullanıcı "Senkronizasyonu
        Başlat" düğmesini görmek için kaydırmak zorunda kalıyordu.
        """
        # Alt çubuk (ilerleme + butonlar) her zaman görünür — kaydırma alanının dışında
        self._build_bottom_bar()
        # Kaydırılabilir içerik alanı
        self._build_scrollable_container()
        self._build_header()

        body = tk.Frame(self._content, bg=THEME.bg)
        body.pack(fill="both", expand=True, padx=16, pady=(0, 10))
        body.columnconfigure(0, weight=1, uniform="cols")
        body.columnconfigure(1, weight=1, uniform="cols")

        # Sol sütun: girdi ve sonuç — kullanıcının okuduğu şeyler.
        left = tk.Frame(body, bg=THEME.bg)
        left.grid(row=0, column=0, sticky="new", padx=(0, 6))
        # Sağ sütun: ayarlar — kullanıcının değiştirdiği şeyler.
        right = tk.Frame(body, bg=THEME.bg)
        right.grid(row=0, column=1, sticky="new", padx=(6, 0))

        self._build_drop_zones(left)
        self._build_info_panel(left)
        self._build_log_panel(left)

        self._build_options_panel(right)
        self._build_sync_mode_panel(right)
        self._build_fps_panel(right)
        self._build_encoding_panel(right)

        self.schedule_later(50, self._fit_to_content)

    def _build_scrollable_container(self) -> None:
        """Kaydırılabilir ana kapsayıcıyı oluşturur."""
        self._canvas = tk.Canvas(
            self, bg=THEME.bg, highlightthickness=0, bd=0,
        )
        # The v2.3 scrollbar was #2a2a3a on a #0f0f13 trough — invisible in
        # practice, so 674 px of hidden content gave no visual cue at all.
        self._scrollbar = tk.Scrollbar(
            self, orient="vertical", command=self._canvas.yview,
            bg=THEME.muted, troughcolor=THEME.card,
            activebackground=THEME.accent, highlightthickness=0,
            bd=0, width=11,
        )
        self._canvas.configure(yscrollcommand=self._scrollbar.set)

        self._scrollbar_visible = False
        self._canvas.pack(side="left", fill="both", expand=True)

        self._content = tk.Frame(self._canvas, bg=THEME.bg)
        self._canvas_window = self._canvas.create_window(
            (0, 0), window=self._content, anchor="nw",
        )

        self._content.bind("<Configure>", self._on_content_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)

        self.bind_all("<MouseWheel>", self._on_mousewheel)
        self.bind_all("<Button-4>", self._on_mousewheel_linux)
        self.bind_all("<Button-5>", self._on_mousewheel_linux)

    def _on_content_configure(self, _event: tk.Event) -> None:  # type: ignore[type-arg]
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))
        self._update_scrollbar_visibility()

    def _on_canvas_configure(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        self._canvas.itemconfig(self._canvas_window, width=event.width)
        self._update_scrollbar_visibility()

    def _update_scrollbar_visibility(self) -> None:
        content_h = self._content.winfo_reqheight()
        canvas_h = self._canvas.winfo_height()
        needs_scroll = content_h > canvas_h

        if needs_scroll and not self._scrollbar_visible:
            self._scrollbar.pack(side="right", fill="y")
            self._scrollbar_visible = True
        elif not needs_scroll and self._scrollbar_visible:
            self._scrollbar.pack_forget()
            self._scrollbar_visible = False

    def _scrolls_itself(self, widget: object) -> bool:
        """Report whether the pointer is over a widget that scrolls on its own.

        ``bind_all`` is the only reliable way to catch the wheel across every
        child, but forwarding every event to the outer canvas stole scrolling
        from the log box. Anything with its own ``yview`` handles it instead.
        """
        return isinstance(widget, (tk.Text, tk.Listbox)) or (
            widget is not self._canvas and isinstance(widget, tk.Canvas)
        )

    def _on_mousewheel(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        if self._scrolls_itself(getattr(event, "widget", None)):
            return
        self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_mousewheel_linux(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        if self._scrolls_itself(getattr(event, "widget", None)):
            return
        if event.num == 4:
            self._canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self._canvas.yview_scroll(1, "units")

    def _build_header(self) -> None:
        """Başlık bölümünü oluşturur — dil seçimi dahil."""
        hdr = tk.Frame(self._content, bg=THEME.bg)
        hdr.pack(fill="x", padx=16, pady=(14, 4))

        # Sol: Başlık ve alt başlık aynı blokta — alt başlık v2.3'te ortalanmış
        # ayrı bir satırdı ve hiçbir şeyle hizalanmıyordu.
        title_frame = tk.Frame(hdr, bg=THEME.bg)
        title_frame.pack(side="left")
        wordmark = tk.Frame(title_frame, bg=THEME.bg)
        wordmark.pack(anchor="w")
        tk.Label(
            wordmark, text="AUDIO", font=FONTS.header, fg=THEME.accent, bg=THEME.bg,
        ).pack(side="left")
        tk.Label(
            wordmark, text="SYNC", font=FONTS.header, fg=THEME.accent2, bg=THEME.bg,
        ).pack(side="left")
        self._subtitle_lbl = tk.Label(
            title_frame,
            text=t("app_subtitle"),
            font=FONTS.small,
            fg=THEME.muted,
            bg=THEME.bg,
            anchor="w",
        )
        self._subtitle_lbl.pack(anchor="w")

        # Sağ: Tool Paths button + Dil seçimi
        self._tool_paths_btn = tk.Button(
            hdr,
            text=t("tool_paths_button"),
            font=FONTS.small,
            fg=THEME.text,
            bg=THEME.card,
            activebackground=THEME.card,
            activeforeground=THEME.accent,
            relief="flat",
            cursor="hand2",
            command=self._open_tool_paths_dialog,
        )
        self._tool_paths_btn.pack(side="right", padx=(0, 8))

        lang_frame = tk.Frame(hdr, bg=THEME.bg)
        lang_frame.pack(side="right")
        self._lang_label = tk.Label(
            lang_frame, text=t("language"), font=FONTS.small,
            fg=THEME.muted, bg=THEME.bg,
        )
        self._lang_label.pack(side="left", padx=(0, 6))

        self._lang_menu = tk.OptionMenu(
            lang_frame,
            self.language_var,
            *[lang.display_name for lang in Language],
            command=self._on_language_change,
        )
        self._lang_menu.config(
            bg=THEME.input_bg, fg=THEME.text, font=FONTS.small,
            activebackground=THEME.card, activeforeground=THEME.text,
            highlightthickness=0, relief="flat", width=8,
        )
        self._lang_menu["menu"].config(
            bg=THEME.input_bg, fg=THEME.text, font=FONTS.small,
            activebackground=THEME.accent, activeforeground=THEME.bg,
        )
        self._lang_menu.pack(side="left")

        tk.Frame(self._content, bg=THEME.border, height=1).pack(
            fill="x", padx=16, pady=(10, 12),
        )

    def _build_drop_zones(self, parent: tk.Frame) -> None:
        """Dosya seçim alanlarını oluşturur."""
        self.zone_src = DropZone(
            parent, t("source_audio"), THEME.accent, self._on_src_pick,
        )
        self.zone_src.pack(fill="x", pady=(0, 8))

        self.zone_sync = DropZone(
            parent, t("sync_audio"), THEME.accent2, self._on_sync_pick,
        )
        self.zone_sync.pack(fill="x", pady=(0, 8))

    def _build_options_panel(self, parent: tk.Frame) -> None:
        """Tespit ayarları panelini oluşturur."""
        options = tk.Frame(
            parent, bg=THEME.card,
            highlightbackground=THEME.border, highlightthickness=1,
        )
        options.pack(fill="x", pady=(0, 8))

        self._options_title_lbl = tk.Label(
            options, text=t("detection_settings"), font=FONTS.small,
            fg=THEME.muted, bg=THEME.card, anchor="w",
        )
        self._options_title_lbl.pack(fill="x", padx=14, pady=(10, 4))

        # İlk farklı kısmı atla
        row1 = tk.Frame(options, bg=THEME.card)
        row1.pack(fill="x", padx=14, pady=(0, 8))
        self._skip_intro_lbl = tk.Label(
            row1, text=t("skip_intro_sec"), font=FONTS.small,
            fg=THEME.text, bg=THEME.card,
        )
        self._skip_intro_lbl.pack(side="left")
        tk.Entry(
            row1, textvariable=self.skip_intro_var, width=8, justify="center",
            bg=THEME.input_bg, fg=THEME.text, insertbackground=THEME.text,
            relief="flat", font=FONTS.mono,
        ).pack(side="right")

        # Tarama penceresi sayısı
        row2 = tk.Frame(options, bg=THEME.card)
        row2.pack(fill="x", padx=14, pady=(0, 8))
        self._scan_window_lbl = tk.Label(
            row2, text=t("scan_window_count"), font=FONTS.small,
            fg=THEME.text, bg=THEME.card,
        )
        self._scan_window_lbl.pack(side="left")
        tk.Entry(
            row2, textvariable=self.segment_count_var, width=8, justify="center",
            bg=THEME.input_bg, fg=THEME.text, insertbackground=THEME.text,
            relief="flat", font=FONTS.mono,
        ).pack(side="right")

        self._force_48k_cb = self._option_checkbox(
            options, "force_48k", self.force_48k_var, pady=(0, 8),
        )
        self._force_48k_note_lbl = self._option_note(options, "force_48k_note")

        # Zamanlama düzeltmeleri.  İkisi de "ölçüm güvenilirse düzelt" mantığını
        # paylaştığı için tek bir not ikisini birden açıklar; ayrı ayrı
        # anlatmak paneli gereksiz uzatıyordu.
        self._correct_drift_cb = self._option_checkbox(
            options, "correct_drift", self.correct_drift_var,
        )
        self._correct_steps_cb = self._option_checkbox(
            options, "correct_steps", self.correct_steps_var,
        )
        self._timing_note_lbl = self._option_note(
            options, "timing_corrections_note", pady=(0, 10),
        )

    def _option_checkbox(
        self,
        parent: tk.Frame,
        key: str,
        variable: tk.BooleanVar,
        *,
        pady: tuple[int, int] = (0, 2),
    ) -> tk.Checkbutton:
        """One themed settings checkbox — the styling lives here, not per widget."""
        box = tk.Checkbutton(
            parent,
            text=t(key),
            variable=variable,
            onvalue=True,
            offvalue=False,
            bg=THEME.card,
            fg=THEME.text,
            selectcolor=THEME.input_bg,
            activebackground=THEME.card,
            activeforeground=THEME.text,
            font=FONTS.small,
            anchor="w",
            relief="flat",
            highlightthickness=0,
        )
        box.pack(fill="x", padx=14, pady=pady)
        return box

    def _option_note(
        self,
        parent: tk.Frame,
        key: str,
        *,
        pady: tuple[int, int] = (0, 6),
    ) -> tk.Label:
        """Explanatory small print under a settings control."""
        note = tk.Label(
            parent,
            text=t(key),
            font=FONTS.tiny,
            fg=THEME.muted,
            bg=THEME.card,
            anchor="w",
            justify="left",
            wraplength=330,
        )
        note.pack(fill="x", padx=14, pady=pady)
        return note

    def _build_sync_mode_panel(self, parent: tk.Frame) -> None:
        """Senkronizasyon modu seçim panelini oluşturur."""
        self._sync_mode_frame = tk.Frame(
            parent, bg=THEME.card,
            highlightbackground=THEME.border, highlightthickness=1,
        )
        self._sync_mode_frame.pack(fill="x", pady=(0, 8))

        self._sync_mode_title_lbl = tk.Label(
            self._sync_mode_frame, text=t("sync_mode"), font=FONTS.small,
            fg=THEME.muted, bg=THEME.card, anchor="w",
        )
        self._sync_mode_title_lbl.pack(fill="x", padx=14, pady=(10, 4))

        # Mod seçimi
        mode_row = tk.Frame(self._sync_mode_frame, bg=THEME.card)
        mode_row.pack(fill="x", padx=14, pady=(0, 6))
        self._sync_mode_label = tk.Label(
            mode_row, text=t("sync_mode_label"), font=FONTS.small,
            fg=THEME.text, bg=THEME.card,
        )
        self._sync_mode_label.pack(side="left")

        turkish = self._i18n.language == Language.TR
        self.sync_mode_var.set(SyncMode.ADELAY_AMIX.label(turkish))
        self._sync_mode_menu = tk.OptionMenu(
            mode_row,
            self.sync_mode_var,
            *[sm.label(turkish) for sm in SyncMode],
        )
        self._sync_mode_menu.config(
            bg=THEME.input_bg, fg=THEME.text, font=FONTS.small,
            activebackground=THEME.card, activeforeground=THEME.text,
            highlightthickness=0, relief="flat", width=24,
        )
        self._sync_mode_menu["menu"].config(
            bg=THEME.input_bg, fg=THEME.text, font=FONTS.small,
            activebackground=THEME.accent, activeforeground=THEME.bg,
        )
        self._sync_mode_menu.pack(side="right")

        # Mod açıklama etiketi
        self._sync_mode_desc_lbl = tk.Label(
            self._sync_mode_frame, text="", font=FONTS.small,
            fg=THEME.muted, bg=THEME.card, anchor="w",
        )
        self._sync_mode_desc_lbl.pack(fill="x", padx=14, pady=(0, 4))

        # Not
        self._sync_mode_note_lbl = tk.Label(
            self._sync_mode_frame,
            text=t("sync_mode_note"),
            font=FONTS.small,
            fg=THEME.muted,
            bg=THEME.card,
            anchor="w",
            justify="left",
        )
        self._sync_mode_note_lbl.pack(fill="x", padx=14, pady=(0, 10))

        # Değişiklik izleyicisi
        self.sync_mode_var.trace_add("write", self._on_sync_mode_change)
        self._update_sync_mode_description()

    def _build_fps_panel(self, parent: tk.Frame) -> None:
        """FPS dönüşüm ayarları panelini oluşturur."""
        self._fps_frame = tk.Frame(
            parent, bg=THEME.card,
            highlightbackground=THEME.border, highlightthickness=1,
        )
        self._fps_frame.pack(fill="x", pady=(0, 8))

        self._fps_title_lbl = tk.Label(
            self._fps_frame, text=t("fps_conversion"), font=FONTS.small,
            fg=THEME.muted, bg=THEME.card, anchor="w",
        )
        self._fps_title_lbl.pack(fill="x", padx=14, pady=(10, 4))

        self._fps_enable_cb = tk.Checkbutton(
            self._fps_frame,
            text=t("fps_enable"),
            variable=self.fps_enabled_var,
            onvalue=True,
            offvalue=False,
            bg=THEME.card,
            fg=THEME.text,
            selectcolor=THEME.input_bg,
            activebackground=THEME.card,
            activeforeground=THEME.text,
            font=FONTS.small,
            anchor="w",
            relief="flat",
            highlightthickness=0,
            command=self._on_fps_toggle,
        )
        self._fps_enable_cb.pack(fill="x", padx=14, pady=(0, 2))

        # Detection is checked against the result before it is kept, so leaving
        # this on cannot make a correct pair worse — it only rescues the pairs
        # whose rate difference is too large to measure any other way.
        self._fps_auto_cb = self._option_checkbox(
            self._fps_frame, "fps_auto", self.fps_auto_var, pady=(0, 6),
        )

        self._fps_settings_frame = tk.Frame(self._fps_frame, bg=THEME.card)
        self._fps_settings_frame.pack(fill="x", padx=14, pady=(0, 10))

        conv_row = tk.Frame(self._fps_settings_frame, bg=THEME.card)
        conv_row.pack(fill="x", pady=(0, 6))
        self._fps_conv_lbl = tk.Label(
            conv_row, text=t("fps_conversion_label"), font=FONTS.small,
            fg=THEME.text, bg=THEME.card,
        )
        self._fps_conv_lbl.pack(side="left")

        self._fps_menu = tk.OptionMenu(
            conv_row,
            self.fps_conversion_var,
            *[fc.display_name for fc in FpsConversion],
        )
        self._fps_menu.config(
            bg=THEME.input_bg, fg=THEME.text, font=FONTS.small,
            activebackground=THEME.card, activeforeground=THEME.text,
            highlightthickness=0, relief="flat", width=18,
        )
        self._fps_menu["menu"].config(
            bg=THEME.input_bg, fg=THEME.text, font=FONTS.small,
            activebackground=THEME.accent, activeforeground=THEME.bg,
        )
        self._fps_menu.pack(side="right")

        self._fps_ratio_lbl = tk.Label(
            self._fps_settings_frame, text="", font=FONTS.small,
            fg=THEME.muted, bg=THEME.card, anchor="w",
        )
        self._fps_ratio_lbl.pack(fill="x", pady=(0, 6))

        self._fps_note_lbl = tk.Label(
            self._fps_settings_frame,
            text=t("fps_note"),
            font=FONTS.small,
            fg=THEME.muted,
            bg=THEME.card,
            anchor="w",
            justify="left",
        )
        self._fps_note_lbl.pack(fill="x", pady=(0, 4))

        self.fps_conversion_var.trace_add("write", self._on_fps_conversion_change)

        self._on_fps_toggle()
        self._update_fps_ratio_label()

    def _build_deew_panel(self, parent: tk.Frame) -> None:
        """Build Deew encoding settings into the given parent frame."""
        # Deew status indicator
        status_row = tk.Frame(parent, bg=THEME.card)
        status_row.pack(fill="x", padx=14, pady=(6, 4))

        self._deew_status_lbl = tk.Label(
            status_row, text="", font=FONTS.small,
            bg=THEME.card, anchor="w",
        )
        self._deew_status_lbl.pack(side="left")
        self._update_deew_status()

        self._deew_settings_frame = tk.Frame(parent, bg=THEME.card)
        self._deew_settings_frame.pack(fill="x", padx=14, pady=(0, 10))

        # Encoder seçimi
        self._enc_desc_lbl = tk.Label(
            self._deew_settings_frame, text=t("deew_desc"), font=FONTS.small,
            fg=THEME.muted, bg=THEME.card, anchor="w",
        )
        self._enc_desc_lbl.pack(fill="x", pady=(0, 6))

        # Format seçimi
        fmt_row = tk.Frame(self._deew_settings_frame, bg=THEME.card)
        fmt_row.pack(fill="x", pady=(0, 6))
        self._fmt_label = tk.Label(
            fmt_row, text=t("format_label"), font=FONTS.small,
            fg=THEME.text, bg=THEME.card,
        )
        self._fmt_label.pack(side="left")

        self._fmt_menu = tk.OptionMenu(
            fmt_row,
            self.deew_format_var,
            *[f.cli_value for f in DeewFormat],
        )
        self._fmt_menu.config(
            bg=THEME.input_bg, fg=THEME.text, font=FONTS.small,
            activebackground=THEME.card, activeforeground=THEME.text,
            highlightthickness=0, relief="flat", width=12,
        )
        self._fmt_menu["menu"].config(
            bg=THEME.input_bg, fg=THEME.text, font=FONTS.small,
            activebackground=THEME.accent, activeforeground=THEME.bg,
        )
        self._fmt_menu.pack(side="right")

        self._fmt_desc_lbl = tk.Label(
            self._deew_settings_frame, text="", font=FONTS.small,
            fg=THEME.muted, bg=THEME.card, anchor="w",
        )
        self._fmt_desc_lbl.pack(fill="x", pady=(0, 6))

        # Kanal düzeni
        ch_row = tk.Frame(self._deew_settings_frame, bg=THEME.card)
        ch_row.pack(fill="x", pady=(0, 6))
        self._ch_label = tk.Label(
            ch_row, text=t("channel_layout"), font=FONTS.small,
            fg=THEME.text, bg=THEME.card,
        )
        self._ch_label.pack(side="left")

        downmix_options = ["auto"] + [dm.display_name for dm in DeewDownmix]
        self._ch_menu = tk.OptionMenu(
            ch_row,
            self.deew_downmix_var,
            *downmix_options,
        )
        self._ch_menu.config(
            bg=THEME.input_bg, fg=THEME.text, font=FONTS.small,
            activebackground=THEME.card, activeforeground=THEME.text,
            highlightthickness=0, relief="flat", width=16,
        )
        self._ch_menu["menu"].config(
            bg=THEME.input_bg, fg=THEME.text, font=FONTS.small,
            activebackground=THEME.accent, activeforeground=THEME.bg,
        )
        self._ch_menu.pack(side="right")

        # Bitrate
        br_row = tk.Frame(self._deew_settings_frame, bg=THEME.card)
        br_row.pack(fill="x", pady=(0, 6))
        self._br_label = tk.Label(
            br_row, text=t("bitrate_label"), font=FONTS.small,
            fg=THEME.text, bg=THEME.card,
        )
        self._br_label.pack(side="left")

        self._br_menu = tk.OptionMenu(
            br_row,
            self.deew_bitrate_var,
            t("default_bitrate"),
        )
        self._br_menu.config(
            bg=THEME.input_bg, fg=THEME.text, font=FONTS.small,
            activebackground=THEME.card, activeforeground=THEME.text,
            highlightthickness=0, relief="flat", width=12,
        )
        self._br_menu["menu"].config(
            bg=THEME.input_bg, fg=THEME.text, font=FONTS.small,
            activebackground=THEME.accent, activeforeground=THEME.bg,
        )
        self._br_menu.pack(side="right")

        # Deew-only ayarlar
        self._deew_only_frame = tk.Frame(self._deew_settings_frame, bg=THEME.card)
        self._deew_only_frame.pack(fill="x")

        drc_row = tk.Frame(self._deew_only_frame, bg=THEME.card)
        drc_row.pack(fill="x", pady=(0, 6))
        self._drc_label = tk.Label(
            drc_row, text=t("drc_profile"), font=FONTS.small,
            fg=THEME.text, bg=THEME.card,
        )
        self._drc_label.pack(side="left")

        self._drc_menu = tk.OptionMenu(
            drc_row,
            self.deew_drc_var,
            *[d.cli_value for d in DeewDRC],
        )
        self._drc_menu.config(
            bg=THEME.input_bg, fg=THEME.text, font=FONTS.small,
            activebackground=THEME.card, activeforeground=THEME.text,
            highlightthickness=0, relief="flat", width=16,
        )
        self._drc_menu["menu"].config(
            bg=THEME.input_bg, fg=THEME.text, font=FONTS.small,
            activebackground=THEME.accent, activeforeground=THEME.bg,
        )
        self._drc_menu.pack(side="right")

        dn_row = tk.Frame(self._deew_only_frame, bg=THEME.card)
        dn_row.pack(fill="x", pady=(0, 6))
        self._dn_label = tk.Label(
            dn_row, text=t("dialnorm_label"), font=FONTS.small,
            fg=THEME.text, bg=THEME.card,
        )
        self._dn_label.pack(side="left")
        tk.Entry(
            dn_row, textvariable=self.deew_dialnorm_var, width=8, justify="center",
            bg=THEME.input_bg, fg=THEME.text, insertbackground=THEME.text,
            relief="flat", font=FONTS.mono,
        ).pack(side="right")

        self._delete_wav_cb = tk.Checkbutton(
            self._deew_settings_frame,
            text=t("delete_intermediate_wav"),
            variable=self.deew_delete_wav_var,
            onvalue=True,
            offvalue=False,
            bg=THEME.card,
            fg=THEME.text,
            selectcolor=THEME.input_bg,
            activebackground=THEME.card,
            activeforeground=THEME.text,
            font=FONTS.small,
            anchor="w",
            relief="flat",
            highlightthickness=0,
        )
        self._delete_wav_cb.pack(fill="x", pady=(0, 4))

        self._enc_note_lbl = tk.Label(
            self._deew_settings_frame,
            text=t("deew_note"),
            font=FONTS.small,
            fg=THEME.muted,
            bg=THEME.card,
            anchor="w",
            justify="left",
        )
        self._enc_note_lbl.pack(fill="x", pady=(0, 4))

        # Değişiklik izleyicileri
        self.deew_format_var.trace_add("write", self._on_deew_format_change)
        self.deew_downmix_var.trace_add("write", self._on_deew_channel_change)

        self._update_channel_options()
        self._update_bitrate_options()
        self._update_format_description()

    def _build_encoding_panel(self, parent: tk.Frame) -> None:
        """Build the unified encoding pipeline panel."""
        # Main card
        card = tk.Frame(
            parent, bg=THEME.card,
            highlightbackground=THEME.border, highlightthickness=1,
        )
        card.pack(fill="x", pady=(0, 8))

        # Title
        self._encoding_title_lbl = tk.Label(
            card, text=t("encoding_pipeline"), font=FONTS.label,
            fg=THEME.accent, bg=THEME.card, anchor="w",
        )
        self._encoding_title_lbl.pack(fill="x", padx=14, pady=(10, 6))

        # Pipeline selector row
        sel_row = tk.Frame(card, bg=THEME.card)
        sel_row.pack(fill="x", padx=14, pady=(0, 8))

        self._encoding_pipeline_lbl = tk.Label(
            sel_row, text=t("encoding_pipeline_label"), font=FONTS.small,
            fg=THEME.text, bg=THEME.card,
        )
        self._encoding_pipeline_lbl.pack(side="left", padx=(0, 8))

        pipeline_options = [
            (EncodingPipeline.NONE.value, t("encoding_none")),
            (EncodingPipeline.DEEW.value, t("encoding_deew")),
            (EncodingPipeline.FFMPEG.value, t("encoding_ffmpeg")),
            (EncodingPipeline.QAAC.value, t("encoding_qaac")),
        ]

        self._encoding_pipeline_menu = tk.OptionMenu(
            sel_row, self._encoding_pipeline_var,
            *[v for v, _ in pipeline_options],
            command=self._on_encoding_pipeline_change,
        )
        self._encoding_pipeline_menu.config(
            bg=THEME.input_bg, fg=THEME.text, font=FONTS.small,
            highlightthickness=0, relief="flat", activebackground=THEME.accent,
            activeforeground=THEME.bg,
        )
        self._encoding_pipeline_menu["menu"].config(
            bg=THEME.input_bg, fg=THEME.text, font=FONTS.small,
            activebackground=THEME.accent, activeforeground=THEME.bg,
        )
        self._encoding_pipeline_menu.pack(side="left", fill="x", expand=True)

        # ── FFmpeg sub-panel ──
        self._ffmpeg_enc_frame = tk.Frame(card, bg=THEME.card)

        # FFmpeg format selector
        ff_row1 = tk.Frame(self._ffmpeg_enc_frame, bg=THEME.card)
        ff_row1.pack(fill="x", padx=14, pady=(0, 4))

        self._ffmpeg_format_lbl = tk.Label(
            ff_row1, text=t("encoding_format"), font=FONTS.small,
            fg=THEME.text, bg=THEME.card,
        )
        self._ffmpeg_format_lbl.pack(side="left", padx=(0, 8))

        ffmpeg_formats = [
            (FFmpegOutputFormat.AAC.codec, t("ffmpeg_aac_label")),
            (FFmpegOutputFormat.FLAC.codec, t("ffmpeg_flac_label")),
            (FFmpegOutputFormat.OPUS.codec, t("ffmpeg_opus_label")),
            (FFmpegOutputFormat.AC3.codec, t("ffmpeg_ac3_label")),
            (FFmpegOutputFormat.EAC3.codec, t("ffmpeg_eac3_label")),
        ]

        self._ffmpeg_format_menu = tk.OptionMenu(
            ff_row1, self._ffmpeg_format_var,
            *[v for v, _ in ffmpeg_formats],
            command=self._on_ffmpeg_format_change,
        )
        self._ffmpeg_format_menu.config(
            bg=THEME.input_bg, fg=THEME.text, font=FONTS.small,
            highlightthickness=0, relief="flat",
        )
        self._ffmpeg_format_menu["menu"].config(
            bg=THEME.input_bg, fg=THEME.text, font=FONTS.small,
        )
        self._ffmpeg_format_menu.pack(side="left", fill="x", expand=True)

        # FFmpeg AAC bitrate
        self._ffmpeg_aac_frame = tk.Frame(self._ffmpeg_enc_frame, bg=THEME.card)
        self._ffmpeg_aac_frame.pack(fill="x", padx=14, pady=(0, 4))
        self._ffmpeg_aac_bitrate_lbl = tk.Label(
            self._ffmpeg_aac_frame, text=t("aac_bitrate_label"), font=FONTS.small,
            fg=THEME.text, bg=THEME.card,
        )
        self._ffmpeg_aac_bitrate_lbl.pack(side="left", padx=(0, 8))
        tk.Entry(
            self._ffmpeg_aac_frame, textvariable=self._ffmpeg_aac_bitrate_var,
            width=8, bg=THEME.input_bg, fg=THEME.text, font=FONTS.small,
            insertbackground=THEME.text, relief="flat",
        ).pack(side="left")

        # FFmpeg FLAC compression
        self._ffmpeg_flac_frame = tk.Frame(self._ffmpeg_enc_frame, bg=THEME.card)
        self._ffmpeg_flac_compression_lbl = tk.Label(
            self._ffmpeg_flac_frame, text=t("ffmpeg_flac_compression_label"), font=FONTS.small,
            fg=THEME.text, bg=THEME.card,
        )
        self._ffmpeg_flac_compression_lbl.pack(side="left", padx=(0, 8))
        tk.Entry(
            self._ffmpeg_flac_frame, textvariable=self._ffmpeg_flac_compression_var,
            width=8, bg=THEME.input_bg, fg=THEME.text, font=FONTS.small,
            insertbackground=THEME.text, relief="flat",
        ).pack(side="left")

        # FFmpeg FLAC bit depth
        self._ffmpeg_flac_bd_frame = tk.Frame(self._ffmpeg_enc_frame, bg=THEME.card)
        self._ffmpeg_flac_bd_lbl = tk.Label(
            self._ffmpeg_flac_bd_frame, text=t("flac_bit_depth_label"), font=FONTS.small,
            fg=THEME.text, bg=THEME.card,
        )
        self._ffmpeg_flac_bd_lbl.pack(side="left", padx=(0, 8))

        ffmpeg_bd_options = [("24", t("flac_24bit")), ("16", t("flac_16bit"))]
        self._ffmpeg_flac_bd_menu = tk.OptionMenu(
            self._ffmpeg_flac_bd_frame, self._ffmpeg_flac_bit_depth_var,
            *[v for v, _ in ffmpeg_bd_options],
        )
        self._ffmpeg_flac_bd_menu.config(
            bg=THEME.input_bg, fg=THEME.text, font=FONTS.small,
            highlightthickness=0, relief="flat",
        )
        self._ffmpeg_flac_bd_menu["menu"].config(
            bg=THEME.input_bg, fg=THEME.text, font=FONTS.small,
        )
        self._ffmpeg_flac_bd_menu.pack(side="left")

        # FFmpeg Opus bitrate
        self._ffmpeg_opus_frame = tk.Frame(self._ffmpeg_enc_frame, bg=THEME.card)
        self._ffmpeg_opus_bitrate_lbl = tk.Label(
            self._ffmpeg_opus_frame, text=t("opus_bitrate_label"), font=FONTS.small,
            fg=THEME.text, bg=THEME.card,
        )
        self._ffmpeg_opus_bitrate_lbl.pack(side="left", padx=(0, 8))
        tk.Entry(
            self._ffmpeg_opus_frame, textvariable=self._ffmpeg_opus_bitrate_var,
            width=8, bg=THEME.input_bg, fg=THEME.text, font=FONTS.small,
            insertbackground=THEME.text, relief="flat",
        ).pack(side="left")

        # FFmpeg AC3/EAC3 bitrate
        self._ffmpeg_lossy_frame = tk.Frame(self._ffmpeg_enc_frame, bg=THEME.card)
        self._ffmpeg_lossy_bitrate_lbl = tk.Label(
            self._ffmpeg_lossy_frame, text=t("ac3_bitrate_label"), font=FONTS.small,
            fg=THEME.text, bg=THEME.card,
        )
        self._ffmpeg_lossy_bitrate_lbl.pack(side="left", padx=(0, 8))
        self._ffmpeg_lossy_bitrate_menu = tk.OptionMenu(
            self._ffmpeg_lossy_frame,
            self._ffmpeg_ac3eac3_bitrate_var,
            str(FFMPEG_AC3_DEFAULT_BITRATE),
        )
        self._ffmpeg_lossy_bitrate_menu.config(
            bg=THEME.input_bg, fg=THEME.text, font=FONTS.small,
            highlightthickness=0, relief="flat",
        )
        self._ffmpeg_lossy_bitrate_menu["menu"].config(
            bg=THEME.input_bg, fg=THEME.text, font=FONTS.small,
        )
        self._ffmpeg_lossy_bitrate_menu.pack(side="left")

        # FFmpeg AC3/EAC3 channel layout
        self._ffmpeg_channel_frame = tk.Frame(self._ffmpeg_enc_frame, bg=THEME.card)
        self._ffmpeg_channel_lbl = tk.Label(
            self._ffmpeg_channel_frame, text=t("channel_layout"), font=FONTS.small,
            fg=THEME.text, bg=THEME.card,
        )
        self._ffmpeg_channel_lbl.pack(side="left", padx=(0, 8))
        self._ffmpeg_channel_menu = tk.OptionMenu(
            self._ffmpeg_channel_frame,
            self._ffmpeg_downmix_var,
            "auto",
        )
        self._ffmpeg_channel_menu.config(
            bg=THEME.input_bg, fg=THEME.text, font=FONTS.small,
            highlightthickness=0, relief="flat",
        )
        self._ffmpeg_channel_menu["menu"].config(
            bg=THEME.input_bg, fg=THEME.text, font=FONTS.small,
        )
        self._ffmpeg_channel_menu.pack(side="left")

        # ── qaac sub-panel ──
        self._qaac_enc_frame = tk.Frame(card, bg=THEME.card)

        # qaac mode selector
        qa_row1 = tk.Frame(self._qaac_enc_frame, bg=THEME.card)
        qa_row1.pack(fill="x", padx=14, pady=(0, 4))

        self._qaac_mode_lbl = tk.Label(
            qa_row1, text=t("encoding_mode"), font=FONTS.small,
            fg=THEME.text, bg=THEME.card,
        )
        self._qaac_mode_lbl.pack(side="left", padx=(0, 8))

        qaac_modes = [
            (QaacMode.TVBR.flag, t("qaac_tvbr_label")),
            (QaacMode.CVBR.flag, t("qaac_cvbr_label")),
            (QaacMode.ABR.flag, t("qaac_abr_label")),
            (QaacMode.CBR.flag, t("qaac_cbr_label")),
        ]

        self._qaac_mode_menu = tk.OptionMenu(
            qa_row1, self._qaac_mode_var,
            *[v for v, _ in qaac_modes],
            command=self._on_qaac_mode_change,
        )
        self._qaac_mode_menu.config(
            bg=THEME.input_bg, fg=THEME.text, font=FONTS.small,
            highlightthickness=0, relief="flat",
        )
        self._qaac_mode_menu["menu"].config(
            bg=THEME.input_bg, fg=THEME.text, font=FONTS.small,
        )
        self._qaac_mode_menu.pack(side="left", fill="x", expand=True)

        # qaac TVBR quality
        self._qaac_tvbr_frame = tk.Frame(self._qaac_enc_frame, bg=THEME.card)
        self._qaac_tvbr_frame.pack(fill="x", padx=14, pady=(0, 4))
        self._qaac_tvbr_quality_lbl = tk.Label(
            self._qaac_tvbr_frame, text=t("qaac_quality_label"), font=FONTS.small,
            fg=THEME.text, bg=THEME.card,
        )
        self._qaac_tvbr_quality_lbl.pack(side="left", padx=(0, 8))
        tk.Entry(
            self._qaac_tvbr_frame, textvariable=self._qaac_tvbr_quality_var,
            width=8, bg=THEME.input_bg, fg=THEME.text, font=FONTS.small,
            insertbackground=THEME.text, relief="flat",
        ).pack(side="left")

        # qaac CVBR bitrate
        self._qaac_cvbr_frame = tk.Frame(self._qaac_enc_frame, bg=THEME.card)
        self._qaac_cvbr_bitrate_lbl = tk.Label(
            self._qaac_cvbr_frame, text=t("encoding_bitrate"), font=FONTS.small,
            fg=THEME.text, bg=THEME.card,
        )
        self._qaac_cvbr_bitrate_lbl.pack(side="left", padx=(0, 8))
        tk.Entry(
            self._qaac_cvbr_frame, textvariable=self._qaac_cvbr_bitrate_var,
            width=8, bg=THEME.input_bg, fg=THEME.text, font=FONTS.small,
            insertbackground=THEME.text, relief="flat",
        ).pack(side="left")

        # qaac ABR bitrate
        self._qaac_abr_frame = tk.Frame(self._qaac_enc_frame, bg=THEME.card)
        self._qaac_abr_bitrate_lbl = tk.Label(
            self._qaac_abr_frame, text=t("encoding_bitrate"), font=FONTS.small,
            fg=THEME.text, bg=THEME.card,
        )
        self._qaac_abr_bitrate_lbl.pack(side="left", padx=(0, 8))
        tk.Entry(
            self._qaac_abr_frame, textvariable=self._qaac_abr_bitrate_var,
            width=8, bg=THEME.input_bg, fg=THEME.text, font=FONTS.small,
            insertbackground=THEME.text, relief="flat",
        ).pack(side="left")

        # qaac CBR bitrate
        self._qaac_cbr_frame = tk.Frame(self._qaac_enc_frame, bg=THEME.card)
        self._qaac_cbr_bitrate_lbl = tk.Label(
            self._qaac_cbr_frame, text=t("encoding_bitrate"), font=FONTS.small,
            fg=THEME.text, bg=THEME.card,
        )
        self._qaac_cbr_bitrate_lbl.pack(side="left", padx=(0, 8))
        tk.Entry(
            self._qaac_cbr_frame, textvariable=self._qaac_cbr_bitrate_var,
            width=8, bg=THEME.input_bg, fg=THEME.text, font=FONTS.small,
            insertbackground=THEME.text, relief="flat",
        ).pack(side="left")

        # qaac checkboxes
        qa_checks = tk.Frame(self._qaac_enc_frame, bg=THEME.card)
        qa_checks.pack(fill="x", padx=14, pady=(0, 8))

        self._qaac_he_aac_cb = tk.Checkbutton(
            qa_checks, text=t("encoding_he_aac"), variable=self._qaac_he_aac_var,
            bg=THEME.card, fg=THEME.text, selectcolor=THEME.input_bg,
            activebackground=THEME.card, activeforeground=THEME.text,
            font=FONTS.small,
        )
        self._qaac_he_aac_cb.pack(side="left", padx=(0, 12))

        self._qaac_no_delay_cb = tk.Checkbutton(
            qa_checks, text=t("encoding_no_delay"), variable=self._qaac_no_delay_var,
            bg=THEME.card, fg=THEME.text, selectcolor=THEME.input_bg,
            activebackground=THEME.card, activeforeground=THEME.text,
            font=FONTS.small,
        )
        self._qaac_no_delay_cb.pack(side="left")

        # ── Deew sub-panel ──
        self._deew_enc_frame = tk.Frame(card, bg=THEME.card)
        self._build_deew_panel(self._deew_enc_frame)

        # Bottom padding
        tk.Frame(card, bg=THEME.card, height=6).pack(fill="x")

        # Store card reference for refresh
        self._encoding_card = card

        # Initialize visibility
        self._on_encoding_pipeline_change(self._encoding_pipeline_var.get())

    def _on_encoding_pipeline_change(self, value: str) -> None:
        """Show/hide encoding sub-panels based on pipeline selection."""
        # Hide all sub-panels
        self._ffmpeg_enc_frame.pack_forget()
        self._qaac_enc_frame.pack_forget()
        self._deew_enc_frame.pack_forget()

        if value == EncodingPipeline.FFMPEG.value:
            self._ffmpeg_enc_frame.pack(fill="x", pady=(0, 4))
            self._on_ffmpeg_format_change(self._ffmpeg_format_var.get())
        elif value == EncodingPipeline.QAAC.value:
            self._qaac_enc_frame.pack(fill="x", pady=(0, 4))
            self._on_qaac_mode_change(self._qaac_mode_var.get())
        elif value == EncodingPipeline.DEEW.value:
            self._deew_enc_frame.pack(fill="x", pady=(0, 4))

        self.schedule_later(50, self._fit_to_content)

    def _on_ffmpeg_format_change(self, value: str) -> None:
        """Show/hide FFmpeg format-specific fields."""
        self._ffmpeg_aac_frame.pack_forget()
        self._ffmpeg_flac_frame.pack_forget()
        self._ffmpeg_flac_bd_frame.pack_forget()
        self._ffmpeg_opus_frame.pack_forget()
        self._ffmpeg_lossy_frame.pack_forget()
        self._ffmpeg_channel_frame.pack_forget()

        if value == FFmpegOutputFormat.AAC.codec:
            self._ffmpeg_aac_frame.pack(fill="x", padx=14, pady=(0, 4))
        elif value == FFmpegOutputFormat.FLAC.codec:
            self._ffmpeg_flac_frame.pack(fill="x", padx=14, pady=(0, 4))
            self._ffmpeg_flac_bd_frame.pack(fill="x", padx=14, pady=(0, 4))
        elif value == FFmpegOutputFormat.OPUS.codec:
            self._ffmpeg_opus_frame.pack(fill="x", padx=14, pady=(0, 4))
        elif value in (FFmpegOutputFormat.AC3.codec, FFmpegOutputFormat.EAC3.codec):
            self._update_ffmpeg_lossy_options()
            self._ffmpeg_lossy_frame.pack(fill="x", padx=14, pady=(0, 4))
            self._ffmpeg_channel_frame.pack(fill="x", padx=14, pady=(0, 4))

        self.schedule_later(50, self._fit_to_content)

    def _on_qaac_mode_change(self, value: str) -> None:
        """Show/hide qaac mode-specific fields."""
        self._qaac_tvbr_frame.pack_forget()
        self._qaac_cvbr_frame.pack_forget()
        self._qaac_abr_frame.pack_forget()
        self._qaac_cbr_frame.pack_forget()

        if value == QaacMode.TVBR.flag:
            self._qaac_tvbr_frame.pack(fill="x", padx=14, pady=(0, 4))
        elif value == QaacMode.CVBR.flag:
            self._qaac_cvbr_frame.pack(fill="x", padx=14, pady=(0, 4))
        elif value == QaacMode.ABR.flag:
            self._qaac_abr_frame.pack(fill="x", padx=14, pady=(0, 4))
        elif value == QaacMode.CBR.flag:
            self._qaac_cbr_frame.pack(fill="x", padx=14, pady=(0, 4))

        self.schedule_later(50, self._fit_to_content)

    def _build_info_panel(self, parent: tk.Frame) -> None:
        """Ölçüm panelini oluşturur.

        Bu aracın ürettiği tek asıl sayı gecikmedir; v2.3'te dört eşit satırdan
        biri olarak, diğer meta verilerle aynı puntoda gösteriliyordu.  Burada
        gecikme bir ölçüm aleti ekranı gibi öne çıkar; güven ve drift ise onu
        yorumlamaya yarayan yardımcı telemetri olarak hemen altında durur.
        """
        info_frame = tk.Frame(
            parent, bg=THEME.card,
            highlightbackground=THEME.border, highlightthickness=1,
        )
        info_frame.pack(fill="x", pady=(0, 8))

        self._readout_caption = tk.Label(
            info_frame, text=t("detected_delay").rstrip(":").upper(),
            font=FONTS.section, fg=THEME.muted, bg=THEME.card, anchor="w",
        )
        self._readout_caption.pack(fill="x", padx=14, pady=(9, 0))

        # Değer ve birim aynı satırda ama ayrı boyutta: sayı tek başına okunur
        # kalsın, "ms" onu küçültmesin.
        value_row = tk.Frame(info_frame, bg=THEME.card)
        value_row.pack(fill="x", padx=14, pady=(0, 2))
        self.delay_val = tk.Label(
            value_row, text="—", font=FONTS.readout,
            fg=THEME.muted, bg=THEME.card, anchor="w",
        )
        self.delay_val.pack(side="left")
        self._readout_unit = tk.Label(
            value_row, text="", font=FONTS.readout_unit,
            fg=THEME.muted, bg=THEME.card,
        )
        self._readout_unit.pack(side="left", padx=(6, 0), pady=(0, 7))

        self._readout_detail = tk.Label(
            info_frame, text=t("readout_idle"), font=FONTS.small,
            fg=THEME.muted, bg=THEME.card, anchor="w", justify="left",
        )
        self._readout_detail.pack(fill="x", padx=14, pady=(0, 9))

        tk.Frame(info_frame, bg=THEME.border, height=1).pack(fill="x")

        # Çıktı özellikleri — ölçümün değil, üretilecek dosyanın bilgisi.
        rows = [
            ("channel", "ch_val"),
            ("bit_depth", "bit_val"),
            ("output_sample_rate", "sr_val"),
        ]
        self._info_labels: list[tuple[tk.Label, str]] = []
        for i, (key, attr) in enumerate(rows):
            row = tk.Frame(info_frame, bg=THEME.card)
            row.pack(
                fill="x", padx=14,
                pady=(7 if i == 0 else 2, 8 if i == len(rows) - 1 else 2),
            )
            lbl_left = tk.Label(
                row, text=t(key), font=FONTS.small,
                fg=THEME.muted, bg=THEME.card,
            )
            lbl_left.pack(side="left")
            lbl = tk.Label(
                row, text="—", font=FONTS.info_value,
                fg=THEME.text, bg=THEME.card,
            )
            lbl.pack(side="right")
            setattr(self, attr, lbl)
            self._info_labels.append((lbl_left, key))

    def _show_readout(
        self,
        delay_ms: float | None,
        *,
        detail: str = "",
        colour: str | None = None,
    ) -> None:
        """Drive the measurement display."""
        if delay_ms is None:
            self.delay_val.config(text="—", fg=THEME.muted)
            self._readout_unit.config(text="")
            self._readout_detail.config(text=detail or t("readout_idle"), fg=THEME.muted)
            return

        self.delay_val.config(text=f"{delay_ms:+.0f}", fg=colour or THEME.accent)
        self._readout_unit.config(text="ms", fg=THEME.muted)
        self._readout_detail.config(text=detail, fg=colour or THEME.muted)

    def _build_log_panel(self, parent: tk.Frame) -> None:
        """Log panelini oluşturur."""
        log_outer = tk.Frame(
            parent, bg=THEME.card,
            highlightbackground=THEME.border, highlightthickness=1,
        )
        log_outer.pack(fill="x", pady=(0, 8))
        self._log_title_lbl = tk.Label(
            log_outer, text=t("log_label"), font=FONTS.small,
            fg=THEME.muted, bg=THEME.card, anchor="w",
        )
        self._log_title_lbl.pack(fill="x", padx=12, pady=(8, 0))

        self.log_box = tk.Text(
            log_outer,
            height=9,
            bg=THEME.input_bg,
            fg=THEME.text,
            font=FONTS.mono,
            relief="flat",
            insertbackground=THEME.text,
            state="disabled",
            wrap="word",
            padx=8,
            pady=6,
        )
        self.log_box.pack(fill="both", expand=True, padx=8, pady=(2, 8))

    def _build_bottom_bar(self) -> None:
        """İlerleme çubuğu ve çalıştır butonunu sabit alt çubukta oluşturur.

        Bu bileşenler kaydırılabilir alanın **dışında** yer alır ve
        panel açılıp kapansa bile her zaman görünür kalır.
        """
        self._bottom_bar = tk.Frame(self, bg=THEME.bg)
        self._bottom_bar.pack(side="bottom", fill="x")

        # Ayırıcı çizgi
        tk.Frame(self._bottom_bar, bg=THEME.border, height=1).pack(fill="x")

        # İlerleme çubuğu
        self.progress_canvas = tk.Canvas(
            self._bottom_bar, height=3, bg=THEME.border, highlightthickness=0,
        )
        self.progress_canvas.pack(fill="x")
        self._progress_bar = self.progress_canvas.create_rectangle(
            0, 0, 0, 3, fill=THEME.accent, outline="",
        )

        # Tek sıra: solda durum metni, sağda eylemler.  v2.3'te üç düğme alt
        # alta tam genişlikte duruyor ve 800 piksellik pencerenin dörtte birini
        # yiyordu; üçü de aynı görsel ağırlıkta olduğu için hangisinin asıl
        # eylem olduğu da belli olmuyordu.
        bar = tk.Frame(self._bottom_bar, bg=THEME.bg)
        bar.pack(fill="x", padx=16, pady=10)

        status_col = tk.Frame(bar, bg=THEME.bg)
        status_col.pack(side="left", fill="x", expand=True)
        self._status_lbl = tk.Label(
            status_col, text="", font=FONTS.small,
            fg=THEME.muted, bg=THEME.bg, anchor="w",
        )
        self._status_lbl.pack(side="left")
        self._percent_lbl = tk.Label(
            status_col, text="", font=FONTS.mono,
            fg=THEME.muted, bg=THEME.bg, anchor="w",
        )
        self._percent_lbl.pack(side="left", padx=(8, 0))

        # Sağdan sola paketlenir; bu yüzden asıl eylem en sağda kalsın diye
        # önce o eklenir.
        self.run_btn = tk.Button(
            bar,
            text=t("start_sync"),
            font=FONTS.button,
            fg=THEME.bg,
            bg=THEME.accent,
            activebackground=THEME.accent,
            activeforeground=THEME.bg,
            relief="flat",
            padx=20,
            pady=9,
            cursor="hand2",
            command=self._start,
        )
        self.run_btn.pack(side="right")

        self.analyze_btn = tk.Button(
            bar,
            text=t("analyze_only"),
            font=FONTS.button,
            fg=THEME.accent2,
            bg=THEME.card,
            activebackground=THEME.raised,
            activeforeground=THEME.accent2,
            relief="flat",
            padx=16,
            pady=9,
            cursor="hand2",
            command=self._start_analyze,
        )
        self.analyze_btn.pack(side="right", padx=(0, 8))

        # İptal yalnızca iptal edilecek bir şey varken görünür.
        self.cancel_btn = tk.Button(
            bar,
            text=t("btn_cancel"),
            font=FONTS.button,
            fg=THEME.muted,
            bg=THEME.card,
            activebackground=THEME.raised,
            activeforeground=THEME.err,
            relief="flat",
            padx=16,
            pady=9,
            cursor="hand2",
            state="disabled",
            command=self._cancel_processing,
        )
        self._cancel_visible = False

    def _set_cancel_active(self, active: bool) -> None:
        """Show Cancel only while there is something to cancel.

        A permanently visible disabled button reads as a control that does not
        work; the action bar stays quieter when it offers only what is
        currently possible.
        """
        self.cancel_btn.config(
            state="normal" if active else "disabled",
            text=t("btn_cancel"),
        )
        if active and not self._cancel_visible:
            self.cancel_btn.pack(side="right", padx=(0, 8))
            self._cancel_visible = True
        elif not active and self._cancel_visible:
            self.cancel_btn.pack_forget()
            self._cancel_visible = False

    # ── Dil Değişikliği ──────────────────────────────────────────────────

    def _open_tool_paths_dialog(self) -> None:
        """Open the tool paths configuration dialog."""
        dialog = tk.Toplevel(self)
        dialog.title(t("tool_paths_title"))
        dialog.geometry("600x400")
        dialog.resizable(False, False)
        dialog.configure(bg=THEME.bg)
        dialog.transient(self)
        dialog.grab_set()

        # Description
        tk.Label(
            dialog, text=t("tool_paths_description"),
            font=FONTS.small, fg=THEME.muted, bg=THEME.bg,
            wraplength=560, justify="left",
        ).pack(fill="x", padx=20, pady=(16, 12))

        # Tool path rows
        tools = [
            ("ffmpeg", t("tool_path_ffmpeg")),
            ("ffprobe", t("tool_path_ffprobe")),
            ("qaac", t("tool_path_qaac")),
            ("deew", t("tool_path_deew")),
        ]

        path_vars: dict[str, tk.StringVar] = {}
        status_labels: dict[str, tk.Label] = {}

        for tool_name, label_text in tools:
            frame = tk.Frame(dialog, bg=THEME.bg)
            frame.pack(fill="x", padx=20, pady=(0, 8))

            tk.Label(
                frame, text=label_text, font=FONTS.small,
                fg=THEME.text, bg=THEME.bg, width=14, anchor="w",
            ).pack(side="left")

            current_path = getattr(TOOL_PATHS, tool_name, None) or ""
            var = tk.StringVar(value=current_path)
            path_vars[tool_name] = var

            entry = tk.Entry(
                frame, textvariable=var, font=FONTS.small,
                bg=THEME.input_bg, fg=THEME.text,
                insertbackground=THEME.text, relief="flat",
            )
            entry.pack(side="left", fill="x", expand=True, padx=(4, 4))

            def _browse(v=var, d=dialog):
                from tkinter import filedialog as _fd
                path = _fd.askopenfilename(parent=d, title="Select executable")
                if path:
                    v.set(path)

            tk.Button(
                frame, text=t("tool_path_browse"), font=FONTS.small,
                fg=THEME.text, bg=THEME.input_bg, relief="flat",
                command=_browse,
            ).pack(side="left", padx=(0, 2))

            def _clear(v=var):
                v.set("")

            tk.Button(
                frame, text=t("tool_path_clear"), font=FONTS.small,
                fg=THEME.muted, bg=THEME.input_bg, relief="flat",
                command=_clear,
            ).pack(side="left")

            # Status label
            status_lbl = tk.Label(
                dialog, text="", font=FONTS.small,
                fg=THEME.muted, bg=THEME.bg, anchor="w",
            )
            status_lbl.pack(fill="x", padx=34, pady=(0, 4))
            status_labels[tool_name] = status_lbl

        # Update status for each tool
        def _update_statuses():
            for tool_name, lbl in status_labels.items():
                custom = path_vars[tool_name].get().strip()
                if custom:
                    if os.path.isfile(custom):
                        lbl.config(text=t("tool_path_custom", path=custom), fg="#4ade80")
                    else:
                        lbl.config(text=t("tool_path_not_found"), fg=THEME.accent2)
                else:
                    try:
                        found = resolve_tool(tool_name)
                        lbl.config(text=t("tool_path_found", path=found), fg="#4ade80")
                    except OSError:
                        lbl.config(text=t("tool_path_using_path"), fg=THEME.muted)

        _update_statuses()

        # Save button
        def _save():
            paths = ToolPaths(
                ffmpeg=path_vars["ffmpeg"].get().strip() or None,
                ffprobe=path_vars["ffprobe"].get().strip() or None,
                qaac=path_vars["qaac"].get().strip() or None,
                deew=path_vars["deew"].get().strip() or None,
            )
            ok = save_tool_paths(paths)
            # The new paths may point at entirely different binaries, so drop
            # every memoized probe result before re-reporting status.
            FFmpegWrapper.reset_availability_cache()
            reset_deew_probe_cache()
            self._deew_available = None
            _update_statuses()
            self._update_deew_status()
            if not ok:
                messagebox.showwarning(
                    t("tool_paths_title"),
                    t("tool_paths_save_failed"),
                )

        btn_frame = tk.Frame(dialog, bg=THEME.bg)
        btn_frame.pack(fill="x", padx=20, pady=(8, 16))

        tk.Button(
            btn_frame, text=t("btn_save"),
            font=FONTS.button, fg=THEME.bg, bg=THEME.accent,
            activebackground=THEME.accent, activeforeground=THEME.bg,
            relief="flat", padx=20, pady=8, cursor="hand2",
            command=_save,
        ).pack(side="right")

        tk.Button(
            btn_frame, text=t("btn_cancel"),
            font=FONTS.button, fg=THEME.text, bg=THEME.card,
            activebackground=THEME.card, activeforeground=THEME.text,
            relief="flat", padx=20, pady=8, cursor="hand2",
            command=dialog.destroy,
        ).pack(side="right", padx=(0, 8))

    def _on_language_change(self, selected: str) -> None:
        """Dil değiştiğinde tüm UI metinlerini günceller."""
        for lang in Language:
            if lang.display_name == selected:
                self._i18n.set_language(lang)
                break
        self._refresh_all_texts()

    def _refresh_all_texts(self) -> None:
        """Tüm UI metinlerini aktif dile göre günceller."""
        # Başlık
        self._subtitle_lbl.config(text=t("app_subtitle"))
        self._lang_label.config(text=t("language"))

        # Tespit ayarları
        self._options_title_lbl.config(text=t("detection_settings"))
        self._skip_intro_lbl.config(text=t("skip_intro_sec"))
        self._scan_window_lbl.config(text=t("scan_window_count"))
        self._force_48k_cb.config(text=t("force_48k"))
        self._force_48k_note_lbl.config(text=t("force_48k_note"))
        self._correct_drift_cb.config(text=t("correct_drift"))
        self._correct_steps_cb.config(text=t("correct_steps"))
        self._timing_note_lbl.config(text=t("timing_corrections_note"))

        # Ölçüm paneli — değer yerinde kalır, yalnızca etiketler çevrilir.
        self._readout_caption.config(text=t("detected_delay").rstrip(":").upper())
        if self.delay_val.cget("text") == "—":
            self._readout_detail.config(text=t("readout_idle"))

        # Senkronizasyon modu
        self._sync_mode_title_lbl.config(text=t("sync_mode"))
        self._sync_mode_label.config(text=t("sync_mode_label"))
        self._sync_mode_note_lbl.config(text=t("sync_mode_note"))
        self._rebuild_sync_mode_menu()
        self._update_sync_mode_description()

        # FPS
        self._fps_title_lbl.config(text=t("fps_conversion"))
        self._fps_enable_cb.config(text=t("fps_enable"))
        self._fps_auto_cb.config(text=t("fps_auto"))
        self._fps_conv_lbl.config(text=t("fps_conversion_label"))
        self._fps_note_lbl.config(text=t("fps_note"))
        self._update_fps_ratio_label()

        # Deew
        self._enc_desc_lbl.config(text=t("deew_desc"))
        self._fmt_label.config(text=t("format_label"))
        self._ch_label.config(text=t("channel_layout"))
        self._br_label.config(text=t("bitrate_label"))
        self._drc_label.config(text=t("drc_profile"))
        self._dn_label.config(text=t("dialnorm_label"))
        self._delete_wav_cb.config(text=t("delete_intermediate_wav"))
        self._enc_note_lbl.config(text=t("deew_note"))
        self._update_deew_status()
        self._update_bitrate_options()
        self._update_format_description()

        # Encoding panel
        self._encoding_title_lbl.config(text=t("encoding_pipeline"))
        self._encoding_pipeline_lbl.config(text=t("encoding_pipeline_label"))
        self._ffmpeg_format_lbl.config(text=t("encoding_format"))
        self._ffmpeg_aac_bitrate_lbl.config(text=t("aac_bitrate_label"))
        self._ffmpeg_flac_compression_lbl.config(text=t("ffmpeg_flac_compression_label"))
        self._ffmpeg_opus_bitrate_lbl.config(text=t("opus_bitrate_label"))
        self._ffmpeg_channel_lbl.config(text=t("channel_layout"))
        self._qaac_mode_lbl.config(text=t("encoding_mode"))
        self._qaac_tvbr_quality_lbl.config(text=t("qaac_quality_label"))
        self._qaac_cvbr_bitrate_lbl.config(text=t("encoding_bitrate"))
        self._qaac_abr_bitrate_lbl.config(text=t("encoding_bitrate"))
        self._qaac_cbr_bitrate_lbl.config(text=t("encoding_bitrate"))
        self._qaac_he_aac_cb.config(text=t("encoding_he_aac"))
        self._qaac_no_delay_cb.config(text=t("encoding_no_delay"))
        self._ffmpeg_flac_bd_lbl.config(text=t("flac_bit_depth_label"))
        self._on_ffmpeg_format_change(self._ffmpeg_format_var.get())

        # Tool paths button
        self._tool_paths_btn.config(text=t("tool_paths_button"))

        # Bilgi paneli
        for lbl, key in self._info_labels:
            lbl.config(text=t(key))

        # Log
        self._log_title_lbl.config(text=t("log_label"))

        # Butonlar
        if not self._processing:
            self.analyze_btn.config(text=t("analyze_only"))
            self.cancel_btn.config(text=t("btn_cancel"))
            self.run_btn.config(text=t("start_sync"))
        elif self._cancel_event.is_set():
            self.cancel_btn.config(text=t("canceling"))
        else:
            self.cancel_btn.config(text=t("btn_cancel"))

        # Drop zones
        self.zone_src.update_label(t("source_audio"))
        self.zone_sync.update_label(t("sync_audio"))

    # ── Sync Mode UI Yardımcıları ────────────────────────────────────────

    def _on_sync_mode_change(self, *_args: object) -> None:
        """Senkronizasyon modu değiştiğinde açıklama etiketini günceller."""
        self._update_sync_mode_description()

    def _update_sync_mode_description(self) -> None:
        """Senkronizasyon modu açıklama etiketini günceller."""
        mode = self._get_selected_sync_mode()
        turkish = self._i18n.language == Language.TR
        desc = mode.description_tr if turkish else mode.description_en
        self._sync_mode_desc_lbl.config(text=f"  → {desc}")

    def _get_selected_sync_mode(self) -> SyncMode:
        """Seçili senkronizasyon modunu döndürür.

        Etiket iki dilde de eşleştirilir; aksi hâlde dil değişince menüdeki
        seçim geçerli bir moda karşılık gelmez ve sessizce varsayılana düşerdi.
        """
        selected = self.sync_mode_var.get()
        for sm in SyncMode:
            if selected in (sm.display_name, sm.display_name_tr):
                return sm
        return SyncMode.ADELAY_AMIX

    def _rebuild_sync_mode_menu(self) -> None:
        """Relabel the mode menu after a language change."""
        turkish = self._i18n.language == Language.TR
        current = self._get_selected_sync_mode()

        menu = self._sync_mode_menu["menu"]
        menu.delete(0, "end")
        for mode in SyncMode:
            label = mode.label(turkish)
            menu.add_command(
                label=label,
                command=lambda value=label: self.sync_mode_var.set(value),
            )
        self.sync_mode_var.set(current.label(turkish))

    # ── FPS UI Yardımcıları ──────────────────────────────────────────────

    def _on_fps_toggle(self) -> None:
        if self.fps_enabled_var.get():
            self._show_fps_settings(True)
        else:
            self._show_fps_settings(False)

    def _show_fps_settings(self, show: bool) -> None:
        if show:
            self._fps_settings_frame.pack(fill="x", padx=14, pady=(0, 10))
        else:
            self._fps_settings_frame.pack_forget()
        self.schedule_later(50, self._fit_to_content)

    def _on_fps_conversion_change(self, *_args: object) -> None:
        self._update_fps_ratio_label()

    def _update_fps_ratio_label(self) -> None:
        conversion = self._get_selected_fps_conversion()
        if conversion is not None:
            ratio = conversion.tempo_ratio
            atempo = 1.0 / ratio
            if atempo < 1.0:
                direction = t("fps_slowdown")
                pct = (1.0 - atempo) * 100.0
            else:
                direction = t("fps_speedup")
                pct = (atempo - 1.0) * 100.0
            self._fps_ratio_lbl.config(
                text=f"  → oran: {ratio:.6f}  |  %{pct:.3f} {direction}",
            )
        else:
            self._fps_ratio_lbl.config(text="")

    def _get_selected_fps_conversion(self) -> FpsConversion | None:
        selected = self.fps_conversion_var.get()
        for fc in FpsConversion:
            if fc.display_name == selected:
                return fc
        return None

    # ── Deew UI Yardımcıları ─────────────────────────────────────────────

    def _update_deew_status(self) -> None:
        """Refresh the deew badge without blocking the event loop.

        Resolving the backend starts deew with a 15 s timeout; doing that
        inline froze the window during startup and on every language switch.
        """
        if self._deew_available is None:
            self._deew_status_lbl.config(text=t("deew_checking"), fg=THEME.muted)
            self._probe_deew_status_async()
            return

        if self._deew_available:
            self._deew_status_lbl.config(text=t("deew_ready"), fg="#4ade80")
        else:
            self._deew_status_lbl.config(text=t("deew_unavailable"), fg=THEME.accent2)

    def _probe_deew_status_async(self) -> None:
        """Run the deew runtime probe on a worker thread."""
        if self._deew_probe_running:
            return
        self._deew_probe_running = True

        def _probe() -> None:
            try:
                available, _detail = get_deew_runtime_status()
            except Exception:
                available = False
            self.schedule(lambda: self._on_deew_status_probed(available))

        threading.Thread(target=_probe, daemon=True).start()

    def _on_deew_status_probed(self, available: bool) -> None:
        self._deew_probe_running = False
        self._deew_available = available
        self._update_deew_status()

    def _on_deew_toggle(self) -> None:
        """Legacy no-op — Deew visibility is now controlled by the pipeline dropdown."""
        pass

    def _show_deew_settings(self, show: bool) -> None:
        """Legacy no-op — Deew settings are always visible when the sub-panel is shown."""
        pass

    def _on_deew_format_change(self, *_args: object) -> None:
        self._update_channel_options()
        self._update_bitrate_options()
        self._update_format_description()

    def _on_deew_channel_change(self, *_args: object) -> None:
        self._update_bitrate_options()

    def _update_channel_options(self) -> None:
        fmt = self._get_selected_format()
        menu = self._ch_menu["menu"]
        menu.delete(0, "end")

        options = ["auto"]
        for dm in DeewDownmix:
            if dm == DeewDownmix.SURROUND_71 and fmt == DeewFormat.DD:
                continue
            options.append(dm.display_name)

        for opt in options:
            menu.add_command(
                label=opt,
                command=lambda v=opt: self.deew_downmix_var.set(v),
            )

        current = self.deew_downmix_var.get()
        if current not in options:
            self.deew_downmix_var.set("auto")

    def _update_format_description(self) -> None:
        fmt_value = self.deew_format_var.get()
        for f in DeewFormat:
            if f.cli_value == fmt_value:
                self._fmt_desc_lbl.config(text=f"  → {f.display_name} ({f.extension})")
                return
        self._fmt_desc_lbl.config(text="")

    def _update_bitrate_options(self) -> None:
        fmt = self._get_selected_format()
        downmix = self._get_selected_downmix()
        key = get_deew_bitrate_key(fmt, downmix)
        bitrates = DEEW_COMMON_BITRATES.get(key, [256, 384, 448, 640])
        default_br = DEEW_DEFAULT_BITRATES.get(key, 448)

        menu = self._br_menu["menu"]
        menu.delete(0, "end")

        menu.add_command(
            label=f"{t('default_bitrate')} ({default_br})",
            command=lambda: self.deew_bitrate_var.set(""),
        )
        menu.add_separator()

        for br in bitrates:
            label = f"{br} kbps"
            menu.add_command(
                label=label,
                command=lambda b=br: self.deew_bitrate_var.set(str(b)),
            )

        current = self.deew_bitrate_var.get()
        if current and current.isdigit() and int(current) not in bitrates:
            self.deew_bitrate_var.set("")

    def _get_selected_ffmpeg_format(self) -> FFmpegOutputFormat:
        fmt_value = self._ffmpeg_format_var.get()
        for fmt in FFmpegOutputFormat:
            if fmt.codec == fmt_value:
                return fmt
        return FFmpegOutputFormat.AAC

    def _parse_downmix_value(self, value: str) -> DeewDownmix | None:
        if value == "auto":
            return None
        for dm in DeewDownmix:
            if dm.display_name == value:
                return dm
        return None

    def _update_ffmpeg_lossy_options(self) -> None:
        fmt = self._get_selected_ffmpeg_format()
        is_eac3 = fmt == FFmpegOutputFormat.EAC3
        bitrates = FFMPEG_EAC3_BITRATES if is_eac3 else FFMPEG_AC3_BITRATES
        default_br = FFMPEG_EAC3_DEFAULT_BITRATE if is_eac3 else FFMPEG_AC3_DEFAULT_BITRATE

        self._ffmpeg_lossy_bitrate_lbl.config(
            text=t("eac3_bitrate_label") if is_eac3 else t("ac3_bitrate_label"),
        )

        menu = self._ffmpeg_lossy_bitrate_menu["menu"]
        menu.delete(0, "end")
        for br in bitrates:
            menu.add_command(
                label=f"{br} kbps",
                command=lambda b=br: self._ffmpeg_ac3eac3_bitrate_var.set(str(b)),
            )

        current = self._ffmpeg_ac3eac3_bitrate_var.get()
        if not current.isdigit() or int(current) not in bitrates:
            self._ffmpeg_ac3eac3_bitrate_var.set(str(default_br))

        channel_menu = self._ffmpeg_channel_menu["menu"]
        channel_menu.delete(0, "end")

        options = ["auto"]
        for dm in DeewDownmix:
            if fmt == FFmpegOutputFormat.AC3 and dm == DeewDownmix.SURROUND_71:
                continue
            options.append(dm.display_name)

        for opt in options:
            channel_menu.add_command(
                label=opt,
                command=lambda v=opt: self._ffmpeg_downmix_var.set(v),
            )

        current_downmix = self._ffmpeg_downmix_var.get()
        if current_downmix not in options:
            self._ffmpeg_downmix_var.set("auto")

    def _get_selected_format(self) -> DeewFormat:
        fmt_value = self.deew_format_var.get()
        for f in DeewFormat:
            if f.cli_value == fmt_value:
                return f
        return DeewFormat.DDP

    def _get_selected_downmix(self) -> DeewDownmix | None:
        return self._parse_downmix_value(self.deew_downmix_var.get())

    def _get_selected_ffmpeg_downmix(self) -> DeewDownmix | None:
        return self._parse_downmix_value(self._ffmpeg_downmix_var.get())

    def _get_selected_drc(self) -> DeewDRC:
        drc_value = self.deew_drc_var.get()
        for d in DeewDRC:
            if d.cli_value == drc_value:
                return d
        return DeewDRC.MUSIC_LIGHT

    # ── Olay Yöneticileri ────────────────────────────────────────────────

    def _on_src_pick(self, path: str) -> None:
        ext = os.path.splitext(path)[1].lower()
        if ext in CONTAINER_EXTENSIONS:
            self._handle_container_async(path, "src")
        else:
            self._src_path = path
            self._log(t("log_source", name=os.path.basename(path)))

    def _on_sync_pick(self, path: str) -> None:
        ext = os.path.splitext(path)[1].lower()
        if ext in CONTAINER_EXTENSIONS:
            self._handle_container_async(path, "sync")
        else:
            self._sync_path = path
            self._log(t("log_sync_file", name=os.path.basename(path)))

    # ── Container / MKV Handling (non-blocking) ──────────────────────────

    def _handle_container_async(self, path: str, role: str) -> None:
        """Handle container files without blocking the UI.

        Phase 1 (background): probe audio streams with ffprobe.
        Phase 2 (main thread): show stream selection dialog if needed.
        Phase 3 (background): extract the selected audio stream.
        Phase 4 (main thread): update UI with the extracted file.

        Args:
            path: Container file path.
            role: "src" or "sync".
        """
        # Guard against concurrent extraction for the same role
        if getattr(self, f"_extracting_{role}", False):
            return
        setattr(self, f"_extracting_{role}", True)

        self._log(t("log_mkv_detected"))
        zone = self.zone_src if role == "src" else self.zone_sync

        # Show loading state
        zone.show_status(t("mkv_extracting"))

        def _probe_thread() -> None:
            """Background: probe streams."""
            try:
                streams = self._ffmpeg.probe_audio_streams(path)
            except Exception:
                streams = []
            # Back to main thread for dialog
            self.schedule(lambda: self._container_on_probed(path, role, streams))

        threading.Thread(target=_probe_thread, daemon=True).start()

    def _container_on_probed(
        self, path: str, role: str, streams: list[dict[str, str]],
    ) -> None:
        """Main thread: handle probe results, show dialog if needed."""
        zone = self.zone_src if role == "src" else self.zone_sync

        if not streams:
            messagebox.showwarning(t("mkv_select_title"), t("mkv_no_audio"))
            zone.clear_selection()
            setattr(self, f"_extracting_{role}", False)
            return

        # Single stream — auto-select
        if len(streams) == 1:
            stream_index = int(streams[0].get("index", 0))
            self._log(t("mkv_single_stream"))
        else:
            # Multiple streams — show selection dialog (on main thread)
            stream_index = ask_stream_selection(
                self, streams, os.path.basename(path),
            )
            if stream_index is None:
                zone.clear_selection()
                setattr(self, f"_extracting_{role}", False)
                return

        # Find codec for the selected stream
        codec = "unknown"
        for s in streams:
            if int(s.get("index", -1)) == stream_index:
                codec = s.get("codec_name", "unknown")
                break

        # Start extraction in background
        self._log(t("mkv_extracting"))
        zone.show_status(t("mkv_extracting"))

        def _extract_thread() -> None:
            """Background: extract audio stream."""
            out_ext = next(
                (
                    s.get("suggested_ext", ".mka")
                    for s in streams
                    if int(s.get("index", -1)) == stream_index
                ),
                CODEC_EXTENSION_MAP.get(codec, ".mka"),
            )

            fd, tmp_path = _tempfile_mod.mkstemp(
                prefix=f"audiosync_{role}_", suffix=out_ext,
            )
            os.close(fd)

            try:
                self._ffmpeg.extract_audio_stream(path, tmp_path, stream_index)
                # Back to main thread to update UI
                self.schedule(lambda: self._container_on_extracted(
                    tmp_path, role,
                ))
            except Exception as exc:
                error_text = str(exc)
                self.schedule(lambda: self._container_on_extract_error(
                    error_text, tmp_path, role,
                ))

        threading.Thread(target=_extract_thread, daemon=True).start()

    def _container_on_extracted(self, tmp_path: str, role: str) -> None:
        """Main thread: update UI after successful extraction."""
        log_key = "log_source" if role == "src" else "log_sync_file"
        zone = self.zone_src if role == "src" else self.zone_sync

        self._log(t("mkv_extracted", name=os.path.basename(tmp_path)))
        self._log(t(log_key, name=os.path.basename(tmp_path)))

        if role == "src":
            self._src_path = tmp_path
        else:
            self._sync_path = tmp_path

        zone.set_file_external(tmp_path)

        # Track temp file for cleanup
        if not hasattr(self, "_container_temp_files"):
            self._container_temp_files: list[str] = []
        self._container_temp_files.append(tmp_path)

        setattr(self, f"_extracting_{role}", False)

    def _container_on_extract_error(
        self, error: str, tmp_path: str, role: str,
    ) -> None:
        """Main thread: handle extraction error."""
        zone = self.zone_src if role == "src" else self.zone_sync

        self._log(t("mkv_extract_error", err=error))
        zone.clear_selection()

        if os.path.isfile(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass

        setattr(self, f"_extracting_{role}", False)

    # ── Cleanup ──────────────────────────────────────────────────────────

    def schedule(self, callback: Callable[[], None]) -> None:
        """Run ``callback`` on the UI thread, ignoring it after teardown.

        Background probes outlive the window when the user closes it mid-run,
        and ``after()`` on a destroyed interpreter raises from the worker
        thread — which leaves the Tcl side in an unusable state.
        """
        if self._closing:
            return
        try:
            self.after(0, callback)
        except (tk.TclError, RuntimeError):
            pass

    def schedule_later(self, delay_ms: int, callback: Callable[[], None]) -> None:
        """Schedule a delayed callback, remembering it so teardown can cancel it."""
        if self._closing:
            return
        try:
            self._pending_after_ids.add(self.after(delay_ms, callback))
        except (tk.TclError, RuntimeError):
            pass

    def _cancel_pending_callbacks(self) -> None:
        """Drop timers that would otherwise fire into a destroyed interpreter."""
        for after_id in self._pending_after_ids:
            try:
                self.after_cancel(after_id)
            except (tk.TclError, RuntimeError, ValueError):
                pass
        self._pending_after_ids.clear()

    def destroy(self) -> None:
        """Clean up temporary container extraction files on exit."""
        self._closing = True
        self._cancel_event.set()
        self._cancel_pending_callbacks()
        for tmp in getattr(self, "_container_temp_files", []):
            try:
                if os.path.isfile(tmp):
                    os.remove(tmp)
            except OSError:
                pass
        super().destroy()

    # ── İş Mantığı Koordinasyonu ─────────────────────────────────────────

    def _clear_log(self) -> None:
        """Log metin kutusunu temizler."""
        def _do() -> None:
            self.log_box.config(state="normal")
            self.log_box.delete("1.0", "end")
            self.log_box.config(state="disabled")
        self.schedule(_do)

    def _cancel_processing(self) -> None:
        """Request cancellation for the current background operation."""
        with self._processing_lock:
            if not self._processing:
                return
        if self._cancel_event.is_set():
            return

        self._cancel_event.set()
        self._log(t("log_cancel_requested"))
        self.schedule(lambda: self.cancel_btn.config(state="disabled", text=t("canceling")))

    def _check_cancelled(self) -> None:
        """Raise a dedicated exception if the user requested cancellation."""
        if self._cancel_event.is_set():
            raise OperationCancelledError("Processing cancelled by user.")

    def _log_timing(self, step_message: str, started_at: float) -> None:
        """Log the elapsed time for a pipeline step."""
        elapsed = time.perf_counter() - started_at
        self._log(t("log_timing", step=step_message, seconds=elapsed))

    def _get_analyzer(self) -> "AudioAnalyzer":
        """Create the heavy analyzer lazily to keep startup lighter."""
        if self._analyzer is None:
            from audio_sync.core.analyzer import AudioAnalyzer as _AudioAnalyzer

            self._analyzer = _AudioAnalyzer(config=self._config)
        return self._analyzer

    def _prepare_analysis(
        self,
        src_path: str,
        sync_path: str,
        *,
        force_48k: bool,
        fps_conversion: FpsConversion | None,
        probe_message: str,
        decode_message: str,
        probe_progress: int,
        post_probe_progress: int,
        fps_progress: int,
        decode_start_progress: int,
        src_decoded_progress: int,
        sync_decoded_progress: int,
        fps_tmp_prefix: str,
        detail_logger: Callable[[AudioInfo, AudioInfo, OutputSampleRate], None] | None = None,
    ) -> _PreparedAnalysis:
        """Probe, optionally FPS-convert, and decode the pair for analysis."""
        self._log(probe_message)
        self._set_progress(probe_progress)
        probe_started = time.perf_counter()
        src_info = self._ffmpeg.probe_audio(src_path)
        sync_info = self._ffmpeg.probe_audio(sync_path)
        self._log_timing(probe_message, probe_started)
        self._check_cancelled()

        output_sr = OutputSampleRate.decide(
            src_info.sample_rate,
            sync_info.sample_rate,
            force_48k,
        )
        self._update_info_panel(sync_info, output_sr)
        if detail_logger is not None:
            detail_logger(src_info, sync_info, output_sr)
        self._set_progress(post_probe_progress)

        effective_sync_path = sync_path
        fps_tmp_path: str | None = None
        if fps_conversion is not None:
            self._log(t("log_fps_applying", name=fps_conversion.display_name))
            self._set_progress(fps_progress)
            fps_started = time.perf_counter()

            fps_tmp_fd, fps_tmp_path = _tempfile_mod.mkstemp(
                prefix=fps_tmp_prefix,
                suffix=".wav",
            )
            os.close(fps_tmp_fd)

            fps_summary = self._ffmpeg.apply_fps_conversion(
                sync_path,
                fps_tmp_path,
                fps_conversion,
                sync_info,
                cancel_event=self._cancel_event,
            )
            self._log(f"FPS: {fps_summary}")
            self._log_timing(t("log_fps_applying", name=fps_conversion.display_name), fps_started)
            effective_sync_path = fps_tmp_path
            sync_info = self._ffmpeg.probe_audio(effective_sync_path)
            self._log(t("log_fps_done"))
            self._check_cancelled()

        self._log(decode_message)
        self._set_progress(decode_start_progress)
        decode_started = time.perf_counter()
        src_pcm_path: str | None = None
        sync_pcm_path: str | None = None
        try:
            src_rate, src_pcm_path, src_samples = self._ffmpeg.decode_mono_pcm_to_file(
                src_path,
                cancel_event=self._cancel_event,
                prefix="audiosync_src_pcm_",
            )
            self._set_progress(src_decoded_progress)
            self._check_cancelled()
            sync_rate, sync_pcm_path, sync_samples = self._ffmpeg.decode_mono_pcm_to_file(
                effective_sync_path,
                cancel_event=self._cancel_event,
                prefix="audiosync_sync_pcm_",
            )
            self._set_progress(sync_decoded_progress)
            self._log_timing(decode_message, decode_started)
            self._check_cancelled()
        except Exception:
            for tmp_path in (src_pcm_path, sync_pcm_path):
                if tmp_path and os.path.isfile(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass
            raise

        return _PreparedAnalysis(
            src_info=src_info,
            sync_info=sync_info,
            output_sr=output_sr,
            effective_sync_path=effective_sync_path,
            fps_tmp_path=fps_tmp_path,
            src_rate=src_rate,
            sync_rate=sync_rate,
            src_pcm_path=src_pcm_path,
            sync_pcm_path=sync_pcm_path,
            src_samples=src_samples,
            sync_samples=sync_samples,
        )

    def _calculate_delay_result(
        self,
        prepared: _PreparedAnalysis,
        *,
        skip_sec: float,
        segment_count: int,
        analyze_message: str,
        progress: int,
    ) -> AnalysisResult:
        """Run the actual delay analysis on disk-backed PCM buffers."""
        self._log(analyze_message)
        self._set_progress(progress)
        analysis_started = time.perf_counter()
        result = self._get_analyzer().calculate_delay_from_pcm_files(
            prepared.src_rate,
            prepared.src_pcm_path,
            prepared.sync_pcm_path,
            sync_rate=prepared.sync_rate,
            skip_intro_sec=skip_sec,
            total_segments=segment_count,
        )
        self._log_timing(analyze_message, analysis_started)
        self._check_cancelled()
        return result

    def _start_analyze(self) -> None:
        """Start analysis-only mode — no file modifications."""
        src = self._src_path
        sync = self._sync_path

        if not src or not sync:
            messagebox.showwarning("Audio Sync", t("analyze_no_files"))
            return

        if not os.path.isfile(src) or not os.path.isfile(sync):
            messagebox.showwarning("Audio Sync", t("analyze_no_files"))
            return

        try:
            FFmpegWrapper.check_availability()
        except OSError as e:
            messagebox.showerror("FFmpeg", str(e))
            return

        with self._processing_lock:
            if self._processing:
                return
            self._processing = True

        self._cancel_event.clear()
        self.analyze_btn.config(state="disabled", text=t("analyzing"))
        self._set_cancel_active(True)
        self.run_btn.config(state="disabled")
        self._clear_log()
        self._set_progress(0)

        threading.Thread(target=self._analyze_only, daemon=True).start()

    def _analyze_only(self) -> None:
        """Background thread: passive analysis only, no file modifications."""
        src = self._src_path
        sync = self._sync_path
        fps_tmp_path: str | None = None
        src_pcm_path: str | None = None
        sync_pcm_path: str | None = None

        try:
            self._log(t("analyze_started"))
            self._set_progress(5)
            fps_conversion = self._get_selected_fps_conversion() if self.fps_enabled_var.get() else None
            prepared = self._prepare_analysis(
                src,
                sync,
                force_48k=False,
                fps_conversion=fps_conversion,
                probe_message=t("analyze_probing"),
                decode_message=t("analyze_converting"),
                probe_progress=10,
                post_probe_progress=15,
                fps_progress=20,
                decode_start_progress=25,
                src_decoded_progress=40,
                sync_decoded_progress=55,
                fps_tmp_prefix="audiosync_analyze_fps_",
                detail_logger=lambda src_info, sync_info, _output_sr: (
                    self._log(t(
                        "analyze_src_info",
                        channels=src_info.channels,
                        bits=src_info.bits,
                        sample_rate=src_info.sample_rate,
                    )),
                    self._log(t(
                        "analyze_sync_info",
                        channels=sync_info.channels,
                        bits=sync_info.bits,
                        sample_rate=sync_info.sample_rate,
                    )),
                ),
            )
            fps_tmp_path = prepared.fps_tmp_path
            src_pcm_path = prepared.src_pcm_path
            sync_pcm_path = prepared.sync_pcm_path

            skip_sec = parse_float(
                self.skip_intro_var.get(), default=120.0, minimum=0.0, maximum=3600.0,
            )
            segment_count = parse_int(
                self.segment_count_var.get(), default=12, minimum=4, maximum=40,
            )

            result = self._calculate_delay_result(
                prepared,
                skip_sec=skip_sec,
                segment_count=segment_count,
                analyze_message=t("analyze_calculating"),
                progress=60,
            )
            self._set_progress(85)
            self._check_cancelled()

            self._log("")
            self._log(t("analyze_result_header"))
            self._log("")

            abs_ms = abs(result.delay_ms)
            hours = int(abs_ms // 3600000)
            minutes = int((abs_ms % 3600000) // 60000)
            seconds = int((abs_ms % 60000) // 1000)
            millis = int(abs_ms % 1000)
            time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"
            self._log(t("sync_point_time", time=time_str))

            description = self._get_analyzer().describe_offset(result.delay_ms)
            self._log(t("delay_amount", delay_ms=result.delay_ms, description=description))

            if result.confidence >= 8.0:
                conf_level = t("confidence_high")
            elif result.confidence >= 4.0:
                conf_level = t("confidence_medium")
            else:
                conf_level = t("confidence_low")
            self._log(t("confidence_score", confidence=result.confidence) + f" ({conf_level})")

            if result.drift_ms_per_min is not None:
                self._log(t("drift_amount", drift=result.drift_ms_per_min))
            else:
                self._log(t("drift_none"))

            # Worth saying even when the drift could not be measured — that is
            # exactly the case a large frame-rate mismatch produces.
            suspected = SyncPipeline.suspected_fps_conversion(result)
            if suspected is not None and not self.fps_enabled_var.get():
                self._log(t("drift_looks_like_fps", name=suspected.display_name))

            # Analyze-only has to show the regions too, otherwise the single
            # headline delay looks wrong to anyone whose file actually steps.
            if result.has_step_discontinuity:
                self._log(
                    t(
                        "steps_found",
                        count=len(result.offset_regions),
                        span=result.step_span_ms,
                    )
                )
                for region in result.offset_regions:
                    start, end = region.bounds_in_minutes(t("steps_region_end"))
                    self._log(
                        t(
                            "steps_region",
                            start=start,
                            end=end,
                            lag=region.lag_ms,
                            windows=region.window_count,
                        )
                    )

            self._log(t("coarse_delay", coarse_ms=result.coarse_ms))
            self._log(t("segments_used", used=result.used_segments, total=result.total_segments))

            self._log("")
            self._log(t("analyze_result_header"))
            self._log("")

            self.schedule(lambda: self._display_analysis_result(result))

            self._set_progress(100)
            self._log(t("analyze_complete"))

        except OperationCancelledError:
            self._log(t("log_cancelled"))
        except Exception as e:
            self._log(f"❌ Error: {e}")
            import traceback
            self._log(traceback.format_exc())
        finally:
            for tmp_path in (fps_tmp_path, src_pcm_path, sync_pcm_path):
                if tmp_path and os.path.isfile(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass

            def _restore() -> None:
                with self._processing_lock:
                    self._processing = False
                self._cancel_event.clear()
                self.analyze_btn.config(state="normal", text=t("analyze_only"))
                self._set_cancel_active(False)
                self.run_btn.config(state="normal", text=t("start_sync"))

            self.schedule(_restore)

    def _start(self) -> None:
        """Senkronizasyon işlemini başlatır."""
        with self._processing_lock:
            if self._processing:
                return
            self._processing = True

        if not self._src_path or not self._sync_path:
            messagebox.showwarning(t("missing_file_title"), t("missing_file_msg"))
            self._reset_processing()
            return

        try:
            validate_file(self._src_path, t("source_audio"))
            validate_file(self._sync_path, t("sync_audio"))
        except (FileNotFoundError, PermissionError, ValueError) as e:
            messagebox.showerror(t("file_error_title"), str(e))
            self._reset_processing()
            return

        # External tool checks each start a process, so run them off the event
        # loop and resume on the main thread once they answer.
        pipeline = self._encoding_pipeline_var.get()
        self.run_btn.config(state="disabled", text=t("checking_tools"))
        self.analyze_btn.config(state="disabled")
        threading.Thread(
            target=self._preflight_tools,
            args=(pipeline,),
            daemon=True,
        ).start()

    def _preflight_tools(self, pipeline: str) -> None:
        """Worker thread: verify every external tool the run will need."""
        try:
            FFmpegWrapper.check_availability()
        except OSError as exc:
            self._fail_preflight(t("ffmpeg_not_found_title"), str(exc))
            return

        if pipeline == EncodingPipeline.DEEW.value:
            try:
                resolve_deew_backend()
            except OSError as exc:
                self._fail_preflight(t("deew_not_found_title"), str(exc))
                return

        if pipeline == EncodingPipeline.QAAC.value:
            ok, detail = QaacEncoder.check_availability()
            if not ok:
                self._fail_preflight("qaac", detail)
                return

        self.schedule(self._continue_start)

    def _fail_preflight(self, title: str, message: str) -> None:
        """Report a failed tool check and hand the buttons back."""
        def _show() -> None:
            self._reset_processing()
            self.run_btn.config(state="normal", text=t("start_sync"))
            self.analyze_btn.config(state="normal", text=t("analyze_only"))
            messagebox.showerror(title, message)

        self.schedule(_show)

    def _continue_start(self) -> None:
        """Main thread: collect settings, ask for the output path, then run."""
        deew_enabled = (self._encoding_pipeline_var.get() == EncodingPipeline.DEEW.value)
        pipeline = self._encoding_pipeline_var.get()
        ffmpeg_format = self._get_selected_ffmpeg_format()
        ffmpeg_lossy_default = (
            FFMPEG_EAC3_DEFAULT_BITRATE
            if ffmpeg_format == FFmpegOutputFormat.EAC3
            else FFMPEG_AC3_DEFAULT_BITRATE
        )
        ffmpeg_downmix = self._get_selected_ffmpeg_downmix()

        # ── Capture encoding params on main thread (thread-safe) ──
        encoding_params: dict = {
            "pipeline": pipeline,
            "ffmpeg_format": ffmpeg_format.codec,
            "ffmpeg_aac_bitrate": parse_int(
                self._ffmpeg_aac_bitrate_var.get(), default=256, minimum=32, maximum=512,
            ),
            "ffmpeg_flac_compression": parse_int(
                self._ffmpeg_flac_compression_var.get(), default=5, minimum=0, maximum=12,
            ),
            "ffmpeg_flac_bit_depth": parse_int(
                self._ffmpeg_flac_bit_depth_var.get(), default=24, minimum=16, maximum=24,
            ),
            "ffmpeg_opus_bitrate": parse_int(
                self._ffmpeg_opus_bitrate_var.get(), default=128, minimum=6, maximum=512,
            ),
            "ffmpeg_ac3eac3_bitrate": parse_int(
                self._ffmpeg_ac3eac3_bitrate_var.get(),
                default=ffmpeg_lossy_default,
                minimum=64,
                maximum=1024,
            ),
            "ffmpeg_downmix_channels": ffmpeg_downmix.channels if ffmpeg_downmix else None,
            "qaac_mode": self._qaac_mode_var.get(),
            "qaac_tvbr_quality": parse_int(
                self._qaac_tvbr_quality_var.get(), default=91, minimum=0, maximum=127,
            ),
            "qaac_cvbr_bitrate": parse_int(
                self._qaac_cvbr_bitrate_var.get(), default=256, minimum=32, maximum=512,
            ),
            "qaac_abr_bitrate": parse_int(
                self._qaac_abr_bitrate_var.get(), default=256, minimum=32, maximum=512,
            ),
            "qaac_cbr_bitrate": parse_int(
                self._qaac_cbr_bitrate_var.get(), default=256, minimum=32, maximum=512,
            ),
            "qaac_he_aac": self._qaac_he_aac_var.get(),
            "qaac_no_delay": self._qaac_no_delay_var.get(),
        }

        if deew_enabled:
            fmt = self._get_selected_format()
            ext = fmt.extension
            ext_label = fmt.display_name
            filetypes = [(ext_label, f"*{ext}"), ("WAV", "*.wav")]
        elif pipeline == EncodingPipeline.FFMPEG.value:
            if ffmpeg_format == FFmpegOutputFormat.AAC:
                ext = ".m4a"
                filetypes = [("AAC/M4A", "*.m4a"), ("WAV", "*.wav")]
            elif ffmpeg_format == FFmpegOutputFormat.FLAC:
                ext = ".flac"
                filetypes = [("FLAC", "*.flac"), ("WAV", "*.wav")]
            elif ffmpeg_format == FFmpegOutputFormat.OPUS:
                ext = ".opus"
                filetypes = [("Opus", "*.opus"), ("WAV", "*.wav")]
            elif ffmpeg_format == FFmpegOutputFormat.AC3:
                ext = ".ac3"
                filetypes = [("AC3", "*.ac3"), ("WAV", "*.wav")]
            elif ffmpeg_format == FFmpegOutputFormat.EAC3:
                ext = ".eac3"
                filetypes = [("E-AC3", "*.eac3"), ("EC3", "*.ec3"), ("WAV", "*.wav")]
            else:
                ext = ".wav"
                filetypes = [("WAV", "*.wav")]
        elif pipeline == EncodingPipeline.QAAC.value:
            ext = ".m4a"
            filetypes = [("AAC/M4A", "*.m4a"), ("WAV", "*.wav")]
        else:
            ext = ".wav"
            filetypes = [("WAV", "*.wav")]

        out_path = filedialog.asksaveasfilename(
            defaultextension=ext,
            filetypes=filetypes,
            title=t("save_output_title"),
        )
        if not out_path:
            self._reset_processing()
            self.run_btn.config(state="normal", text=t("start_sync"))
            self.analyze_btn.config(state="normal", text=t("analyze_only"))
            return

        skip_sec = parse_float(self.skip_intro_var.get(), default=120.0, minimum=0.0, maximum=3600.0)
        segment_count = parse_int(self.segment_count_var.get(), default=12, minimum=4, maximum=40)
        force_48k = bool(self.force_48k_var.get())

        fps_conversion: FpsConversion | None = None
        if self.fps_enabled_var.get():
            fps_conversion = self._get_selected_fps_conversion()

        sync_mode = self._get_selected_sync_mode()

        deew_params: dict | None = None
        if deew_enabled:
            deew_params = {
                "format": self._get_selected_format(),
                "bitrate": self._get_deew_bitrate(),
                "downmix": self._get_selected_downmix(),
                "drc": self._get_selected_drc(),
                "dialnorm": parse_int(
                    self.deew_dialnorm_var.get(), default=0, minimum=-31, maximum=0,
                ),
                "delete_wav": self.deew_delete_wav_var.get(),
            }

        src_path = self._src_path
        sync_path = self._sync_path

        self._cancel_event.clear()
        self.analyze_btn.config(state="disabled")
        self._set_cancel_active(True)
        self.run_btn.config(state="disabled", text=t("processing"))
        self._set_progress(0)

        # Keyword arguments, not a positional tuple: the list has grown to a
        # dozen entries and a mis-ordered tuple would silently pass the wrong
        # value rather than fail.
        threading.Thread(
            target=self._process,
            kwargs={
                "src_path": src_path,
                "sync_path": sync_path,
                "out_path": out_path,
                "skip_sec": skip_sec,
                "segment_count": segment_count,
                "force_48k": force_48k,
                "fps_conversion": fps_conversion,
                "deew_params": deew_params,
                "sync_mode": sync_mode,
                "encoding_params": encoding_params,
                "correct_drift": self.correct_drift_var.get(),
                "correct_steps": self.correct_steps_var.get(),
                "auto_fps": self.fps_auto_var.get(),
            },
            daemon=True,
        ).start()

    def _get_deew_bitrate(self) -> int | None:
        br_str = self.deew_bitrate_var.get().strip()
        if not br_str or not br_str.isdigit():
            return None
        return int(br_str)

    def _process(
        self,
        src_path: str,
        sync_path: str,
        out_path: str,
        skip_sec: float,
        segment_count: int,
        force_48k: bool,
        fps_conversion: FpsConversion | None = None,
        deew_params: dict | None = None,
        sync_mode: SyncMode = SyncMode.ADELAY_AMIX,
        encoding_params: dict | None = None,
        correct_drift: bool = True,
        correct_steps: bool = True,
        auto_fps: bool = True,
    ) -> None:
        """Run the typed, atomic synchronization pipeline on a worker thread."""
        enc = encoding_params or {}
        try:
            pipeline = EncodingPipeline(
                enc.get("pipeline", EncodingPipeline.NONE.value)
            )
            ffmpeg_format_value = enc.get(
                "ffmpeg_format",
                FFmpegOutputFormat.AAC.codec,
            )
            ffmpeg_format = next(
                (
                    candidate
                    for candidate in FFmpegOutputFormat
                    if candidate.codec == ffmpeg_format_value
                ),
                FFmpegOutputFormat.AAC,
            )
            encoding = EncodingRequest(
                pipeline=pipeline,
                ffmpeg=FFmpegEncodeConfig(
                    format=ffmpeg_format,
                    aac_bitrate=enc.get("ffmpeg_aac_bitrate", 256),
                    flac_compression=enc.get("ffmpeg_flac_compression", 5),
                    flac_bit_depth=enc.get("ffmpeg_flac_bit_depth", 24),
                    opus_bitrate=enc.get("ffmpeg_opus_bitrate", 128),
                    ac3_bitrate=enc.get(
                        "ffmpeg_ac3eac3_bitrate",
                        FFMPEG_AC3_DEFAULT_BITRATE,
                    ),
                    eac3_bitrate=enc.get(
                        "ffmpeg_ac3eac3_bitrate",
                        FFMPEG_EAC3_DEFAULT_BITRATE,
                    ),
                ),
                qaac=QaacConfig(
                    mode=next(
                        (
                            candidate
                            for candidate in QaacMode
                            if candidate.flag == enc.get("qaac_mode")
                        ),
                        QaacMode.TVBR,
                    ),
                    tvbr_quality=enc.get("qaac_tvbr_quality", 91),
                    cvbr_bitrate=enc.get("qaac_cvbr_bitrate", 256),
                    abr_bitrate=enc.get("qaac_abr_bitrate", 256),
                    cbr_bitrate=enc.get("qaac_cbr_bitrate", 256),
                    he_aac=enc.get("qaac_he_aac", False),
                    no_delay=enc.get("qaac_no_delay", True),
                ),
                deew=DeewConfig(
                    enabled=deew_params is not None,
                    format=(
                        deew_params["format"]
                        if deew_params is not None
                        else DeewFormat.DDP
                    ),
                    bitrate=(
                        deew_params["bitrate"]
                        if deew_params is not None
                        else None
                    ),
                    downmix=(
                        deew_params["downmix"]
                        if deew_params is not None
                        else None
                    ),
                    drc=(
                        deew_params["drc"]
                        if deew_params is not None
                        else DeewDRC.MUSIC_LIGHT
                    ),
                    dialnorm=(
                        deew_params["dialnorm"]
                        if deew_params is not None
                        else 0
                    ),
                    delete_intermediate_wav=(
                        deew_params["delete_wav"]
                        if deew_params is not None
                        else True
                    ),
                ),
                ffmpeg_channels=enc.get("ffmpeg_downmix_channels"),
            )
            request = SyncRequest(
                source_path=src_path,
                sync_path=sync_path,
                output_path=out_path,
                skip_intro_sec=skip_sec,
                total_segments=segment_count,
                force_48k=force_48k,
                fps_conversion=fps_conversion,
                sync_mode=sync_mode,
                encoding=encoding,
                correct_drift=correct_drift,
                correct_steps=correct_steps,
                auto_fps_conversion=auto_fps,
            )
            outcome = self._pipeline.run(
                request,
                cancel_event=self._cancel_event,
                on_log=self._log,
                on_progress=self._set_progress,
            )

            self._delay_ms = outcome.analysis.delay_ms
            self._update_info_panel(
                outcome.sync_info,
                outcome.output_sample_rate,
            )
            self._display_analysis_result(outcome.analysis)
            self._log(t("log_command", cmd=outcome.sync_summary))
            if outcome.encoding_summary:
                self._log(
                    t(
                        "encoding_complete",
                        summary=outcome.encoding_summary,
                    )
                )
            self.schedule(
                lambda: messagebox.showinfo(
                    t("success_title"),
                    t("file_saved_msg", path=outcome.output_path),
                ),
            )
        except OperationCancelledError:
            self._log(t("log_cancelled"))
        except EncodingError as exc:
            self._log(t("log_error", err=exc))
            if exc.fallback_path:
                self._log(
                    t(
                        "log_wav_preserved",
                        name=os.path.basename(exc.fallback_path),
                    )
                )
            self.schedule(
                lambda err=str(exc): messagebox.showerror(t("error_title"), err),
            )
        except Exception as exc:
            self._log(t("log_error", err=exc))
            self.schedule(
                lambda err=str(exc): messagebox.showerror(t("error_title"), err),
            )
        finally:
            with self._processing_lock:
                self._processing = False

            def _restore_buttons() -> None:
                self._cancel_event.clear()
                self.analyze_btn.config(state="normal", text=t("analyze_only"))
                self._set_cancel_active(False)
                self.run_btn.config(state="normal", text=t("start_sync"))

            self.schedule(_restore_buttons)

    def _reset_processing(self) -> None:
        with self._processing_lock:
            self._processing = False
        self._cancel_event.clear()
        self.schedule(lambda: self._set_cancel_active(False))

    # ── Bilgi Gösterimi ──────────────────────────────────────────────────

    def _update_info_panel(self, sync_info: AudioInfo, output_sr: OutputSampleRate) -> None:
        self.schedule(lambda: self.ch_val.config(text=t("channel_info", ch=sync_info.channels)))
        self.schedule(lambda: self.bit_val.config(
            text=f"{sync_info.bits}-bit  →  {sync_info.codec.codec_name}",
        ))
        self.schedule(lambda: self.sr_val.config(text=output_sr.label))

    def _log_audio_info(
        self,
        src_info: AudioInfo,
        sync_info: AudioInfo,
        output_sr: OutputSampleRate,
        skip_sec: float,
        segment_count: int,
    ) -> None:
        self._log(t("log_src_sr", src_sr=src_info.sample_rate, sync_sr=sync_info.sample_rate))
        self._log(t("log_output_info", ch=sync_info.channels, bits=sync_info.bits, codec=sync_info.codec.codec_name))
        self._log(t("log_output_sr", label=output_sr.label))
        self._log(t("log_detection_params", skip=skip_sec, segments=segment_count))

    def _display_analysis_result(self, result: AnalysisResult) -> None:
        if result.delay_ms >= 0:
            relation = t("sync_ahead")
        else:
            relation = t("sync_behind")
        label_color = THEME.accent if result.delay_ms >= 0 else THEME.accent2

        # Güven skoru korelasyon tepesinin gürültü tabanına oranıdır; kullanıcı
        # bu ölçeği bilmek zorunda kalmasın diye sözle nitelendirilir.  Ayrıca
        # pencereler birbirinden çok ayrışıyorsa skor yüksek olsa bile sonuç
        # dosyanın tamamı için geçerli değildir — bu, skoru geçersiz kılar.
        scattered = result.windows_disagree_ms >= self._config.window_disagreement_warn_ms
        if scattered or result.confidence < 2.0:
            quality, quality_colour = t("confidence_weak"), THEME.err
        elif result.confidence >= 4.0:
            quality, quality_colour = t("confidence_strong"), THEME.ok
        else:
            quality, quality_colour = t("confidence_fair"), THEME.warn

        detail = t(
            "readout_detail",
            relation=relation,
            quality=quality,
            used=result.used_segments,
            total=result.total_segments,
        )
        if result.has_step_discontinuity:
            detail += t(
                "readout_steps",
                count=len(result.offset_regions),
                span=result.step_span_ms,
            )
        elif result.drift_ms_per_min is not None and abs(result.drift_ms_per_min) >= 1.0:
            detail += t("readout_drift", drift=result.drift_ms_per_min)

        if scattered:
            detail += t("readout_scattered", spread=result.windows_disagree_ms)

        self.schedule(
            lambda: self._show_readout(
                result.delay_ms,
                detail=detail,
                colour=label_color if result.confidence >= 2.0 else quality_colour,
            ),
        )

        self._log(t("log_coarse_delay", ms=result.coarse_ms))
        self._log(t("log_validation",
            used=result.used_segments,
            total=result.total_segments,
            conf=result.confidence,
        ))

        if result.skip_fallback:
            self._log(t("log_skip_fallback"))

        if result.drift_ms_per_min is not None:
            self._log(t("log_drift", drift=result.drift_ms_per_min))
            if abs(result.drift_ms_per_min) >= self._config.drift_warning_threshold:
                self._log(t("log_drift_warning"))

        self._log(t("log_final_delay", ms=result.delay_ms, relation=relation))

    # ── UI Yardımcıları ──────────────────────────────────────────────────

    def _log(self, msg: str) -> None:
        def _write() -> None:
            self.log_box.config(state="normal")
            self.log_box.insert("end", f"› {msg}\n")
            self.log_box.see("end")
            self.log_box.config(state="disabled")

        self.schedule(_write)
        # The newest log line doubles as the current-stage caption.
        if msg.strip():
            self._set_status(msg.strip())

    def _set_status(self, text: str) -> None:
        """Show the current stage next to the progress bar."""
        caption = text if len(text) <= 56 else f"{text[:55]}…"

        def _write() -> None:
            self._status_lbl.config(text=caption)

        self.schedule(_write)

    def _set_progress(self, pct: int) -> None:
        pct = max(0, min(100, int(pct)))

        def _draw() -> None:
            w = self.progress_canvas.winfo_width()
            x = int(w * pct / 100)
            self.progress_canvas.coords(self._progress_bar, 0, 0, x, 4)
            # "%100" is the Turkish form; it was hard-coded and leaked into the
            # English UI. The i18n table decides which side the sign goes on.
            self._percent_lbl.config(text=t("percent", pct=pct) if pct else "")

        self.schedule(_draw)

    def _fit_to_content(self) -> None:
        """Refresh the scroll region and, on first layout, size the window.

        The initial size is derived from what the content actually needs rather
        than hard-coded, then clamped to the work area.  v2.3 opened at a fixed
        800×800 regardless of the 1262 px of content behind it, so the primary
        action sat below the fold on every screen.
        """
        self.update_idletasks()
        if not hasattr(self, "_canvas"):
            return

        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

        if getattr(self, "_initial_size_applied", False):
            return
        self._initial_size_applied = True

        content_w = self._content.winfo_reqwidth()
        content_h = self._content.winfo_reqheight()
        chrome_h = self._bottom_bar.winfo_reqheight()

        # Leave room for the taskbar and window frame; a window that opens
        # partly off-screen is worse than one that opens slightly small.
        # Past ~1100 px the two columns just grow whitespace, so cap the width
        # rather than letting a 4K display stretch the layout across the desk.
        max_w = min(1100, int(self.winfo_screenwidth() * 0.94))
        max_h = int(self.winfo_screenheight() * 0.88)

        width = max(self.minsize()[0], min(content_w + 24, max_w))
        height = max(self.minsize()[1], min(content_h + chrome_h + 16, max_h))

        x = max(0, (self.winfo_screenwidth() - width) // 2)
        y = max(0, (self.winfo_screenheight() - height) // 3)
        self.geometry(f"{width}x{height}+{x}+{y}")
