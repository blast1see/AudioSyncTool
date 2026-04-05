"""Main application window — UI coordination only.

Business logic resides in ``core.analyzer`` and ``core.ffmpeg_wrapper``,
utility functions in ``utils``.
"""

from __future__ import annotations

import os
import shutil
import tempfile as _tempfile_mod
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

from audio_sync.config import (
    THEME, FONTS, SYNC_CONFIG, SyncConfig, SyncMode,
    DeewFormat, DeewDownmix, DeewDRC,
    DEEW_COMMON_BITRATES, DEEW_DEFAULT_BITRATES,
    get_deew_bitrate_key,
    FpsConversion,
    EncoderType,
    FFMPEG_AC3_BITRATES, FFMPEG_EAC3_BITRATES,
    FFMPEG_AC3_DEFAULT_BITRATE, FFMPEG_EAC3_DEFAULT_BITRATE,
    CONTAINER_EXTENSIONS,
    CODEC_EXTENSION_MAP,
    EncodingPipeline,
    FFmpegOutputFormat,
    FFmpegEncodeConfig,
    QaacMode,
    QaacConfig,
    ToolPaths,
    save_tool_paths,
    TOOL_PATHS,
    resolve_tool,
)
from audio_sync.core.analyzer import AudioAnalyzer
from audio_sync.core.deew_encoder import DeewEncoder, encode_wav_to_dolby
from audio_sync.core.encoder import QaacEncoder
from audio_sync.core.ffmpeg_wrapper import FFmpegWrapper
from audio_sync.core.models import AnalysisResult, AudioInfo, OutputSampleRate, ProgressCallback
from audio_sync.i18n import Language, I18n, get_i18n, t
from audio_sync.ui.drop_zone import DropZone, is_dnd_available
from audio_sync.ui.stream_dialog import ask_stream_selection
from audio_sync.utils import parse_float, parse_int, validate_file, temporary_wav_files

# Try to use tkinterdnd2 for drag & drop support
_TkBase: type = tk.Tk
try:
    from tkinterdnd2 import TkinterDnD
    _TkBase = TkinterDnD.Tk  # type: ignore[assignment]
except ImportError:
    pass


class AudioSyncApp(_TkBase):  # type: ignore[misc]
    """Audio Sync Tool main window.

    Uses tkinterdnd2.TkinterDnD.Tk as base when available for drag & drop,
    otherwise falls back to standard tk.Tk.
    """

    def __init__(
        self,
        config: SyncConfig = SYNC_CONFIG,
        ffmpeg: FFmpegWrapper | None = None,
        analyzer: AudioAnalyzer | None = None,
    ) -> None:
        super().__init__()
        self.title("Audio Sync Tool")
        self.geometry("800x800")
        self.resizable(True, True)
        self.minsize(700, 700)
        self.configure(bg=THEME.bg)

        # i18n
        self._i18n = get_i18n()

        # Bağımlılıklar (Dependency Injection)
        self._config = config
        self._ffmpeg = ffmpeg or FFmpegWrapper(config=config)
        self._analyzer = analyzer or AudioAnalyzer(config=config)

        # Durum
        self._src_path: str = ""
        self._sync_path: str = ""
        self._delay_ms: float | None = None
        self._processing: bool = False
        self._processing_lock = threading.Lock()

        # Kullanıcı ayarları
        self.skip_intro_var = tk.StringVar(value="120")
        self.segment_count_var = tk.StringVar(value="12")
        self.force_48k_var = tk.BooleanVar(value=False)

        # Senkronizasyon modu
        self.sync_mode_var = tk.StringVar(value=SyncMode.ADELAY_AMIX.display_name)

        # FPS dönüşüm ayarları
        self.fps_enabled_var = tk.BooleanVar(value=False)
        self.fps_conversion_var = tk.StringVar(value=FpsConversion.FPS_25_TO_23976.display_name)

        # Dolby encoding ayarları
        self.deew_enabled_var = tk.BooleanVar(value=False)
        self.encoder_type_var = tk.StringVar(value=EncoderType.FFMPEG.cli_value)
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
        """Ana arayüzü oluşturur — alt metotlara delege eder."""
        # Alt çubuk (ilerleme + buton) her zaman görünür — kaydırma alanının dışında
        self._build_bottom_bar()
        # Kaydırılabilir içerik alanı
        self._build_scrollable_container()
        self._build_header()
        self._build_drop_zones()
        self._build_options_panel()
        self._build_sync_mode_panel()
        self._build_fps_panel()
        self._build_encoding_panel()
        self._build_info_panel()
        self._build_log_panel()
        self.after(50, self._fit_to_content)

    def _build_scrollable_container(self) -> None:
        """Kaydırılabilir ana kapsayıcıyı oluşturur."""
        self._canvas = tk.Canvas(
            self, bg=THEME.bg, highlightthickness=0, bd=0,
        )
        self._scrollbar = tk.Scrollbar(
            self, orient="vertical", command=self._canvas.yview,
            bg=THEME.border, troughcolor=THEME.bg,
            activebackground=THEME.muted, highlightthickness=0,
            bd=0, width=10,
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

    def _on_mousewheel(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_mousewheel_linux(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        if event.num == 4:
            self._canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self._canvas.yview_scroll(1, "units")

    def _build_header(self) -> None:
        """Başlık bölümünü oluşturur — dil seçimi dahil."""
        hdr = tk.Frame(self._content, bg=THEME.bg)
        hdr.pack(fill="x", padx=30, pady=(28, 6))

        # Sol: Başlık
        title_frame = tk.Frame(hdr, bg=THEME.bg)
        title_frame.pack(side="left")
        tk.Label(
            title_frame, text="AUDIO", font=FONTS.header, fg=THEME.accent, bg=THEME.bg,
        ).pack(side="left")
        tk.Label(
            title_frame, text="SYNC", font=FONTS.header, fg=THEME.accent2, bg=THEME.bg,
        ).pack(side="left")

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

        self._subtitle_lbl = tk.Label(
            self._content,
            text=t("app_subtitle"),
            font=FONTS.small,
            fg=THEME.muted,
            bg=THEME.bg,
        )
        self._subtitle_lbl.pack()

        tk.Frame(self._content, bg=THEME.border, height=1).pack(fill="x", padx=30, pady=18)

    def _build_drop_zones(self) -> None:
        """Dosya seçim alanlarını oluşturur."""
        self.zone_src = DropZone(
            self._content, t("source_audio"), THEME.accent, self._on_src_pick,
        )
        self.zone_src.pack(fill="x", padx=30, pady=(0, 12))

        self.zone_sync = DropZone(
            self._content, t("sync_audio"), THEME.accent2, self._on_sync_pick,
        )
        self.zone_sync.pack(fill="x", padx=30, pady=(0, 12))

    def _build_options_panel(self) -> None:
        """Tespit ayarları panelini oluşturur."""
        options = tk.Frame(
            self._content, bg=THEME.card,
            highlightbackground=THEME.border, highlightthickness=1,
        )
        options.pack(fill="x", padx=30, pady=(0, 14))

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

        # 48 kHz zorla
        self._force_48k_cb = tk.Checkbutton(
            options,
            text=t("force_48k"),
            variable=self.force_48k_var,
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
        self._force_48k_cb.pack(fill="x", padx=14, pady=(0, 8))

        self._force_48k_note_lbl = tk.Label(
            options,
            text=t("force_48k_note"),
            font=FONTS.small,
            fg=THEME.muted,
            bg=THEME.card,
            anchor="w",
            justify="left",
        )
        self._force_48k_note_lbl.pack(fill="x", padx=14, pady=(0, 10))

    def _build_sync_mode_panel(self) -> None:
        """Senkronizasyon modu seçim panelini oluşturur."""
        self._sync_mode_frame = tk.Frame(
            self._content, bg=THEME.card,
            highlightbackground=THEME.border, highlightthickness=1,
        )
        self._sync_mode_frame.pack(fill="x", padx=30, pady=(0, 14))

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

        self._sync_mode_menu = tk.OptionMenu(
            mode_row,
            self.sync_mode_var,
            *[sm.display_name for sm in SyncMode],
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

    def _build_fps_panel(self) -> None:
        """FPS dönüşüm ayarları panelini oluşturur."""
        self._fps_frame = tk.Frame(
            self._content, bg=THEME.card,
            highlightbackground=THEME.border, highlightthickness=1,
        )
        self._fps_frame.pack(fill="x", padx=30, pady=(0, 14))

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
        self._fps_enable_cb.pack(fill="x", padx=14, pady=(0, 6))

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
        """Build Dolby encoding settings into the given parent frame."""
        # DEE status indicator
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
        enc_row = tk.Frame(self._deew_settings_frame, bg=THEME.card)
        enc_row.pack(fill="x", pady=(0, 6))
        self._enc_label = tk.Label(
            enc_row, text=t("encoder_label"), font=FONTS.small,
            fg=THEME.text, bg=THEME.card,
        )
        self._enc_label.pack(side="left")

        self._enc_menu = tk.OptionMenu(
            enc_row,
            self.encoder_type_var,
            *[e.cli_value for e in EncoderType],
        )
        self._enc_menu.config(
            bg=THEME.input_bg, fg=THEME.text, font=FONTS.small,
            activebackground=THEME.card, activeforeground=THEME.text,
            highlightthickness=0, relief="flat", width=12,
        )
        self._enc_menu["menu"].config(
            bg=THEME.input_bg, fg=THEME.text, font=FONTS.small,
            activebackground=THEME.accent, activeforeground=THEME.bg,
        )
        self._enc_menu.pack(side="right")

        self._enc_desc_lbl = tk.Label(
            self._deew_settings_frame, text="", font=FONTS.small,
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

        # DEE-only ayarlar
        self._dee_only_frame = tk.Frame(self._deew_settings_frame, bg=THEME.card)
        self._dee_only_frame.pack(fill="x")

        drc_row = tk.Frame(self._dee_only_frame, bg=THEME.card)
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

        dn_row = tk.Frame(self._dee_only_frame, bg=THEME.card)
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
            text="",
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
        self.encoder_type_var.trace_add("write", self._on_encoder_type_change)

        self._update_channel_options()
        self._update_bitrate_options()
        self._update_format_description()
        self._update_encoder_ui()

    def _build_encoding_panel(self) -> None:
        """Build the unified encoding pipeline panel."""
        # Main card
        card = tk.Frame(
            self._content, bg=THEME.card,
            highlightbackground=THEME.border, highlightthickness=1,
        )
        card.pack(fill="x", padx=30, pady=(0, 14))

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
            (EncodingPipeline.DOLBY.value, t("encoding_dolby")),
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

        # ── Dolby sub-panel ──
        self._dolby_enc_frame = tk.Frame(card, bg=THEME.card)
        self._build_deew_panel(self._dolby_enc_frame)

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
        self._dolby_enc_frame.pack_forget()

        if value == EncodingPipeline.FFMPEG.value:
            self._ffmpeg_enc_frame.pack(fill="x", pady=(0, 4))
            self._on_ffmpeg_format_change(self._ffmpeg_format_var.get())
        elif value == EncodingPipeline.QAAC.value:
            self._qaac_enc_frame.pack(fill="x", pady=(0, 4))
            self._on_qaac_mode_change(self._qaac_mode_var.get())
        elif value == EncodingPipeline.DOLBY.value:
            self._dolby_enc_frame.pack(fill="x", pady=(0, 4))

        self.after(50, self._fit_to_content)

    def _on_ffmpeg_format_change(self, value: str) -> None:
        """Show/hide FFmpeg format-specific fields."""
        self._ffmpeg_aac_frame.pack_forget()
        self._ffmpeg_flac_frame.pack_forget()
        self._ffmpeg_flac_bd_frame.pack_forget()
        self._ffmpeg_opus_frame.pack_forget()

        if value == FFmpegOutputFormat.AAC.codec:
            self._ffmpeg_aac_frame.pack(fill="x", padx=14, pady=(0, 4))
        elif value == FFmpegOutputFormat.FLAC.codec:
            self._ffmpeg_flac_frame.pack(fill="x", padx=14, pady=(0, 4))
            self._ffmpeg_flac_bd_frame.pack(fill="x", padx=14, pady=(0, 4))
        elif value == FFmpegOutputFormat.OPUS.codec:
            self._ffmpeg_opus_frame.pack(fill="x", padx=14, pady=(0, 4))

        self.after(50, self._fit_to_content)

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

        self.after(50, self._fit_to_content)

    def _build_info_panel(self) -> None:
        """Bilgi panelini oluşturur."""
        info_frame = tk.Frame(
            self._content, bg=THEME.card,
            highlightbackground=THEME.border, highlightthickness=1,
        )
        info_frame.pack(fill="x", padx=30, pady=(0, 14))

        rows = [
            ("detected_delay", "delay_val"),
            ("channel", "ch_val"),
            ("bit_depth", "bit_val"),
            ("output_sample_rate", "sr_val"),
        ]
        self._info_labels: list[tuple[tk.Label, str]] = []
        for i, (key, attr) in enumerate(rows):
            row = tk.Frame(info_frame, bg=THEME.card)
            row.pack(
                fill="x", padx=16,
                pady=(8 if i == 0 else 4, 8 if i == len(rows) - 1 else 4),
            )
            lbl_left = tk.Label(
                row, text=t(key), font=FONTS.small,
                fg=THEME.muted, bg=THEME.card,
            )
            lbl_left.pack(side="left")
            lbl = tk.Label(
                row, text="—", font=FONTS.info_value,
                fg=THEME.accent, bg=THEME.card,
            )
            lbl.pack(side="right")
            setattr(self, attr, lbl)
            self._info_labels.append((lbl_left, key))

    def _build_log_panel(self) -> None:
        """Log panelini oluşturur."""
        log_outer = tk.Frame(
            self._content, bg=THEME.card,
            highlightbackground=THEME.border, highlightthickness=1,
        )
        log_outer.pack(fill="x", padx=30, pady=(0, 14))
        self._log_title_lbl = tk.Label(
            log_outer, text=t("log_label"), font=FONTS.small,
            fg=THEME.muted, bg=THEME.card, anchor="w",
        )
        self._log_title_lbl.pack(fill="x", padx=12, pady=(8, 0))

        self.log_box = tk.Text(
            log_outer,
            height=6,
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
        self.log_box.pack(fill="x", padx=8, pady=(2, 10))

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
            self._bottom_bar, height=4, bg=THEME.border, highlightthickness=0,
        )
        self.progress_canvas.pack(fill="x", padx=30, pady=(8, 6))
        self._progress_bar = self.progress_canvas.create_rectangle(
            0, 0, 0, 4, fill=THEME.accent, outline="",
        )

        # Analiz butonu
        self.analyze_btn = tk.Button(
            self._bottom_bar,
            text=t("analyze_only"),
            font=FONTS.button,
            fg=THEME.bg,
            bg=THEME.accent2,
            activebackground=THEME.accent2,
            activeforeground=THEME.bg,
            relief="flat",
            padx=0,
            pady=12,
            cursor="hand2",
            command=self._start_analyze,
        )
        self.analyze_btn.pack(fill="x", padx=30, pady=(0, 6))

        # Çalıştır butonu
        self.run_btn = tk.Button(
            self._bottom_bar,
            text=t("start_sync"),
            font=FONTS.button,
            fg=THEME.bg,
            bg=THEME.accent,
            activebackground=THEME.accent,
            activeforeground=THEME.bg,
            relief="flat",
            padx=0,
            pady=12,
            cursor="hand2",
            command=self._start,
        )
        self.run_btn.pack(fill="x", padx=30, pady=(0, 12))

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
            ("deew", t("tool_path_dee")),
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
            _update_statuses()
            self._update_deew_status()
            if not ok:
                messagebox.showwarning(
                    t("tool_paths_title"),
                    "Failed to save tool paths to disk.",
                )

        btn_frame = tk.Frame(dialog, bg=THEME.bg)
        btn_frame.pack(fill="x", padx=20, pady=(8, 16))

        tk.Button(
            btn_frame, text=t("tool_paths_saved").replace(".", ""),
            font=FONTS.button, fg=THEME.bg, bg=THEME.accent,
            activebackground=THEME.accent, activeforeground=THEME.bg,
            relief="flat", padx=20, pady=8, cursor="hand2",
            command=_save,
        ).pack(side="right")

        tk.Button(
            btn_frame, text=t("cancel"),
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

        # Senkronizasyon modu
        self._sync_mode_title_lbl.config(text=t("sync_mode"))
        self._sync_mode_label.config(text=t("sync_mode_label"))
        self._sync_mode_note_lbl.config(text=t("sync_mode_note"))
        self._update_sync_mode_description()

        # FPS
        self._fps_title_lbl.config(text=t("fps_conversion"))
        self._fps_enable_cb.config(text=t("fps_enable"))
        self._fps_conv_lbl.config(text=t("fps_conversion_label"))
        self._fps_note_lbl.config(text=t("fps_note"))
        self._update_fps_ratio_label()

        # Dolby
        self._enc_label.config(text=t("encoder_label"))
        self._fmt_label.config(text=t("format_label"))
        self._ch_label.config(text=t("channel_layout"))
        self._br_label.config(text=t("bitrate_label"))
        self._drc_label.config(text=t("drc_profile"))
        self._dn_label.config(text=t("dialnorm_label"))
        self._delete_wav_cb.config(text=t("delete_intermediate_wav"))
        self._update_deew_status()
        self._update_encoder_ui()

        # Encoding panel
        self._encoding_title_lbl.config(text=t("encoding_pipeline"))
        self._encoding_pipeline_lbl.config(text=t("encoding_pipeline_label"))
        self._ffmpeg_format_lbl.config(text=t("encoding_format"))
        self._ffmpeg_aac_bitrate_lbl.config(text=t("aac_bitrate_label"))
        self._ffmpeg_flac_compression_lbl.config(text=t("ffmpeg_flac_compression_label"))
        self._ffmpeg_opus_bitrate_lbl.config(text=t("opus_bitrate_label"))
        self._qaac_mode_lbl.config(text=t("encoding_mode"))
        self._qaac_tvbr_quality_lbl.config(text=t("qaac_quality_label"))
        self._qaac_cvbr_bitrate_lbl.config(text=t("encoding_bitrate"))
        self._qaac_abr_bitrate_lbl.config(text=t("encoding_bitrate"))
        self._qaac_cbr_bitrate_lbl.config(text=t("encoding_bitrate"))
        self._qaac_he_aac_cb.config(text=t("encoding_he_aac"))
        self._qaac_no_delay_cb.config(text=t("encoding_no_delay"))
        self._ffmpeg_flac_bd_lbl.config(text=t("flac_bit_depth_label"))

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
            self.run_btn.config(text=t("start_sync"))

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
        if mode is not None:
            lang = self._i18n.language
            desc = mode.description_tr if lang == Language.TR else mode.description_en
            self._sync_mode_desc_lbl.config(text=f"  → {desc}")
        else:
            self._sync_mode_desc_lbl.config(text="")

    def _get_selected_sync_mode(self) -> SyncMode | None:
        """Seçili senkronizasyon modunu döndürür."""
        selected = self.sync_mode_var.get()
        for sm in SyncMode:
            if sm.display_name == selected:
                return sm
        return SyncMode.ADELAY_AMIX

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
        self.after(50, self._fit_to_content)

    def _on_fps_conversion_change(self, *_args: object) -> None:
        self._update_fps_ratio_label()

    def _update_fps_ratio_label(self) -> None:
        conversion = self._get_selected_fps_conversion()
        if conversion is not None:
            ratio = conversion.tempo_ratio
            atempo = 1.0 / ratio
            if atempo > 1.0:
                direction = t("fps_slowdown")
                pct = (atempo - 1.0) * 100.0
            else:
                direction = t("fps_speedup")
                pct = (1.0 - atempo) * 100.0
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
        dee_ok = DeewEncoder.is_available()
        if dee_ok:
            self._deew_status_lbl.config(text=t("dee_ready"), fg="#4ade80")
        else:
            self._deew_status_lbl.config(text=t("dee_not_installed"), fg=THEME.accent2)

    def _on_deew_toggle(self) -> None:
        """Legacy no-op — Dolby visibility is now controlled by the pipeline dropdown."""
        pass

    def _on_encoder_type_change(self, *_args: object) -> None:
        self._update_encoder_ui()
        self._update_bitrate_options()

    def _get_selected_encoder(self) -> EncoderType:
        enc_value = self.encoder_type_var.get()
        for e in EncoderType:
            if e.cli_value == enc_value:
                return e
        return EncoderType.FFMPEG

    def _update_encoder_ui(self) -> None:
        encoder = self._get_selected_encoder()
        is_dee = encoder == EncoderType.DEE

        if is_dee:
            self._dee_only_frame.pack(fill="x")
            self._enc_desc_lbl.config(text=t("dee_desc"))
            self._enc_note_lbl.config(text=t("dee_note"))
        else:
            self._dee_only_frame.pack_forget()
            self._enc_desc_lbl.config(text=t("ffmpeg_enc_desc"))
            self._enc_note_lbl.config(text=t("ffmpeg_enc_note"))

        self.after(50, self._fit_to_content)

    def _show_deew_settings(self, show: bool) -> None:
        """Legacy no-op — Dolby settings are always visible when the sub-panel is shown."""
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
        encoder = self._get_selected_encoder()

        if encoder == EncoderType.FFMPEG:
            if fmt == DeewFormat.DD:
                bitrates = FFMPEG_AC3_BITRATES
                default_br = FFMPEG_AC3_DEFAULT_BITRATE
            else:
                bitrates = FFMPEG_EAC3_BITRATES
                default_br = FFMPEG_EAC3_DEFAULT_BITRATE
        else:
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

    def _get_selected_format(self) -> DeewFormat:
        fmt_value = self.deew_format_var.get()
        for f in DeewFormat:
            if f.cli_value == fmt_value:
                return f
        return DeewFormat.DDP

    def _get_selected_downmix(self) -> DeewDownmix | None:
        dm_value = self.deew_downmix_var.get()
        if dm_value == "auto":
            return None
        for dm in DeewDownmix:
            if dm.display_name == dm_value:
                return dm
        return None

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
        log_key = "log_source" if role == "src" else "log_sync_file"
        zone = self.zone_src if role == "src" else self.zone_sync

        # Show loading state
        zone._name_lbl.config(text=t("mkv_extracting"), fg=THEME.muted)

        def _probe_thread() -> None:
            """Background: probe streams."""
            try:
                streams = self._ffmpeg.probe_audio_streams(path)
            except Exception:
                streams = []
            # Back to main thread for dialog
            self.after(0, lambda: self._container_on_probed(path, role, streams))

        threading.Thread(target=_probe_thread, daemon=True).start()

    def _container_on_probed(
        self, path: str, role: str, streams: list[dict[str, str]],
    ) -> None:
        """Main thread: handle probe results, show dialog if needed."""
        zone = self.zone_src if role == "src" else self.zone_sync

        if not streams:
            messagebox.showwarning(t("mkv_select_title"), t("mkv_no_audio"))
            zone._name_lbl.config(text=t("no_file_selected"), fg=THEME.muted)
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
                zone._name_lbl.config(text=t("no_file_selected"), fg=THEME.muted)
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
        zone._name_lbl.config(text=t("mkv_extracting"), fg=THEME.muted)

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
                self.after(0, lambda: self._container_on_extracted(
                    tmp_path, role,
                ))
            except Exception as e:
                self.after(0, lambda: self._container_on_extract_error(
                    str(e), tmp_path, role,
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
        zone._name_lbl.config(text=t("no_file_selected"), fg=THEME.muted)

        if os.path.isfile(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass

        setattr(self, f"_extracting_{role}", False)

    # ── Cleanup ──────────────────────────────────────────────────────────

    def destroy(self) -> None:
        """Clean up temporary container extraction files on exit."""
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
        self.after(0, _do)

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

        self.analyze_btn.config(state="disabled", text=t("analyzing"))
        self.run_btn.config(state="disabled")
        self._clear_log()
        self._set_progress(0)

        threading.Thread(target=self._analyze_only, daemon=True).start()

    def _analyze_only(self) -> None:
        """Background thread: passive analysis only, no file modifications."""
        src = self._src_path
        sync = self._sync_path
        tmp_dir = _tempfile_mod.mkdtemp(prefix="audio_sync_analyze_")

        try:
            self._log(t("analyze_started"))
            self._set_progress(5)

            # Step 1: Probe audio files
            self._log(t("analyze_probing"))
            src_info = self._ffmpeg.probe_audio(src)
            sync_info = self._ffmpeg.probe_audio(sync)
            self._set_progress(15)

            # Log file info
            self._log(t("analyze_src_info",
                         channels=src_info.channels,
                         bits=src_info.bits,
                         sample_rate=src_info.sample_rate))
            self._log(t("analyze_sync_info",
                         channels=sync_info.channels,
                         bits=sync_info.bits,
                         sample_rate=sync_info.sample_rate))

            # Update info panel on main thread
            output_sr = OutputSampleRate.decide(
                src_info.sample_rate, sync_info.sample_rate, False,
            )
            self.after(0, lambda: self._update_info_panel(sync_info, output_sr))

            # Step 2: Convert to mono WAV for analysis
            self._log(t("analyze_converting"))
            self._set_progress(25)

            src_wav = os.path.join(tmp_dir, "src_mono.wav")
            sync_wav = os.path.join(tmp_dir, "sync_mono.wav")
            self._ffmpeg.to_wav_mono(src, src_wav)
            self._set_progress(40)
            self._ffmpeg.to_wav_mono(sync, sync_wav)
            self._set_progress(55)

            # Step 3: Calculate delay
            self._log(t("analyze_calculating"))

            skip_sec = parse_float(
                self.skip_intro_var.get(), default=120.0, minimum=0.0, maximum=3600.0,
            )
            segment_count = parse_int(
                self.segment_count_var.get(), default=12, minimum=4, maximum=40,
            )

            result = self._analyzer.calculate_delay(
                src_wav, sync_wav,
                skip_intro_sec=skip_sec,
                total_segments=segment_count,
            )
            self._set_progress(85)

            # Step 4: Display comprehensive results
            self._log("")
            self._log(t("analyze_result_header"))
            self._log("")

            # Sync point time (convert delay_ms to timestamp format)
            abs_ms = abs(result.delay_ms)
            hours = int(abs_ms // 3600000)
            minutes = int((abs_ms % 3600000) // 60000)
            seconds = int((abs_ms % 60000) // 1000)
            millis = int(abs_ms % 1000)
            time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"
            self._log(t("sync_point_time", time=time_str))

            # Delay amount with description
            description = AudioAnalyzer.describe_offset(result.delay_ms)
            self._log(t("delay_amount", delay_ms=result.delay_ms, description=description))

            # Confidence score with level
            if result.confidence >= 8.0:
                conf_level = t("confidence_high")
            elif result.confidence >= 4.0:
                conf_level = t("confidence_medium")
            else:
                conf_level = t("confidence_low")
            self._log(t("confidence_score", confidence=result.confidence) + f" ({conf_level})")

            # Drift amount
            if result.drift_ms_per_min is not None:
                self._log(t("drift_amount", drift=result.drift_ms_per_min))
            else:
                self._log(t("drift_none"))

            # Coarse delay
            self._log(t("coarse_delay", coarse_ms=result.coarse_ms))

            # Segments used
            self._log(t("segments_used", used=result.used_segments, total=result.total_segments))

            self._log("")
            self._log(t("analyze_result_header"))
            self._log("")

            # Also use existing display method for info panel update
            self.after(0, lambda: self._display_analysis_result(result))

            self._set_progress(100)
            self._log(t("analyze_complete"))

        except Exception as e:
            self._log(f"❌ Error: {e}")
            import traceback
            self._log(traceback.format_exc())
        finally:
            # Clean up temp files
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass

            # Re-enable buttons on main thread
            def _restore() -> None:
                with self._processing_lock:
                    self._processing = False
                self.analyze_btn.config(state="normal", text=t("analyze_only"))
                self.run_btn.config(state="normal", text=t("start_sync"))

            self.after(0, _restore)

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
            FFmpegWrapper.check_availability()
        except OSError as e:
            messagebox.showerror(t("ffmpeg_not_found_title"), str(e))
            self._reset_processing()
            return

        deew_enabled = (self._encoding_pipeline_var.get() == EncodingPipeline.DOLBY.value)
        encoder = self._get_selected_encoder()

        if deew_enabled and encoder == EncoderType.DEE:
            try:
                DeewEncoder.check_availability()
            except OSError as e:
                messagebox.showerror(t("deew_not_found_title"), str(e))
                self._reset_processing()
                return

        # Encoding pipeline availability checks
        pipeline = self._encoding_pipeline_var.get()

        if pipeline == EncodingPipeline.QAAC.value:
            ok, msg = QaacEncoder.check_availability()
            if not ok:
                messagebox.showerror("qaac", msg)
                self._reset_processing()
                return

        try:
            validate_file(self._src_path, t("source_audio"))
            validate_file(self._sync_path, t("sync_audio"))
        except (FileNotFoundError, PermissionError, ValueError) as e:
            messagebox.showerror(t("file_error_title"), str(e))
            self._reset_processing()
            return

        # ── Capture encoding params on main thread (thread-safe) ──
        encoding_params: dict = {
            "pipeline": pipeline,
            "ffmpeg_format": self._ffmpeg_format_var.get(),
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
            fmt_codec = self._ffmpeg_format_var.get()
            if fmt_codec == FFmpegOutputFormat.AAC.codec:
                ext = ".m4a"
                filetypes = [("AAC/M4A", "*.m4a"), ("WAV", "*.wav")]
            elif fmt_codec == FFmpegOutputFormat.FLAC.codec:
                ext = ".flac"
                filetypes = [("FLAC", "*.flac"), ("WAV", "*.wav")]
            elif fmt_codec == FFmpegOutputFormat.OPUS.codec:
                ext = ".opus"
                filetypes = [("Opus", "*.opus"), ("WAV", "*.wav")]
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
            return

        skip_sec = parse_float(self.skip_intro_var.get(), default=120.0, minimum=0.0, maximum=3600.0)
        segment_count = parse_int(self.segment_count_var.get(), default=12, minimum=4, maximum=40)
        force_48k = bool(self.force_48k_var.get())

        fps_conversion: FpsConversion | None = None
        if self.fps_enabled_var.get():
            fps_conversion = self._get_selected_fps_conversion()

        sync_mode = self._get_selected_sync_mode() or SyncMode.ADELAY_AMIX

        deew_params: dict | None = None
        if deew_enabled:
            deew_params = {
                "encoder": encoder,
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

        self.analyze_btn.config(state="disabled")
        self.run_btn.config(state="disabled", text=t("processing"))
        self._set_progress(0)

        threading.Thread(
            target=self._process,
            args=(src_path, sync_path, out_path, skip_sec, segment_count, force_48k,
                  fps_conversion, deew_params, sync_mode, encoding_params),
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
    ) -> None:
        """Arka plan thread'inde senkronizasyon işlemini yürütür."""
        fps_tmp_path: str | None = None
        wav_out_path: str | None = None  # Dolby encoding ara WAV dosyası
        needs_encoding: bool = False

        try:
            # 1. Ses bilgilerini oku
            self._log(t("log_reading_info"))
            self._set_progress(5)
            src_info = self._ffmpeg.probe_audio(src_path)
            sync_info = self._ffmpeg.probe_audio(sync_path)

            output_sr = OutputSampleRate.decide(src_info.sample_rate, sync_info.sample_rate, force_48k)

            self._update_info_panel(sync_info, output_sr)
            self._log_audio_info(src_info, sync_info, output_sr, skip_sec, segment_count)
            self._log(t("log_sync_mode", mode=sync_mode.display_name))

            # 1.5. FPS dönüşümü (etkinse)
            effective_sync_path = sync_path
            if fps_conversion is not None:
                self._log(t("log_fps_applying", name=fps_conversion.display_name))
                self._set_progress(8)

                fps_tmp_fd, fps_tmp_path = _tempfile_mod.mkstemp(
                    prefix="audiosync_fps_", suffix=".wav",
                )
                os.close(fps_tmp_fd)

                fps_summary = self._ffmpeg.apply_fps_conversion(
                    sync_path, fps_tmp_path, fps_conversion, sync_info,
                )
                self._log(f"FPS: {fps_summary}")

                effective_sync_path = fps_tmp_path
                sync_info = self._ffmpeg.probe_audio(effective_sync_path)
                self._log(t("log_fps_done"))

            # 2. Mono WAV hazırla
            self._log(t("log_preparing_mono"))
            self._set_progress(15)

            with temporary_wav_files() as (tmp_src, tmp_sync):
                self._ffmpeg.to_wav_mono(src_path, tmp_src)
                self._ffmpeg.to_wav_mono(effective_sync_path, tmp_sync)

                # 3. Gecikme analizi
                self._log(t("log_analyzing"))
                self._set_progress(35)
                result = self._analyzer.calculate_delay(
                    tmp_src, tmp_sync,
                    skip_intro_sec=skip_sec,
                    total_segments=segment_count,
                )

            # 4. Sonuçları göster
            self._delay_ms = result.delay_ms
            self._display_analysis_result(result)

            # 5. FFmpeg ile senkronizasyon uygula
            # Determine if we need a temp WAV (any encoding pipeline selected)
            enc = encoding_params or {}
            pipeline = enc.get("pipeline", EncodingPipeline.NONE.value)
            needs_encoding = (
                deew_params is not None
                or pipeline in (
                    EncodingPipeline.FFMPEG.value,
                    EncodingPipeline.QAAC.value,
                )
            )

            if needs_encoding:
                # Sync to temp WAV, then encode to final output
                _fd, wav_out_path = _tempfile_mod.mkstemp(
                    suffix=".wav", prefix="audiosync_",
                    dir=os.path.dirname(out_path) or ".",
                )
                os.close(_fd)
            else:
                # No encoding — sync directly to user's chosen path
                wav_out_path = out_path

            self._log(t("log_applying_sync"))
            self._set_progress(55)
            cmd_summary = self._ffmpeg.apply_sync(
                src_path, effective_sync_path, result.delay_ms,
                sync_info, output_sr, wav_out_path,
                sync_mode=sync_mode,
            )
            self._log(t("log_command", cmd=cmd_summary))

            # 6. Dolby encoding (etkinse)
            if deew_params is not None:
                self._set_progress(70)
                enc_type: EncoderType = deew_params["encoder"]
                fmt: DeewFormat = deew_params["format"]

                if enc_type == EncoderType.FFMPEG:
                    self._log(t("log_ffmpeg_dolby_start"))

                    ffmpeg_bitrate = deew_params["bitrate"]
                    if ffmpeg_bitrate is None:
                        from audio_sync.config import (
                            FFMPEG_AC3_DEFAULT_BITRATE as _ac3_def,
                            FFMPEG_EAC3_DEFAULT_BITRATE as _eac3_def,
                        )
                        ffmpeg_bitrate = _ac3_def if fmt == DeewFormat.DD else _eac3_def

                    ffmpeg_channels: int | None = None
                    if deew_params["downmix"] is not None:
                        ffmpeg_channels = deew_params["downmix"].channels

                    self._log(t("log_dolby_info",
                        fmt=fmt.display_name,
                        br=ffmpeg_bitrate,
                        ch=ffmpeg_channels or t("source_keep"),
                        enc="FFmpeg",
                    ))

                    try:
                        enc_summary = self._ffmpeg.encode_to_dolby(
                            input_wav=wav_out_path,
                            output_path=out_path,
                            fmt=fmt,
                            bitrate=ffmpeg_bitrate,
                            channels=ffmpeg_channels,
                        )
                        self._log(t("log_command", cmd=enc_summary))
                        self._set_progress(95)
                        self._log(t("log_ffmpeg_dolby_done", name=os.path.basename(out_path)))

                        if deew_params["delete_wav"] and os.path.isfile(wav_out_path):
                            try:
                                os.remove(wav_out_path)
                                self._log(t("log_intermediate_wav_deleted"))
                            except OSError:
                                self._log(t("log_intermediate_wav_delete_fail"))
                    except Exception as ffmpeg_err:
                        self._log(t("log_ffmpeg_enc_error", err=ffmpeg_err))
                        wav_fallback = str(Path(out_path).with_suffix(".wav"))
                        if os.path.isfile(wav_out_path):
                            shutil.move(wav_out_path, wav_fallback)
                            self._log(t("log_wav_preserved", name=os.path.basename(wav_fallback)))
                            out_path = wav_fallback
                        else:
                            raise RuntimeError(
                                f"FFmpeg encoding failed and WAV file not found: {ffmpeg_err}"
                            ) from ffmpeg_err
                else:
                    self._log(t("log_deew_start"))
                    self._log(t("log_dolby_info",
                        fmt=fmt.display_name,
                        br=deew_params['bitrate'] or t("default_bitrate"),
                        ch=deew_params['downmix'].display_name if deew_params['downmix'] else t("source_keep"),
                        enc="DEE",
                    ))

                    try:
                        final_path = encode_wav_to_dolby(
                            input_wav=wav_out_path,
                            final_output_path=out_path,
                            fmt=fmt,
                            bitrate=deew_params["bitrate"],
                            downmix=deew_params["downmix"],
                            drc=deew_params["drc"],
                            dialnorm=deew_params["dialnorm"],
                            delete_wav=deew_params["delete_wav"],
                            progress_callback=self._log,
                        )
                        self._set_progress(95)
                        self._log(t("log_deew_dolby_done", name=os.path.basename(final_path)))
                    except Exception as deew_err:
                        self._log(t("log_deew_error", err=deew_err))
                        wav_fallback = str(Path(out_path).with_suffix(".wav"))
                        if os.path.isfile(wav_out_path):
                            shutil.move(wav_out_path, wav_fallback)
                            self._log(t("log_wav_preserved", name=os.path.basename(wav_fallback)))
                            out_path = wav_fallback
                        else:
                            raise RuntimeError(
                                f"Deew encoding failed and WAV file not found: {deew_err}"
                            ) from deew_err

            # 6b. Encoding pipeline (FFmpeg/qaac/Native — when not using Dolby)
            if deew_params is None:
                if pipeline == EncodingPipeline.FFMPEG.value:
                    self._log(t("encoding_started"))
                    fmt_codec = enc.get("ffmpeg_format", FFmpegOutputFormat.AAC.codec)

                    if fmt_codec == FFmpegOutputFormat.AAC.codec:
                        bitrate = enc.get("ffmpeg_aac_bitrate", 256)
                        summary = self._ffmpeg.encode_to_aac(wav_out_path, out_path, bitrate=bitrate)
                    elif fmt_codec == FFmpegOutputFormat.FLAC.codec:
                        compression = enc.get("ffmpeg_flac_compression", 5)
                        bit_depth = enc.get("ffmpeg_flac_bit_depth", 24)
                        summary = self._ffmpeg.encode_to_flac(wav_out_path, out_path, compression=compression, bit_depth=bit_depth)
                    elif fmt_codec == FFmpegOutputFormat.OPUS.codec:
                        bitrate = enc.get("ffmpeg_opus_bitrate", 128)
                        summary = self._ffmpeg.encode_to_opus(wav_out_path, out_path, bitrate=bitrate)
                    else:
                        summary = ""

                    self._log(t("encoding_complete", summary=summary))
                    self._set_progress(95)

                elif pipeline == EncodingPipeline.QAAC.value:
                    self._log(t("encoding_started"))
                    mode_flag = enc.get("qaac_mode", QaacMode.TVBR.flag)
                    mode = next((m for m in QaacMode if m.flag == mode_flag), QaacMode.TVBR)

                    config = QaacConfig(
                        mode=mode,
                        tvbr_quality=enc.get("qaac_tvbr_quality", 91),
                        cvbr_bitrate=enc.get("qaac_cvbr_bitrate", 256),
                        abr_bitrate=enc.get("qaac_abr_bitrate", 256),
                        cbr_bitrate=enc.get("qaac_cbr_bitrate", 256),
                        he_aac=enc.get("qaac_he_aac", False),
                        no_delay=enc.get("qaac_no_delay", True),
                    )

                    summary = QaacEncoder.encode(wav_out_path, out_path, config)
                    self._log(t("encoding_complete", summary=summary))
                    self._set_progress(95)

            # 7. Tamamlandı
            self._set_progress(100)
            self._log(t("log_completed", name=os.path.basename(out_path)))
            self.after(0, lambda: messagebox.showinfo(
                t("success_title"), t("file_saved_msg", path=out_path),
            ))

        except Exception as e:
            self._log(t("log_error", err=e))
            self.after(0, lambda err=str(e): messagebox.showerror(t("error_title"), err))
            # Clean up partial/corrupt output file on encoding failure
            if needs_encoding and os.path.isfile(out_path):
                try:
                    os.remove(out_path)
                except OSError:
                    pass
        finally:
            # Geçici dosyaları temizle
            for tmp_path in (fps_tmp_path, wav_out_path):
                if tmp_path is not None and tmp_path != out_path and os.path.isfile(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass
            with self._processing_lock:
                self._processing = False

            def _restore_buttons() -> None:
                self.analyze_btn.config(state="normal", text=t("analyze_only"))
                self.run_btn.config(state="normal", text=t("start_sync"))

            self.after(0, _restore_buttons)

    def _reset_processing(self) -> None:
        with self._processing_lock:
            self._processing = False

    # ── Bilgi Gösterimi ──────────────────────────────────────────────────

    def _update_info_panel(self, sync_info: AudioInfo, output_sr: OutputSampleRate) -> None:
        self.after(0, lambda: self.ch_val.config(text=t("channel_info", ch=sync_info.channels)))
        self.after(0, lambda: self.bit_val.config(
            text=f"{sync_info.bits}-bit  →  {sync_info.codec.codec_name}",
        ))
        self.after(0, lambda: self.sr_val.config(text=output_sr.label))

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

        self.after(
            0,
            lambda: self.delay_val.config(
                text=f"{abs(result.delay_ms):.1f} ms  ({relation})",
                fg=label_color,
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

        self.after(0, _write)

    def _set_progress(self, pct: int) -> None:
        def _draw() -> None:
            w = self.progress_canvas.winfo_width()
            x = int(w * pct / 100)
            self.progress_canvas.coords(self._progress_bar, 0, 0, x, 4)

        self.after(0, _draw)

    def _fit_to_content(self) -> None:
        """Update scroll region without changing window size."""
        self.update_idletasks()
        if hasattr(self, '_canvas'):
            self._canvas.configure(scrollregion=self._canvas.bbox("all"))
