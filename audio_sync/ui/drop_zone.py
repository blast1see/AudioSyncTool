"""File selection area widget with drag & drop support."""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import filedialog
from typing import Callable

from audio_sync.config import THEME, FONTS, SUPPORTED_AUDIO_EXTENSIONS, ALL_SUPPORTED_EXTENSIONS_LIST
from audio_sync.i18n import t
from audio_sync.utils import short_name

# Try to import tkinterdnd2 for native drag & drop support
_DND_AVAILABLE = False
try:
    import tkinterdnd2  # noqa: F401
    _DND_AVAILABLE = True
except ImportError:
    pass


def is_dnd_available() -> bool:
    """Check if drag & drop support is available."""
    return _DND_AVAILABLE


class DropZone(tk.Frame):
    """File selection area — label, filename display, select button, and drop zone.

    Supports native drag & drop when tkinterdnd2 is available.

    Args:
        parent: Parent widget.
        label: Area label (e.g. "SOURCE AUDIO").
        color: Accent color (hex).
        on_select: Callback when a file is selected.
            Receives the full path of the selected file.
        **kw: Additional ``tk.Frame`` parameters.
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
        self._default_border = THEME.border
        self.config(highlightbackground=self._default_border, highlightthickness=1)

        self._build_header(label, color)
        self._build_filename_label()
        self._build_drop_hint()
        self._build_select_button(color)
        self._setup_drag_drop()

    def _build_header(self, label: str, color: str) -> None:
        """Build the header row."""
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
        """Build the filename display label."""
        self._name_lbl = tk.Label(
            self,
            text=t("no_file_selected"),
            font=FONTS.small,
            fg=THEME.muted,
            bg=THEME.card,
            width=54,
            justify="center",
        )
        self._name_lbl.pack(pady=(0, 4))

    def _build_drop_hint(self) -> None:
        """Build the drag & drop hint label."""
        self._drop_hint_lbl = tk.Label(
            self,
            text=t("drop_hint"),
            font=FONTS.small,
            fg=THEME.muted,
            bg=THEME.card,
            justify="center",
        )
        self._drop_hint_lbl.pack(pady=(0, 6))

    def _build_select_button(self, color: str) -> None:
        """Build the file selection button."""
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

    def _setup_drag_drop(self) -> None:
        """Set up drag & drop if tkinterdnd2 is available."""
        if not _DND_AVAILABLE:
            return

        try:
            # Register as a drop target
            self.drop_target_register("DND_Files")  # type: ignore[attr-defined]
            self.dnd_bind("<<DropEnter>>", self._on_drop_enter)  # type: ignore[attr-defined]
            self.dnd_bind("<<DropLeave>>", self._on_drop_leave)  # type: ignore[attr-defined]
            self.dnd_bind("<<Drop>>", self._on_drop)  # type: ignore[attr-defined]
        except (AttributeError, tk.TclError):
            pass  # DnD not available for this widget

    def _on_drop_enter(self, event: object) -> None:
        """Visual feedback when dragging over the zone."""
        self.config(highlightbackground=self._color, highlightthickness=2)
        self._drop_hint_lbl.config(text=t("drop_hover"), fg=self._color)

    def _on_drop_leave(self, event: object) -> None:
        """Reset visual feedback when leaving the zone."""
        self.config(highlightbackground=self._default_border, highlightthickness=1)
        self._drop_hint_lbl.config(text=t("drop_hint"), fg=THEME.muted)

    def _on_drop(self, event: object) -> None:
        """Handle file drop."""
        self.config(highlightbackground=self._default_border, highlightthickness=1)
        self._drop_hint_lbl.config(text=t("drop_hint"), fg=THEME.muted)

        # Extract file path from the drop event
        data = getattr(event, "data", "")
        if not data:
            return

        # tkinterdnd2 wraps paths with spaces in braces: {C:/path with spaces/file.mkv}
        path = data.strip()
        if path.startswith("{") and path.endswith("}"):
            path = path[1:-1]
        # Handle multiple files — take only the first one
        elif " " in path and not os.path.exists(path):
            # Try splitting by space and taking the first valid path
            for candidate in path.split():
                candidate = candidate.strip("{}")
                if os.path.isfile(candidate):
                    path = candidate
                    break

        if os.path.isfile(path):
            ext = os.path.splitext(path)[1].lower()
            if ext not in ALL_SUPPORTED_EXTENSIONS_LIST:
                return
            self._set_file(path)

    def _pick(self) -> None:
        """Open file selection dialog and process the selection."""
        path = filedialog.askopenfilename(
            filetypes=[
                (t("audio_files"), SUPPORTED_AUDIO_EXTENSIONS),
                (t("all_files"), "*.*"),
            ]
        )
        if path:
            self._set_file(path)

    def _set_file(self, path: str) -> None:
        """Set the selected file and notify the callback."""
        self.filepath.set(path)
        basename = os.path.basename(path)
        self._name_lbl.config(text=short_name(basename), fg=self._color)
        self._on_select(path)

    def set_file_external(self, path: str) -> None:
        """Set file from external code (e.g. after MKV stream extraction).

        Args:
            path: Full path to the file.
        """
        self.filepath.set(path)
        basename = os.path.basename(path)
        self._name_lbl.config(text=short_name(basename), fg=self._color)

    def update_label(self, label: str) -> None:
        """Update the label text (for language changes).

        Args:
            label: New label text.
        """
        self._label_lbl.config(text=f"  {label}")
        self._select_btn.config(text=t("select_file"))
        self._drop_hint_lbl.config(text=t("drop_hint"))
        # Update placeholder if no file is selected
        if not self.filepath.get():
            self._name_lbl.config(text=t("no_file_selected"))
