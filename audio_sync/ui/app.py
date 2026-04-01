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
)
from audio_sync.core.analyzer import AudioAnalyzer
from audio_sync.core.deew_encoder import DeewEncoder, encode_wav_to_dolby
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
        self.geometry("900x700")
        self.resizable(True, True)
        self.minsize(600, 500)
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
        self._build_deew_panel()
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

        # Sağ: Dil seçimi
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

    def _build_deew_panel(self) -> None:
        """Dolby encoding ayarları panelini oluşturur (DEE ve FFmpeg desteği)."""
        self._deew_frame = tk.Frame(
            self._content, bg=THEME.card,
            highlightbackground=THEME.border, highlightthickness=1,
        )
        self._deew_frame.pack(fill="x", padx=30, pady=(0, 14))

        header_row = tk.Frame(self._deew_frame, bg=THEME.card)
        header_row.pack(fill="x", padx=14, pady=(10, 4))

        self._dolby_title_lbl = tk.Label(
            header_row, text=t("dolby_encoding"), font=FONTS.small,
            fg=THEME.muted, bg=THEME.card, anchor="w",
        )
        self._dolby_title_lbl.pack(side="left")

        self._deew_status_lbl = tk.Label(
            header_row, text="", font=FONTS.small,
            bg=THEME.card, anchor="e",
        )
        self._deew_status_lbl.pack(side="right")
        self._update_deew_status()

        self._dolby_enable_cb = tk.Checkbutton(
            self._deew_frame,
            text=t("dolby_enable"),
            variable=self.deew_enabled_var,
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
            command=self._on_deew_toggle,
        )
        self._dolby_enable_cb.pack(fill="x", padx=14, pady=(0, 6))

        self._deew_settings_frame = tk.Frame(self._deew_frame, bg=THEME.card)
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

        self._on_deew_toggle()
        self._update_channel_options()
        self._update_bitrate_options()
        self._update_format_description()
        self._update_encoder_ui()

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
        self._dolby_title_lbl.config(text=t("dolby_encoding"))
        self._dolby_enable_cb.config(text=t("dolby_enable"))
        self._enc_label.config(text=t("encoder_label"))
        self._fmt_label.config(text=t("format_label"))
        self._ch_label.config(text=t("channel_layout"))
        self._br_label.config(text=t("bitrate_label"))
        self._drc_label.config(text=t("drc_profile"))
        self._dn_label.config(text=t("dialnorm_label"))
        self._delete_wav_cb.config(text=t("delete_intermediate_wav"))
        self._update_deew_status()
        self._update_encoder_ui()

        # Bilgi paneli
        for lbl, key in self._info_labels:
            lbl.config(text=t(key))

        # Log
        self._log_title_lbl.config(text=t("log_label"))

        # Buton
        if not self._processing:
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
        if self.deew_enabled_var.get():
            self._show_deew_settings(True)
        else:
            self._show_deew_settings(False)

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
        if show:
            self._deew_settings_frame.pack(fill="x", padx=14, pady=(0, 10))
        else:
            self._deew_settings_frame.pack_forget()
        self.after(50, self._fit_to_content)

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
            out_ext = CODEC_EXTENSION_MAP.get(codec, ".mka")

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

        deew_enabled = self.deew_enabled_var.get()
        encoder = self._get_selected_encoder()

        if deew_enabled and encoder == EncoderType.DEE:
            try:
                DeewEncoder.check_availability()
            except OSError as e:
                messagebox.showerror(t("deew_not_found_title"), str(e))
                self._reset_processing()
                return

        try:
            validate_file(self._src_path, t("source_audio"))
            validate_file(self._sync_path, t("sync_audio"))
        except (FileNotFoundError, PermissionError, ValueError) as e:
            messagebox.showerror(t("file_error_title"), str(e))
            self._reset_processing()
            return

        if deew_enabled:
            fmt = self._get_selected_format()
            ext = fmt.extension
            ext_label = fmt.display_name
            filetypes = [(ext_label, f"*{ext}")]
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

        self.run_btn.config(state="disabled", text=t("processing"))
        self._set_progress(0)

        threading.Thread(
            target=self._process,
            args=(src_path, sync_path, out_path, skip_sec, segment_count, force_48k,
                  fps_conversion, deew_params, sync_mode),
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
    ) -> None:
        """Arka plan thread'inde senkronizasyon işlemini yürütür."""
        fps_tmp_path: str | None = None
        wav_out_path: str | None = None  # Dolby encoding ara WAV dosyası

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
            if deew_params is not None:
                _fd, wav_out_path = _tempfile_mod.mkstemp(
                    suffix=".wav", prefix="audiosync_",
                    dir=os.path.dirname(out_path) or ".",
                )
                os.close(_fd)
            else:
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

            # 7. Tamamlandı
            self._set_progress(100)
            self._log(t("log_completed", name=os.path.basename(out_path)))
            self.after(0, lambda: messagebox.showinfo(
                t("success_title"), t("file_saved_msg", path=out_path),
            ))

        except Exception as e:
            self._log(t("log_error", err=e))
            self.after(0, lambda err=str(e): messagebox.showerror(t("error_title"), err))
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
            self.after(0, lambda: self.run_btn.config(
                state="normal", text=t("start_sync"),
            ))

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
        """Pencere boyutunu içeriğe göre ayarlar ve kaydırma bölgesini günceller.

        İçerik ekran yüksekliğini aşarsa pencere maksimum boyutta kalır
        ve kaydırma çubuğu otomatik olarak görünür hale gelir.
        Alt çubuk (ilerleme + buton) her zaman görünür kalır.
        """
        self.update_idletasks()
        content_h = self._content.winfo_reqheight() + 20
        bottom_h = self._bottom_bar.winfo_reqheight()
        max_h = self.winfo_screenheight() - 80
        current_w = self.winfo_width()
        target_w = max(600, current_w)
        target_h = min(max(500, content_h + bottom_h), max_h)
        self.geometry(f"{target_w}x{target_h}")
        # Kaydırma bölgesini güncelle — panel açılıp kapandığında gerekli
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))
        self._update_scrollbar_visibility()
