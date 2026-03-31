"""Dosya seçim alanı widget'ı."""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import filedialog
from typing import Callable

from audio_sync.config import THEME, FONTS, SUPPORTED_AUDIO_EXTENSIONS
from audio_sync.i18n import t
from audio_sync.utils import short_name


class DropZone(tk.Frame):
    """Dosya seçim alanı — etiket, dosya adı gösterimi ve seçim butonu içerir.

    Args:
        parent: Üst widget.
        label: Alan etiketi (ör. "KAYNAK SES").
        color: Vurgu rengi (hex).
        on_select: Dosya seçildiğinde çağrılacak callback.
            Seçilen dosyanın tam yolunu parametre olarak alır.
        **kw: ``tk.Frame`` için ek parametreler.
    """

    def __init__(
        self,
        parent: tk.Widget,
        label: str,
        color: str,
        on_select: Callable[[str], None],
        **kw: object,
    ) -> None:
        super().__init__(parent, bg=THEME.card, bd=0, **kw)
        self._on_select = on_select
        self._color = color
        self.filepath = tk.StringVar(value="")
        self.config(highlightbackground=THEME.border, highlightthickness=1)

        self._build_header(label, color)
        self._build_filename_label()
        self._build_select_button(color)

    def _build_header(self, label: str, color: str) -> None:
        """Üst başlık satırını oluşturur."""
        self._header_frame = tk.Frame(self, bg=THEME.card)
        self._header_frame.pack(fill="x", padx=16, pady=(14, 4))
        self._dot_lbl = tk.Label(
            self._header_frame, text="●", font=FONTS.dot, fg=color, bg=THEME.card,
        )
        self._dot_lbl.pack(side="left")
        self._label_lbl = tk.Label(
            self._header_frame, text=f"  {label}", font=FONTS.label, fg=THEME.text, bg=THEME.card,
        )
        self._label_lbl.pack(side="left")

    def _build_filename_label(self) -> None:
        """Dosya adı gösterim etiketini oluşturur."""
        self._name_lbl = tk.Label(
            self,
            text=t("no_file_selected"),
            font=FONTS.small,
            fg=THEME.muted,
            bg=THEME.card,
            width=54,
            justify="center",
        )
        self._name_lbl.pack(pady=(0, 10))

    def _build_select_button(self, color: str) -> None:
        """Dosya seçim butonunu oluşturur."""
        self._select_btn = tk.Button(
            self,
            text=t("select_file"),
            font=FONTS.button,
            fg=THEME.bg,
            bg=color,
            activebackground=color,
            activeforeground=THEME.bg,
            relief="flat",
            padx=18,
            pady=6,
            cursor="hand2",
            command=self._pick,
        )
        self._select_btn.pack(pady=(0, 14))

    def _pick(self) -> None:
        """Dosya seçim diyaloğunu açar ve seçimi işler."""
        path = filedialog.askopenfilename(
            filetypes=[
                (t("audio_files"), SUPPORTED_AUDIO_EXTENSIONS),
                (t("all_files"), "*.*"),
            ]
        )
        if path:
            self.filepath.set(path)
            basename = os.path.basename(path)
            self._name_lbl.config(text=short_name(basename), fg=self._color)
            self._on_select(path)

    def update_label(self, label: str) -> None:
        """Etiket metnini günceller (dil değişikliği için).

        Args:
            label: Yeni etiket metni.
        """
        self._label_lbl.config(text=f"  {label}")
        self._select_btn.config(text=t("select_file"))
        # Dosya seçilmemişse placeholder'ı güncelle
        if not self.filepath.get():
            self._name_lbl.config(text=t("no_file_selected"))
