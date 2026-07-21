from __future__ import annotations

import pytest

from audio_sync.i18n import Language

pytestmark = pytest.mark.gui


def test_gui_opens_switches_panels_and_languages() -> None:
    from audio_sync.ui.app import AudioSyncApp

    try:
        app = AudioSyncApp()
    except Exception as exc:
        pytest.fail(f"GUI could not start: {exc}")

    try:
        app.withdraw()
        app.update_idletasks()
        assert app._sync_mode_frame.winfo_exists()
        assert app._fps_frame.winfo_exists()

        app._encoding_pipeline_var.set("ffmpeg")
        app._on_encoding_pipeline_change("ffmpeg")
        assert app._ffmpeg_enc_frame.winfo_manager() == "pack"

        app._on_language_change(Language.TR.display_name)
        assert app._i18n.language is Language.TR
        app._on_language_change(Language.EN.display_name)
        assert app._i18n.language is Language.EN
    finally:
        app.destroy()
