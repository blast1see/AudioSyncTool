"""MKV/Container audio stream selection dialog."""

from __future__ import annotations

import tkinter as tk
from typing import Optional

from audio_sync.config import THEME, FONTS
from audio_sync.i18n import t


class StreamSelectionDialog(tk.Toplevel):
    """Dialog for selecting an audio stream from a container file.

    Shows a list of audio streams with codec, channels, sample rate,
    language, and title information. The user selects one stream.

    Args:
        parent: Parent window.
        streams: List of stream info dicts from FFmpegWrapper.probe_audio_streams().
        filename: Name of the container file (for display).
    """

    def __init__(
        self,
        parent: tk.Widget,
        streams: list[dict[str, str]],
        filename: str = "",
    ) -> None:
        super().__init__(parent)
        self.title(t("mkv_select_title"))
        self.configure(bg=THEME.bg)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._selected_index: int | None = None
        self._streams = streams

        self._build_ui(filename)

        # Center on parent
        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_x()
        py = parent.winfo_y()
        w = self.winfo_width()
        h = self.winfo_height()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"+{x}+{y}")

    def _build_ui(self, filename: str) -> None:
        """Build the dialog UI."""
        # Header
        header = tk.Frame(self, bg=THEME.bg)
        header.pack(fill="x", padx=20, pady=(16, 8))

        if filename:
            tk.Label(
                header, text=filename, font=FONTS.button,
                fg=THEME.accent, bg=THEME.bg, anchor="w",
            ).pack(fill="x")

        tk.Label(
            header, text=t("mkv_select_prompt"), font=FONTS.small,
            fg=THEME.text, bg=THEME.bg, anchor="w", justify="left",
        ).pack(fill="x", pady=(4, 0))

        # Stream list
        list_frame = tk.Frame(self, bg=THEME.card)
        list_frame.pack(fill="both", expand=True, padx=20, pady=8)

        self._radio_var = tk.IntVar(value=0)

        for i, stream in enumerate(self._streams):
            stream_frame = tk.Frame(list_frame, bg=THEME.card)
            stream_frame.pack(fill="x", padx=8, pady=4)

            # Format stream info
            codec = stream.get("codec_name", "unknown")
            channels = stream.get("channels", "?")
            sample_rate = stream.get("sample_rate", "?")
            language = stream.get("language", "und")
            title = stream.get("title", "")
            bit_rate = stream.get("bit_rate", "N/A")

            # Format bitrate nicely
            br_display = ""
            try:
                br_int = int(bit_rate)
                if br_int > 0:
                    br_display = f" | {br_int // 1000}kbps"
            except (ValueError, TypeError):
                pass

            title_display = f" | {title}" if title else ""
            label_text = (
                f"  #{stream.get('index', i)}: {codec} | "
                f"{channels}ch | {sample_rate}Hz | "
                f"{language}{br_display}{title_display}"
            )

            rb = tk.Radiobutton(
                stream_frame,
                text=label_text,
                variable=self._radio_var,
                value=i,
                font=FONTS.mono,
                fg=THEME.text,
                bg=THEME.card,
                selectcolor=THEME.input_bg,
                activebackground=THEME.card,
                activeforeground=THEME.accent,
                highlightthickness=0,
                anchor="w",
            )
            rb.pack(fill="x")

        # Buttons
        btn_frame = tk.Frame(self, bg=THEME.bg)
        btn_frame.pack(fill="x", padx=20, pady=(8, 16))

        tk.Button(
            btn_frame, text=t("btn_ok"), font=FONTS.button,
            fg=THEME.bg, bg=THEME.accent,
            activebackground=THEME.accent, activeforeground=THEME.bg,
            relief="flat", padx=24, pady=6, cursor="hand2",
            command=self._on_ok,
        ).pack(side="right", padx=(8, 0))

        tk.Button(
            btn_frame, text=t("btn_cancel"), font=FONTS.button,
            fg=THEME.text, bg=THEME.border,
            activebackground=THEME.muted, activeforeground=THEME.text,
            relief="flat", padx=24, pady=6, cursor="hand2",
            command=self._on_cancel,
        ).pack(side="right")

    def _on_ok(self) -> None:
        """Accept the selected stream."""
        idx = self._radio_var.get()
        if 0 <= idx < len(self._streams):
            self._selected_index = int(self._streams[idx].get("index", idx))
        self.destroy()

    def _on_cancel(self) -> None:
        """Cancel the selection."""
        self._selected_index = None
        self.destroy()

    @property
    def selected_stream_index(self) -> int | None:
        """The FFmpeg stream index of the selected stream, or None if cancelled."""
        return self._selected_index


def ask_stream_selection(
    parent: tk.Widget,
    streams: list[dict[str, str]],
    filename: str = "",
) -> Optional[int]:
    """Show a stream selection dialog and return the selected stream index.

    Args:
        parent: Parent window.
        streams: List of stream info dicts.
        filename: Container filename for display.

    Returns:
        FFmpeg stream index of the selected stream, or None if cancelled.
    """
    dialog = StreamSelectionDialog(parent, streams, filename)
    dialog.wait_window()
    return dialog.selected_stream_index
